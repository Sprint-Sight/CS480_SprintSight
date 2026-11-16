"""Analysis layer: load per-example rows from MLflow runs and produce the
tables + statistics.

The runner's job is to populate MLflow; this module's job is to
answer questions. Keeping them separate means can re-run analysis
without re-running expensive model calls.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import mlflow
import pandas as pd

from evaluation.offline.attach_judge_scores import load_judge_scores, merge_judge_scores
from schemas.run_record import normalize_run_record

log = logging.getLogger(__name__)


# ---------- Loading --------------------------------------------------------

def _download_per_example_jsonl(run_id: str, dest_dir: Path) -> Path | None:
    client = mlflow.tracking.MlflowClient()
    for art in client.list_artifacts(run_id):
        if art.path.endswith("per_example.jsonl"):
            local = client.download_artifacts(run_id, art.path, str(dest_dir))
            return Path(local)
    return None


def load_runs(
    experiment: str,
    filter_string: str = "",
    cache_dir: str | Path = ".eval_cache",
) -> pd.DataFrame:
    """Return one row per (run, example, repeat) spanning the given MLflow
    experiment. Pass `filter_string` through to mlflow.search_runs (e.g.
    'params.phase = "final"').
    """
    cache_root = Path(cache_dir)
    cache_root.mkdir(exist_ok=True)
    exp = mlflow.get_experiment_by_name(experiment)
    if exp is None:
        raise KeyError(f"MLflow experiment '{experiment}' not found.")
    runs = cast(
        pd.DataFrame,
        mlflow.search_runs(experiment_ids=[exp.experiment_id], filter_string=filter_string)
    )
    if runs.empty:
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    for _, run_row in runs.iterrows():
        run_id = run_row["run_id"]
        local = _download_per_example_jsonl(run_id, cache_root / run_id)
        if local is None:
            log.warning("Run %s has no per_example.jsonl artifact; skipping.", run_id)
            continue
        with local.open("r", encoding="utf-8") as f:
            rows = [normalize_run_record(json.loads(line)) for line in f if line.strip()]
        if not rows:
            continue
        df = pd.DataFrame(rows)
        df["mlflow_run_id"] = run_id
        # Propagate selected run-level columns so filtering by model /
        # dataset is cheap during analysis.
        for col in ("params.model_name", "params.dataset_name", "params.dataset_hash",
                    "params.prompt_version", "params.prompt_hash", "params.model_digest",
                    "params.git_sha", "params.seed", "params.phase"):
            if col in run_row:
                df[col.replace("params.", "")] = run_row[col]
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    return normalize_groundedness(combined)


def normalize_groundedness(df: pd.DataFrame) -> pd.DataFrame:
    """Make `groundedness_rate` NaN wherever the assessment made no citations.

    Rows written before metrics.groundedness_rate returned NaN hold 1.0 for "nothing to check";
    averaging those in credits a model for citing nothing. The old value is kept as
    `groundedness_rate_legacy` (rows written since carry it already) so earlier tables can be
    reproduced. Safe to call twice.
    """
    if "groundedness_rate" not in df.columns:
        return df
    out = df.copy()
    rate = pd.to_numeric(out["groundedness_rate"], errors="coerce")
    legacy = pd.to_numeric(out["groundedness_rate_legacy"], errors="coerce") if "groundedness_rate_legacy" in out else rate
    out["groundedness_rate_legacy"] = legacy.fillna(rate)
    if "groundedness_citations_total" in out.columns:
        total = pd.to_numeric(out["groundedness_citations_total"], errors="coerce")
        # 1.0 with zero citations is only ever the old "nothing to check" value
        rate = rate.mask((total == 0) & (rate == 1.0))
    out["groundedness_rate"] = rate
    return out


def load_engine_results(
    results_dir: str | Path = "results",
    *,
    judge: bool = True,
) -> pd.DataFrame:
    """Rows for assessments the engine itself ran (the API path), in the same shape as
    `load_runs`, so production runs go through `comparison_table`, the bootstrap and the
    consistency summary like benchmark runs do. Reads `raw_results_*.jsonl`, normalising rows
    written before the unified schema, and (unless `judge=False`) attaches the judge verdicts
    from `raw_judge_results_*.jsonl` by `trace_id`."""
    root = Path(results_dir)
    rows = [
        normalize_run_record(json.loads(line))
        for path in sorted(root.glob("raw_results_*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    frame = normalize_groundedness(pd.DataFrame(rows))
    if frame.empty or not judge:
        return frame
    judge_files = sorted(root.glob("raw_judge_results_*.jsonl"))
    if not judge_files:
        return frame
    return merge_judge_scores(frame, load_judge_scores(judge_files))


# ---------- Which runs were pooled ------------------------------------------

def run_summary(df: pd.DataFrame) -> pd.DataFrame:
    """One row per pooled run: model, dataset, dataset hash, phase and its example count."""
    columns = [c for c in ("model", "dataset_name", "dataset_hash", "phase") if c in df.columns]
    return (
        df.groupby(["mlflow_run_id", *columns], dropna=False)["example_id"]
        .nunique()
        .rename("n_examples")
        .reset_index()
    )


def mixed_run_warnings(df: pd.DataFrame) -> list[str]:
    """Why the pooled runs should not be averaged together, if they should not.

    `analyze` reads every run in the experiment. Runs on different datasets, on different
    versions of one dataset (same name, new export) or from different phases (a smoke test next
    to the final sweep) measure different things, and a model's mean across them is not a
    result. Each warning names the filter that isolates one group.
    """
    warnings: list[str] = []
    runs = run_summary(df)
    if "dataset_name" in runs and runs["dataset_name"].nunique(dropna=False) > 1:
        names = sorted(map(str, runs["dataset_name"].unique()))
        warnings.append(
            f"runs on {len(names)} datasets are pooled ({', '.join(names)}); analyse one with "
            f"--filter 'params.dataset_name = \"{names[0]}\"'"
        )
    if {"dataset_name", "dataset_hash"} <= set(runs.columns):
        for name, group in runs.groupby("dataset_name", dropna=False):
            hashes = sorted(map(str, group["dataset_hash"].unique()))
            if len(hashes) > 1:
                warnings.append(
                    f"dataset {name} changed between runs ({len(hashes)} hashes: {', '.join(hashes)}); "
                    f"the examples differ, so analyse one version with "
                    f"--filter 'params.dataset_hash = \"{hashes[-1]}\"'"
                )
    if "phase" in runs and runs["phase"].nunique(dropna=False) > 1:
        phases = sorted(map(str, runs["phase"].unique()))
        warnings.append(
            f"runs from {len(phases)} phases are pooled ({', '.join(phases)}); report the final "
            f"sweep alone with --filter 'params.phase = \"final\"'"
        )
    # One model measured with different prompts or different weights is two systems under one name.
    for column, what, param in (
        ("prompt_hash", "prompt text", "params.prompt_hash"),
        ("model_digest", "model weights", "params.model_digest"),
    ):
        if not {"model", column} <= set(df.columns):
            continue
        # No value = the run predates the column (NaN) or MLflow stringified a None ("None")
        known = df.dropna(subset=[column])
        known = known[known[column].astype(str) != "None"]
        for name, group in known.groupby("model", dropna=False):
            values = sorted(map(str, group[column].unique()))
            if len(values) > 1:
                warnings.append(
                    f"model {name} was run with {len(values)} different {what} "
                    f"({column}: {', '.join(values)}); analyse one with "
                    f"--filter 'params.model_name = \"{name}\" and {param} = \"{values[-1]}\"'"
                )
    return warnings


# ---------- Comparison table ----------------------------------------------

@dataclass(frozen=True)
class MetricSpec:
    column: str
    label: str
    higher_is_better: bool = True


# The MINIMUM set of metrics: quality,
# reliability, performance each represented.
DEFAULT_METRICS: list[MetricSpec] = [
    MetricSpec("format_valid", "Format validity rate", True),
    MetricSpec("groundedness_rate", "Citation groundedness", True),
    MetricSpec("dimension_completion_rate", "Dimension completion rate", True),
    MetricSpec("overall_score", "Overall score (0–10)", True),
    MetricSpec("judge_quality_score", "Judge quality score (external)", True),
    MetricSpec("latency_s", "Latency (s)", False),
]

# Shown in `comparison_table` next to the headline metrics so the old numbers stay reproducible.
LEGACY_METRICS: list[MetricSpec] = [
    MetricSpec("groundedness_rate_legacy", "Citation groundedness, no citations = 1.0 (legacy)", True),
]


def _is_complete(df: pd.DataFrame) -> pd.Series:
    """Rows whose assessment scored every dimension (`format_valid` is True)."""
    if "format_valid" not in df:
        return pd.Series(False, index=df.index)
    return df["format_valid"].eq(True)


def _is_partial(df: pd.DataFrame) -> pd.Series:
    """Rows that scored some but not all dimensions. Their `overall_score` is an average over
    the scored dimensions only (services/evaluator.py), so it is not comparable with a complete
    assessment's."""
    if {"dimensions_present", "dimensions_total"} <= set(df.columns):
        present = pd.to_numeric(df["dimensions_present"], errors="coerce")
        total = pd.to_numeric(df["dimensions_total"], errors="coerce")
        return (present > 0) & (present < total)
    if "overall_score" in df:
        return ~_is_complete(df) & pd.to_numeric(df["overall_score"], errors="coerce").notna()
    return pd.Series(False, index=df.index)


def comparison_table(df: pd.DataFrame, metrics: Iterable[MetricSpec] | None = None) -> pd.DataFrame:
    """Model × metric mean (± SD, n).

    Missing values are dropped per metric so a model that didn't produce
    an overall_score for some examples still has a defensible mean on the
    examples where it did produce one — but the `n` column reveals that.

    Groundedness is NaN for an assessment with no citations, so its `n` is the number of rows
    that cited something. `n_partial` counts the rows that scored only some dimensions; their
    overall_score is pooled here, which `comparison_table_complete` avoids. `overall_score` on a
    dataset without gold labels (d_real_sprints) is the engine's own grade, not accuracy.
    """
    metrics = tuple(metrics) if metrics is not None else (*DEFAULT_METRICS, *LEGACY_METRICS)
    df = normalize_groundedness(df)
    partial = _is_partial(df)
    out_rows = []
    for model, group in df.groupby("model"):
        row: dict[str, Any] = {
            "model": model,
            "n_examples": group["example_id"].nunique(),
            "n_partial": int(partial.loc[group.index].sum()),
        }
        for spec in metrics:
            if spec.column not in group:
                row[f"{spec.label} mean"] = None
                row[f"{spec.label} sd"] = None
                row[f"{spec.label} n"] = 0
                continue
            vals = pd.to_numeric(group[spec.column], errors="coerce").dropna()
            row[f"{spec.label} mean"] = float(vals.mean()) if not vals.empty else None
            row[f"{spec.label} sd"] = float(vals.std(ddof=1)) if len(vals) >= 2 else None
            row[f"{spec.label} n"] = int(vals.shape[0])
        out_rows.append(row)
    if not out_rows:
        return pd.DataFrame(columns=["model", "n_examples", "n_partial"]).set_index("model")
    return pd.DataFrame(out_rows).set_index("model").sort_index()


def comparison_table_complete(df: pd.DataFrame, metrics: Iterable[MetricSpec] | None = None) -> pd.DataFrame:
    """`comparison_table` over `format_valid == True` rows only, i.e. assessments that scored
    every dimension, so each overall_score is an average over the same set of dimensions.

    `n_partial` is the number of partially scored rows left out (some dimensions scored, some
    failed), and `n_rows_total` all rows the model produced, so a model that mostly fails does
    not look good on the few rows that worked. Models with no complete row stay in the table
    with n = 0. The format-validity rate is dropped: it is 1.0 here by construction.
    """
    df = normalize_groundedness(df)
    if metrics is None:
        metrics = [m for m in (*DEFAULT_METRICS, *LEGACY_METRICS) if m.column != "format_valid"]
    complete = df[_is_complete(df)]
    table = comparison_table(complete, metrics)
    partial = _is_partial(df)
    counts = pd.DataFrame({
        "n_partial": partial.groupby(df["model"]).sum().astype(int),
        "n_rows_total": df.groupby("model").size(),
    })
    n_examples = table["n_examples"].reindex(counts.index).fillna(0).astype(int)
    table = table.drop(columns=["n_examples", "n_partial"]).reindex(counts.index)
    for column in table.columns[table.columns.str.endswith(" n")]:
        table[column] = table[column].fillna(0).astype(int)  # a model with no complete row has n = 0
    table.insert(0, "n_examples", n_examples)
    table.insert(1, "n_partial", counts["n_partial"])
    table.insert(2, "n_rows_total", counts["n_rows_total"])
    table.index.name = "model"
    return table


# ---------- Consistency (within-model, across repeats) ---------------------

def consistency_summary(df: pd.DataFrame, metric: str = "overall_score") -> pd.DataFrame:
    """SD of `metric` across repeats, per (model, example). Then averaged
    per model for the headline table."""
    if "repeat_index" not in df:
        return pd.DataFrame()
    local = df.copy()
    local[metric] = pd.to_numeric(local[metric], errors="coerce")
    per = (
        local.groupby(["model", "example_id"])[metric]
        .agg(["mean", "std", "count"])
        .reset_index()
    )
    out = (
        per.groupby("model")
        .agg(
            mean_of_example_means=("mean", "mean"),
            mean_of_example_stds=("std", "mean"),
            n_examples=("example_id", "nunique"),
        )
        .reset_index()
    )
    out.rename(columns={"mean_of_example_stds": f"{metric}_sd_within_example_mean"}, inplace=True)
    return out

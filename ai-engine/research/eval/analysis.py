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

from research.eval.attach_judge_scores import load_judge_scores, merge_judge_scores
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
    'tags.phase = "preliminary"').
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
        for col in ("params.model_name", "params.dataset_name", "params.prompt_version", "params.seed"):
            if col in run_row:
                df[col.replace("params.", "")] = run_row[col]
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    return combined


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
    frame = pd.DataFrame(rows)
    if frame.empty or not judge:
        return frame
    judge_files = sorted(root.glob("raw_judge_results_*.jsonl"))
    if not judge_files:
        return frame
    return merge_judge_scores(frame, load_judge_scores(judge_files))


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


def comparison_table(df: pd.DataFrame, metrics: Iterable[MetricSpec] = tuple(DEFAULT_METRICS)) -> pd.DataFrame:
    """Model × metric mean (± SD, n).

    Missing values are dropped per metric so a model that didn't produce
    an overall_score for some examples still has a defensible mean on the
    examples where it did produce one — but the `n` column reveals that.
    """
    out_rows = []
    for model, group in df.groupby("model"):
        row: dict[str, Any] = {"model": model, "n_examples": group["example_id"].nunique()}
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
    return pd.DataFrame(out_rows).set_index("model").sort_index()


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

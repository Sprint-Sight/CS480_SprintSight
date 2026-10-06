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

import mlflow
import numpy as np
import pandas as pd

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
    runs = mlflow.search_runs(experiment_ids=[exp.experiment_id], filter_string=filter_string)
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
            rows = [json.loads(line) for line in f if line.strip()]
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
        row = {"model": model, "n_examples": group["example_id"].nunique()}
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


# ---------- Paired bootstrap -----------------------------------------------

def _paired_pivot(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Pivot to example_id × model with the per-example VALUE of `metric`.

    Repeats are averaged per (model, example) before pivoting — the
    paired comparison is between models on the same example, so repeat
    runs within a model get collapsed first.
    """
    if "model" not in df or metric not in df:
        return pd.DataFrame()
    numeric = pd.to_numeric(df[metric], errors="coerce")
    local = df.assign(_metric=numeric)
    collapsed = local.groupby(["example_id", "model"])["_metric"].mean().reset_index()
    return collapsed.pivot(index="example_id", columns="model", values="_metric")


@dataclass(frozen=True)
class PairedResult:
    model_a: str
    model_b: str
    metric: str
    n: int
    mean_diff: float
    ci_low: float
    ci_high: float
    median_diff: float
    win_rate_a: float


def paired_bootstrap_diff(
    df: pd.DataFrame,
    metric: str,
    model_a: str,
    model_b: str,
    n_boot: int = 10_000,
    seed: int = 42,
) -> PairedResult | None:
    """Mean(A - B) with a 95% percentile bootstrap CI, computed on the
    examples where BOTH models produced a value for the metric. Returns
    None when there are fewer than 3 paired observations — a CI from 2
    points is theatre, not statistics."""
    pivot = _paired_pivot(df, metric)
    if model_a not in pivot or model_b not in pivot:
        return None
    pair = pivot[[model_a, model_b]].dropna()
    if len(pair) < 3:
        return None
    diffs = (pair[model_a] - pair[model_b]).to_numpy()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(diffs), size=(n_boot, len(diffs)))
    means = diffs[idx].mean(axis=1)
    lo, hi = np.quantile(means, [0.025, 0.975])
    return PairedResult(
        model_a=model_a,
        model_b=model_b,
        metric=metric,
        n=len(diffs),
        mean_diff=float(diffs.mean()),
        ci_low=float(lo),
        ci_high=float(hi),
        median_diff=float(np.median(diffs)),
        win_rate_a=float((diffs > 0).mean() + 0.5 * (diffs == 0).mean()),
    )


def pairwise_ci_table(df: pd.DataFrame, metric: str, models: Iterable[str] | None = None, **kwargs) -> pd.DataFrame:
    """One row per unordered model pair"""
    if models is None:
        models = sorted(df["model"].dropna().unique())
    models = list(models)
    rows = []
    for i, a in enumerate(models):
        for b in models[i + 1:]:
            result = paired_bootstrap_diff(df, metric, a, b, **kwargs)
            if result is None:
                rows.append({
                    "pair": f"{a} vs {b}", "metric": metric, "n": 0,
                    "mean_diff": None, "ci_low": None, "ci_high": None,
                    "win_rate_a": None, "note": "insufficient paired data",
                })
            else:
                rows.append({
                    "pair": f"{a} vs {b}",
                    "metric": metric,
                    "n": result.n,
                    "mean_diff": result.mean_diff,
                    "ci_low": result.ci_low,
                    "ci_high": result.ci_high,
                    "win_rate_a": result.win_rate_a,
                    "note": "CI excludes 0" if result.ci_low * result.ci_high > 0 else "CI includes 0",
                })
    return pd.DataFrame(rows)


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

"""Paired bootstrap statistics shared by the online prompt promotion and the offline analysis.

evaluation/online/promote.py uses paired_bootstrap_diff to decide whether a challenger prompt beats
production; evaluation/offline/analysis.py, plots.py and the judge study use it (and
pairwise_ci_table) for model comparisons. Pure numpy/pandas: no MLflow.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import pandas as pd


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

"""Paired bootstrap statistics shared by the online prompt promotion and the offline analysis.

evaluation/online/promote.py uses paired_bootstrap_diff to decide whether a challenger prompt beats
production; evaluation/offline/analysis.py, plots.py and the judge study use it (and
pairwise_ci_table) for model comparisons. Pure numpy/pandas: no MLflow.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


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


# ---------- Generic bootstrap helpers (from the judge study) -----------------

def bootstrap_ci(
    values: Sequence[float],
    statistic: Callable[[np.ndarray], float] = np.mean,
    *,
    n_boot: int = 10_000,
    seed: int = 42,
    alpha: float = 0.05,
) -> tuple[float | None, float | None, float | None]:
    """Percentile bootstrap CI for an arbitrary statistic.

    Percentile rather than BCa: with the 5-50 row datasets this study
    operates on, the bias-correction and acceleration terms are themselves
    estimated from too little data to be trustworthy, and a plain percentile
    interval is the conservative, explainable choice. Returns (None, None,
    None) below three observations -- an interval from two points is theatre.
    """
    array = np.asarray([v for v in values if v is not None and not is_nan(v)], dtype=float)
    if array.size < 3:
        return (float(statistic(array)) if array.size else None, None, None)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, array.size, size=(n_boot, array.size))
    draws = np.array([statistic(array[row]) for row in indices], dtype=float)
    draws = draws[~np.isnan(draws)]
    if draws.size == 0:
        return (float(statistic(array)), None, None)
    low, high = np.quantile(draws, [alpha / 2, 1 - alpha / 2])
    return float(statistic(array)), float(low), float(high)


def is_nan(value: Any) -> bool:
    try:
        return bool(math.isnan(float(value)))
    except (TypeError, ValueError):
        return False


def paired_bootstrap_statistic(
    x: np.ndarray,
    y: np.ndarray,
    statistic: Callable[[np.ndarray, np.ndarray], float],
    *,
    n_boot: int = 2000,
    seed: int = 42,
    alpha: float = 0.05,
) -> tuple[float | None, float | None]:
    """CI for a two-sample paired statistic (kappa, rho) by resampling PAIRS.

    Resampling pairs, not each vector independently, is what keeps the
    pairing intact -- bootstrapping the two rater vectors separately would
    destroy exactly the association being measured.
    """
    if x.size < 3:
        return (None, None)
    rng = np.random.default_rng(seed)
    draws: list[float] = []
    degenerate = 0
    for _ in range(n_boot):
        index = rng.integers(0, x.size, size=x.size)
        try:
            value = statistic(x[index], y[index])
        except (ValueError, ZeroDivisionError, FloatingPointError):
            # A resample can land on a single rating level, where kappa and
            # rho are undefined. Skipping those draws is correct; counting
            # them is what tells us whether the interval is trustworthy.
            degenerate += 1
            continue
        if value is not None and not is_nan(value):
            draws.append(float(value))
    if degenerate:
        log.debug(
            "%d of %d bootstrap resamples were degenerate (single rating level).",
            degenerate, n_boot,
        )
    if len(draws) < 20:
        # Too few usable draws for a percentile interval to mean anything --
        # which is itself a signal that the ratings have almost no variance.
        log.warning(
            "Bootstrap CI not estimable: only %d of %d resamples yielded a "
            "defined statistic.", len(draws), n_boot,
        )
        return (None, None)
    low, high = np.quantile(np.asarray(draws), [alpha / 2, 1 - alpha / 2])
    return (float(low), float(high))

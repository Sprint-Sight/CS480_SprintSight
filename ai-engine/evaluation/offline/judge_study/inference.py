"""Statistical inference for model comparisons (Part 8): paired tests, effect sizes and
multiplicity correction.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, Literal

import numpy as np
import pandas as pd

from evaluation.offline.judge_study.frame import DETERMINISTIC_METRIC_COLUMNS
from evaluation.offline.judge_study.specs import JUDGE_METRIC_NAMES
from evaluation.stats import bootstrap_ci, is_nan, paired_bootstrap_diff

log = logging.getLogger(__name__)


#
# With five fixtures and three models, the difference between "model A is
# better" and "model A scored higher on this sample" is the whole report. Three
# commitments:
#
#   Paired, always. Every model sees the identical examples, so the paired
#     difference removes example difficulty from the comparison -- by far the
#     largest variance component when n is 5.
#   An effect size next to every p. Cliff's delta is reported because it is
#     non-parametric, bounded, and interpretable on an ordinal 1-5 scale,
#     where Cohen's d would assume an interval scale the rubric does not have.
#   Multiplicity correction. Comparing 3 models on 5 metrics is 15 tests; at
#     alpha 0.05 roughly one spurious "significant" result is expected. Holm
#     controls the family-wise error rate for the small confirmatory set;
#     Benjamini-Hochberg controls FDR for the wider exploratory sweep. Both
#     are provided and the choice is recorded in the output.


def holm_bonferroni(pvalues: Sequence[float]) -> list[float]:
    """Holm step-down adjusted p-values. Controls FWER; use for the headline
    confirmatory comparisons, where one false claim is costly."""
    values = [(p, index) for index, p in enumerate(pvalues) if p is not None and not is_nan(p)]
    adjusted: list[float | None] = [None] * len(pvalues)
    running = 0.0
    m = len(values)
    for rank, (p, index) in enumerate(sorted(values)):
        running = max(running, (m - rank) * p)
        adjusted[index] = min(1.0, running)
    return [1.0 if value is None else value for value in adjusted]


def benjamini_hochberg(pvalues: Sequence[float]) -> list[float]:
    """BH step-up adjusted p-values. Controls FDR; use for the exploratory
    sweep across many metrics, where tolerating some false positives in
    exchange for power is the right trade."""
    values = [(p, index) for index, p in enumerate(pvalues) if p is not None and not is_nan(p)]
    adjusted: list[float | None] = [None] * len(pvalues)
    m = len(values)
    running = 1.0
    for rank, (p, index) in enumerate(sorted(values, reverse=True)):
        position = m - rank
        running = min(running, p * m / position)
        adjusted[index] = min(1.0, running)
    return [1.0 if value is None else value for value in adjusted]


def cliffs_delta(a: Sequence[float], b: Sequence[float]) -> tuple[float | None, str]:
    """Cliff's delta plus its conventional magnitude label.

    delta is P(a > b) - P(a < b): the probability that a randomly chosen
    observation from A beats one from B, rescaled to [-1, 1]. No normality or
    interval-scale assumption, which is what makes it the right effect size
    for a 1-5 rubric. Thresholds follow Romano et al. (2006).
    """
    x = np.asarray([v for v in a if v is not None and not is_nan(v)], dtype=float)
    y = np.asarray([v for v in b if v is not None and not is_nan(v)], dtype=float)
    if x.size == 0 or y.size == 0:
        return None, "not estimable"
    greater = int(np.sum(x[:, None] > y[None, :]))
    less = int(np.sum(x[:, None] < y[None, :]))
    delta = (greater - less) / (x.size * y.size)
    magnitude = abs(delta)
    if magnitude < 0.147:
        label = "negligible"
    elif magnitude < 0.33:
        label = "small"
    elif magnitude < 0.474:
        label = "medium"
    else:
        label = "large"
    return float(delta), label


def paired_model_comparison(
    frame: pd.DataFrame,
    metric: str,
    model_a: str,
    model_b: str,
    *,
    n_boot: int = 10_000,
    seed: int = 42,
    higher_is_better: bool = True,
) -> dict[str, Any]:
    """Paired comparison of two models on one metric.

    Repeats are averaged per (model, example) before pairing: the comparison
    is between models on the same example, so within-model repeat variation
    belongs to the consistency analysis in Part 7, not here.
    """
    from scipy import stats as scipy_stats  # type: ignore[import-untyped]

    if metric not in frame.columns:
        return {"metric": metric, "pair": f"{model_a} vs {model_b}", "n": 0,
                "note": "metric column absent"}

    local = frame.assign(_value=pd.to_numeric(frame[metric], errors="coerce"))
    collapsed = (
        local.groupby(["example_id", "model"])["_value"].mean().reset_index()
    )
    pivot = collapsed.pivot(index="example_id", columns="model", values="_value")
    if model_a not in pivot.columns or model_b not in pivot.columns:
        return {"metric": metric, "pair": f"{model_a} vs {model_b}", "n": 0,
                "note": "one model absent from this metric"}

    pair = pivot[[model_a, model_b]].dropna()
    result: dict[str, Any] = {
        "metric": metric,
        "pair": f"{model_a} vs {model_b}",
        "model_a": model_a,
        "model_b": model_b,
        "higher_is_better": higher_is_better,
        "n": len(pair),
    }

    # The mean difference, its percentile bootstrap CI and the win rate come
    # from evaluation.stats.paired_bootstrap_diff -- the function the
    # model-comparison report already uses -- so a CI quoted here and a CI
    # quoted by `cli.py analyze` are the same estimator with the same seed,
    # not two bootstraps that happen to be near each other. What this adds on
    # top is a significance test, an effect size, and the power floor, none of
    # which analysis.py computes.
    delegated = paired_bootstrap_diff(
        frame.assign(**{metric: local["_value"]}),
        metric,
        model_a,
        model_b,
        n_boot=n_boot,
        seed=seed,
    )
    # The smallest p-value the Wilcoxon signed-rank test can return at this n,
    # which is 2 / 2**n for a two-sided test. At n=5 that is 0.0625, so NOTHING
    # can reach alpha=0.05 however large the effect -- and after multiplicity
    # correction the floor rises further. Reporting it alongside the p-value is
    # what stops "not significant" being misread as "no difference"; at these
    # sample sizes the CI and the effect size are the evidence, not the p.
    result["min_attainable_p"] = (
        float(2 ** (1 - len(pair))) if len(pair) >= 1 else None
    )
    result["p_can_reach_0.05"] = bool(result["min_attainable_p"] <= 0.05) if pair.size else False

    if len(pair) < 3:
        result["note"] = "fewer than 3 paired examples; no inference attempted"
        return result

    differences = (pair[model_a] - pair[model_b]).to_numpy(dtype=float)
    if delegated is not None:
        result.update({
            "mean_diff": delegated.mean_diff,
            "ci_low": delegated.ci_low,
            "ci_high": delegated.ci_high,
            "median_diff": delegated.median_diff,
            # Ties split, so win_rate is comparable with the pairwise tournament.
            "win_rate_a": delegated.win_rate_a,
        })
    else:
        point, low, high = bootstrap_ci(differences.tolist(), n_boot=n_boot, seed=seed)
        result.update({
            "mean_diff": point,
            "ci_low": low,
            "ci_high": high,
            "median_diff": float(np.median(differences)),
            "win_rate_a": float(
                (differences > 0).mean() + 0.5 * (differences == 0).mean()
            ),
        })

    if np.allclose(differences, 0):
        result["wilcoxon_p"] = 1.0
        result["note"] = "models identical on every paired example"
    else:
        try:
            # Wilcoxon signed-rank, not a paired t-test: n is small and the
            # rubric is ordinal, so normality cannot be assumed.
            test = scipy_stats.wilcoxon(differences, zero_method="zsplit")
            result["wilcoxon_p"] = float(test.pvalue)
        except ValueError as error:
            result["wilcoxon_p"] = None
            result["note"] = f"wilcoxon not applicable: {error}"

    delta, magnitude = cliffs_delta(pair[model_a].tolist(), pair[model_b].tolist())
    result["cliffs_delta"] = delta
    result["effect_magnitude"] = magnitude
    # Read back off the result, not off locals: the CI may have come from the
    # delegated paired_bootstrap_diff rather than from bootstrap_ci here.
    ci_low, ci_high = result.get("ci_low"), result.get("ci_high")
    result["ci_excludes_zero"] = bool(
        ci_low is not None and ci_high is not None and ci_low * ci_high > 0
    )
    return result


def model_comparison_report(
    frame: pd.DataFrame,
    metrics: Sequence[str] | None = None,
    *,
    correction: Literal["holm", "bh", "none"] = "holm",
    **kwargs: Any,
) -> pd.DataFrame:
    """Every model pair against every metric, with multiplicity correction.

    The ``significant`` column uses the CORRECTED p-value and is the only
    column anyone should quote. The raw p is kept beside it so the correction
    is auditable rather than invisible.
    """
    if "model" not in frame.columns:
        raise KeyError("frame has no 'model' column")
    models = sorted(frame["model"].dropna().unique())
    if metrics is None:
        metrics = [
            f"judge_{name}" for name in JUDGE_METRIC_NAMES if f"judge_{name}" in frame.columns
        ] + ["judge_composite"] + [
            column for column, _ in DETERMINISTIC_METRIC_COLUMNS if column in frame.columns
        ]
    direction = {column: better for column, better in DETERMINISTIC_METRIC_COLUMNS}

    rows: list[dict[str, Any]] = []
    for metric in metrics:
        if metric not in frame.columns:
            continue
        for index, model_a in enumerate(models):
            for model_b in models[index + 1:]:
                rows.append(
                    paired_model_comparison(
                        frame,
                        metric,
                        model_a,
                        model_b,
                        higher_is_better=direction.get(metric, True),
                        **kwargs,
                    )
                )
    report = pd.DataFrame(rows)
    if report.empty or "wilcoxon_p" not in report.columns:
        return report

    raw = report["wilcoxon_p"].tolist()
    if correction == "holm":
        report["p_adjusted"] = holm_bonferroni(raw)
    elif correction == "bh":
        report["p_adjusted"] = benjamini_hochberg(raw)
    else:
        report["p_adjusted"] = raw
    report["correction"] = correction
    report["n_tests"] = int(report["wilcoxon_p"].notna().sum())
    report["significant"] = report["p_adjusted"] < 0.05
    if "min_attainable_p" in report.columns:
        underpowered = report[report["min_attainable_p"] > 0.05]
        if not underpowered.empty:
            log.warning(
                "%d of %d comparisons are UNDERPOWERED BY CONSTRUCTION: at n=%s the "
                "Wilcoxon test cannot return p<=0.05 at any effect size. Report the "
                "bootstrap CI and Cliff's delta for these, never the p-value.",
                len(underpowered),
                len(report),
                sorted(underpowered["n"].unique().tolist()),
            )
    return report

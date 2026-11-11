"""Meta-evaluation (Part 5): is the judge measuring anything? Judge-vs-human agreement
(kappa, rho, tau, alpha, ICC) with bootstrap CIs, and the calibration report.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from evaluation.offline.judge_study.specs import JUDGE_METRIC_NAMES
from evaluation.stats import paired_bootstrap_statistic

#
# This is the part that makes the rest of the numbers reportable. An LLM
# judge is a measurement instrument, and an instrument with no stated
# reliability produces results a reader is entitled to ignore. We report a
# panel of coefficients rather than one, because each is blind to a different
# failure:
#
#   Cohen's kappa          chance-corrected exact agreement. Catches a judge
#                          that looks accurate only because the human
#                          distribution is skewed.
#   Quadratic-weighted kappa  the headline for an ORDERED 1-5 rubric: a 5-vs-4
#                          disagreement should not be penalised like 5-vs-1.
#                          This is the standard for ordinal rater agreement.
#   Spearman rho           rank agreement. A judge that is uniformly two
#                          points harsh is still perfectly useful for RANKING
#                          models, and only rho shows that.
#   Kendall tau-b          rho's robustness check; handles the heavy ties a
#                          5-point scale produces better than rho does.
#   Pearson r              linear agreement, reported only to be compared
#                          against rho. r much greater than rho means a
#                          single outlier row is carrying the correlation.
#   Krippendorff's alpha   handles missing annotations natively, which matters
#                          because human annotation coverage is partial.
#   ICC(2,1)               absolute agreement, not just covariation. Two
#                          raters can correlate at 0.95 and still be three
#                          points apart on every item.
#   Mean signed error      the bias term. Positive means the judge is more
#                          generous than the human, which is the documented
#                          failure mode of LLM judges and the one most likely
#                          to flatter our own system.
#
# Everything is reported with a bootstrap CI and an n. A kappa from eight
# annotated rows is an anecdote, and the report says so rather than leaving
# the reader to guess.

# Landis & Koch (1977) bands. Conventional, widely understood by markers and
# reviewers, and stated explicitly so nobody has to guess what "good" means.
_KAPPA_BANDS = (
    (0.81, "almost perfect"),
    (0.61, "substantial"),
    (0.41, "moderate"),
    (0.21, "fair"),
    (0.01, "slight"),
    (-1.01, "poor / no better than chance"),
)


def interpret_kappa(value: float | None) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "not estimable"
    for threshold, label in _KAPPA_BANDS:
        if value >= threshold:
            return label
    return "poor / no better than chance"


def krippendorff_alpha_ordinal(ratings: np.ndarray) -> float | None:
    """Krippendorff's alpha with the ordinal difference function.

    ``ratings`` is (n_raters, n_items); NaN marks a missing judgement. Hand
    implemented because the ``krippendorff`` package is not in this project's
    requirements and a reproducibility claim gets weaker with every optional
    dependency a reader has to install. Alpha earns its place over kappa
    because it handles unequal annotation coverage natively -- our human
    annotations are partial by construction.
    """
    matrix = np.asarray(ratings, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] < 2:
        return None

    # Units with at least two ratings are the only ones alpha is defined over.
    usable = matrix[:, np.sum(~np.isnan(matrix), axis=0) >= 2]
    if usable.shape[1] < 2:
        return None

    values = usable[~np.isnan(usable)]
    levels = np.unique(values)
    if levels.size < 2:
        return None  # no variance: alpha is undefined, not 1.0

    # Ordinal difference: squared distance in cumulative rank mass.
    counts = {level: float(np.sum(values == level)) for level in levels}
    cumulative: dict[float, float] = {}
    running = 0.0
    for level in levels:
        cumulative[level] = running + counts[level] / 2.0
        running += counts[level]

    def ordinal_delta(a: float, b: float) -> float:
        return (cumulative[a] - cumulative[b]) ** 2

    observed_numerator = 0.0
    observed_pairs = 0.0
    for column in usable.T:
        present = column[~np.isnan(column)]
        m = present.size
        if m < 2:
            continue
        for i in range(m):
            for j in range(m):
                if i == j:
                    continue
                observed_numerator += ordinal_delta(present[i], present[j]) / (m - 1)
                observed_pairs += 1.0 / (m - 1)
    if observed_pairs == 0:
        return None
    observed_disagreement = observed_numerator / observed_pairs

    total = values.size
    expected_numerator = 0.0
    for a in levels:
        for b in levels:
            if a == b:
                continue
            expected_numerator += counts[a] * counts[b] * ordinal_delta(a, b)
    expected_disagreement = expected_numerator / (total * (total - 1))
    if expected_disagreement == 0:
        return None
    return float(1.0 - observed_disagreement / expected_disagreement)


def icc_2_1(ratings: np.ndarray) -> float | None:
    """ICC(2,1): two-way random effects, absolute agreement, single rater.

    Reported alongside the correlations because they answer different
    questions. A judge that scores every output exactly two points above the
    human correlates at r = 1.0 and has an ICC near zero -- and for a grading
    tool whose scores students see, absolute agreement is the one that
    matters. Needs complete rows, so it runs on the listwise-complete subset
    and reports its own n via the caller.
    """
    matrix = np.asarray(ratings, dtype=float)
    if matrix.ndim != 2:
        return None
    matrix = matrix[:, ~np.isnan(matrix).any(axis=0)]  # listwise-complete items
    n_raters, n_items = matrix.shape
    if n_items < 3 or n_raters < 2:
        return None

    grand_mean = matrix.mean()
    item_means = matrix.mean(axis=0)
    rater_means = matrix.mean(axis=1)

    ss_items = n_raters * np.sum((item_means - grand_mean) ** 2)
    ss_raters = n_items * np.sum((rater_means - grand_mean) ** 2)
    ss_total = np.sum((matrix - grand_mean) ** 2)
    ss_error = ss_total - ss_items - ss_raters

    df_items = n_items - 1
    df_raters = n_raters - 1
    df_error = df_items * df_raters
    if df_error <= 0:
        return None

    ms_items = ss_items / df_items
    ms_raters = ss_raters / df_raters
    ms_error = ss_error / df_error

    denominator = ms_items + df_raters * ms_error + (n_raters * (ms_raters - ms_error)) / n_items
    if denominator == 0:
        return None
    return float((ms_items - ms_error) / denominator)


@dataclass
class CalibrationReport:
    """Everything needed to decide how far to trust one judge metric."""

    metric: str
    n: int
    n_available: int
    exact_agreement: float | None = None
    within_one_agreement: float | None = None
    cohen_kappa: float | None = None
    cohen_kappa_ci: tuple[float | None, float | None] = (None, None)
    quadratic_kappa: float | None = None
    quadratic_kappa_ci: tuple[float | None, float | None] = (None, None)
    spearman_rho: float | None = None
    spearman_p: float | None = None
    spearman_ci: tuple[float | None, float | None] = (None, None)
    kendall_tau: float | None = None
    kendall_p: float | None = None
    pearson_r: float | None = None
    krippendorff_alpha: float | None = None
    icc_2_1: float | None = None
    mae: float | None = None
    mean_signed_error: float | None = None
    judge_mean: float | None = None
    human_mean: float | None = None
    judge_distinct_scores: int = 0
    interpretation: str = "not estimable"
    warnings: list[str] = field(default_factory=list)

    def to_row(self) -> dict[str, Any]:
        row = {
            key: value
            for key, value in self.__dict__.items()
            if not isinstance(value, (tuple, list))
        }
        row["cohen_kappa_ci_low"], row["cohen_kappa_ci_high"] = self.cohen_kappa_ci
        row["quadratic_kappa_ci_low"], row["quadratic_kappa_ci_high"] = self.quadratic_kappa_ci
        row["spearman_ci_low"], row["spearman_ci_high"] = self.spearman_ci
        row["warnings"] = "; ".join(self.warnings)
        return row


def evaluate_judge_calibration(
    frame: pd.DataFrame,
    metric: str,
    *,
    judge_column: str | None = None,
    human_column: str | None = None,
    n_boot: int = 2000,
    seed: int = 42,
) -> CalibrationReport:
    """Agreement between the LLM judge and the human baseline for one metric.

    Operates on whichever rows have BOTH a judge score and a human
    annotation, and reports that count as ``n`` next to the total available.
    Every coefficient is None rather than a plausible-looking number when the
    data cannot support it -- a kappa of 0.0 and an unestimable kappa mean
    very different things to a reader.
    """
    from scipy import stats as scipy_stats  # type: ignore[import-untyped]
    from sklearn.metrics import cohen_kappa_score  # type: ignore[import-untyped]

    judge_col = judge_column or f"judge_{metric}"
    human_col = human_column or f"human_{metric}"

    missing = [column for column in (judge_col, human_col) if column not in frame.columns]
    if missing:
        return CalibrationReport(
            metric=metric,
            n=0,
            n_available=len(frame),
            warnings=[f"missing columns: {', '.join(missing)}"],
        )

    paired = frame[[judge_col, human_col]].apply(pd.to_numeric, errors="coerce").dropna()
    n = len(paired)
    report = CalibrationReport(metric=metric, n=n, n_available=len(frame))

    if n == 0:
        report.warnings.append("no rows carry both a judge score and a human annotation")
        return report

    judge_values = paired[judge_col].to_numpy(dtype=float)
    human_values = paired[human_col].to_numpy(dtype=float)

    report.judge_mean = float(judge_values.mean())
    report.human_mean = float(human_values.mean())
    report.mae = float(np.mean(np.abs(judge_values - human_values)))
    # Signed, judge minus human: positive is a lenient judge.
    report.mean_signed_error = float(np.mean(judge_values - human_values))

    judge_int = np.rint(judge_values).astype(int)
    human_int = np.rint(human_values).astype(int)
    report.exact_agreement = float(np.mean(judge_int == human_int))
    report.within_one_agreement = float(np.mean(np.abs(judge_int - human_int) <= 1))
    report.judge_distinct_scores = int(np.unique(judge_int).size)

    if report.judge_distinct_scores == 1:
        # The single most common silent failure: a judge that answers 4 to
        # everything scores a respectable MAE and a kappa of exactly 0.
        report.warnings.append(
            f"judge returned the constant value {judge_int[0]} on every row -- "
            "it is not discriminating, and no correlation is interpretable"
        )

    if n < 10:
        report.warnings.append(
            f"n={n} is too small for a stable agreement coefficient; treat "
            "every figure here as indicative only"
        )

    labels = sorted(set(judge_int.tolist()) | set(human_int.tolist()))
    if len(labels) >= 2:
        try:
            report.cohen_kappa = float(
                cohen_kappa_score(human_int, judge_int, labels=labels)
            )
            report.quadratic_kappa = float(
                cohen_kappa_score(human_int, judge_int, labels=labels, weights="quadratic")
            )
            report.cohen_kappa_ci = paired_bootstrap_statistic(
                human_int.astype(float),
                judge_int.astype(float),
                lambda a, b: cohen_kappa_score(
                    np.rint(a).astype(int), np.rint(b).astype(int)
                ),
                n_boot=n_boot,
                seed=seed,
            )
            report.quadratic_kappa_ci = paired_bootstrap_statistic(
                human_int.astype(float),
                judge_int.astype(float),
                lambda a, b: cohen_kappa_score(
                    np.rint(a).astype(int), np.rint(b).astype(int), weights="quadratic"
                ),
                n_boot=n_boot,
                seed=seed,
            )
        except Exception:  # noqa: BLE001
            report.warnings.append("kappa could not be computed on this label set")
    else:
        report.warnings.append("only one rating level present; kappa undefined")

    if n >= 3 and np.std(judge_values) > 0 and np.std(human_values) > 0:
        rho = scipy_stats.spearmanr(judge_values, human_values)
        report.spearman_rho = float(rho.statistic)
        report.spearman_p = float(rho.pvalue)
        report.spearman_ci = paired_bootstrap_statistic(
            judge_values,
            human_values,
            lambda a, b: float(scipy_stats.spearmanr(a, b).statistic),
            n_boot=n_boot,
            seed=seed,
        )
        tau = scipy_stats.kendalltau(judge_values, human_values, variant="b")
        report.kendall_tau = float(tau.statistic)
        report.kendall_p = float(tau.pvalue)
        report.pearson_r = float(scipy_stats.pearsonr(judge_values, human_values).statistic)
    else:
        report.warnings.append(
            "no variance in at least one rater; rank correlation undefined"
        )

    stacked = np.vstack([human_values, judge_values])
    report.krippendorff_alpha = krippendorff_alpha_ordinal(stacked)
    report.icc_2_1 = icc_2_1(stacked)

    # Headline interpretation follows quadratic kappa: the rubric is ordinal,
    # so near-miss disagreements should not be treated as total disagreements.
    report.interpretation = interpret_kappa(
        report.quadratic_kappa if report.quadratic_kappa is not None else report.cohen_kappa
    )
    return report


def calibration_table(
    frame: pd.DataFrame,
    metrics: Sequence[str] = JUDGE_METRIC_NAMES,
    **kwargs: Any,
) -> pd.DataFrame:
    """One calibration row per judge metric, ready to log or print."""
    rows = [
        evaluate_judge_calibration(frame, metric, **kwargs).to_row() for metric in metrics
    ]
    return pd.DataFrame(rows).set_index("metric")

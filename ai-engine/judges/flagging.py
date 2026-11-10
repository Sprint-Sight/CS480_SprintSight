"""When does a judged trace get flagged for review, and for whom.

Two kinds of reason used to be mixed in one list and sent to the same queue:

  * production: things any assessment can be checked for (fabricated or misattributed
    citations, too little evidence, a judge that produced nothing). A person acting on the
    report needs to know about these.
  * research: comparisons against a hand-written gold assessment. Only the benchmark teams
    have one, so a "grade error vs gold" says something about the *model under test*, not
    about whether a real team's report is trustworthy. Queueing it for an instructor is noise.

`evaluate_flags` is pure (a dict of metric values in, reasons out) so the rules can be tested
without MLflow. judges/run_judges.py decides what to do with each audience.

Thresholds are starting points, not calibrated values: they should be revisited once the
judge has been validated against human labels (see the inter-annotator test plan).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

Audience = Literal["production", "research"]

# Column names in the evaluate() result frame: "<scorer feedback name>/value".
GRADE_COL = "grade_penalised_mae/value"
HALLUCINATION_COL = "citation_hallucination_rate/value"
JUDGE_FAILURE_CLASS_COL = "citation_judge_failure_class/value"  # set only when the judge call failed
SEVERITY_WEIGHTED_COL = "citation_severity_weighted_rate/value"
SEVERITY_WEIGHTED_INCL_DROPPED_COL = "citation_severity_weighted_rate_incl_dropped/value"
CITATION_COUNT_COL = "citation_count/value"
GROUNDED_COL = "citation_grounded_rate/value"
CRITICAL_COL = "citations_dropped_by_code/value"
PEDAGOGY_HARSH_COL = "pedagogy_harsh/value"
JUSTIFICATION_COL = "justification_hard_contradictions/value"  # inert until judges/narrative_judge.py exists: an absent column reads as None
NARRATIVE_COL = "narrative_contradiction_count/value"
PEDAGOGY_COL = "pedagogy_score/value"

MIN_PEDAGOGY_SCORE = 0.6
MAX_HALLUCINATION = 0.1
# Severity-weighted share of judged citations (judges/citation_ground_custom_judge.VERDICT_WEIGHT).
# Unlike the plain hallucination rate it separates a slip in a line count from a wrong author or
# a contradicted record: 0.15 is, for example, one contradicted citation in six, or three wrong
# attributions in ten. Uncalibrated.
MAX_SEVERITY_WEIGHTED_RATE = 0.15
MIN_CITATIONS = 10
MIN_GROUNDED_RATE = 0.5
MAX_PENALISED_MAE = 3  # research only: needs a gold assessment


@dataclass(frozen=True)
class FlagReason:
    code: str
    message: str
    audience: Audience


def _value(values: Mapping[str, object], column: str):
    value = values.get(column)
    if value is None:
        return None
    try:
        if math.isnan(value):  # type: ignore[arg-type]
            return None
    except TypeError:  # not a number at all (a string cell, say): leave it for the caller
        pass
    return value


def evaluate_flags(values: Mapping[str, object], *, has_gold: bool, with_judge: bool) -> list[FlagReason]:
    """Reasons to flag one judged trace. `values` maps result-frame columns to cell values."""
    reasons: list[FlagReason] = []

    if has_gold:  # research: the gold scorer only runs for benchmark teams
        mae = _value(values, GRADE_COL)
        if mae is None:
            reasons.append(FlagReason("GOLD_SCORER_NO_OUTPUT", "grade scorer produced no output", "research"))
        elif mae > MAX_PENALISED_MAE:
            reasons.append(FlagReason(
                "GOLD_GRADE_ERROR", f"grade_penalised_mae={mae} > {MAX_PENALISED_MAE}", "research"))

    if not with_judge:
        return reasons

    halluc = _value(values, HALLUCINATION_COL)
    count = _value(values, CITATION_COUNT_COL)
    grounded = _value(values, GROUNDED_COL)
    severity = _value(values, SEVERITY_WEIGHTED_COL)
    severity_incl_dropped = _value(values, SEVERITY_WEIGHTED_INCL_DROPPED_COL)

    if halluc is None:
        why = _value(values, JUDGE_FAILURE_CLASS_COL)  # e.g. "context_truncated", "timeout"
        reasons.append(FlagReason(
            "JUDGE_NO_OUTPUT", f"citation judge produced no output{f' ({why})' if why else ''}", "production"))
    elif halluc > MAX_HALLUCINATION:
        reasons.append(FlagReason(
            "JUDGE_HALLUCINATION", f"hallucination_rate={halluc} > {MAX_HALLUCINATION}", "production"))
    if severity is not None and severity > MAX_SEVERITY_WEIGHTED_RATE:
        reasons.append(FlagReason(
            "JUDGE_SEVERITY_WEIGHTED",
            f"severity_weighted_rate={severity} > {MAX_SEVERITY_WEIGHTED_RATE}", "production"))
    if count is not None and count < MIN_CITATIONS:
        reasons.append(FlagReason(
            "JUDGE_LOW_COVERAGE", f"citation_count={count} < {MIN_CITATIONS}", "production"))
    if grounded is not None and grounded < MIN_GROUNDED_RATE:
        reasons.append(FlagReason(
            "JUDGE_LOW_GROUNDED_RATE", f"grounded_rate={grounded} < {MIN_GROUNDED_RATE}", "production"))
    if dropped := _value(values, CRITICAL_COL):
        detail = f" (severity-weighted rate incl. dropped: {severity_incl_dropped})" if severity_incl_dropped is not None else ""
        reasons.append(FlagReason(
            "JUDGE_CODE_DROPPED_CITATIONS",
            f"{int(dropped)} fabricated citation(s) removed by code{detail}", "production"))
    for column, code, label in (
        (JUSTIFICATION_COL, "JUDGE_JUSTIFICATION_CONTRADICTION", "justification_hard_contradictions"),
        (NARRATIVE_COL, "JUDGE_NARRATIVE_CONTRADICTION", "narrative_contradictions"),
        (PEDAGOGY_HARSH_COL, "JUDGE_HARSH_TONE", "harsh_tone"),
    ):
        if flagged := _value(values, column):
            reasons.append(FlagReason(code, f"{label}={int(flagged)}", "production"))
    pedagogy = _value(values, PEDAGOGY_COL)
    if pedagogy is not None and pedagogy < MIN_PEDAGOGY_SCORE:
        reasons.append(FlagReason("JUDGE_LOW_PEDAGOGY", f"pedagogy_score={pedagogy} < {MIN_PEDAGOGY_SCORE}", "production"))
    return reasons


def production_reasons(reasons: list[FlagReason]) -> list[FlagReason]:
    return [reason for reason in reasons if reason.audience == "production"]


def research_reasons(reasons: list[FlagReason]) -> list[FlagReason]:
    return [reason for reason in reasons if reason.audience == "research"]

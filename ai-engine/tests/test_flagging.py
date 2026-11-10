"""When a judged trace is flagged, and which flags reach the review queue."""

import math

import pandas as pd
import pytest

from judges import run_judges
from judges.flagging import (
    CITATION_COUNT_COL,
    CRITICAL_COL,
    GRADE_COL,
    GROUNDED_COL,
    HALLUCINATION_COL,
    MAX_SEVERITY_WEIGHTED_RATE,
    SEVERITY_WEIGHTED_COL,
    SEVERITY_WEIGHTED_INCL_DROPPED_COL,
    evaluate_flags,
    production_reasons,
    research_reasons,
)

HEALTHY = {
    HALLUCINATION_COL: 0.0,
    SEVERITY_WEIGHTED_COL: 0.02,
    CITATION_COUNT_COL: 14,
    GROUNDED_COL: 0.95,
    CRITICAL_COL: 0,
}


def codes(reasons) -> set[str]:
    return {reason.code for reason in reasons}


def test_a_healthy_judged_trace_raises_nothing() -> None:
    assert evaluate_flags(HEALTHY, has_gold=False, with_judge=True) == []


def test_the_severity_weighted_rate_is_a_gate_of_its_own() -> None:
    # Few hallucinations by count, but the ones there are serious: only the weighted rate sees it.
    values = {**HEALTHY, HALLUCINATION_COL: 0.05, SEVERITY_WEIGHTED_COL: MAX_SEVERITY_WEIGHTED_RATE + 0.1}

    reasons = evaluate_flags(values, has_gold=False, with_judge=True)

    assert codes(reasons) == {"JUDGE_SEVERITY_WEIGHTED"}
    assert "severity_weighted_rate" in reasons[0].message


def test_a_rate_exactly_at_the_threshold_is_not_flagged() -> None:
    values = {**HEALTHY, SEVERITY_WEIGHTED_COL: MAX_SEVERITY_WEIGHTED_RATE}
    assert evaluate_flags(values, has_gold=False, with_judge=True) == []


def test_a_judge_that_produced_nothing_fails_closed() -> None:
    for missing in (None, math.nan):
        values = {**HEALTHY, HALLUCINATION_COL: missing}
        assert codes(evaluate_flags(values, has_gold=False, with_judge=True)) == {"JUDGE_NO_OUTPUT"}


def test_thin_evidence_and_fabrications_are_production_flags() -> None:
    values = {**HEALTHY, CITATION_COUNT_COL: 4, GROUNDED_COL: 0.3, CRITICAL_COL: 2,
              SEVERITY_WEIGHTED_INCL_DROPPED_COL: 0.4}

    reasons = evaluate_flags(values, has_gold=False, with_judge=True)

    assert codes(reasons) == {"JUDGE_LOW_COVERAGE", "JUDGE_LOW_GROUNDED_RATE", "JUDGE_CODE_DROPPED_CITATIONS"}
    assert all(reason.audience == "production" for reason in reasons)
    dropped = next(reason for reason in reasons if reason.code == "JUDGE_CODE_DROPPED_CITATIONS")
    assert "2 fabricated" in dropped.message and "0.4" in dropped.message


def test_a_gold_comparison_is_a_research_flag_not_a_production_one() -> None:
    values = {**HEALTHY, GRADE_COL: 5.0}

    reasons = evaluate_flags(values, has_gold=True, with_judge=True)

    assert codes(reasons) == {"GOLD_GRADE_ERROR"}
    assert production_reasons(reasons) == []
    assert codes(research_reasons(reasons)) == {"GOLD_GRADE_ERROR"}


def test_a_missing_gold_score_is_a_research_flag() -> None:
    reasons = evaluate_flags({**HEALTHY, GRADE_COL: None}, has_gold=True, with_judge=True)
    assert codes(reasons) == {"GOLD_SCORER_NO_OUTPUT"}
    assert research_reasons(reasons) == reasons


def test_gold_rules_do_not_apply_without_a_gold() -> None:
    assert evaluate_flags({**HEALTHY, GRADE_COL: 9.0}, has_gold=False, with_judge=True) == []


def test_judge_rules_do_not_apply_when_the_judge_was_not_run() -> None:
    assert evaluate_flags({HALLUCINATION_COL: None}, has_gold=False, with_judge=False) == []


def test_production_and_research_reasons_can_occur_together() -> None:
    values = {**HEALTHY, GRADE_COL: 6.0, HALLUCINATION_COL: 0.4}

    reasons = evaluate_flags(values, has_gold=True, with_judge=True)

    assert codes(production_reasons(reasons)) == {"JUDGE_HALLUCINATION"}
    assert codes(research_reasons(reasons)) == {"GOLD_GRADE_ERROR"}


# ------------------------------------------------- what reaches the review queue


@pytest.fixture
def queued(monkeypatch) -> list:
    calls: list = []
    monkeypatch.setattr(run_judges, "add_to_review_queue", lambda name, ids: calls.append((name, ids)))
    monkeypatch.setattr(run_judges, "_log", lambda message: None)
    return calls


def _frame(**overrides) -> pd.DataFrame:
    return pd.DataFrame([{"trace_id": "tr-1", **HEALTHY, GRADE_COL: 1.0, **overrides}])


def test_a_production_flag_is_queued(queued) -> None:
    run_judges._flag_for_review(_frame(**{HALLUCINATION_COL: 0.5}), with_judge=True)
    assert queued == [("review_queue_tr-1", ["tr-1"])]


def test_a_research_only_flag_is_not_queued(queued) -> None:
    run_judges._flag_for_review(_frame(**{GRADE_COL: 8.0}), with_judge=True)
    assert queued == []


def test_research_flags_can_be_queued_on_request(queued, monkeypatch) -> None:
    monkeypatch.setattr(run_judges, "QUEUE_RESEARCH_FLAGS", True)
    run_judges._flag_for_review(_frame(**{GRADE_COL: 8.0}), with_judge=True)
    assert queued == [("review_queue_tr-1", ["tr-1"])]


def test_a_clean_trace_is_not_queued(queued) -> None:
    run_judges._flag_for_review(_frame(), with_judge=True)
    assert queued == []

"""Prompt promotion: per-dimension evidence, the severity gate, and bootstrap-backed comparison."""

import json
from types import SimpleNamespace

import pytest

from evaluation.online import promote
from evaluation.online.promote import (
    JUDGE_RESULTS_TAG,
    MIN_CITATIONS_FOR_PROMOTION,
    PROMOTION_HALLUCINATION_THRESHOLD,
    PROMOTION_MAE_THRESHOLD,
    PROMOTION_SEVERITY_WEIGHTED_THRESHOLD,
    _compare,
    _dimension_scores,
    _passes_criteria,
)

GOOD = {"abs_error": 1.0, "hallucination": 0.0, "severity_weighted": 0.0, "citation_count": 6.0}


def version(results: dict) -> SimpleNamespace:
    return SimpleNamespace(tags={JUDGE_RESULTS_TAG: json.dumps(results)})


def results(**errors: float) -> dict:
    return {key: {"abs_error": error, "hallucination": 0.0, "severity_weighted": 0.0} for key, error in errors.items()}


# ------------------------------------------------------ per-dimension evidence


def test_a_dimension_never_borrows_the_overall_rate_or_count() -> None:
    # The trace as a whole cited plenty and was clean, but this dimension has no citation metrics.
    metrics = {
        "citation_hallucination_rate/mean": 0.0,
        "citation_severity_weighted_rate/mean": 0.0,
        "citation_count/mean": 20.0,
        "grade_abs_error_testing/mean": 1.0,
    }

    scores = _dimension_scores(metrics, "testing")

    assert scores == {"abs_error": 1.0}  # no hallucination, severity or citation_count invented
    assert _passes_criteria(scores) is False


def test_a_dimension_is_scored_from_its_own_citations() -> None:
    metrics = {
        "citation_hallucination_rate_testing/mean": 0.0,
        "citation_severity_weighted_rate_testing/mean": 0.05,
        "citation_count_testing/mean": 4.0,
        "citation_hallucination_rate_cicd/mean": 0.9,  # another dimension's numbers stay out
    }

    assert _dimension_scores(metrics, "testing") == {
        "hallucination": 0.0, "severity_weighted": 0.05, "citation_count": 4.0,
    }


# ------------------------------------------------------------- absolute gates


def test_a_clean_well_evidenced_dimension_passes() -> None:
    assert _passes_criteria(GOOD) is True


def test_the_citation_count_floor_applies_to_the_dimension() -> None:
    assert _passes_criteria({**GOOD, "citation_count": MIN_CITATIONS_FOR_PROMOTION - 1}) is False
    assert _passes_criteria({**GOOD, "citation_count": MIN_CITATIONS_FOR_PROMOTION}) is True


def test_a_serious_but_rare_hallucination_blocks_promotion_via_severity() -> None:
    # Hallucination rate is under its gate; the severity-weighted rate is what fails.
    scores = {**GOOD, "hallucination": PROMOTION_HALLUCINATION_THRESHOLD,
              "severity_weighted": PROMOTION_SEVERITY_WEIGHTED_THRESHOLD + 0.01}
    assert _passes_criteria(scores) is False


def test_both_citation_rates_must_be_present() -> None:
    assert _passes_criteria({k: v for k, v in GOOD.items() if k != "severity_weighted"}) is False
    assert _passes_criteria({k: v for k, v in GOOD.items() if k != "hallucination"}) is False


def test_grade_error_against_gold_still_gates_when_a_gold_exists() -> None:
    assert _passes_criteria({**GOOD, "abs_error": PROMOTION_MAE_THRESHOLD + 0.1}) is False
    assert _passes_criteria({k: v for k, v in GOOD.items() if k != "abs_error"}) is True  # no gold: not required


# ------------------------------------------------------ comparison via bootstrap


def test_a_consistent_improvement_promotes() -> None:
    production = version(results(a=3, b=3, c=3, d=3))
    challenger = version(results(a=1, b=1, c=1, d=1))

    verdict, detail = _compare(challenger, production)

    assert verdict == "promote"
    assert detail["mean_abs_error_gain"] == 2.0
    assert detail["ci95"][0] > 0
    assert detail["citation_regressions"] == []


def test_a_gain_the_bootstrap_cannot_tell_from_luck_is_not_promoted() -> None:
    # Mean gain is 0.5 (well above MIN_IMPROVEMENT) but it rests on one big win; the CI includes 0.
    production = version(results(a=4, b=2, c=3, d=3))
    challenger = version(results(a=1, b=3, c=2, d=4))

    verdict, detail = _compare(challenger, production)

    assert detail["mean_abs_error_gain"] == 0.5
    assert detail["ci95"][0] <= 0
    assert verdict == "keep"


def test_a_big_gain_on_two_inputs_is_insufficient_evidence() -> None:
    # The old mean-gain rule promoted on two inputs; a CI from two points is not evidence.
    production = version(results(a=5, b=5))
    challenger = version(results(a=1, b=1))

    verdict, detail = _compare(challenger, production)

    assert verdict == "insufficient"
    assert detail["needed"] == 3


def test_inputs_without_a_gold_error_do_not_count_toward_the_sample() -> None:
    production = version({**results(a=3, b=3), "c": {"hallucination": 0.0}})
    challenger = version({**results(a=1, b=1), "c": {"hallucination": 0.0}})

    verdict, detail = _compare(challenger, production)

    assert verdict == "insufficient"
    assert detail["inputs_with_abs_error_on_both"] == 2


@pytest.mark.parametrize("metric", ["hallucination", "severity_weighted"])
def test_a_citation_regression_blocks_an_otherwise_better_prompt(metric) -> None:
    production = results(a=3, b=3, c=3, d=3)
    challenger = results(a=1, b=1, c=1, d=1)
    challenger["c"][metric] = 0.5  # much worse on one shared input

    verdict, detail = _compare(version(challenger), version(production))

    assert verdict == "keep"
    assert detail["citation_regressions"] == ["c"]


def test_inputs_only_one_side_has_are_ignored() -> None:
    production = version(results(a=3, b=3, c=3, only_prod=0))
    challenger = version(results(a=1, b=1, c=1, only_challenger=9))

    verdict, detail = _compare(challenger, production)

    assert verdict == "promote"
    assert detail["shared_inputs"] == 3


# --------------------------------------------- end to end through _determine_promotion


def test_a_dimension_that_cited_nothing_is_neither_recorded_nor_promoted(monkeypatch) -> None:
    recorded, promoted = [], []
    monkeypatch.setattr(promote, "_record_result", lambda client, name, ver, key, scores, trace_id: recorded.append(name))
    monkeypatch.setattr(promote, "_promote", lambda name, ver, reason: promoted.append(name))
    monkeypatch.setattr(promote, "get_production_prompt", lambda name: None)
    client = SimpleNamespace(
        get_trace=lambda trace_id: SimpleNamespace(info=SimpleNamespace(tags={"model": "m", "judge_model": "j"}))
    )
    judge_result = SimpleNamespace(metrics={
        "citation_hallucination_rate/mean": 0.0,  # overall numbers that used to be borrowed
        "citation_count/mean": 30.0,
        "citation_hallucination_rate_testing/mean": 0.0,
        "citation_severity_weighted_rate_testing/mean": 0.0,
        "citation_count_testing/mean": 5.0,
    })

    promote._determine_promotion(
        judge_result, "tr-1", "team", "s1", {"Evaluate_testing": 3, "Evaluate_cicd": 2}, client,
    )

    assert recorded == ["Evaluate_testing"]  # cicd had no citations of its own: nothing to record
    assert promoted == ["Evaluate_testing"]

"""A judge that failed for a passing reason is retried; one that cannot succeed is not."""

from types import SimpleNamespace

import pandas as pd
import pytest
from evaluation.judges.flagging import (
    HALLUCINATION_COL,
    JUDGE_FAILURE_CLASS_COL,
    evaluate_flags,
)
from evaluation.online import promote
from evaluation.online.promote import (
    JudgeTransientFailure,
    judge_transient_failures,
    run_judge_and_promotion,
)


def result_with(*classes) -> SimpleNamespace:
    return SimpleNamespace(result_df=pd.DataFrame({"trace_id": ["t"] * len(classes), JUDGE_FAILURE_CLASS_COL: list(classes)}))


def test_transient_judge_failures_are_found() -> None:
    assert judge_transient_failures([result_with("timeout")]) == {"timeout"}
    assert judge_transient_failures([result_with("infra_unavailable"), result_with("timeout")]) == {"infra_unavailable", "timeout"}


def test_permanent_judge_failures_are_not_transient() -> None:
    for permanent in ("context_truncated", "schema_validation", "output_length", "unknown"):
        assert judge_transient_failures([result_with(permanent)]) == set()


def test_a_successful_judge_has_no_failure_to_retry() -> None:
    assert judge_transient_failures([result_with(None)]) == set()
    assert judge_transient_failures([SimpleNamespace(result_df=pd.DataFrame({"trace_id": ["t"]}))]) == set()
    assert judge_transient_failures([SimpleNamespace(result_df=None)]) == set()


def test_the_flag_message_says_why_the_judge_produced_nothing() -> None:
    values = {HALLUCINATION_COL: None, JUDGE_FAILURE_CLASS_COL: "context_truncated"}

    (reason,) = evaluate_flags(values, has_gold=False, with_judge=True)

    assert reason.code == "JUDGE_NO_OUTPUT"
    assert reason.message == "citation judge produced no output (context_truncated)"


def test_the_flag_message_is_unchanged_without_a_recorded_class() -> None:
    (reason,) = evaluate_flags({HALLUCINATION_COL: None}, has_gold=False, with_judge=True)
    assert reason.message == "citation judge produced no output"


@pytest.fixture
def judged(monkeypatch):
    state = SimpleNamespace(results=[], promotions=0)
    monkeypatch.setattr(promote.mlflow, "flush_trace_async_logging", lambda: None)
    monkeypatch.setattr(promote, "_failed_dimensions", lambda trace: set())
    monkeypatch.setattr(promote, "run_judge_evaluation", lambda *a, **k: state.results)

    def count(*args, **kwargs):
        state.promotions += 1

    monkeypatch.setattr(promote, "_determine_promotion", count)
    state.client = SimpleNamespace(get_trace=lambda trace_id: None)
    return state


def run(state) -> None:
    run_judge_and_promotion("exp", "tr-1", "team", {}, state.client, "s1")


def test_a_transient_judge_failure_raises_so_the_queue_retries(judged) -> None:
    judged.results = [result_with("timeout")]

    with pytest.raises(JudgeTransientFailure, match="timeout"):
        run(judged)

    assert judged.promotions == 0


def test_a_permanent_judge_failure_does_not_raise(judged) -> None:
    judged.results = [result_with("context_truncated")]

    run(judged)  # flagged for review already; retrying could not help

    assert judged.promotions == 1


def test_a_healthy_judge_run_proceeds_to_promotion(judged) -> None:
    judged.results = [result_with(None)]

    run(judged)

    assert judged.promotions == 1

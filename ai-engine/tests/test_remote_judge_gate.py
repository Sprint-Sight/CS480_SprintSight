"""A judge blocked by the remote gate, or failing, must leave a failure class the queue can read."""

import contextlib
from types import SimpleNamespace

import pandas as pd
import pytest

from evaluation.judges import citation_grounding as grounding
from evaluation.judges import sprint_feedback_judge as feedback_judge
from evaluation.judges.flagging import (
    FEEDBACK_JUDGE_FAILURE_CLASS_COL,
    HALLUCINATION_COL,
    JUDGE_FAILURE_CLASS_COL,
    evaluate_flags,
)
from evaluation.online.promote import judge_failure_classes, judge_transient_failures
from prompts.dimension_criteria import DIMENSIONS
from schemas.failure_class import FailureClass, describe_failure, is_transient

ENV = grounding.ALLOW_REMOTE_JUDGE_ENV


def fixture_trace() -> SimpleNamespace:
    """Just what the scorers read: tags (fixture-tagged, so the hosted judge is chosen) and spans."""
    root = SimpleNamespace(parent_id=None, inputs={}, outputs={"rubric_scores": {DIMENSIONS[0]: {"score": 8, "justification": "Solid work overall."}}})
    return SimpleNamespace(info=SimpleNamespace(trace_id="tr-1", tags={"fixture": "true", "team_id": "t1", "model": "m"}),
                           data=SimpleNamespace(spans=[root]))


def by_name(feedbacks) -> dict:
    return {f.name: f for f in feedbacks}


@pytest.fixture
def no_mlflow_tracing(monkeypatch):
    for module in (grounding, feedback_judge):
        monkeypatch.setattr(module.mlflow, "start_span", lambda **k: contextlib.nullcontext(SimpleNamespace(
            set_inputs=lambda *a: None, set_outputs=lambda *a: None, set_status=lambda *a: None)))
        monkeypatch.setattr(module.mlflow, "update_current_trace", lambda **k: None)


def test_the_new_class_is_permanent_and_described() -> None:
    assert FailureClass("remote_judge_disabled") is FailureClass.REMOTE_JUDGE_DISABLED
    assert is_transient(FailureClass.REMOTE_JUDGE_DISABLED) is False
    assert "disabled" in describe_failure(FailureClass.REMOTE_JUDGE_DISABLED)


def test_citation_judge_gate_reports_error_and_failure_class(monkeypatch) -> None:
    monkeypatch.delenv(ENV, raising=False)

    feedbacks = by_name(grounding.llm_judge_citation_grounding(fixture_trace()))

    assert feedbacks["citation_hallucination_rate"].error is not None
    assert feedbacks["citation_judge_failure_class"].value == "remote_judge_disabled"


def test_feedback_judge_gate_reports_error_and_failure_class(monkeypatch) -> None:
    monkeypatch.delenv(ENV, raising=False)

    feedbacks = by_name(feedback_judge.llm_judge_sprint_feedback_consistency(fixture_trace()))

    assert feedbacks["narrative_contradiction_count"].error is not None
    assert feedbacks["judge_failure_class"].value == "remote_judge_disabled"


def test_with_the_opt_in_the_citation_judge_runs_on_the_hosted_provider(monkeypatch, no_mlflow_tracing) -> None:
    monkeypatch.setenv(ENV, "1")
    seen = {}

    async def fake_judge(bundle, rubric, judge_model, judge_provider="ollama"):
        seen.update(model=judge_model, provider=judge_provider)
        return {"coverage": 1.0, "hallucination_rate": 0.0, "citation_count": 0}, []

    monkeypatch.setattr(grounding, "_bundle_of", lambda trace, team: object())
    monkeypatch.setattr(grounding, "read_candidate", lambda trace, bundle: (object(), 0))
    monkeypatch.setattr(grounding, "judge_assessment_detailed", fake_judge)

    feedbacks = by_name(grounding.llm_judge_citation_grounding(fixture_trace()))

    assert seen == {"model": grounding.FIXTURE_JUDGE_MODEL, "provider": "openai"}
    assert "citation_judge_failure_class" not in feedbacks
    assert feedbacks["citation_hallucination_rate"].error is None


def test_with_the_opt_in_a_judge_failure_is_still_classified(monkeypatch, no_mlflow_tracing) -> None:
    monkeypatch.setenv(ENV, "1")

    async def timing_out(*args, **kwargs):
        raise TimeoutError("no answer")

    monkeypatch.setattr(grounding, "_bundle_of", lambda trace, team: object())
    monkeypatch.setattr(grounding, "read_candidate", lambda trace, bundle: (object(), 0))
    monkeypatch.setattr(grounding, "judge_assessment_detailed", timing_out)

    feedbacks = by_name(grounding.llm_judge_citation_grounding(fixture_trace()))

    assert feedbacks["citation_judge_failure_class"].value == "timeout"


def _fake_hosted_client(seen: dict):
    class Completions:
        async def create(self, **kwargs):
            seen.update(kwargs)
            model = kwargs["response_model"]  # the real id-checking model, as instructor would validate it
            ids = [f"D-{DIMENSIONS[0]}", "S1"]
            return model(verdicts=[{"item_id": i, "label": "consistent", "reasoning": "agrees with the scores"} for i in ids])

    return lambda provider="ollama": SimpleNamespace(chat=SimpleNamespace(completions=Completions()))


def test_the_openai_feedback_judge_does_not_need_a_num_ctx_entry(monkeypatch) -> None:
    seen: dict = {}
    monkeypatch.setattr(feedback_judge, "create_llm_client", _fake_hosted_client(seen))
    monkeypatch.setattr(feedback_judge, "MODEL_NUM_CTX", {})  # gpt-4o-mini is deliberately absent
    assessment = {"rubric_scores": {DIMENSIONS[0]: {"score": 8, "justification": "Solid work overall."}}, "strengths": ["Good tests"]}

    result = _run(feedback_judge.judge_sprint_feedback(assessment, "gpt-4o-mini", "openai"))

    assert seen["extra_body"] == {}
    assert result["items"] == 2


def test_the_ollama_feedback_judge_still_requires_num_ctx(monkeypatch) -> None:
    monkeypatch.setattr(feedback_judge, "MODEL_NUM_CTX", {})
    with pytest.raises(ValueError, match="MODEL_NUM_CTX"):
        _run(feedback_judge.judge_sprint_feedback({"rubric_scores": {}}, "unknown-model", "ollama"))


def test_a_failing_feedback_judge_records_its_class(monkeypatch, no_mlflow_tracing) -> None:
    monkeypatch.setenv(ENV, "1")

    async def timing_out(*args, **kwargs):
        raise TimeoutError("no answer")

    monkeypatch.setattr(feedback_judge, "judge_sprint_feedback", timing_out)

    feedbacks = by_name(feedback_judge.llm_judge_sprint_feedback_consistency(fixture_trace()))

    assert feedbacks["narrative_contradiction_count"].error is not None
    assert feedbacks["judge_failure_class"].value == "timeout"


def _result(**columns) -> SimpleNamespace:
    return SimpleNamespace(result_df=pd.DataFrame({"trace_id": ["t"], **{k: [v] for k, v in columns.items()}}))


def test_promote_reads_both_failure_columns() -> None:
    assert judge_transient_failures([_result(**{FEEDBACK_JUDGE_FAILURE_CLASS_COL: "timeout"})]) == {"timeout"}
    assert judge_transient_failures([_result(**{JUDGE_FAILURE_CLASS_COL: "infra_unavailable"})]) == {"infra_unavailable"}
    blocked = _result(**{JUDGE_FAILURE_CLASS_COL: "remote_judge_disabled", FEEDBACK_JUDGE_FAILURE_CLASS_COL: "remote_judge_disabled"})
    assert judge_transient_failures([blocked]) == set()          # config, not worth retrying...
    assert judge_failure_classes([blocked]) == {"remote_judge_disabled"}  # ...but it is no longer invisible


def test_the_flag_message_names_the_disabled_judge() -> None:
    (reason,) = evaluate_flags({HALLUCINATION_COL: None, JUDGE_FAILURE_CLASS_COL: "remote_judge_disabled"}, has_gold=False, with_judge=True)
    assert reason.message == "citation judge produced no output (remote_judge_disabled)"


def _run(coro):
    import asyncio

    return asyncio.run(coro)

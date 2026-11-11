"""Retry exhaustion inside evaluate_sprint: classified, flagged, never silently scored."""

import asyncio
from types import SimpleNamespace
from typing import Any

import httpx
import mlflow
import openai
import pytest
from instructor.core.exceptions import InstructorRetryException
from mlflow import MlflowClient
from pydantic import ValidationError

from llmops import mlflow_config
from prompts.dimension_criteria import DIMENSIONS
from schemas.all_dimensions_failed_error import AllDimensionsFailedError
from schemas.artifact_bundle import ArtifactBundle
from schemas.rubrics_dimension_score import ModelOutput, RubricDimensionScore
from services import evaluator

# Typed Any, see tests/test_failures.py.
REQUEST: Any = httpx.Request("POST", "http://ollama:11434/v1/chat/completions")
LONG_DETAIL = "x" * 900  # the old code cut error text at 300 characters


def _bundle() -> ArtifactBundle:
    return ArtifactBundle(
        team_id="team-a", sprint_id="s1", commits=[], jira_tickets=[], peer_evaluations=[],
        collaboration_metrics={}, artifact_metrics={}, project_context_documents=[],
        repo_snapshot=None, instructor_expectations="None.",
    )


def _schema_failure() -> InstructorRetryException:
    with pytest.raises(ValidationError) as raised:
        ModelOutput.model_validate({})
    try:
        try:
            raise raised.value
        except ValidationError as inner:
            raise InstructorRetryException("retries exhausted", n_attempts=4, total_usage=None) from inner
    except InstructorRetryException as exc:
        return exc


@pytest.fixture
def harness(tmp_path, monkeypatch):
    uri = f"sqlite:///{tmp_path}/mlflow.db"
    previous = mlflow.get_tracking_uri()
    mlflow.set_tracking_uri(uri)
    monkeypatch.setattr(mlflow_config, "_configured", True)
    monkeypatch.setattr(mlflow_config, "_experiment_ids", {})
    client = MlflowClient(tracking_uri=uri)
    experiment_id = client.create_experiment("exp", artifact_location=str(tmp_path / "art"))

    state = SimpleNamespace(failures={}, queued=[], saved=[], client=client, experiment_id=experiment_id, hang=False)

    async def fake_dimension(bundle, dimension, model, prompt, num_ctx=None):
        if state.hang:
            await asyncio.sleep(60)  # stands in for a long Ollama generation
        if dimension in state.failures:
            raise state.failures[dimension]
        return RubricDimensionScore(
            dimension=dimension, score=8, justification="A solid justification.", evidence_citations=[]
        )

    async def fake_feedback(*args, **kwargs):
        return SimpleNamespace(strengths=["s"], weaknesses=["w"], recommendations=["r"])

    async def no_gpu(*args, **kwargs):
        return None

    monkeypatch.setattr(evaluator, "evaluate_dimension", fake_dimension)
    monkeypatch.setattr(evaluator, "generate_sprint_feedback", fake_feedback)
    monkeypatch.setattr(evaluator, "_log_gpu_offload", no_gpu)
    monkeypatch.setattr(evaluator, "register_all_dimension_prompts", lambda *a, **k: {f"Evaluate_{d}": 1 for d in DIMENSIONS})
    monkeypatch.setattr(evaluator, "register_sprint_feedback_prompt", lambda *a, **k: SimpleNamespace(version=1))
    monkeypatch.setattr(evaluator, "add_to_review_queue", lambda queue, ids: state.queued.append((queue, ids)))
    monkeypatch.setattr(evaluator, "save_run_results", lambda **kwargs: state.saved.append(kwargs))
    yield state
    mlflow.flush_trace_async_logging()
    mlflow.set_tracking_uri(previous)


def _evaluate(state, trace_ids=None):
    return asyncio.run(
        evaluator.evaluate_sprint(_bundle(), "sprintsight-qwen", "exp", state.client, trace_ids)
    )


def test_exhausted_retries_are_classified_and_flagged(harness) -> None:
    harness.failures = {
        "testing": openai.APITimeoutError(request=REQUEST),
        "cicd": _schema_failure(),
    }

    trace_ids: list[str] = []
    assessment, _ = _evaluate(harness, trace_ids)

    assert set(assessment.failed_dimensions) == {"testing", "cicd"}
    assert assessment.evaluation_failed is True
    assert assessment.rubric_scores.testing.failure_class == "timeout"
    assert assessment.rubric_scores.cicd.failure_class == "schema_validation"
    assert assessment.trace_id == trace_ids[0]


def test_the_report_text_is_user_safe_and_the_detail_is_not_truncated(harness) -> None:
    harness.failures = {"testing": RuntimeError(LONG_DETAIL)}

    assessment, _ = _evaluate(harness)

    testing = assessment.rubric_scores.testing
    assert LONG_DETAIL in testing.error_detail  # kept in full for operators
    assert LONG_DETAIL not in testing.justification  # never shown to students
    assert "manual review" in testing.justification
    assert "manual review" in assessment.executive_summary
    assert "1 of 6" in assessment.executive_summary  # says how many FAILED, not how many passed


def test_the_placeholder_score_does_not_distort_the_overall_score(harness) -> None:
    harness.failures = {"testing": openai.APITimeoutError(request=REQUEST)}

    assessment, _ = _evaluate(harness)

    assert assessment.rubric_scores.testing.score == 1  # placeholder, flagged evaluation_failed
    assert assessment.overall_score == 8.0  # mean of the five real scores, not (5*8+1)/6


def test_a_cancelled_assessment_is_failed_in_mlflow_for_both_its_run_and_its_trace(harness) -> None:
    # The backend hung up (see api/disconnect.py). The run was already marked FAILED, but the
    # trace stayed OK because MLflow records an error only for ordinary exceptions.
    harness.hang = True

    async def scenario() -> None:
        task = asyncio.ensure_future(
            evaluator.evaluate_sprint(_bundle(), "sprintsight-qwen", "exp", harness.client, [])
        )
        await asyncio.sleep(2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    mlflow.flush_trace_async_logging()

    (run,) = harness.client.search_runs([harness.experiment_id])
    (trace,) = harness.client.search_traces(locations=[harness.experiment_id])
    assert run.info.status == "FAILED"
    assert trace.info.state.name == "ERROR"
    assert trace.info.tags["cancelled"] == "client_disconnected"
    assert trace.info.trace_metadata["mlflow.sourceRun"] == run.info.run_id
    assert harness.queued == [] and harness.saved == []  # nothing was reported for the abandoned work


def test_the_failure_class_is_visible_as_mlflow_tags(harness) -> None:
    harness.failures = {"testing": openai.APITimeoutError(request=REQUEST), "cicd": _schema_failure()}

    _evaluate(harness)

    tags = harness.client.search_runs([harness.experiment_id])[0].data.tags
    assert tags["failure_class.testing"] == "timeout"
    assert tags["failure_class.cicd"] == "schema_validation"
    assert set(tags["failed_dimensions"].split(",")) == {"testing", "cicd"}


def test_a_partial_failure_is_queued_for_review_once(harness) -> None:
    harness.failures = {"testing": openai.APITimeoutError(request=REQUEST)}

    assessment, _ = _evaluate(harness)

    assert harness.queued == [("review_queue_team-a_s1", [assessment.trace_id])]
    assert harness.saved[0]["failure_classes"] == {"testing": "timeout"}
    assert harness.saved[0]["failed_dimensions"]["testing"].startswith("timeout: ")


def test_a_clean_run_is_not_queued_and_logs_its_metrics_on_its_own_run(harness) -> None:
    assessment, _ = _evaluate(harness)

    assert assessment.evaluation_failed is False
    assert harness.queued == []
    runs = harness.client.search_runs([harness.experiment_id])
    assert len(runs) == 1
    assert runs[0].info.status == "FINISHED"
    assert runs[0].data.metrics["overall_score"] == 8.0
    assert runs[0].data.metrics["failed_dimensions_count"] == 0
    assert mlflow.active_run() is None


def test_every_dimension_failing_still_queues_the_trace_then_raises(harness) -> None:
    harness.failures = {dim: httpx.ConnectError("refused") for dim in DIMENSIONS}

    with pytest.raises(AllDimensionsFailedError) as raised:
        _evaluate(harness)

    assert len(harness.queued) == 1
    assert set(raised.value.failed_dimensions) == set(DIMENSIONS)
    assert all(text.startswith("infra_unavailable: ") for text in raised.value.failed_dimensions.values())

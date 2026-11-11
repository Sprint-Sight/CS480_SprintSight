"""POST /assess/sprint/data: returns the trace id and hands judging to the durable queue."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import assessment as route
from evaluation.online.job_queue import JudgeJobQueue
from schemas.modelname import ModelName
from schemas.rubrics_dimension_score import RubricDimensionScore
from schemas.rubrics_score import RubricsScore
from schemas.sprint_assessment import SprintAssessment

BODY = {
    "sprint_context": {
        "course_id": "c1",
        "project_id": "team-a",
        "sprint_id": "s1",
        "captured_at": "2026-01-01T00:00:00Z",
    }
}
URL = f"/assess/sprint/data?modelname={next(iter(ModelName)).value}"
VERSIONS = {"Evaluate_testing": 4}


def _assessment(*, failed: tuple[str, ...] = ()) -> SprintAssessment:
    dims = {
        name: RubricDimensionScore(
            dimension=name, score=1 if name in failed else 8, justification="A justification.",
            evidence_citations=[], evaluation_failed=name in failed,
            failure_class="timeout" if name in failed else None,
        )
        for name in ("code_quality", "testing", "documentation", "requirements", "collaboration", "cicd")
    }
    return SprintAssessment(
        sprint_id="s1", team_id="team-a", overall_score=8, rubric_scores=RubricsScore(**dims),
        executive_summary="Summary.", key_recommendations=["Add tests."],
    )


@pytest.fixture
def queue(tmp_path, monkeypatch) -> JudgeJobQueue:
    judge_queue = JudgeJobQueue(tmp_path / "jobs.sqlite3")
    monkeypatch.setattr(route, "get_judge_queue", lambda: judge_queue)
    return judge_queue


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(route.router)
    return TestClient(app)


def _fake_evaluate(assessment: SprintAssessment, trace_id: str = "tr-abc"):
    async def evaluate(bundle, model, experiment, mlflow_client, trace_ids, *args, **kwargs):
        trace_ids.append(trace_id)
        return assessment, VERSIONS

    return evaluate


def test_response_carries_the_trace_id_and_failure_flags(client, queue, monkeypatch) -> None:
    monkeypatch.setattr(route, "evaluate_sprint", _fake_evaluate(_assessment(failed=("testing",))))

    response = client.post(URL, json=BODY)

    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"] == "tr-abc"
    assert body["evaluation_failed"] is True
    assert body["failed_dimensions"] == ["testing"]
    assert body["rubric_scores"]["testing"]["failure_class"] == "timeout"


def test_a_clean_assessment_is_not_flagged(client, queue, monkeypatch) -> None:
    monkeypatch.setattr(route, "evaluate_sprint", _fake_evaluate(_assessment()))

    body = client.post(URL, json=BODY).json()

    assert body["evaluation_failed"] is False
    assert body["failed_dimensions"] == []


def test_judging_is_queued_durably_after_grading(client, queue, monkeypatch) -> None:
    monkeypatch.setattr(route, "evaluate_sprint", _fake_evaluate(_assessment()))

    client.post(URL, json=BODY)

    job = queue.claim_next()
    assert job is not None
    assert (job.trace_id, job.team_id, job.sprint_id) == ("tr-abc", "team-a", "s1")
    assert job.experiment_name == "SprintSight Evaluations"
    assert job.prompt_versions == VERSIONS


def test_a_failed_assessment_queues_nothing(client, queue, monkeypatch) -> None:
    async def explode(*args, **kwargs):
        raise RuntimeError("model gone")

    monkeypatch.setattr(route, "evaluate_sprint", explode)

    response = client.post(URL, json=BODY)

    assert response.status_code == 500
    assert queue.claim_next() is None


def test_an_unavailable_queue_does_not_fail_the_assessment(client, monkeypatch) -> None:
    def broken_queue():
        raise OSError("disk full")

    monkeypatch.setattr(route, "get_judge_queue", broken_queue)
    monkeypatch.setattr(route, "evaluate_sprint", _fake_evaluate(_assessment()))

    response = client.post(URL, json=BODY)

    assert response.status_code == 200
    assert response.json()["trace_id"] == "tr-abc"

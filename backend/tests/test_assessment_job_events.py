"""The job event stream always carries the terminal event (M1) and "started" only once."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints import assessment as assessment_endpoints
from app.main import app
from app.repositories.in_memory import InMemoryAssessmentJobRepository, job_repo
from app.repositories.interfaces import ProjectRecord
from app.schemas.assessment import AssessRequest
from app.services.assessmentService.service import run_assessment_job

client = TestClient(app)


def faculty_headers() -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login", json={"email": "faculty@sprintsight.edu", "password": "password123"}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def request_for(course_id: str = "cs480") -> AssessRequest:
    return AssessRequest(course_id=course_id, project_id="proj-a", sprint_id="sp1")


class WorkerFinishesAfterTheFirstRead:
    """A job store where the worker finishes right after the stream's first read.

    That is the window the old stream lost the final event in: whichever of the status and the
    events the stream read first was already stale by the time it read the other. The endpoint's
    own access check reads the job once before streaming starts (read 1), so the stream's first
    read is read 2."""

    def __init__(self, real: InMemoryAssessmentJobRepository, job_id: str) -> None:
        self.real, self.job_id, self.reads = real, job_id, 0

    def _worker_finishes_after_first_read(self) -> None:
        self.reads += 1
        if self.reads == 2:
            self.real.finish_job(
                self.job_id,
                "failed",
                {"status": "failed", "message": "The assessment failed.", "error_message": "boom"},
                status="failed",
                error_message="boom",
            )

    def get_job(self, job_id):
        record = self.real.get_job(job_id)
        snapshot = record.model_copy() if record else None  # the in-memory record is mutated in place
        self._worker_finishes_after_first_read()
        return snapshot

    def list_events(self, job_id):
        events = self.real.list_events(job_id)
        self._worker_finishes_after_first_read()
        return events


@pytest.fixture
def instructor_course(override_user_repository):
    override_user_repository.assign_instructor("cs480", "u-faculty-1")
    return "cs480"


def test_the_stream_still_delivers_a_failure_the_worker_writes_right_after_its_first_read(
    instructor_course, monkeypatch
) -> None:
    real = InMemoryAssessmentJobRepository()
    job = real.create_job(request_for(instructor_course))
    monkeypatch.setattr(
        assessment_endpoints, "job_repo", WorkerFinishesAfterTheFirstRead(real, job.job_id)
    )

    response = client.get(
        f"/api/v1/assessments/jobs/{job.job_id}/events", headers=faculty_headers()
    )

    assert response.status_code == 200
    assert "event: failed" in response.text
    assert '"error_message": "boom"' in response.text


def test_finish_job_writes_the_event_before_the_status() -> None:
    order: list[str] = []

    class Spy(InMemoryAssessmentJobRepository):
        def append_event(self, job_id, event, data):
            order.append(f"event:{event}")
            super().append_event(job_id, event, data)

        def update_job(self, job_id, **fields):
            order.append(f"status:{fields.get('status')}")
            return super().update_job(job_id, **fields)

    repository = Spy()
    job = repository.create_job(request_for())
    order.clear()

    finished = repository.finish_job(
        job.job_id, "completed", {"status": "completed"}, status="completed", report_id="rpt-1"
    )

    assert order == ["event:completed", "status:completed"]
    assert finished is not None
    assert (finished.status, finished.progress, finished.report_id) == ("completed", 100, "rpt-1")
    assert repository.list_events(job.job_id)[-1].event == "completed"


def test_a_failing_worker_leaves_a_failed_event_and_failed_status(monkeypatch) -> None:
    repository = InMemoryAssessmentJobRepository()
    monkeypatch.setattr(job_repo, "_target", repository)
    job = repository.create_job(request_for())

    # No local repository: the worker fails before it reaches the AI engine.
    run_assessment_job(
        job.job_id, request_for(), SimpleNamespace(local_repo_path=None), None, None
    )

    state = repository.get_job(job.job_id)
    assert state is not None
    assert (state.status, state.current_stage, state.progress) == ("failed", "failed", 100)
    last = repository.list_events(job.job_id)[-1]
    assert last.event == "failed"
    assert last.data["error_message"] == state.error_message


def test_a_new_job_announces_started_exactly_once(instructor_course, monkeypatch) -> None:
    monkeypatch.setattr(assessment_endpoints._executor, "submit", lambda *a, **k: None)
    override = app.dependency_overrides
    from app.dependencies.auth import get_project_repository

    override[get_project_repository]().create_project(
        ProjectRecord(
            id="proj-a",
            project_name="P",
            team_name="T",
            description=None,
            course_id=instructor_course,
            course_code="CS480",
            github_repo_url=None,
            local_repo_path="some-repo",
            created_by="u-faculty-1",
            created_at=datetime.now(UTC),
        ),
        [],
    )

    response = client.post(
        "/api/v1/assessments/assess",
        json={"course_id": instructor_course, "project_id": "proj-a", "sprint_id": "sp1"},
        headers=faculty_headers(),
    )

    assert response.status_code == 202, response.text
    events = [e.event for e in job_repo.list_events(response.json()["job_id"])]
    assert events.count("started") == 1

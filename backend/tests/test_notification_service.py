"""Tests for the notification service and the LLM report-completed instructor email flow.

These tests verify that when an LLM-generated assessment report finishes, the
assigned active instructors are notified by email, and that edge cases (inactive
or unassigned instructors, no instructors, SMTP delivery failure, missing SMTP
configuration) are handled without crashing the assessment job.
"""

from datetime import UTC, datetime
from pathlib import Path
from smtplib import SMTPException
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.repositories.in_memory import (
    InMemoryAssessmentRepository,
    InMemoryManualTextRepository,
    InMemoryMetricsRepository,
    InMemoryProjectRepository,
    InMemoryUserRepository,
    job_repo,
)
from app.repositories.interfaces import ProjectRecord, Role, UserRecord
from app.schemas.assessment import (
    AssessmentReport,
    AssessRequest,
    TeamScore,
)
from app.services.assessmentService.service import (
    _notify_instructors_report_completed,
    run_assessment_job,
)
from app.services.notificationService.service import (
    NotificationConfigurationError,
    NotificationDeliveryError,
    SMTPNotificationService,
)


class FakeNotificationService:
    is_configured = True

    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str]] = []

    def send_email(self, recipient: str, subject: str, body: str) -> None:
        self.messages.append((recipient, subject, body))


class FailingNotificationService:
    is_configured = True

    def __init__(self, fail_for: set[str] | None = None) -> None:
        self.messages: list[tuple[str, str, str]] = []
        self.fail_for = fail_for or set()

    def send_email(self, recipient: str, subject: str, body: str) -> None:
        if recipient in self.fail_for:
            raise SMTPException("smtp delivery failed")
        self.messages.append((recipient, subject, body))


def _instructor_report(course_id: str) -> AssessmentReport:
    return AssessmentReport(
        report_id="rpt-notify-1",
        model_name="test-model",
        mode="test",
        course_id=course_id,
        project_id="proj-notify",
        sprint_id="sp1",
        generated_at=datetime.now(UTC),
        rubric_weights={},
        team_score=TeamScore(score=85, rationale="Strong sprint delivery."),
        individual_scores=[],
        recommendations=[],
    )


def _create_user(
    repo: InMemoryUserRepository,
    email: str,
    full_name: str,
    role: Role,
    active: bool = True,
) -> UserRecord:
    user = UserRecord(
        id=f"u-{email.split('@')[0]}",
        email=email,
        full_name=full_name,
        role=role,
        hashed_password="x",
    )
    repo.create_user(user)
    stored = repo.get_by_email(email)
    assert stored is not None
    if not active:
        repo.update_user(stored.id, email, full_name, role, False)
    return stored


# ---------------------------------------------------------------------------
# SMTPNotificationService configuration / delivery behavior
# ---------------------------------------------------------------------------


def test_smtp_service_raises_when_not_configured() -> None:
    settings = get_settings().model_copy(
        update={
            "email_smtp_host": "",
            "email_smtp_username": "",
            "email_smtp_password": "",
            "email_from_address": "",
        }
    )
    service = SMTPNotificationService(settings)
    assert service.is_configured is False
    with pytest.raises(NotificationConfigurationError):
        service.send_email("instructor@example.test", "Report completed", "body")


def test_smtp_delivery_error_raises_notification_delivery_error(monkeypatch) -> None:
    class FakeSMTP:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def login(self, *args, **kwargs):
            raise OSError("connection refused")

        def send_message(self, message):
            raise OSError("connection refused")

    monkeypatch.setattr(
        "app.services.notificationService.service.smtplib.SMTP",
        lambda *args, **kwargs: FakeSMTP(),
    )
    settings = get_settings().model_copy(
        update={
            "email_smtp_host": "smtp.example.test",
            "email_smtp_username": "user",
            "email_smtp_password": "pass",
            "email_from_address": "notify@example.test",
            "email_smtp_use_tls": False,
            "email_smtp_use_ssl": False,
        }
    )
    service = SMTPNotificationService(settings)
    assert service.is_configured is True
    with pytest.raises(NotificationDeliveryError):
        service.send_email("instructor@example.test", "Report completed", "body")


# ---------------------------------------------------------------------------
# _notify_instructors_report_completed behavior
# ---------------------------------------------------------------------------


def test_assigned_active_instructor_reports_completed_email() -> None:
    """Baseline: the active instructor assigned to the course is notified."""
    user_repository = InMemoryUserRepository()
    project_repository = InMemoryProjectRepository()
    course = project_repository.create_course(
        "CS480", "SprintSight", "001", 2026, "Fall", "u-faculty-1",
    )
    notifications = FakeNotificationService()

    _notify_instructors_report_completed(
        _instructor_report(course.id),
        SimpleNamespace(project_name="Notify Project"),
        user_repository,
        project_repository,
        notifications,
        "job-notify-baseline",
    )

    assert [m[0] for m in notifications.messages] == ["faculty@sprintsight.edu"]
    assert "rpt-notify-1" in notifications.messages[0][2]
    assert "The LLM assessment report has been completed." in notifications.messages[0][2]


def test_inactive_instructor_is_not_notified() -> None:
    user_repository = InMemoryUserRepository()
    project_repository = InMemoryProjectRepository()
    course = project_repository.create_course(
        "CS480", "SprintSight", "001", 2026, "Fall", "u-faculty-1",
    )
    _create_user(
        user_repository,
        "inactive.instr@sprintsight.edu",
        "Inactive Instructor",
        Role.INSTRUCTOR,
        active=False,
    )
    project_repository.assign_instructor(course.id, "u-inactive-instr")
    notifications = FakeNotificationService()

    _notify_instructors_report_completed(
        _instructor_report(course.id),
        SimpleNamespace(project_name="Notify Project"),
        user_repository,
        project_repository,
        notifications,
        "job-notify-inactive",
    )

    assert [m[0] for m in notifications.messages] == ["faculty@sprintsight.edu"]


def test_unassigned_instructor_is_not_notified() -> None:
    user_repository = InMemoryUserRepository()
    project_repository = InMemoryProjectRepository()
    course = project_repository.create_course(
        "CS480", "SprintSight", "001", 2026, "Fall", "u-faculty-1",
    )
    _create_user(
        user_repository,
        "unassigned.instr@sprintsight.edu",
        "Unassigned Instructor",
        Role.INSTRUCTOR,
        active=True,
    )
    notifications = FakeNotificationService()

    _notify_instructors_report_completed(
        _instructor_report(course.id),
        SimpleNamespace(project_name="Notify Project"),
        user_repository,
        project_repository,
        notifications,
        "job-notify-unassigned",
    )

    assert [m[0] for m in notifications.messages] == ["faculty@sprintsight.edu"]


def test_all_assigned_active_instructors_are_notified() -> None:
    user_repository = InMemoryUserRepository()
    project_repository = InMemoryProjectRepository()
    course = project_repository.create_course(
        "CS480", "SprintSight", "001", 2026, "Fall", "u-faculty-1",
    )
    second = _create_user(
        user_repository,
        "second.instr@sprintsight.edu",
        "Second Instructor",
        Role.INSTRUCTOR,
        active=True,
    )
    project_repository.assign_instructor(course.id, second.id)
    notifications = FakeNotificationService()

    _notify_instructors_report_completed(
        _instructor_report(course.id),
        SimpleNamespace(project_name="Notify Project"),
        user_repository,
        project_repository,
        notifications,
        "job-notify-multiple",
    )

    recipients = [m[0] for m in notifications.messages]
    assert "faculty@sprintsight.edu" in recipients
    assert "second.instr@sprintsight.edu" in recipients
    assert len(recipients) == 2


def test_no_instructors_does_not_crash_and_sends_no_email() -> None:
    user_repository = InMemoryUserRepository()
    project_repository = InMemoryProjectRepository()
    course = project_repository.create_course(
        "CS480", "SprintSight", "001", 2026, "Fall", "u-faculty-1",
    )
    # The creator is auto-assigned; unassign them so there are zero instructors.
    project_repository.unassign_instructor(course.id, "u-faculty-1")
    notifications = FakeNotificationService()

    # Should not raise.
    _notify_instructors_report_completed(
        _instructor_report(course.id),
        SimpleNamespace(project_name="Notify Project"),
        user_repository,
        project_repository,
        notifications,
        "job-notify-none",
    )

    assert notifications.messages == []


def test_smtp_delivery_failure_is_handled_gracefully_and_continues() -> None:
    user_repository = InMemoryUserRepository()
    project_repository = InMemoryProjectRepository()
    course = project_repository.create_course(
        "CS480", "SprintSight", "001", 2026, "Fall", "u-faculty-1",
    )
    second = _create_user(
        user_repository,
        "failing.instr@sprintsight.edu",
        "Failing Instructor",
        Role.INSTRUCTOR,
        active=True,
    )
    project_repository.assign_instructor(course.id, second.id)
    notifications = FailingNotificationService(fail_for={"failing.instr@sprintsight.edu"})

    _notify_instructors_report_completed(
        _instructor_report(course.id),
        SimpleNamespace(project_name="Notify Project"),
        user_repository,
        project_repository,
        notifications,
        "job-notify-failing",
    )

    # The working instructor still received the email.
    recipients = [m[0] for m in notifications.messages]
    assert recipients == ["faculty@sprintsight.edu"]

    # The failure was recorded as a job event rather than crashing the job.
    events = job_repo.list_events("job-notify-failing")
    failure_events = [e for e in events if e.event == "notification_failed"]
    assert failure_events
    assert "could not be delivered" in failure_events[0].data["message"].lower()


# ---------------------------------------------------------------------------
# End-to-end: run_assessment_job saves the LLM report and notifies instructor
# ---------------------------------------------------------------------------


def test_run_assessment_job_saves_report_and_notifies_instructor(monkeypatch) -> None:
    """The full background job: LLM result -> report persisted -> instructor emailed."""
    user_repository = InMemoryUserRepository()
    project_repository = InMemoryProjectRepository()
    assessment_repository = InMemoryAssessmentRepository()
    manual_text_repository = InMemoryManualTextRepository()
    metrics_repository = InMemoryMetricsRepository()
    notifications = FakeNotificationService()

    course = project_repository.create_course(
        "CS480", "SprintSight", "001", 2026, "Fall", "u-faculty-1",
    )
    project = project_repository.create_project(
        ProjectRecord(
            id="proj-notify-e2e",
            project_name="E2E Notify Project",
            team_name="Team",
            description=None,
            course_id=course.id,
            course_code="CS480",
            github_repo_url=None,
            local_repo_path="cs-480-proj",
            created_by="u-faculty-1",
            created_at=datetime.now(UTC),
        ),
        [],
    )

    ai_result = {
        "overall_score": 8.5,
        "executive_summary": "Strong sprint delivery.",
        "key_recommendations": ["Add unit tests."],
        "member_contributions": [],
    }
    monkeypatch.setattr(
        "app.services.assessmentService.service.send_assessment_to_ai_engine",
        lambda *args, **kwargs: ai_result,
    )
    monkeypatch.setattr(
        "app.services.assessmentService.service.resolve_local_repository_path",
        lambda path: Path("/tmp/fake-repo"),
    )
    monkeypatch.setattr(
        "app.services.assessmentService.service.ingest_github_metrics",
        lambda *args, **kwargs: SimpleNamespace(
            course_id=course.id,
            project_id="proj-notify-e2e",
            sprint_id="sp1",
            captured_at=datetime.now(UTC),
            commit_frequency=1.0,
            code_churn=0,
            pr_turnaround_hours=None,
            assigned_story_points=None,
            completion_percent=None,
            commits=[],
            local_repo_path=None,
            head_sha=None,
        ),
    )

    job_record = job_repo.create_job(
        AssessRequest(
            course_id=course.id,
            project_id="proj-notify-e2e",
            sprint_id="sp1",
            model_name="mock-model",
        )
    )
    job_id = job_record.job_id

    run_assessment_job(
        job_id=job_id,
        payload=AssessRequest(
            course_id=course.id,
            project_id="proj-notify-e2e",
            sprint_id="sp1",
            model_name="mock-model",
        ),
        project=project,
        metrics_repository=metrics_repository,
        manual_text_repository=manual_text_repository,
        assessment_repository=assessment_repository,
        user_repository=user_repository,
        project_repository=project_repository,
        notification_service=notifications,
    )

    job = job_repo.get_job(job_id)
    assert job is not None
    assert job.status == "completed"
    assert job.report_id is not None

    saved = assessment_repository.get_report(job.report_id)
    assert saved is not None
    assert saved.course_id == course.id
    assert saved.team_score.score == 85.0

    # The assigned active instructor (faculty@sprintsight.edu) was emailed.
    recipients = [m[0] for m in notifications.messages]
    assert recipients == ["faculty@sprintsight.edu"]
    assert job.report_id in notifications.messages[0][2]
    assert "The LLM assessment report has been completed." in notifications.messages[0][2]

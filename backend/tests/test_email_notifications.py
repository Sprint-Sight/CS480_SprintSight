import re
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.in_memory import InMemoryProjectRepository, InMemoryUserRepository
from app.schemas.assessment import AssessmentReport, TeamScore
from app.services.assessmentService.service import _notify_instructors_report_completed

client = TestClient(app)


class FakeNotificationService:
    is_configured = True

    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str]] = []

    def send_email(self, recipient: str, subject: str, body: str) -> None:
        self.messages.append((recipient, subject, body))


def _token_from_email(body: str) -> str:
    match = re.search(r"^Token \(expires in \d+ minutes\):\n([^\n]+)", body, re.MULTILINE)
    assert match
    return match.group(1)


def test_first_time_password_setup_uses_email_token(monkeypatch) -> None:
    notifications = FakeNotificationService()
    monkeypatch.setattr(app.state, "notification_service", notifications)
    admin_login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@sprintsight.edu", "password": "password123"},
    )
    response = client.post(
        "/api/v1/users",
        json={
            "email": "email.setup@sprintsight.edu",
            "full_name": "Email Setup",
            "role": "student",
            "password": "temporary123",
        },
        headers={"Authorization": f"Bearer {admin_login.json()['access_token']}"},
    )
    assert response.status_code == 201
    assert len(notifications.messages) == 1
    recipient, subject, body = notifications.messages[0]
    assert recipient == "email.setup@sprintsight.edu"
    assert subject == "Set your SprintSight password"

    complete = client.post(
        "/api/v1/auth/first-time-password/complete",
        json={"token": _token_from_email(body), "new_password": "emailFirst123"},
    )
    assert complete.status_code == 200
    assert complete.json()["must_change_password"] is False
    assert client.post(
        "/api/v1/auth/login",
        json={"email": recipient, "password": "emailFirst123"},
    ).status_code == 200
    assert client.post(
        "/api/v1/auth/first-time-password/complete",
        json={"token": _token_from_email(body), "new_password": "replayed123"},
    ).status_code == 400


def test_password_reset_email_is_single_use_and_unknown_accounts_are_generic(monkeypatch) -> None:
    notifications = FakeNotificationService()
    monkeypatch.setattr(app.state, "notification_service", notifications)
    response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "faculty@sprintsight.edu"},
    )
    assert response.status_code == 202
    assert len(notifications.messages) == 1
    recipient, subject, body = notifications.messages[0]
    assert recipient == "faculty@sprintsight.edu"
    assert subject == "Reset your SprintSight password"

    complete = client.post(
        "/api/v1/auth/password-reset/complete",
        json={"token": _token_from_email(body), "new_password": "emailReset123"},
    )
    assert complete.status_code == 200
    assert client.post(
        "/api/v1/auth/password-reset/complete",
        json={"token": _token_from_email(body), "new_password": "replayed123"},
    ).status_code == 400
    assert client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "not.registered@sprintsight.edu"},
    ).json() == response.json()
    assert len(notifications.messages) == 1


def test_unauthenticated_legacy_password_change_is_not_available() -> None:
    response = client.post(
        "/api/v1/users/change-password",
        json={"email": "faculty@sprintsight.edu", "password": "attacker123"},
    )
    assert response.status_code == 405
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "faculty@sprintsight.edu", "password": "password123"},
    ).status_code == 200


def test_completed_report_email_targets_assigned_active_instructors() -> None:
    user_repository = InMemoryUserRepository()
    project_repository = InMemoryProjectRepository()
    course = project_repository.create_course(
        "CS480", "SprintSight", "001", 2026, "Fall", "u-faculty-1",
    )
    notifications = FakeNotificationService()
    report = AssessmentReport(
        report_id="rpt-email-test",
        model_name="test-model",
        mode="test",
        course_id=course.id,
        project_id="project-email-test",
        sprint_id="sprint-1",
        generated_at=datetime.now(UTC),
        rubric_weights={},
        team_score=TeamScore(score=83, rationale="Good work."),
        individual_scores=[],
        recommendations=[],
    )

    _notify_instructors_report_completed(
        report,
        SimpleNamespace(project_name="Email Test Project"),
        user_repository,
        project_repository,
        notifications,
        "job-email-test",
    )

    assert [message[0] for message in notifications.messages] == ["faculty@sprintsight.edu"]
    assert "rpt-email-test" in notifications.messages[0][2]

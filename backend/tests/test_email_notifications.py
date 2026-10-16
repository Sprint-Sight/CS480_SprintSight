import re
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.repositories.in_memory import InMemoryProjectRepository, InMemoryUserRepository
from app.schemas.assessment import AssessmentReport, TeamScore
from app.services.assessmentService.service import _notify_instructors_report_completed
from app.services.notificationService.service import SMTPNotificationService

client = TestClient(app)


class FakeNotificationService:
    is_configured = True

    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str]] = []

    def send_email(self, recipient: str, subject: str, body: str) -> None:
        self.messages.append((recipient, subject, body))


def _token_from_email(body: str) -> str:
    link = re.search(r"https?://\S+", body)
    assert link
    return parse_qs(urlparse(link.group(0)).query)["token"][0]


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
    assert "http://localhost:3000/set-password?" in body
    assert "purpose=first-time-password" in body
    assert "This link expires in 1440 minutes" in body

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
    assert "http://localhost:3000/set-password?" in body
    assert "purpose=password-reset" in body
    assert "This link expires in 30 minutes" in body

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


def test_smtp_email_contains_clickable_html_link(monkeypatch) -> None:
    sent_messages = []

    class FakeSMTP:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def login(self, *_args):
            return None

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setattr(
        "app.services.notificationService.service.smtplib.SMTP",
        lambda *_args, **_kwargs: FakeSMTP(),
    )
    settings = get_settings().model_copy(
        update={
            "email_smtp_host": "smtp.example.test",
            "email_smtp_username": "test-user",
            "email_smtp_password": "test-password",
            "email_from_address": "notify@example.test",
            "email_smtp_use_tls": False,
            "email_smtp_use_ssl": False,
        },
    )
    service = SMTPNotificationService(settings)

    service.send_email(
        "recipient@example.test",
        "Set password",
        "Click this link:\nhttps://frontend.example.test/set-password?token=a.b&purpose=reset",
    )

    html_part = next(
        part for part in sent_messages[0].walk()
        if part.get_content_type() == "text/html"
    )
    assert html_part
    assert (
        '<a href="https://frontend.example.test/set-password?token=a.b&amp;purpose=reset">'
        in html_part.get_content()
    )


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

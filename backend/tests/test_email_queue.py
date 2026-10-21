"""Tests for the durable outbound email queue and the hardened SMTP transport.

The queue exists so that a bulk student import cannot spend the whole email
provider's daily quota in a single request, and so that a provider-side quota
error degrades gracefully instead of turning every request into a stack trace.
"""

import smtplib
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.repositories.in_memory import InMemoryEmailOutboxRepository
from app.services.notificationService.queue import EmailQueue
from app.services.notificationService.service import (
    FileNotificationService,
    NotificationCircuitOpenError,
    NotificationDeliveryError,
    NotificationQuotaExceededError,
    SMTPNotificationService,
)

client = TestClient(app)


class RecordingTransport:
    """Transport double that records what the dispatcher hands it."""

    is_configured = True

    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str]] = []
        self.errors: list[Exception] = []

    def send_email(self, recipient: str, subject: str, body: str) -> None:
        if self.errors:
            raise self.errors.pop(0)
        self.messages.append((recipient, subject, body))


def _settings(**overrides):
    base = {
        "email_transport": "smtp",
        "email_daily_send_cap": 450,
        "email_send_interval_seconds": 0.0,
        "email_dispatch_interval_seconds": 5.0,
        "email_smtp_max_attempts": 3,
        "email_smtp_retry_backoff_seconds": 0.0,
        "email_smtp_circuit_breaker_seconds": 300,
        "email_quota_backoff_seconds": 1800,
        "email_queue_max_attempts": 5,
    }
    base.update(overrides)
    return get_settings().model_copy(update=base)


# ---------------------------------------------------------------------------
# Queue behaviour
# ---------------------------------------------------------------------------


def test_queue_defers_delivery_until_the_dispatcher_runs() -> None:
    transport = RecordingTransport()
    queue = EmailQueue(InMemoryEmailOutboxRepository(), transport, _settings())

    queue.send_email("student@sprintsight.edu", "Set your password", "https://example.test")

    assert transport.messages == []
    assert queue.pending_count() == 1

    assert queue.deliver_pending() == 1
    assert len(transport.messages) == 1
    assert transport.messages[0][0] == "student@sprintsight.edu"


def test_queue_survives_a_restart_because_messages_are_persisted() -> None:
    repository = InMemoryEmailOutboxRepository()
    transport = RecordingTransport()
    queue = EmailQueue(repository, transport, _settings())

    queue.send_email("student@sprintsight.edu", "Set your password", "body")

    # A fresh queue over the same repository still has the message waiting.
    restarted = EmailQueue(repository, transport, _settings())
    assert restarted.pending_count() == 1
    assert restarted.deliver_pending() == 1


def test_daily_cap_holds_messages_over_the_limit() -> None:
    transport = RecordingTransport()
    queue = EmailQueue(
        InMemoryEmailOutboxRepository(),
        transport,
        _settings(email_daily_send_cap=2),
    )

    for index in range(5):
        queue.send_email(f"student{index}@sprintsight.edu", "Subject", "body")

    assert queue.deliver_pending() == 2
    assert len(transport.messages) == 2
    assert queue.pending_count() == 3

    # The cap is counted per UTC day and is not reset mid-pass.
    assert queue.deliver_pending() == 0
    assert len(transport.messages) == 2


def test_dispatcher_spaces_deliveries_out_at_the_configured_rate() -> None:
    transport = RecordingTransport()
    queue = EmailQueue(
        InMemoryEmailOutboxRepository(),
        transport,
        _settings(email_send_interval_seconds=0.25),
    )
    for index in range(3):
        queue.send_email(f"student{index}@sprintsight.edu", "Subject", "body")

    started = time.monotonic()
    assert queue.deliver_pending() == 3
    elapsed = time.monotonic() - started

    # Two gaps between three messages.
    assert elapsed >= 0.5


def test_quota_error_keeps_the_message_queued_for_later() -> None:
    transport = RecordingTransport()
    transport.errors.append(NotificationQuotaExceededError("daily sending limit reached"))
    queue = EmailQueue(
        InMemoryEmailOutboxRepository(),
        transport,
        _settings(email_quota_backoff_seconds=0),
    )

    queue.send_email("student@sprintsight.edu", "Subject", "body")
    assert queue.deliver_pending() == 0

    # The message is still pending and will be retried once the quota resets.
    assert queue.pending_count() == 1
    transport.errors.clear()
    assert queue.deliver_pending() == 1
    assert len(transport.messages) == 1


def test_failed_delivery_is_retried_rather_than_dropped() -> None:
    transport = RecordingTransport()
    transport.errors.append(NotificationDeliveryError("temporary failure"))
    queue = EmailQueue(InMemoryEmailOutboxRepository(), transport, _settings())

    queue.send_email("student@sprintsight.edu", "Subject", "body")
    assert queue.deliver_pending() == 0
    assert queue.pending_count() == 1


def test_delivery_gives_up_after_too_many_attempts() -> None:
    transport = RecordingTransport()
    transport.errors.append(NotificationDeliveryError("permanent failure"))
    queue = EmailQueue(
        InMemoryEmailOutboxRepository(),
        transport,
        _settings(email_queue_max_attempts=1),
    )

    queue.send_email("student@sprintsight.edu", "Subject", "body")
    assert queue.deliver_pending() == 0
    # The message exhausted its attempts and is no longer waiting for a retry.
    assert queue.pending_count() == 0


def test_transport_that_is_not_configured_does_not_drain_the_queue() -> None:
    class DisabledTransport(RecordingTransport):
        is_configured = False

    queue = EmailQueue(InMemoryEmailOutboxRepository(), DisabledTransport(), _settings())
    queue.send_email("student@sprintsight.edu", "Subject", "body")

    assert queue.deliver_pending() == 0
    assert queue.pending_count() == 1


# ---------------------------------------------------------------------------
# SMTP transport hardening
# ---------------------------------------------------------------------------


class _FakeSMTP:
    """SMTP double whose send_message raises whatever the test set up."""

    error: Exception | None = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def login(self, *args, **kwargs):
        return None

    def starttls(self, *args, **kwargs):
        return None

    def send_message(self, message):
        if self.error is not None:
            raise self.error


def _smtp_service(monkeypatch, error: Exception, **overrides) -> SMTPNotificationService:
    fake = type("Fake", (_FakeSMTP,), {"error": error})
    monkeypatch.setattr(
        "app.services.notificationService.service.smtplib.SMTP",
        lambda *args, **kwargs: fake(),
    )
    settings = _settings(
        email_smtp_host="smtp.example.test",
        email_smtp_username="user",
        email_smtp_password="pass",
        email_from_address="notify@example.test",
        email_smtp_use_tls=False,
        email_smtp_use_ssl=False,
        **overrides,
    )
    return SMTPNotificationService(settings)


def test_gmail_daily_limit_is_reported_as_a_quota_error(monkeypatch) -> None:
    error = smtplib.SMTPDataError(
        550,
        b"5.4.5 Daily user sending limit exceeded. For more information on Gmail",
    )
    service = _smtp_service(monkeypatch, error)

    with pytest.raises(NotificationQuotaExceededError):
        service.send_email("student@sprintsight.edu", "Subject", "body")


def test_quota_error_opens_the_circuit_so_later_sends_fail_fast(monkeypatch) -> None:
    error = smtplib.SMTPDataError(
        550,
        b"5.4.5 Daily user sending limit exceeded. For more information on Gmail",
    )
    service = _smtp_service(monkeypatch, error)

    with pytest.raises(NotificationQuotaExceededError):
        service.send_email("student@sprintsight.edu", "Subject", "body")

    # The next attempt short-circuits instead of paying another SMTP round trip.
    assert service.circuit_open is True
    with pytest.raises(NotificationCircuitOpenError):
        service.send_email("student@sprintsight.edu", "Subject", "body")


def test_permanent_failures_are_not_retried(monkeypatch) -> None:
    service = _smtp_service(
        monkeypatch,
        smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted"),
    )

    with pytest.raises(NotificationDeliveryError):
        service.send_email("student@sprintsight.edu", "Subject", "body")


def test_transient_failures_are_retried(monkeypatch) -> None:
    calls = {"count": 0}

    class FlakySMTP(_FakeSMTP):
        def send_message(self, message):
            calls["count"] += 1
            if calls["count"] == 1:
                raise smtplib.SMTPResponseException(421, b"4.7.0 Service not available")
            return None

    monkeypatch.setattr(
        "app.services.notificationService.service.smtplib.SMTP",
        lambda *args, **kwargs: FlakySMTP(),
    )
    settings = _settings(
        email_smtp_host="smtp.example.test",
        email_smtp_username="user",
        email_smtp_password="pass",
        email_from_address="notify@example.test",
        email_smtp_use_tls=False,
        email_smtp_use_ssl=False,
    )
    service = SMTPNotificationService(settings)

    service.send_email("student@sprintsight.edu", "Subject", "body")
    assert calls["count"] == 2


# ---------------------------------------------------------------------------
# File transport (dev / demo)
# ---------------------------------------------------------------------------


def test_file_transport_writes_the_message_to_disk(tmp_path: Path) -> None:
    settings = _settings(email_transport="file", email_outbox_path=tmp_path / "outbox")
    service = FileNotificationService(settings)

    service.send_email("student@sprintsight.edu", "Set your password", "https://example.test/x")

    written = list((tmp_path / "outbox").glob("*.eml"))
    assert len(written) == 1
    content = written[0].read_text(encoding="utf-8")
    assert "student@sprintsight.edu" in content
    assert "Set your password" in content


# ---------------------------------------------------------------------------
# Bulk import suppression flag
# ---------------------------------------------------------------------------


def test_bulk_import_can_suppress_notifications(stub_notification_service) -> None:
    instructor_token = client.post(
        "/api/v1/auth/login",
        json={"email": "faculty@sprintsight.edu", "password": "password123"},
    ).json()["access_token"]
    course = client.post(
        "/api/v1/courses",
        json={
            "code": "CS480",
            "name": "Quiet Import",
            "section": "001",
            "year": 2026,
            "term": "Fall",
        },
        headers={"Authorization": f"Bearer {instructor_token}"},
    ).json()

    csv_body = (
        "student_name,student_id,student_email\n"
        "Quiet Student,480999,quiet.student@sprintsight.edu\n"
    )
    response = client.post(
        f"/api/v1/courses/{course['id']}/students/import",
        files={"file": ("students.csv", csv_body, "text/csv")},
        params={"suppress_notifications": "true"},
        headers={"Authorization": f"Bearer {instructor_token}"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["created_students"] == 1
    assert response.json()["notifications_suppressed"] is True
    assert stub_notification_service.messages == []


def test_bulk_import_sends_setup_emails_by_default(stub_notification_service) -> None:
    instructor_token = client.post(
        "/api/v1/auth/login",
        json={"email": "faculty@sprintsight.edu", "password": "password123"},
    ).json()["access_token"]
    course = client.post(
        "/api/v1/courses",
        json={
            "code": "CS481",
            "name": "Loud Import",
            "section": "001",
            "year": 2026,
            "term": "Fall",
        },
        headers={"Authorization": f"Bearer {instructor_token}"},
    ).json()

    csv_body = (
        "student_name,student_id,student_email\n"
        "Loud Student,480998,loud.student@sprintsight.edu\n"
    )
    response = client.post(
        f"/api/v1/courses/{course['id']}/students/import",
        files={"file": ("students.csv", csv_body, "text/csv")},
        headers={"Authorization": f"Bearer {instructor_token}"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["notifications_suppressed"] is False
    assert [message[0] for message in stub_notification_service.messages] == [
        "loud.student@sprintsight.edu"
    ]

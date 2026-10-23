import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.config import Settings
from app.repositories.interfaces import EmailOutboxRecord, EmailOutboxRepository
from app.services.notificationService.service import (
    EmailTransport,
    NotificationConfigurationError,
    NotificationDeliveryError,
    NotificationQuotaExceededError,
)

logger = logging.getLogger(__name__)

# How long a message may sit in the ``sending`` state before another worker
# assumes the previous attempt died and takes it back.
STALE_CLAIM_WINDOW = timedelta(minutes=10)

# How many messages a single dispatch pass tries to deliver.
DEFAULT_BATCH_SIZE = 25


class EmailQueue:
    """Durable outbound email queue.

    Messages are persisted first and delivered later by a dispatcher, which keeps
    a steady send rate and never exceeds a daily cap. This is what stops a bulk
    student import from spending the whole provider quota in one request.
    """

    def __init__(
        self,
        repository: EmailOutboxRepository,
        transport: EmailTransport,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._transport = transport
        self._settings = settings
        self._last_send_at = 0.0
        self._warned_not_configured = False
        self._warned_cap_reached = False

    @property
    def is_configured(self) -> bool:
        return self._transport.is_configured

    @property
    def daily_cap(self) -> int:
        return self._settings.email_daily_send_cap

    def _start_of_day(self, now: datetime) -> datetime:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    def sent_today(self, now: datetime | None = None) -> int:
        now = now or datetime.now(UTC)
        return self._repository.count_emails_sent_since(self._start_of_day(now))

    def enqueue(
        self,
        recipient: str,
        subject: str,
        body: str,
        kind: str = "general",
        scheduled_for: datetime | None = None,
    ) -> EmailOutboxRecord:
        """Persist a message for later delivery."""
        now = datetime.now(UTC)
        record = EmailOutboxRecord(
            id=str(uuid4()),
            recipient=recipient,
            subject=subject,
            body=body,
            kind=kind,
            status="pending",
            attempts=0,
            created_at=now,
            scheduled_for=scheduled_for or now,
        )
        return self._repository.enqueue_email(record)

    def send_email(
        self,
        recipient: str,
        subject: str,
        body: str,
        kind: str = "general",
    ) -> None:
        """Queue a message. Delivery happens asynchronously."""
        self.enqueue(recipient, subject, body, kind=kind)

    def _wait_for_rate_limit(self) -> None:
        interval = self._settings.email_send_interval_seconds
        if interval <= 0:
            return
        elapsed = time.monotonic() - self._last_send_at
        if self._last_send_at and elapsed < interval:
            time.sleep(interval - elapsed)
        self._last_send_at = time.monotonic()

    def deliver_pending(self, limit: int | None = None) -> int:
        """Run one dispatch pass. Returns the number of messages delivered."""
        if not self._transport.is_configured:
            if not self._warned_not_configured:
                logger.warning("Email delivery is not configured; the outbox is not draining.")
                self._warned_not_configured = True
            return 0

        now = datetime.now(UTC)
        self._repository.requeue_stale_emails(now - STALE_CLAIM_WINDOW)

        sent_today = self.sent_today(now)
        remaining = self.daily_cap - sent_today
        if remaining <= 0:
            if not self._warned_cap_reached:
                logger.warning(
                    "Daily email cap reached (%s sent); holding %s more message(s) until tomorrow.",
                    sent_today,
                    self.daily_cap,
                )
                self._warned_cap_reached = True
            return 0
        self._warned_cap_reached = False

        batch_size = limit or DEFAULT_BATCH_SIZE
        claimed = self._repository.claim_due_emails(now, min(batch_size, remaining))
        if not claimed:
            return 0

        delivered = 0
        for record in claimed:
            try:
                self._wait_for_rate_limit()
                self._transport.send_email(record.recipient, record.subject, record.body)
            except NotificationQuotaExceededError as exc:
                # The provider is done for now: put the message back and stop the pass.
                self._repository.mark_email_failed(
                    record.id,
                    str(exc),
                    now + timedelta(seconds=self._settings.email_quota_backoff_seconds),
                )
                logger.warning(
                    "The email provider rejected delivery because a sending quota was "
                    "reached. Delivery is paused until the quota resets."
                )
                break
            except NotificationConfigurationError as exc:
                self._repository.mark_email_failed(record.id, str(exc), None)
                logger.error("Email delivery is not configured; the outbox is blocked.")
                break
            except NotificationDeliveryError as exc:
                if record.attempts >= self._settings.email_queue_max_attempts:
                    self._repository.mark_email_failed(record.id, str(exc), None)
                    logger.error(
                        "Giving up on a queued email to %s after %s attempts: %s",
                        record.recipient,
                        record.attempts,
                        exc,
                    )
                    continue
                retry_after = now + timedelta(
                    seconds=max(30, self._settings.email_smtp_retry_backoff_seconds * 10)
                )
                self._repository.mark_email_failed(record.id, str(exc), retry_after)
                logger.warning("Could not deliver a queued email to %s: %s", record.recipient, exc)
                continue
            except Exception as exc:  # pragma: no cover - defensive
                self._repository.mark_email_failed(record.id, str(exc), None)
                logger.exception("Unexpected failure while delivering a queued email.")
                continue
            self._repository.mark_email_sent(record.id, datetime.now(UTC))
            delivered += 1

        return delivered

    def pending_count(self) -> int:
        return sum(
            1
            for record in self._repository.list_emails(limit=1000)
            if record.status == "pending"
        )


class EmailDispatcher:
    """Background worker that drains the queue on a fixed interval."""

    def __init__(self, queue: EmailQueue, interval_seconds: float) -> None:
        self._queue = queue
        self._interval = max(0.5, interval_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="email-dispatcher", daemon=True
        )
        self._thread.start()
        logger.info("Email dispatcher started (every %ss).", self._interval)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._queue.deliver_pending()
            except Exception:  # pragma: no cover - defensive
                logger.exception("The email dispatcher pass failed.")
            self._stop.wait(self._interval)

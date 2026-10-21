import logging
import smtplib
import time
from email.message import EmailMessage
from html import escape
from pathlib import Path
from typing import Protocol

from app.core.config import Settings

logger = logging.getLogger(__name__)


class NotificationConfigurationError(RuntimeError):
    """Raised when email delivery has not been configured."""


class NotificationDeliveryError(RuntimeError):
    """Raised when the provider failed to deliver a message."""


class NotificationQuotaExceededError(NotificationDeliveryError):
    """Raised when the provider rejected the message because a quota was exhausted.

    Typically a per-day or per-hour sending limit (Gmail free accounts are capped
    at 500 messages/day). Retrying immediately cannot help, so the caller should
    stop sending and let the queue drain later.
    """


class NotificationCircuitOpenError(NotificationDeliveryError):
    """Raised when delivery is skipped because the provider is known to be unhealthy."""


class EmailTransport(Protocol):
    """Anything able to hand a message to an email provider."""

    @property
    def is_configured(self) -> bool: ...

    def send_email(self, recipient: str, subject: str, body: str) -> None: ...


# Substrings providers use to signal "you have hit a sending limit".
_QUOTA_MARKERS = (
    "sending limit",
    "daily limit",
    "daily user sending",
    "quota",
    "too many",
    "rate limit",
    "rate exceeded",
    "message rate",
    "try again later",
    "mailbox full",
    "insufficient system storage",
)

# SMTP reply codes that unambiguously mean "a quota was exhausted".
_QUOTA_CODES = frozenset({452})


def _is_quota_error(exc: Exception) -> bool:
    """Detect "you have hit a sending limit" errors.

    Providers report this inconsistently: Gmail answers ``550 5.4.5 Daily user
    sending limit exceeded``, others use ``452 insufficient system storage``.
    The error text is the reliable signal, so it is checked first.
    """
    if isinstance(exc, smtplib.SMTPResponseException):
        if exc.smtp_code in _QUOTA_CODES:
            return True
        text = exc.smtp_error
        detail = text.decode("utf-8", "replace") if isinstance(text, bytes) else str(text)
        lowered = detail.lower()
        return any(marker in lowered for marker in _QUOTA_MARKERS)
    return False


def _is_transient_error(exc: Exception) -> bool:
    """Transient errors are worth retrying; permanent ones are not."""
    if isinstance(exc, smtplib.SMTPResponseException):
        # 4xx is "temporary problem", 5xx is "permanent".
        return 400 <= exc.smtp_code < 500
    if isinstance(exc, (smtplib.SMTPAuthenticationError, smtplib.SMTPHeloError)):
        return False
    if isinstance(exc, (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused)):
        return False
    if isinstance(exc, (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, OSError)):
        return True
    return False


def build_message(settings: Settings, recipient: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = (
        f"{settings.email_from_name} <{settings.email_from_address}>"
    )
    message["To"] = recipient
    message.set_content(body)
    links = [
        line
        for line in body.splitlines()
        if line.startswith(("http://", "https://"))
    ]
    html_body = escape(body).replace("\n", "<br>\n")
    for link in links:
        safe_link = escape(link, quote=True)
        html_body = html_body.replace(
            safe_link,
            f'<a href="{safe_link}">{escape(link)}</a>',
        )
    message.add_alternative(
        f"<html><body>{html_body}</body></html>",
        subtype="html",
    )
    return message


class SMTPNotificationService:
    """SMTP transport with quota detection, bounded retries and a circuit breaker."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._circuit_open_until = 0.0

    @property
    def is_configured(self) -> bool:
        return all(
            (
                self._settings.email_smtp_host,
                self._settings.email_smtp_username,
                self._settings.email_smtp_password,
                self._settings.email_from_address,
            )
        )

    @property
    def circuit_open(self) -> bool:
        return time.monotonic() < self._circuit_open_until

    def _open_circuit(self) -> None:
        self._circuit_open_until = (
            time.monotonic() + self._settings.email_smtp_circuit_breaker_seconds
        )

    def _deliver(self, message: EmailMessage) -> None:
        if self._settings.email_smtp_use_ssl:
            with smtplib.SMTP_SSL(
                self._settings.email_smtp_host,
                self._settings.email_smtp_port,
                timeout=20,
            ) as server:
                server.login(
                    self._settings.email_smtp_username,
                    self._settings.email_smtp_password,
                )
                server.send_message(message)
        else:
            with smtplib.SMTP(
                self._settings.email_smtp_host,
                self._settings.email_smtp_port,
                timeout=20,
            ) as server:
                if self._settings.email_smtp_use_tls:
                    server.starttls()
                server.login(
                    self._settings.email_smtp_username,
                    self._settings.email_smtp_password,
                )
                server.send_message(message)

    def send_email(self, recipient: str, subject: str, body: str) -> None:
        if not self.is_configured:
            raise NotificationConfigurationError(
                "Email delivery is not configured. "
                "Set EMAIL_SMTP_* and EMAIL_FROM_ADDRESS."
            )

        if self.circuit_open:
            raise NotificationCircuitOpenError(
                "Email delivery is paused because the provider recently rejected messages. "
                "Retry later."
            )

        message = build_message(self._settings, recipient, subject, body)
        attempts = max(1, self._settings.email_smtp_max_attempts)
        backoff = self._settings.email_smtp_retry_backoff_seconds

        for attempt in range(1, attempts + 1):
            try:
                self._deliver(message)
                return
            except (OSError, smtplib.SMTPException) as exc:
                if _is_quota_error(exc):
                    self._open_circuit()
                    raise NotificationQuotaExceededError(
                        "The email provider rejected the message because a sending "
                        "quota or rate limit was reached."
                    ) from exc
                if attempt >= attempts or not _is_transient_error(exc):
                    raise NotificationDeliveryError(
                        "The email provider rejected or could not deliver the message."
                    ) from exc
                logger.warning(
                    "Transient SMTP failure (attempt %s/%s) for %s; retrying in %ss.",
                    attempt,
                    attempts,
                    recipient,
                    backoff * (2 ** (attempt - 1)),
                )
                if backoff:
                    time.sleep(backoff * (2 ** (attempt - 1)))


class FileNotificationService:
    """Transport that writes messages to disk instead of sending them.

    Used for local development and demos: the real setup links still work, but
    nothing is handed to an email provider, so no sending quota is consumed.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._directory = Path(settings.email_outbox_path)

    @property
    def is_configured(self) -> bool:
        return True

    def send_email(self, recipient: str, subject: str, body: str) -> None:
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            message = build_message(self._settings, recipient, subject, body)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            target = self._directory / f"{stamp}-{abs(hash(recipient)) % 100000}.eml"
            target.write_text(message.as_string(), encoding="utf-8")
        except OSError:
            logger.exception("Could not write the outgoing email to %s.", self._directory)
            raise NotificationDeliveryError(
                "The email could not be written to the local outbox."
            ) from None
        logger.info("Email written to the local outbox for %s: %s", recipient, subject)


class DisabledNotificationService:
    """Transport that refuses to send anything.

    Selected with ``EMAIL_TRANSPORT=none`` so a deployment can run with email
    completely switched off.
    """

    @property
    def is_configured(self) -> bool:
        return False

    def send_email(self, recipient: str, subject: str, body: str) -> None:
        raise NotificationConfigurationError("Email delivery is disabled.")


def build_email_transport(settings: Settings) -> EmailTransport:
    """Pick the transport configured through ``EMAIL_TRANSPORT``."""
    transport = (settings.email_transport or "smtp").strip().lower()
    if transport == "file":
        return FileNotificationService(settings)
    if transport in ("none", "disabled", "off"):
        return DisabledNotificationService()
    return SMTPNotificationService(settings)

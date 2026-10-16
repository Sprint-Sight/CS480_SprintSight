import smtplib
from email.message import EmailMessage

from app.core.config import Settings


class NotificationConfigurationError(RuntimeError):
    pass


class NotificationDeliveryError(RuntimeError):
    pass


class SMTPNotificationService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

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

    def send_email(self, recipient: str, subject: str, body: str) -> None:
        if not self.is_configured:
            raise NotificationConfigurationError(
                "Email delivery is not configured. "
                "Set EMAIL_SMTP_* and EMAIL_FROM_ADDRESS."
            )

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = (
            f"{self._settings.email_from_name} <{self._settings.email_from_address}>"
        )
        message["To"] = recipient
        message.set_content(body)

        try:
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
        except (OSError, smtplib.SMTPException) as exc:
            raise NotificationDeliveryError(
                "The email provider rejected or could not deliver the message."
            ) from exc
import logging

from app.repositories.interfaces import UserRecord
from app.services.authService.email_tokens import create_email_action_token, email_action_message
from app.services.notificationService.service import (
    EmailTransport,
    NotificationCircuitOpenError,
    NotificationConfigurationError,
    NotificationDeliveryError,
    NotificationQuotaExceededError,
)

logger = logging.getLogger(__name__)


def send_password_setup_email(
    user: UserRecord,
    notification_service: EmailTransport,
) -> bool:
    """Queue a first-time password setup email for ``user``.

    Returns ``True`` when the message was accepted for delivery. Delivery itself
    happens asynchronously through the outbox, so a provider quota problem never
    blocks the request that created the account.
    """
    if not notification_service.is_configured:
        logger.warning(
            "Password setup email was not sent to user %s because email delivery is not configured.",
            user.id,
        )
        return False

    token = create_email_action_token(user, "first_time_password")
    subject, body = email_action_message(token, "first_time_password")
    try:
        notification_service.send_email(user.email, subject, body)
    except NotificationQuotaExceededError:
        logger.warning(
            "Password setup email for user %s was not queued because the email "
            "provider's sending quota is exhausted.",
            user.id,
        )
        return False
    except NotificationCircuitOpenError:
        logger.warning(
            "Password setup email for user %s was not queued because email delivery "
            "is temporarily paused.",
            user.id,
        )
        return False
    except (NotificationConfigurationError, NotificationDeliveryError):
        logger.exception("Password setup email could not be queued for user %s.", user.id)
        return False
    return True

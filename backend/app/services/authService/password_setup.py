import logging

from app.repositories.interfaces import UserRecord
from app.services.authService.email_tokens import create_email_action_token, email_action_message
from app.services.notificationService.service import (
    NotificationConfigurationError,
    NotificationDeliveryError,
    SMTPNotificationService,
)

logger = logging.getLogger(__name__)


def send_password_setup_email(
    user: UserRecord,
    notification_service: SMTPNotificationService,
) -> bool:
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
    except (NotificationConfigurationError, NotificationDeliveryError):
        logger.exception("Password setup email could not be delivered to user %s.", user.id)
        return False
    return True

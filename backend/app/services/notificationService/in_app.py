import logging
from datetime import UTC, datetime
from uuid import uuid4

from app.repositories.interfaces import NotificationRecord, NotificationRepository

logger = logging.getLogger(__name__)


def create_in_app_notification(
    repository: NotificationRepository,
    recipient_id: str,
    event_type: str,
    title: str,
    message: str,
) -> None:
    notification = NotificationRecord(
        id=str(uuid4()),
        recipient_id=recipient_id,
        event_type=event_type,
        title=title,
        message=message,
        created_at=datetime.now(UTC),
    )
    try:
        repository.create_notification(notification)
    except Exception:
        logger.exception(
            "Could not save in-app notification of type %s for user %s.",
            event_type,
            recipient_id,
        )

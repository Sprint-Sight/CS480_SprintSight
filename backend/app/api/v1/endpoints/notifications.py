from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies.auth import get_current_user, get_notification_repository
from app.repositories.interfaces import NotificationRepository, UserRecord
from app.schemas.notifications import NotificationListResponse, NotificationResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _response(notification) -> NotificationResponse:
    return NotificationResponse(
        id=notification.id,
        event_type=notification.event_type,
        title=notification.title,
        message=notification.message,
        created_at=notification.created_at,
        read_at=notification.read_at,
    )


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[NotificationRepository, Depends(get_notification_repository)],
) -> NotificationListResponse:
    return NotificationListResponse(
        notifications=[
            _response(item)
            for item in repository.list_notifications(current_user.id)
        ],
        unread_count=repository.count_unread_notifications(current_user.id),
    )


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
def mark_notification_read(
    notification_id: UUID,
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[NotificationRepository, Depends(get_notification_repository)],
) -> NotificationResponse:
    notification = repository.mark_notification_read(str(notification_id), current_user.id)
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found.",
        )
    return _response(notification)

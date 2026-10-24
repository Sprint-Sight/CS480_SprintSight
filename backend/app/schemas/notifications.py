from datetime import datetime

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: str
    event_type: str
    title: str
    message: str
    created_at: datetime
    read_at: datetime | None


class NotificationListResponse(BaseModel):
    notifications: list[NotificationResponse]
    unread_count: int

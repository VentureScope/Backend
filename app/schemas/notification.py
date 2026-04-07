"""
Pydantic schemas for Notifications.
"""

from datetime import datetime
from typing import Any
from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: str
    user_id: str
    notification_type: str
    title: str
    body: str
    is_read: bool
    metadata_: dict[str, Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    notifications: list[NotificationResponse]
    total_count: int
    unread_count: int

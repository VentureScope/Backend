"""
Notifications API endpoints.

Routes
------
GET    /api/notifications                      – list notifications (with optional unread filter)
POST   /api/notifications/mark-all-read        – mark all as read
PATCH  /api/notifications/{id}/read            – mark one as read
DELETE /api/notifications/{id}                 – delete one notification
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.notification import NotificationListResponse, NotificationResponse
from app.schemas.user import MessageResponse
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=30, ge=1, le=100),
    unread_only: bool = Query(default=False),
):
    """
    List all notifications for the current user.
    Use `unread_only=true` to filter to unread ones.
    """
    service = NotificationService(db)
    skip = (page - 1) * per_page
    notifications, total, unread = await service.list_notifications(
        current_user.id, skip=skip, limit=per_page, unread_only=unread_only
    )
    return NotificationListResponse(
        notifications=notifications,
        total_count=total,
        unread_count=unread,
    )


@router.post("/mark-all-read", response_model=MessageResponse)
async def mark_all_read(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Mark all unread notifications as read."""
    service = NotificationService(db)
    count = await service.mark_all_read(current_user.id)
    await db.commit()
    return MessageResponse(
        message=f"Marked {count} notification(s) as read",
        detail=None,
    )


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Mark a single notification as read."""
    service = NotificationService(db)
    try:
        notif = await service.mark_read(current_user.id, notification_id)
        await db.commit()
        return notif
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{notification_id}", status_code=204)
async def delete_notification(
    notification_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete a notification."""
    service = NotificationService(db)
    try:
        await service.delete(current_user.id, notification_id)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

"""
Notification Service – business logic for creating and managing notifications.
Also pushes real-time WS events to connected users.
"""

import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.repositories.notification_repository import NotificationRepository
from app.services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = NotificationRepository(db)

    async def create_chat_reply_notification(
        self,
        user_id: str,
        session_id: str,
        message_id: str,
        preview: str,
    ) -> Notification:
        """
        Create a 'chat_reply' notification and push it in real-time via WebSocket
        to ALL sessions of this user (so other tabs get notified too).
        """
        body_preview = preview[:120] + "…" if len(preview) > 120 else preview
        notif = await self.repo.create(
            user_id=user_id,
            title="New AI Reply",
            body=body_preview,
            notification_type="chat_reply",
            metadata={"session_id": session_id, "message_id": message_id},
        )

        # Push real-time notification to all connected sessions for this user
        if ws_manager.is_connected(user_id):
            await ws_manager.broadcast_to_user(
                user_id,
                {
                    "event": "notification",
                    "data": {
                        "id": notif.id,
                        "type": notif.notification_type,
                        "title": notif.title,
                        "body": notif.body,
                        "session_id": session_id,
                        "message_id": message_id,
                        "created_at": notif.created_at.isoformat(),
                    },
                },
            )
        return notif

    async def list_notifications(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 30,
        unread_only: bool = False,
    ) -> tuple[list[Notification], int, int]:
        """Return (notifications, total, unread_count)."""
        notifications = await self.repo.list_for_user(
            user_id, skip=skip, limit=limit, unread_only=unread_only
        )
        total = await self.repo.count_total(user_id)
        unread = await self.repo.count_unread(user_id)
        return notifications, total, unread

    async def mark_read(self, user_id: str, notif_id: str) -> Notification:
        notif = await self.repo.get_by_id(notif_id, user_id)
        if not notif:
            raise ValueError("Notification not found")
        return await self.repo.mark_read(notif)

    async def mark_all_read(self, user_id: str) -> int:
        return await self.repo.mark_all_read(user_id)

    async def delete(self, user_id: str, notif_id: str) -> None:
        notif = await self.repo.get_by_id(notif_id, user_id)
        if not notif:
            raise ValueError("Notification not found")
        await self.repo.delete(notif)

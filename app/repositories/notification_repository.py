"""
Repository for Notification database operations.
"""

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


class NotificationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        user_id: str,
        title: str,
        body: str,
        notification_type: str = "chat_reply",
        metadata: dict | None = None,
    ) -> Notification:
        notif = Notification(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            body=body,
            metadata_=metadata,
        )
        self.db.add(notif)
        await self.db.flush()
        await self.db.refresh(notif)
        return notif

    async def list_for_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 30,
        unread_only: bool = False,
    ) -> list[Notification]:
        query = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            query = query.where(Notification.is_read == False)  # noqa: E712
        query = query.order_by(Notification.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_unread(self, user_id: str) -> int:
        result = await self.db.execute(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id, Notification.is_read == False  # noqa: E712
            )
        )
        return result.scalar() or 0

    async def count_total(self, user_id: str) -> int:
        result = await self.db.execute(
            select(func.count(Notification.id)).where(Notification.user_id == user_id)
        )
        return result.scalar() or 0

    async def get_by_id(self, notif_id: str, user_id: str) -> Notification | None:
        result = await self.db.execute(
            select(Notification).where(
                Notification.id == notif_id, Notification.user_id == user_id
            )
        )
        return result.scalars().one_or_none()

    async def mark_read(self, notif: Notification) -> Notification:
        notif.is_read = True
        await self.db.flush()
        await self.db.refresh(notif)
        return notif

    async def mark_all_read(self, user_id: str) -> int:
        result = await self.db.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read == False)  # noqa: E712
            .values(is_read=True)
            .returning(Notification.id)
        )
        rows = result.fetchall()
        await self.db.flush()
        return len(rows)

    async def delete(self, notif: Notification) -> None:
        await self.db.delete(notif)
        await self.db.flush()

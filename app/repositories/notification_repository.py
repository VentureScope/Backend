"""
Repository for Notification database operations.
"""

from sqlalchemy import select, func, update, case, literal_column
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

    async def list_with_counts(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 30,
        unread_only: bool = False,
    ) -> tuple[list[Notification], int, int]:
        """
        Return (notifications, total_count, unread_count) in a single query
        using SQL window functions, replacing the previous 3-query pattern.

        When the result page is empty (e.g. unread_only=True but no unread rows),
        a fallback scalar query is issued only for unread_count so callers still
        get an accurate badge count.
        """
        # Window functions compute counts across the full filtered set,
        # not just the current page — total over ALL rows for user_id,
        # unread over all rows where is_read IS FALSE.
        total_window = func.count(literal_column("*")).over().label("total_count")
        unread_window = (
            func.count(
                case(
                    (Notification.is_read == False, 1),  # noqa: E712
                    else_=None,
                )
            )
            .over()
            .label("unread_count")
        )

        query = (
            select(Notification, total_window, unread_window)
            .where(Notification.user_id == user_id)
        )
        if unread_only:
            query = query.where(Notification.is_read == False)  # noqa: E712

        query = query.order_by(Notification.created_at.desc()).offset(skip).limit(limit)

        result = await self.db.execute(query)
        rows = result.all()

        if not rows:
            # Page is empty — still need an accurate unread count for badge.
            unread = await self.count_unread(user_id)
            return [], 0, unread

        notifications = [row[0] for row in rows]
        total = rows[0][1]
        unread = rows[0][2]
        return notifications, total, unread

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

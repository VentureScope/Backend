"""
Repository for ChatSession and ChatMessage database operations.
"""

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.chat import ChatSession, ChatMessage


class ChatRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ────────────────── Sessions ──────────────────

    async def create_session(self, user_id: str, title: str = "New Chat") -> ChatSession:
        session = ChatSession(user_id=user_id, title=title)
        self.db.add(session)
        await self.db.flush()
        await self.db.refresh(session)
        return session

    async def get_session(self, session_id: str, user_id: str) -> ChatSession | None:
        """Get a session owned by the given user, with messages eager-loaded."""
        result = await self.db.execute(
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .where(ChatSession.id == session_id, ChatSession.user_id == user_id)
        )
        return result.scalars().one_or_none()

    async def get_session_bare(self, session_id: str, user_id: str) -> ChatSession | None:
        """Get a session without loading messages (lightweight check)."""
        result = await self.db.execute(
            select(ChatSession).where(
                ChatSession.id == session_id, ChatSession.user_id == user_id
            )
        )
        return result.scalars().one_or_none()

    async def list_sessions(
        self, user_id: str, skip: int = 0, limit: int = 20
    ) -> list[ChatSession]:
        result = await self.db.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_sessions(self, user_id: str) -> int:
        result = await self.db.execute(
            select(func.count(ChatSession.id)).where(ChatSession.user_id == user_id)
        )
        return result.scalar() or 0

    async def update_session_title(self, session: ChatSession, title: str) -> ChatSession:
        session.title = title
        await self.db.flush()
        await self.db.refresh(session)
        return session

    async def delete_session(self, session: ChatSession) -> None:
        await self.db.delete(session)
        await self.db.flush()

    # ────────────────── Messages ──────────────────

    async def add_message(
        self, session_id: str, role: str, content: str
    ) -> ChatMessage:
        msg = ChatMessage(session_id=session_id, role=role, content=content)
        self.db.add(msg)
        await self.db.flush()
        await self.db.refresh(msg)
        return msg

    async def get_messages(
        self, session_id: str, limit: int = 50
    ) -> list[ChatMessage]:
        """Return the last `limit` messages ordered oldest-first."""
        result = await self.db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

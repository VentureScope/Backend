"""
Repository for UserKnowledge database operations.
"""

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_knowledge import UserKnowledge


class KnowledgeRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_knowledge(
        self, user_id: str, content: str, embedding: list[float], source_type: str
    ) -> UserKnowledge:
        """Add a new searchable chunk for a user."""
        chunk = UserKnowledge(
            user_id=user_id,
            content=content,
            embedding=embedding,
            source_type=source_type,
        )
        self.db.add(chunk)
        await self.db.flush()
        return chunk

    async def clear_user_knowledge(self, user_id: str, source_type: str | None = None) -> None:
        """Delete all knowledge chunks for a user, optionally filtered by source."""
        query = delete(UserKnowledge).where(UserKnowledge.user_id == user_id)
        if source_type:
            query = query.where(UserKnowledge.source_type == source_type)
        await self.db.execute(query)
        await self.db.flush()

    async def search_user_knowledge(
        self, user_id: str, query_embedding: list[float], limit: int = 5
    ) -> list[UserKnowledge]:
        """
        Search for the most relevant knowledge chunks ONLY within this specific user's data.
        """
        query = (
            select(UserKnowledge)
            .where(UserKnowledge.user_id == user_id)
            .order_by(UserKnowledge.embedding.cosine_distance(query_embedding))
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

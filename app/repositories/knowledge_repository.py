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

    async def search_by_sources(
        self,
        user_id: str,
        query_embedding: list[float],
        source_types: list[str],
        limit: int = 8,
    ) -> list[UserKnowledge]:
        """
        Vector similarity search restricted to specific source_types for a user.

        Only chunks that have been embedded (embedding_status='completed') are
        considered; pending/failed chunks are skipped so we never get None
        embeddings in the cosine distance call.
        """
        query = (
            select(UserKnowledge)
            .where(
                UserKnowledge.user_id == user_id,
                UserKnowledge.source_type.in_(source_types),
                UserKnowledge.embedding_status == "completed",
                UserKnowledge.embedding.is_not(None),
            )
            .order_by(UserKnowledge.embedding.cosine_distance(query_embedding))
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_all_by_user_and_sources(
        self,
        user_id: str,
        source_types: list[str],
    ) -> list[UserKnowledge]:
        """
        Return ALL knowledge chunks for a user filtered by source_types.
        No vector search — plain DB fetch ordered by creation time.
        Useful for checking whether a source type has any data at all.
        """
        query = (
            select(UserKnowledge)
            .where(
                UserKnowledge.user_id == user_id,
                UserKnowledge.source_type.in_(source_types),
            )
            .order_by(UserKnowledge.created_at.asc())
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def search_across_users(
        self,
        user_ids: list[str],
        query_embedding: list[float],
        limit: int = 15,
        source_types: list[str] | None = None,
    ) -> list[UserKnowledge]:
        """
        Vector similarity search across MULTIPLE users' knowledge chunks.
        Used by the org advisor to search knowledge from all org members.

        Only completed embeddings are considered.
        Results are ranked by cosine similarity across the entire member pool.
        """
        if not user_ids:
            return []

        conditions = [
            UserKnowledge.user_id.in_(user_ids),
            UserKnowledge.embedding_status == "completed",
            UserKnowledge.embedding.is_not(None),
        ]
        if source_types:
            conditions.append(UserKnowledge.source_type.in_(source_types))

        query = (
            select(UserKnowledge)
            .where(*conditions)
            .order_by(UserKnowledge.embedding.cosine_distance(query_embedding))
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

"""
Service for ingesting text into UserKnowledge chunks.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.embedding_service import get_embedding_service


class KnowledgeService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = KnowledgeRepository(db)
        self.embedding_service = get_embedding_service()

    async def ingest_knowledge(self, user_id: str, content: str, source_type: str) -> None:
        """Embed text and insert it as a UserKnowledge chunk."""
        if not content or not content.strip():
            return
            
        embedding = self.embedding_service.generate_embedding(content)
        await self.repo.add_knowledge(
            user_id=user_id,
            content=content,
            embedding=embedding,
            source_type=source_type,
        )

    async def replace_user_knowledge(
        self, user_id: str, chunks: list[str], source_type: str
    ) -> None:
        """Clear old knowledge for a source and ingest new chunks."""
        await self.repo.clear_user_knowledge(user_id, source_type=source_type)
        
        for content in chunks:
            if content and content.strip():
                embedding = self.embedding_service.generate_embedding(content)
                await self.repo.add_knowledge(
                    user_id=user_id,
                    content=content,
                    embedding=embedding,
                    source_type=source_type,
                )

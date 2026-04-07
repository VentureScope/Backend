"""
UserKnowledge model for storing individual vector-searchable facts for a user.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.core.database import Base
from app.core.config import settings


class UserKnowledge(Base):
    """
    Searchable chunks of user information (e.g., specific courses, profile entries).
    """

    __tablename__ = "user_knowledge"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # "transcript_courses", "profile", "resume", etc.
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # The actual semantic text that will be fed to the LLM
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # The vector representation of the content
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.EMBEDDING_DIMENSIONS), nullable=False
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_user_knowledge_user_id_source", "user_id", "source_type"),
    )

    def __repr__(self) -> str:
        return f"<UserKnowledge(id={self.id}, user_id={self.user_id}, source={self.source_type})>"

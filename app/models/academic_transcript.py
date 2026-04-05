"""
AcademicTranscript model for storing e-student transcript data.
"""

from datetime import datetime, timezone
from typing import Dict
from sqlalchemy import (
    String,
    Integer,
    DateTime,
    func,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base


class AcademicTranscript(Base):
    """
    Academic transcript data uploaded from e-student system.

    Supports version history with automatic cleanup (keeps latest 3 versions per user).
    Each version represents a separate upload of transcript data.
    """

    __tablename__ = "academic_transcripts"

    # Primary key
    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Foreign key to users
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Student ID from e-student profile (optional, can be scraped)
    student_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    # Complete transcript data (semesters, courses, grades, etc.) stored as JSONB
    transcript_data: Mapped[Dict] = mapped_column(JSONB, nullable=False)

    # Version number for this user (1, 2, 3, ...)
    # When new version is uploaded, old versions beyond the 3 most recent are deleted
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    # When the transcript was uploaded (separate from created_at for clarity)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Standard timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Constraints
    __table_args__ = (
        # Each user can only have one transcript with a specific version number
        UniqueConstraint("user_id", "version", name="uq_user_version"),
        # Composite index for efficient queries by user and version
        Index("ix_academic_transcripts_user_version", "user_id", "version"),
    )

    def __repr__(self) -> str:
        return f"<AcademicTranscript(user_id={self.user_id}, version={self.version}, student_id={self.student_id})>"

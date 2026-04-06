"""
TranscriptConfig model for storing user-specific grading system configurations.
"""

from datetime import datetime, timezone
from typing import Dict, List
from sqlalchemy import String, Float, DateTime, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base


class TranscriptConfig(Base):
    """
    User's grading system configuration for transcript validation.

    Each user has one configuration that defines:
    - GPA scale (e.g., 4.0, 5.0, 10.0)
    - Grade-to-GPA mapping (e.g., A+ = 4.0, A = 4.0, etc.)
    - Grade display order for UI presentation
    """

    __tablename__ = "transcript_configs"

    # Primary key
    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Foreign key to users (one config per user)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )

    # GPA scale (max GPA value, e.g., 4.0, 5.0, 10.0)
    gpa_scale: Mapped[float] = mapped_column(Float, nullable=False)

    # Grade-to-GPA mapping
    # Example: {"A+": 4.0, "A": 4.0, "A-": 3.7, "B+": 3.3, ..., "F": 0.0, "W": null}
    grading_schema: Mapped[Dict] = mapped_column(JSONB, nullable=False)

    # Grade display order for UI (ordered list of grade keys)
    # Example: ["A+", "A", "A-", "B+", "B", "B-", ..., "F", "W", "IP", "-"]
    grade_display_order: Mapped[List] = mapped_column(JSONB, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<TranscriptConfig(user_id={self.user_id}, gpa_scale={self.gpa_scale})>"

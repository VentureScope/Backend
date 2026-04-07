"""
GitHub Sync Snapshot Model - stores persisted GitHub sync payloads per user.
"""

from datetime import datetime, timezone
import uuid

from sqlalchemy import String, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class GitHubSyncSnapshot(Base):
    """Stores the latest GitHub sync payload for a user."""

    __tablename__ = "github_sync_snapshots"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    github_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    repositories_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    contributions_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    organizations_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="github_sync_snapshot")

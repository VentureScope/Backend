"""
AccountBase-equivalent: core user identity and auth (Data Dictionary).
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import String, DateTime, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
import uuid
import enum

# Use pgvector
from pgvector.sqlalchemy import Vector
from app.core.config import settings

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.oauth_account import OAuthAccount
    from app.models.github_sync_snapshot import GitHubSyncSnapshot


class UserRole(str, enum.Enum):
    STUDENT = "student"
    PROFESSIONAL = "professional"
    B2B_CLIENT = "b2b_client"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # Optional for OAuth users
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    profile_picture_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )  # For OAuth profile images
    github_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    career_interest: Mapped[str | None] = mapped_column(String(500), nullable=True)
    skills: Mapped[list | None] = mapped_column(JSON, nullable=True)  # List of skill strings
    cv_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)  # S3 URL for CV
    estudent_profile: Mapped[str | None] = mapped_column(String(1000), nullable=True)  # E-student summarized profile
    
    # Store generated similarity embedding using pgvector
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.EMBEDDING_DIMENSIONS), nullable=True
    )


    # OAuth fields
    oauth_provider: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # 'google', 'github', etc.
    oauth_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # Provider's user ID
    email_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )  # OAuth users are auto-verified
    role: Mapped[str] = mapped_column(
        String(32), default=UserRole.PROFESSIONAL.value, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(
        "OAuthAccount", back_populates="user", cascade="all, delete-orphan"
    )
    github_sync_snapshot: Mapped["GitHubSyncSnapshot"] = relationship(
        "GitHubSyncSnapshot",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )

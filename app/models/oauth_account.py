"""
OAuth Account Model - manages external OAuth provider connections.
"""

from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
import uuid

from app.core.database import Base


class OAuthAccount(Base):
    """
    Stores OAuth account connections for users.

    This model follows industry best practices:
    - Separate OAuth accounts from user accounts
    - Support multiple OAuth providers per user
    - Store provider-specific information
    - Track token refresh capabilities
    """

    __tablename__ = "oauth_accounts"

    # Composite unique constraint to prevent duplicate provider accounts
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_account_id", name="unique_provider_account"
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # Link to user account
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # OAuth provider information
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'google', 'github', etc.
    provider_account_id: Mapped[str] = mapped_column(
        String(255), nullable=False
    )  # Provider's user ID
    provider_email: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # Provider's email

    # OAuth token information (encrypted in production)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Provider profile information
    provider_data: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON string of profile data

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationship back to user
    user: Mapped["User"] = relationship("User", back_populates="oauth_accounts")

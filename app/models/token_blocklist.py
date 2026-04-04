"""
Token Blocklist Model - Stores invalidated JWT tokens for logout functionality.
"""

from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TokenBlocklist(Base):
    """
    Stores invalidated JWT tokens (by their JTI - JWT ID).

    Tokens are added here on logout and checked during authentication.
    Expired entries are cleaned up periodically by background task.
    """

    __tablename__ = "token_blocklist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    jti: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Index for cleanup queries
    __table_args__ = (Index("ix_token_blocklist_expires_at", "expires_at"),)

"""
Certificate model for user profiles.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey, func, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
import uuid

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Certificate(Base):
    """
    Professional certifications and credentials for a user.
    """

    __tablename__ = "certificates"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(500), nullable=False)
    issuer: Mapped[str] = mapped_column(String(255), nullable=False)
    credential_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    credential_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    issue_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expiry_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # None = does not expire
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<Certificate(id={self.id}, user_id={self.user_id}, name={self.name})>"

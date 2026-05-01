"""
Work Experience model for user profiles.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

import uuid

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Experience(Base):
    """
    Work experience entries for a user.
    Multiple experiences per user, each with job title, company, dates, etc.
    """

    __tablename__ = "experiences"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    job_title: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)

    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # None = current job

    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    # List of skills used in this role (JSON)
    skills_used: Mapped[list | None] = mapped_column(String(1000), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship to User
    user: Mapped["User"] = relationship("User", back_populates="experiences")

    def __repr__(self) -> str:
        return f"<Experience(id={self.id}, user_id={self.user_id}, title={self.job_title})>"

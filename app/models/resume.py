from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import String, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
import uuid

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    target_role: Mapped[str] = mapped_column(String(255), nullable=False)
    professional_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    experience: Mapped[list | None] = mapped_column(JSON, nullable=True)
    education: Mapped[list | None] = mapped_column(JSON, nullable=True)
    projects: Mapped[list | None] = mapped_column(JSON, nullable=True)
    certifications: Mapped[list | None] = mapped_column(JSON, nullable=True)
    trending_skills_highlighted: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<Resume(id={self.id}, user_id={self.user_id}, target_role={self.target_role})>"

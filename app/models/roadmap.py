from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import String, DateTime, Text, Integer, ForeignKey, UniqueConstraint, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
import uuid

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class LearningRoadmap(Base):
    __tablename__ = "learning_roadmaps"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    trend_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)

    # "current" — based on today's market demand
    # "future"  — based on projected/emerging market trends
    trend_mode: Mapped[str] = mapped_column(String(20), default="current", nullable=False)

    # LLM-generated skill gap analysis — persisted so it's available without
    # re-running the LLM on every GET request
    skill_gap_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    steps: Mapped[list["LearningRoadmapStep"]] = relationship(
        "LearningRoadmapStep", back_populates="roadmap", cascade="all, delete-orphan"
    )


class LearningRoadmapStep(Base):
    __tablename__ = "learning_roadmap_steps"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    roadmap_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("learning_roadmaps.id", ondelete="CASCADE"), nullable=False
    )
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    roadmap: Mapped["LearningRoadmap"] = relationship(
        "LearningRoadmap", back_populates="steps"
    )
    resources: Mapped[list["LearningRoadmapStepResource"]] = relationship(
        "LearningRoadmapStepResource", back_populates="step", cascade="all, delete-orphan"
    )
    progress: Mapped[list["LearningRoadmapProgress"]] = relationship(
        "LearningRoadmapProgress", back_populates="step", cascade="all, delete-orphan"
    )


class LearningRoadmapStepResource(Base):
    __tablename__ = "learning_roadmap_step_resources"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    step_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("learning_roadmap_steps.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    step: Mapped["LearningRoadmapStep"] = relationship(
        "LearningRoadmapStep", back_populates="resources"
    )
    resource_progress: Mapped[list["LearningRoadmapResourceProgress"]] = relationship(
        "LearningRoadmapResourceProgress",
        back_populates="resource",
        cascade="all, delete-orphan",
    )


class LearningRoadmapResourceProgress(Base):
    """
    Tracks whether a specific user has completed a specific resource.
    One row per (user, resource). step_id is denormalized for fast
    per-step counting without an extra JOIN.
    """
    __tablename__ = "learning_roadmap_resource_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "resource_id", name="uq_user_resource_progress"),
        Index("ix_resource_progress_user_step", "user_id", "step_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    resource_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("learning_roadmap_step_resources.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Denormalized for fast step-level counting
    step_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("learning_roadmap_steps.id", ondelete="CASCADE"),
        nullable=False,
    )
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    resource: Mapped["LearningRoadmapStepResource"] = relationship(
        "LearningRoadmapStepResource", back_populates="resource_progress"
    )

    def __repr__(self) -> str:
        return (
            f"<LearningRoadmapResourceProgress("
            f"user={self.user_id}, resource={self.resource_id}, "
            f"completed={self.completed})>"
        )


class LearningRoadmapProgress(Base):
    __tablename__ = "learning_roadmap_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "step_id", name="uq_user_step_progress"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    step_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("learning_roadmap_steps.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="not_started", nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    step: Mapped["LearningRoadmapStep"] = relationship(
        "LearningRoadmapStep", back_populates="progress"
    )

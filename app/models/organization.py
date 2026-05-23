"""
Organization models — multi-tenant workspace for teams.

Tables:
  organizations            — the org entity itself
  organization_members     — membership join table (owner / member roles)
  organization_invites     — pending email invitations
  organization_roadmaps    — roadmaps shared across an org (reuses LearningRoadmap)
"""

import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import (
    String, Text, DateTime, ForeignKey,
    UniqueConstraint, Index, JSON, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.core.database import Base
from app.core.config import settings

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.roadmap import LearningRoadmap


# ---------------------------------------------------------------------------
# Organization
# ---------------------------------------------------------------------------

class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Identity
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Branding
    tagline: Mapped[str | None] = mapped_column(String(500), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Industry & services
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    core_services: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Web & social links
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Developer ecosystem
    github_orgs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    github_repos: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Extended social
    twitter_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Technology & products
    tech_stacks: Mapped[list | None] = mapped_column(JSON, nullable=True)   # ["React", "K8s", ...]
    products: Mapped[list | None] = mapped_column(JSON, nullable=True)       # [{name, type, url, repos[]}]

    # Additional company info
    headquarters: Mapped[str | None] = mapped_column(String(255), nullable=True)
    founded_year: Mapped[int | None] = mapped_column(nullable=True)
    company_size: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g. "1-10", "11-50"

    # Contact & mission
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mission_statement: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Custom metadata fields [{id, label, value}]
    custom_fields: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Semantic embedding for org discovery and advisor RAG context
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.EMBEDDING_DIMENSIONS), nullable=True
    )
    embedding_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending | completed | failed

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    members: Mapped[list["OrganizationMember"]] = relationship(
        "OrganizationMember", back_populates="organization",
        cascade="all, delete-orphan",
    )
    invites: Mapped[list["OrganizationInvite"]] = relationship(
        "OrganizationInvite", back_populates="organization",
        cascade="all, delete-orphan",
    )
    roadmaps: Mapped[list["OrganizationRoadmap"]] = relationship(
        "OrganizationRoadmap", back_populates="organization",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, legal_name={self.legal_name})>"


# ---------------------------------------------------------------------------
# OrganizationMember
# ---------------------------------------------------------------------------

class OrganizationMember(Base):
    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_member"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # org access role: "owner" | "admin" | "member"
    role: Mapped[str] = mapped_column(String(20), default="member", nullable=False)
    # job/team title set at invite time (e.g. "Frontend Engineer")
    job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="members"
    )
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<OrganizationMember(org={self.organization_id}, user={self.user_id}, role={self.role})>"


# ---------------------------------------------------------------------------
# OrganizationInvite
# ---------------------------------------------------------------------------

def _default_token() -> str:
    return secrets.token_urlsafe(32)

def _default_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=48)


class OrganizationInvite(Base):
    __tablename__ = "organization_invites"
    __table_args__ = (
        Index("ix_org_invite_token", "token", unique=True),
        Index("ix_org_invite_email", "email"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    invited_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    # free-text job/team title set by inviter (e.g. "Frontend Engineer")
    team_role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    token: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, default=_default_token
    )
    # "pending" | "accepted" | "expired" | "cancelled" | "declined"
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_default_expiry
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="invites"
    )

    def is_valid(self) -> bool:
        """True if the invite is pending and not yet expired."""
        return (
            self.status == "pending"
            and datetime.now(timezone.utc) < self.expires_at
        )

    def __repr__(self) -> str:
        return f"<OrganizationInvite(org={self.organization_id}, email={self.email}, status={self.status})>"


# ---------------------------------------------------------------------------
# OrganizationRoadmap  (links an existing LearningRoadmap to an org)
# ---------------------------------------------------------------------------

class OrganizationRoadmap(Base):
    __tablename__ = "organization_roadmaps"
    __table_args__ = (
        UniqueConstraint("organization_id", "roadmap_id", name="uq_org_roadmap"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    roadmap_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("learning_roadmaps.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="roadmaps"
    )
    roadmap: Mapped["LearningRoadmap"] = relationship("LearningRoadmap")

    def __repr__(self) -> str:
        return f"<OrganizationRoadmap(org={self.organization_id}, roadmap={self.roadmap_id})>"

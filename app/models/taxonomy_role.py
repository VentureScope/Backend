"""
TaxonomyRole model: canonical job title taxonomy stored in the database.
Accepted unmatched roles are appended here at runtime so that
title_normalization.py can read from DB instead of a static roles.json file.
"""

import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TaxonomyRole(Base):
    """
    A single canonical role in the job title taxonomy.
    Created when an admin accepts an unmatched_role via
    PATCH /api/admin/taxonomy/unmatched/{id}.
    """

    __tablename__ = "taxonomy_roles"
    __table_args__ = (UniqueConstraint("normalized_title", name="uq_taxonomy_roles_normalized_title"),)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # Human-readable display name, e.g. "Machine Learning Engineer"
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # Lowercase slug for matching, e.g. "machine learning engineer"
    normalized_title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # Optional category grouping, e.g. "Engineering"
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Source unmatched_role ID (Supabase) that triggered creation, for audit
    source_unmatched_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Admin email that accepted the role
    accepted_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<TaxonomyRole(id={self.id}, normalized_title={self.normalized_title})>"

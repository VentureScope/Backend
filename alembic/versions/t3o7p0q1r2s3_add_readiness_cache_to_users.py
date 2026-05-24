"""Add readiness_cache to users table

Revision ID: t3o7p0q1r2s3
Revises: s2n6o9p0q1r2
Create Date: 2026-05-24

Adds readiness_cache JSON column to users table.
Stores the LLM-computed career readiness score, invalidated when
skills/career_interest change or after 24 hours.
"""

from alembic import op
import sqlalchemy as sa

revision = "t3o7p0q1r2s3"
down_revision = "s2n6o9p0q1r2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("readiness_cache", sa.JSON, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "readiness_cache")

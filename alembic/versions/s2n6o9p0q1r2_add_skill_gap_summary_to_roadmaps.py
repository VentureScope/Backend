"""Add skill_gap_summary to learning_roadmaps

Revision ID: s2n6o9p0q1r2
Revises: r1m5n8o9p0q1
Create Date: 2026-05-24

Adds skill_gap_summary column — LLM-generated skill gap analysis
persisted at roadmap creation time.
"""

from alembic import op
import sqlalchemy as sa

revision = "s2n6o9p0q1r2"
down_revision = "r1m5n8o9p0q1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "learning_roadmaps",
        sa.Column("skill_gap_summary", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("learning_roadmaps", "skill_gap_summary")

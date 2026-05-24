"""Add trend_mode to learning_roadmaps

Revision ID: r1m5n8o9p0q1
Revises: q0l4m7n8o9p0
Create Date: 2026-05-24

Adds trend_mode column to learning_roadmaps:
  "current" — generated from today's market demand (default)
  "future"  — generated from projected/emerging market trends
"""

from alembic import op
import sqlalchemy as sa

revision = "r1m5n8o9p0q1"
down_revision = "q0l4m7n8o9p0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "learning_roadmaps",
        sa.Column(
            "trend_mode",
            sa.String(20),
            nullable=False,
            server_default="current",
        ),
    )


def downgrade() -> None:
    op.drop_column("learning_roadmaps", "trend_mode")

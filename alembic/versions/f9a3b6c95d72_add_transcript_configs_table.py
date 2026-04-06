"""Add transcript_configs table

Revision ID: f9a3b6c95d72
Revises: e8f2a5c94b61
Create Date: 2026-04-05

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "f9a3b6c95d72"
down_revision: Union[str, None] = "e8f2a5c94b61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create transcript_configs table for user-specific grading systems."""

    op.create_table(
        "transcript_configs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("gpa_scale", sa.Float(), nullable=False),
        sa.Column("grading_schema", postgresql.JSONB(), nullable=False),
        sa.Column("grade_display_order", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_transcript_config_user_id"),
    )

    # Create indexes for faster lookups
    op.create_index("ix_transcript_configs_user_id", "transcript_configs", ["user_id"])


def downgrade() -> None:
    """Drop transcript_configs table."""

    op.drop_index("ix_transcript_configs_user_id", table_name="transcript_configs")
    op.drop_table("transcript_configs")

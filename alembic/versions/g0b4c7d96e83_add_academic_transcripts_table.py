"""Add academic_transcripts table

Revision ID: g0b4c7d96e83
Revises: f9a3b6c95d72
Create Date: 2026-04-05

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "g0b4c7d96e83"
down_revision: Union[str, None] = "f9a3b6c95d72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create academic_transcripts table for e-student transcript data."""

    op.create_table(
        "academic_transcripts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("student_id", sa.String(), nullable=True),
        sa.Column("transcript_data", postgresql.JSONB(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.UniqueConstraint("user_id", "version", name="uq_user_version"),
    )

    # Create indexes for faster lookups
    op.create_index(
        "ix_academic_transcripts_user_id", "academic_transcripts", ["user_id"]
    )
    op.create_index(
        "ix_academic_transcripts_student_id", "academic_transcripts", ["student_id"]
    )
    op.create_index(
        "ix_academic_transcripts_user_version",
        "academic_transcripts",
        ["user_id", "version"],
    )


def downgrade() -> None:
    """Drop academic_transcripts table."""

    op.drop_index(
        "ix_academic_transcripts_user_version", table_name="academic_transcripts"
    )
    op.drop_index(
        "ix_academic_transcripts_student_id", table_name="academic_transcripts"
    )
    op.drop_index("ix_academic_transcripts_user_id", table_name="academic_transcripts")
    op.drop_table("academic_transcripts")

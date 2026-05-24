"""Add updated_at to resumes table

Revision ID: u4p8q1r2s3t4
Revises: t3o7p0q1r2s3
Create Date: 2026-05-24

Adds updated_at column to resumes table to support the edit endpoint.
"""

from alembic import op
import sqlalchemy as sa

revision = "u4p8q1r2s3t4"
down_revision = "t3o7p0q1r2s3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "resumes",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_column("resumes", "updated_at")

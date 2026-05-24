"""Add certificates table

Revision ID: v5q9r2s3t4u5
Revises: u4p8q1r2s3t4
Create Date: 2026-05-24

Creates the certificates table for storing user professional certifications.
"""

from alembic import op
import sqlalchemy as sa

revision = "v5q9r2s3t4u5"
down_revision = "u4p8q1r2s3t4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "certificates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id", sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("issuer", sa.String(255), nullable=False),
        sa.Column("credential_id", sa.String(255), nullable=True),
        sa.Column("credential_url", sa.String(1000), nullable=True),
        sa.Column("issue_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expiry_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_certificates_user_id", "certificates", ["user_id"])


def downgrade() -> None:
    op.drop_table("certificates")

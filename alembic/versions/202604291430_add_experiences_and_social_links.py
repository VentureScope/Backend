"""add_experiences_and_social_links

Revision ID: auto_202604291430
Revises: c1d2e3f4a567
Create Date: 2026-04-29 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "auto_202604291430"
down_revision = "c1d2e3f4a567"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create experiences table
    op.create_table(
        "experiences",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_title", sa.String(255), nullable=False),
        sa.Column("company", sa.String(255), nullable=False),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("description", sa.String(2000), nullable=True),
        sa.Column("skills_used", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Index("ix_experiences_user_id", "user_id"),
    )

    # Add social_links column to users table
    op.add_column(
        "users",
        sa.Column("social_links", sa.String(2000), nullable=True),
    )


def downgrade() -> None:
    # Drop experiences table
    op.drop_table("experiences")

    # Drop social_links column from users
    op.drop_column("users", "social_links")

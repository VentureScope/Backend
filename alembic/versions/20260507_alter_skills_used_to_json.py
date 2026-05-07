"""alter_skills_used_to_json

Revision ID: auto_20260507
Revises: auto_202604291430
Create Date: 2026-05-07 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "auto_20260507"
down_revision = "auto_202604291430"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Change skills_used column from VARCHAR to JSON."""
    op.alter_column(
        "experiences",
        "skills_used",
        existing_type=sa.String(1000),
        type_=sa.JSON(),
        existing_nullable=True,
    )


def downgrade() -> None:
    """Revert skills_used column from JSON to VARCHAR."""
    op.alter_column(
        "experiences",
        "skills_used",
        existing_type=sa.JSON(),
        type_=sa.String(1000),
        existing_nullable=True,
    )

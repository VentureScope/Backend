"""Add is_active and is_admin fields to users table

Revision ID: b2f8a3c91d45
Revises: 93e091e52124
Create Date: 2026-04-03

Phase B: User Management CRUD - Database Schema Update
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2f8a3c91d45"
down_revision: Union[str, None] = "93e091e52124"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_active and is_admin boolean columns to users table."""
    # Add is_active column with default True (existing users are active)
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )

    # Add is_admin column with default False (existing users are not admins)
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    """Remove is_active and is_admin columns from users table."""
    op.drop_column("users", "is_admin")
    op.drop_column("users", "is_active")

"""add deactivated_at to users

Revision ID: q0l4m7n8o9p0
Revises: p9k3l6m7n8o9
Create Date: 2026-05-24

Adds a nullable deactivated_at timestamptz column to the users table.
Set when is_active is flipped to False (self-service or admin),
NULL for all currently active users.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "q0l4m7n8o9p0"
down_revision: Union[str, None] = "p9k3l6m7n8o9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "deactivated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_users_deactivated_at",
        "users",
        ["deactivated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_users_deactivated_at", table_name="users")
    op.drop_column("users", "deactivated_at")

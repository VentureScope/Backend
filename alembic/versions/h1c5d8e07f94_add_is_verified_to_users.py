"""Add is_verified column to users table

Revision ID: h1c5d8e07f94
Revises: g0b4c7d96e83
Create Date: 2026-05-12

Adds `is_verified` (Boolean, NOT NULL, default False) to the users table.

Migration strategy for existing rows:
  - All existing users are backfilled to is_verified=True so that no
    currently active account is unexpectedly locked out after deployment.
  - Only newly registered users (created after this migration) will start
    with is_verified=False and must complete OTP verification.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision: str = "h1c5d8e07f94"
down_revision: Union[str, None] = "g0b4c7d96e83"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add column as nullable first to allow the backfill below
    op.add_column(
        "users",
        sa.Column("is_verified", sa.Boolean(), nullable=True),
    )

    # Backfill: mark all pre-existing users as verified so they are not
    # locked out after the deployment.
    op.execute("UPDATE users SET is_verified = TRUE")

    # Now tighten the constraint: disallow NULL, default False for new rows
    op.alter_column(
        "users",
        "is_verified",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.text("FALSE"),
    )


def downgrade() -> None:
    op.drop_column("users", "is_verified")

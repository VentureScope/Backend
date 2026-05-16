"""Add MFA columns to users table

Revision ID: j3e7f0a19h26
Revises: i2d6e9f08g05
Create Date: 2026-05-15

Adds `mfa_enabled` (Boolean, NOT NULL, default False) and
`mfa_enrolled_at` (TIMESTAMPTZ, nullable) to the users table.

These columns track MFA status at the application level for display/UX
purposes. The source of truth for factor validity is the internal TOTP
store managed by the backend MFA service.

Migration strategy:
  - All existing users default to mfa_enabled=False.
  - mfa_enrolled_at is nullable (NULL means never enrolled).
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision: str = "j3e7f0a19h26"
down_revision: Union[str, None] = "i2d6e9f08g05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add mfa_enabled with a default of FALSE for all existing rows
    op.add_column(
        "users",
        sa.Column(
            "mfa_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
    )

    # Add mfa_enrolled_at as nullable timestamp
    op.add_column(
        "users",
        sa.Column(
            "mfa_enrolled_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "mfa_enrolled_at")
    op.drop_column("users", "mfa_enabled")

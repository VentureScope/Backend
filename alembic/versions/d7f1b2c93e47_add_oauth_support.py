"""Add OAuth support for Google authentication

Revision ID: d7f1b2c93e47
Revises: c3d9f4a82e56
Create Date: 2026-04-04

OAuth Support: Adds OAuth account management and updates user model for OAuth authentication.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision: str = "d7f1b2c93e47"
down_revision: Union[str, None] = "c3d9f4a82e56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add OAuth support to the database."""

    # 1. Create OAuth accounts table
    op.create_table(
        "oauth_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_account_id", sa.String(255), nullable=False),
        sa.Column("provider_email", sa.String(255), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_data", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "provider", "provider_account_id", name="unique_provider_account"
        ),
    )

    # 2. Add indexes for OAuth accounts
    op.create_index("ix_oauth_accounts_user_id", "oauth_accounts", ["user_id"])
    op.create_index("ix_oauth_accounts_provider", "oauth_accounts", ["provider"])

    # 3. Update users table for OAuth support
    op.alter_column(
        "users", "password_hash", nullable=True
    )  # Make password optional for OAuth users
    op.add_column(
        "users", sa.Column("profile_picture_url", sa.String(500), nullable=True)
    )
    op.add_column("users", sa.Column("oauth_provider", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("oauth_id", sa.String(255), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # 4. Add index for OAuth lookup
    op.create_index(
        "ix_users_oauth_provider_id", "users", ["oauth_provider", "oauth_id"]
    )


def downgrade() -> None:
    """Remove OAuth support from the database."""

    # Remove indexes
    op.drop_index("ix_users_oauth_provider_id", "users")
    op.drop_index("ix_oauth_accounts_provider", "oauth_accounts")
    op.drop_index("ix_oauth_accounts_user_id", "oauth_accounts")

    # Remove OAuth columns from users table
    op.drop_column("users", "email_verified")
    op.drop_column("users", "oauth_id")
    op.drop_column("users", "oauth_provider")
    op.drop_column("users", "profile_picture_url")

    # Restore password_hash as required (note: this will fail if OAuth users exist)
    op.alter_column("users", "password_hash", nullable=False)

    # Drop OAuth accounts table
    op.drop_table("oauth_accounts")

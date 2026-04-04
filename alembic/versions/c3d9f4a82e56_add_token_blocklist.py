"""Add token_blocklist table for logout functionality

Revision ID: c3d9f4a82e56
Revises: b2f8a3c91d45
Create Date: 2026-04-03

Token Blocklist: Stores invalidated JWT tokens for secure logout.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d9f4a82e56"
down_revision: Union[str, None] = "b2f8a3c91d45"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create token_blocklist table."""
    op.create_table(
        "token_blocklist",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("jti", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # Index for fast JTI lookups during authentication
    op.create_index("ix_token_blocklist_jti", "token_blocklist", ["jti"], unique=True)
    # Index for cleanup queries
    op.create_index("ix_token_blocklist_expires_at", "token_blocklist", ["expires_at"])


def downgrade() -> None:
    """Drop token_blocklist table."""
    op.drop_index("ix_token_blocklist_expires_at", table_name="token_blocklist")
    op.drop_index("ix_token_blocklist_jti", table_name="token_blocklist")
    op.drop_table("token_blocklist")

"""Add github sync snapshots table

Revision ID: e8a1f4c2d9b7
Revises: d7f1b2c93e47
Create Date: 2026-04-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e8a1f4c2d9b7"
down_revision: Union[str, None] = "d7f1b2c93e47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "github_sync_snapshots",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("github_username", sa.String(255), nullable=True),
        sa.Column("repositories_json", sa.Text(), nullable=False),
        sa.Column("contributions_json", sa.Text(), nullable=False),
        sa.Column("organizations_json", sa.Text(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_github_sync_snapshots_user_id"),
    )
    op.create_index(
        "ix_github_sync_snapshots_user_id",
        "github_sync_snapshots",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_github_sync_snapshots_user_id", table_name="github_sync_snapshots")
    op.drop_table("github_sync_snapshots")

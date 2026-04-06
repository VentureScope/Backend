"""Merge github sync snapshot and github_username backfill heads

Revision ID: f3b7c1d2e9a4
Revises: e8a1f4c2d9b7, e8f2a5c94b61
Create Date: 2026-04-07
"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "f3b7c1d2e9a4"
down_revision: Union[str, Sequence[str], None] = (
    "e8a1f4c2d9b7",
    "e8f2a5c94b61",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge-only revision; no schema changes."""
    pass


def downgrade() -> None:
    """No-op downgrade for merge-only revision."""
    pass

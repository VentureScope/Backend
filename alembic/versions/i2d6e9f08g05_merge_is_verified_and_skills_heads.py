"""Merge is_verified and skills/experiences heads

Revision ID: i2d6e9f08g05
Revises: h1c5d8e07f94, auto_20260507
Create Date: 2026-05-12

Merges two divergent branches:
  - h1c5d8e07f94 (add_is_verified_to_users)
  - auto_20260507 (alter_skills_used_to_json / experiences)
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision: str = "i2d6e9f08g05"
down_revision: Union[str, Sequence[str], None] = ("h1c5d8e07f94", "auto_20260507")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

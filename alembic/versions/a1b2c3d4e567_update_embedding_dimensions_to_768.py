"""update_embedding_dimensions_to_768

Revision ID: a1b2c3d4e567
Revises: g0b4c7d96e83
Create Date: 2026-04-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e567"
down_revision: Union[str, Sequence[str], None] = ("g0b4c7d96e83", "ad65d55cc035")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN embedding TYPE vector(768);")
    op.execute("ALTER TABLE user_knowledge ALTER COLUMN embedding TYPE vector(768);")


def downgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN embedding TYPE vector(1536);")
    op.execute("ALTER TABLE user_knowledge ALTER COLUMN embedding TYPE vector(1536);")
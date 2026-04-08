"""merge_heads

Revision ID: 4b5fd2f8b761
Revises: 3f017b455d16, f3b7c1d2e9a4
Create Date: 2026-04-07 23:17:45.017446+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4b5fd2f8b761'
down_revision: Union[str, None] = ('3f017b455d16', 'f3b7c1d2e9a4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

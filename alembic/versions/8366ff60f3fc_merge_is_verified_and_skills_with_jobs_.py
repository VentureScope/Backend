"""merge is_verified_and_skills with jobs_roadmap_embedding

Revision ID: 8366ff60f3fc
Revises: i2d6e9f08g05, auto_20260515
Create Date: 2026-05-14 20:12:45.266414+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8366ff60f3fc'
down_revision: Union[str, None] = ('i2d6e9f08g05', 'auto_20260515')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

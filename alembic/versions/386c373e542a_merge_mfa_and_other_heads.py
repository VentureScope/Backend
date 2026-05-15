"""merge mfa and other heads

Revision ID: 386c373e542a
Revises: 8366ff60f3fc, j3e7f0a19h26
Create Date: 2026-05-15 22:41:00.750371+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '386c373e542a'
down_revision: Union[str, None] = ('8366ff60f3fc', 'j3e7f0a19h26')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

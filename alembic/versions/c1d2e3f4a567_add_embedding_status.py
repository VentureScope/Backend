"""add_embedding_status_to_users_and_knowledge

Revision ID: c1d2e3f4a567
Revises: b2c3d4e5f678
Create Date: 2026-04-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1d2e3f4a567"
down_revision: Union[str, None] = "b2c3d4e5f678"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('embedding_status', sa.String(20), nullable=False, server_default='pending'))
    op.add_column('user_knowledge', sa.Column('embedding_status', sa.String(20), nullable=False, server_default='pending'))


def downgrade() -> None:
    op.drop_column('user_knowledge', 'embedding_status')
    op.drop_column('users', 'embedding_status')
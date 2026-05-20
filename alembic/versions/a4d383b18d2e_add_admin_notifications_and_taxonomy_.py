"""add_admin_notifications_and_taxonomy_roles

Revision ID: a4d383b18d2e
Revises: 386c373e542a
Create Date: 2026-05-19 05:35:40.435012+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a4d383b18d2e'
down_revision: Union[str, None] = '386c373e542a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- admin_notifications ---
    op.create_table(
        'admin_notifications',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_admin_notifications_source', 'admin_notifications', ['source'], unique=False)
    op.create_index('ix_admin_notifications_created_at', 'admin_notifications', ['created_at'], unique=False)

    # --- taxonomy_roles ---
    op.create_table(
        'taxonomy_roles',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('normalized_title', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('source_unmatched_id', sa.String(length=36), nullable=True),
        sa.Column('accepted_by', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('normalized_title', name='uq_taxonomy_roles_normalized_title'),
    )
    op.create_index('ix_taxonomy_roles_normalized_title', 'taxonomy_roles', ['normalized_title'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_taxonomy_roles_normalized_title', table_name='taxonomy_roles')
    op.drop_table('taxonomy_roles')

    op.drop_index('ix_admin_notifications_created_at', table_name='admin_notifications')
    op.drop_index('ix_admin_notifications_source', table_name='admin_notifications')
    op.drop_table('admin_notifications')

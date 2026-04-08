"""add_skills_and_cv_url

Revision ID: 35d5958cfe86
Revises: 4b5fd2f8b761
Create Date: 2026-04-07 23:17:50.628006+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '35d5958cfe86'
down_revision: Union[str, None] = '4b5fd2f8b761'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add skills column (JSON array of strings)
    op.add_column('users', sa.Column('skills', sa.JSON(), nullable=True))
    # Add cv_url column (S3 URL for CV)
    op.add_column('users', sa.Column('cv_url', sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'cv_url')
    op.drop_column('users', 'skills')

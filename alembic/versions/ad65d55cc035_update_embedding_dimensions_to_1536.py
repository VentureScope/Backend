"""update_embedding_dimensions_to_1536

Revision ID: ad65d55cc035
Revises: 17d98104cc07
Create Date: 2026-04-05 11:23:44.965087+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ad65d55cc035'
down_revision: Union[str, None] = '17d98104cc07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Update the pgvector dimensions size from 384 to 1536
    op.execute("ALTER TABLE users ALTER COLUMN embedding TYPE vector(1536);")


def downgrade() -> None:
    # Revert back to 384 dimensions
    op.execute("ALTER TABLE users ALTER COLUMN embedding TYPE vector(384);")

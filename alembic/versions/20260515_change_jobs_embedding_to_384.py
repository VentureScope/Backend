"""change_jobs_embedding_to_384

Revision ID: auto_20260515
Revises: auto_20260514
Create Date: 2026-05-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers
revision = "auto_20260515"
down_revision = "auto_20260514"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "jobs",
        "embedding",
        type_=Vector(384),
        postgresql_using="embedding::vector(384)",
    )


def downgrade() -> None:
    op.alter_column(
        "jobs",
        "embedding",
        type_=Vector(768),
        postgresql_using="embedding::vector(768)",
    )

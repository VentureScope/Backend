"""Add embedding columns to organizations table

Revision ID: m6h0i3j4k5l6
Revises: l5g9h2i3j4k5
Create Date: 2026-05-20

Adds:
  - organizations.embedding   (vector)
  - organizations.embedding_status (varchar)
"""

from alembic import op
import sqlalchemy as sa

revision = "m6h0i3j4k5l6"
down_revision = "l5g9h2i3j4k5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure pgvector extension exists
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Add embedding column — dimension matches EMBEDDING_DIMENSIONS setting (384)
    op.add_column(
        "organizations",
        sa.Column(
            "embedding",
            sa.String,  # placeholder — overridden below with raw DDL
            nullable=True,
        ),
    )
    # Replace with proper vector type (pgvector)
    op.execute("ALTER TABLE organizations DROP COLUMN embedding")
    op.execute("ALTER TABLE organizations ADD COLUMN embedding vector(384)")

    op.add_column(
        "organizations",
        sa.Column(
            "embedding_status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
    )

    # Index for fast similarity search
    op.execute(
        "CREATE INDEX ix_organizations_embedding ON organizations "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_organizations_embedding")
    op.drop_column("organizations", "embedding_status")
    op.drop_column("organizations", "embedding")

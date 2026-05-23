"""Add learning_roadmap_resource_progress table

Revision ID: p9k3l6m7n8o9
Revises: o8j2k5l6m7n8
Create Date: 2026-05-23

Tracks per-user, per-resource completion state.
When all resources in a step are completed the step auto-completes.
"""

from alembic import op
import sqlalchemy as sa

revision = "p9k3l6m7n8o9"
down_revision = "o8j2k5l6m7n8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_roadmap_resource_progress",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id", sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "resource_id", sa.String(36),
            sa.ForeignKey("learning_roadmap_step_resources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Denormalized for fast step-level counting
        sa.Column(
            "step_id", sa.String(36),
            sa.ForeignKey("learning_roadmap_steps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("completed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "resource_id", name="uq_user_resource_progress"),
    )
    op.create_index(
        "ix_resource_progress_user_id",
        "learning_roadmap_resource_progress", ["user_id"]
    )
    op.create_index(
        "ix_resource_progress_resource_id",
        "learning_roadmap_resource_progress", ["resource_id"]
    )
    # Composite index for fast step-level counting
    op.create_index(
        "ix_resource_progress_user_step",
        "learning_roadmap_resource_progress", ["user_id", "step_id"]
    )


def downgrade() -> None:
    op.drop_table("learning_roadmap_resource_progress")

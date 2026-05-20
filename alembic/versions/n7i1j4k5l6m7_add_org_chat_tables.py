"""Add org chat tables

Revision ID: n7i1j4k5l6m7
Revises: m6h0i3j4k5l6
Create Date: 2026-05-20

Creates:
  - org_chat_sessions
  - org_chat_messages
"""

from alembic import op
import sqlalchemy as sa

revision = "n7i1j4k5l6m7"
down_revision = "m6h0i3j4k5l6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # org_chat_sessions
    # ------------------------------------------------------------------
    op.create_table(
        "org_chat_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "org_id", sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by", sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False, server_default="New Chat"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_org_chat_sessions_org_id", "org_chat_sessions", ["org_id"])
    op.create_index("ix_org_chat_sessions_created_by", "org_chat_sessions", ["created_by"])

    # ------------------------------------------------------------------
    # org_chat_messages
    # ------------------------------------------------------------------
    op.create_table(
        "org_chat_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id", sa.String(36),
            sa.ForeignKey("org_chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_org_chat_messages_session_id", "org_chat_messages", ["session_id"])


def downgrade() -> None:
    op.drop_table("org_chat_messages")
    op.drop_table("org_chat_sessions")

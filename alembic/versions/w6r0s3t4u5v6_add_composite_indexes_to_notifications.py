"""Add composite indexes to notifications table

Revision ID: w6r0s3t4u5v6
Revises: v5q9r2s3t4u5
Create Date: 2026-05-31

Adds two composite indexes on the notifications table to speed up the
most frequent query patterns:

  1. (user_id, created_at DESC) — covers the paginated list query that
     filters by user and orders by recency.  Replaces the two single-column
     indexes that force the planner to intersect results.

  2. (user_id, is_read) — covers the unread-count scalar query and the
     unread_only filter path.  Without this index every unread check does
     a full scan over all of a user's notifications.

The existing single-column ix_notifications_user_id and
ix_notifications_created_at indexes are kept because other queries
(e.g. admin tooling, websocket fan-out) may still benefit from them.
"""

from alembic import op


def upgrade() -> None:
    op.create_index(
        "ix_notifications_user_created",
        "notifications",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_notifications_user_is_read",
        "notifications",
        ["user_id", "is_read"],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_is_read", table_name="notifications")
    op.drop_index("ix_notifications_user_created", table_name="notifications")

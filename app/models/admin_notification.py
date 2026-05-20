"""
AdminNotification model: stores admin-facing alerts from ML pipeline and Sentry webhooks.
"""

import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Boolean, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AdminNotification(Base):
    """
    A single admin notification record.
    Created by:
      - POST /api/admin/notifications  (ML pipeline webhook)
      - POST /api/admin/sentry-webhook (Sentry alert webhook)
    """

    __tablename__ = "admin_notifications"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # "pipeline" | "sentry"
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # e.g. "training_complete", "error", "rate_threshold"
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Extra data: run_id, sentry issue URL, model_type, etc.
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    def __repr__(self) -> str:
        return (
            f"<AdminNotification(id={self.id}, source={self.source}, "
            f"event_type={self.event_type}, read={self.is_read})>"
        )

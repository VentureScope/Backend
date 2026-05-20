"""
OrgChatSession and OrgChatMessage — AI advisor chat scoped to an organization.

Each org member can have their own private chat sessions with the org advisor.
Sessions are NOT shared across members (private to the creator).
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class OrgChatSession(Base):
    """A private conversation thread between one member and the org AI advisor."""

    __tablename__ = "org_chat_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    org_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(255), nullable=False, default="New Chat"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    messages: Mapped[list["OrgChatMessage"]] = relationship(
        "OrgChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="OrgChatMessage.created_at",
    )

    def __repr__(self) -> str:
        return f"<OrgChatSession(id={self.id}, org={self.org_id}, user={self.created_by})>"


class OrgChatMessage(Base):
    """A single message in an OrgChatSession."""

    __tablename__ = "org_chat_messages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("org_chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # user_id is set for "user" role messages; null for "assistant"
    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped["OrgChatSession"] = relationship(
        "OrgChatSession", back_populates="messages"
    )

    def __repr__(self) -> str:
        return f"<OrgChatMessage(id={self.id}, role={self.role}, session={self.session_id})>"

"""
Pydantic schemas for Chat Sessions and Messages.
"""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# Message schemas
# ─────────────────────────────────────────────

class ChatMessageResponse(BaseModel):
    id: str
    session_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# Session schemas
# ─────────────────────────────────────────────

class ChatSessionCreate(BaseModel):
    title: str = Field(default="New Chat", max_length=255)


class ChatSessionUpdate(BaseModel):
    title: str = Field(max_length=255)


class ChatSessionResponse(BaseModel):
    id: str
    user_id: str
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatSessionWithMessages(ChatSessionResponse):
    messages: list[ChatMessageResponse] = []


# ─────────────────────────────────────────────
# WebSocket message envelope (sent by client)
# ─────────────────────────────────────────────

class WSIncomingMessage(BaseModel):
    """JSON the client sends over the WebSocket."""
    message: str = Field(min_length=1, max_length=2000)


# ─────────────────────────────────────────────
# WebSocket event envelopes (sent by server)
# ─────────────────────────────────────────────

class WSChunkEvent(BaseModel):
    event: Literal["chunk"] = "chunk"
    data: str  # streamed text fragment


class WSDoneEvent(BaseModel):
    event: Literal["done"] = "done"
    message_id: str   # saved assistant message id


class WSErrorEvent(BaseModel):
    event: Literal["error"] = "error"
    detail: str

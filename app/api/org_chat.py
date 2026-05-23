"""
Organization AI Advisor Chat API.

HTTP CRUD + WebSocket endpoint for org-scoped AI advisor conversations.

Routes:
  POST   /api/organizations/{org_id}/chat/sessions          Create session
  GET    /api/organizations/{org_id}/chat/sessions          List my sessions
  GET    /api/organizations/{org_id}/chat/sessions/{id}     Get session + messages
  PATCH  /api/organizations/{org_id}/chat/sessions/{id}     Rename session
  DELETE /api/organizations/{org_id}/chat/sessions/{id}     Delete session
  WS     /api/organizations/{org_id}/chat/ws/{session_id}?token=...

WebSocket frames (identical to personal chat):
  Client → Server: { "message": "..." }
  Server → Client:
    { "event": "chunk",  "data": "..." }
    { "event": "done",   "message_id": "..." }
    { "event": "error",  "detail": "..." }
"""

import json
import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db, AsyncSessionLocal
from app.core.security import decode_access_token_with_details
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.repositories.token_repository import TokenRepository
from app.services.org_chat_service import OrgChatService

router = APIRouter(tags=["org-chat"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas (inline — lightweight)
# ---------------------------------------------------------------------------

class OrgChatSessionCreate(BaseModel):
    title: str = "New Chat"


class OrgChatSessionUpdate(BaseModel):
    title: str


class OrgChatSessionOut(BaseModel):
    id: str
    org_id: str
    created_by: str
    title: str
    created_at: object
    updated_at: object

    model_config = {"from_attributes": True}


class OrgChatMessageOut(BaseModel):
    id: str
    session_id: str
    user_id: str | None
    role: str
    content: str
    created_at: object

    model_config = {"from_attributes": True}


class OrgChatSessionWithMessages(BaseModel):
    id: str
    org_id: str
    created_by: str
    title: str
    created_at: object
    updated_at: object
    messages: list[OrgChatMessageOut] = []

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# HTTP — Session CRUD
# ---------------------------------------------------------------------------

@router.post(
    "/api/organizations/{org_id}/chat/sessions",
    response_model=OrgChatSessionOut,
    status_code=201,
)
async def create_org_chat_session(
    org_id: str,
    body: OrgChatSessionCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Create a new private org advisor chat session."""
    svc = OrgChatService(db)
    return await svc.create_session(org_id, current_user.id, title=body.title)


@router.get(
    "/api/organizations/{org_id}/chat/sessions",
    response_model=list[OrgChatSessionOut],
)
async def list_org_chat_sessions(
    org_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
):
    """List all your private org advisor sessions (newest first)."""
    svc = OrgChatService(db)
    sessions, _ = await svc.list_sessions(
        org_id, current_user.id, page=page, per_page=per_page
    )
    return sessions


@router.get(
    "/api/organizations/{org_id}/chat/sessions/{session_id}",
    response_model=OrgChatSessionWithMessages,
)
async def get_org_chat_session(
    org_id: str,
    session_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Get a specific session including its full message history."""
    svc = OrgChatService(db)
    try:
        session = await svc.get_session(org_id, session_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Load messages
    messages = await svc.repo.get_messages(session_id, limit=200)
    return OrgChatSessionWithMessages(
        id=session.id,
        org_id=session.org_id,
        created_by=session.created_by,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[
            OrgChatMessageOut(
                id=m.id,
                session_id=m.session_id,
                user_id=m.user_id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
            )
            for m in messages
        ],
    )


@router.patch(
    "/api/organizations/{org_id}/chat/sessions/{session_id}",
    response_model=OrgChatSessionOut,
)
async def rename_org_chat_session(
    org_id: str,
    session_id: str,
    body: OrgChatSessionUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Rename an org advisor chat session."""
    svc = OrgChatService(db)
    try:
        session = await svc.rename_session(org_id, session_id, current_user.id, body.title)
        await db.commit()
        return session
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/api/organizations/{org_id}/chat/sessions/{session_id}",
    status_code=204,
)
async def delete_org_chat_session(
    org_id: str,
    session_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Delete an org advisor chat session and all its messages."""
    svc = OrgChatService(db)
    try:
        await svc.delete_session(org_id, session_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------------------
# WebSocket — Real-time org advisor chat
# ---------------------------------------------------------------------------

async def _authenticate_ws(token: str) -> User | None:
    """Authenticate WebSocket via JWT query param."""
    token_result = decode_access_token_with_details(token)
    if not token_result.is_valid:
        return None

    async with AsyncSessionLocal() as db:
        token_repo = TokenRepository(db)
        if await token_repo.is_blocklisted(token_result.payload.jti):
            return None

        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(token_result.payload.sub)
        if not user or not user.is_active:
            return None
        return user


@router.websocket("/api/organizations/{org_id}/chat/ws/{session_id}")
async def org_chat_websocket(
    websocket: WebSocket,
    org_id: str,
    session_id: str,
    token: str = Query(..., description="JWT access token"),
):
    """
    Real-time org advisor WebSocket.

    Connect: ws://host/api/organizations/{org_id}/chat/ws/{session_id}?token=<JWT>

    Client sends:  { "message": "your question" }
    Server sends:
      { "event": "chunk",  "data": "..." }      — token by token
      { "event": "done",   "message_id": "..." } — reply complete
      { "event": "error",  "detail": "..." }     — on error
    """
    # 1. Authenticate
    user = await _authenticate_ws(token)
    if not user:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                payload = json.loads(raw)
                user_message = payload.get("message", "").strip()
                if not user_message:
                    await websocket.send_json({"event": "error", "detail": "Empty message"})
                    continue
            except (json.JSONDecodeError, AttributeError):
                await websocket.send_json({"event": "error", "detail": "Invalid JSON"})
                continue

            # 2. Stream reply
            async with AsyncSessionLocal() as db:
                svc = OrgChatService(db)

                async def send_chunk(chunk: str) -> None:
                    await websocket.send_json({"event": "chunk", "data": chunk})

                try:
                    assistant_msg = await svc.stream_reply(
                        org_id=org_id,
                        user_id=user.id,
                        session_id=session_id,
                        user_message=user_message,
                        on_chunk=send_chunk,
                    )
                    await websocket.send_json(
                        {"event": "done", "message_id": assistant_msg.id}
                    )
                except ValueError as e:
                    await websocket.send_json({"event": "error", "detail": str(e)})
                except RuntimeError as e:
                    await websocket.send_json(
                        {"event": "error", "detail": "AI service error. Please try again."}
                    )
                    logger.error("Org chat stream error: %s", e)

    except WebSocketDisconnect:
        logger.info("Org WS disconnected: user=%s org=%s session=%s", user.id, org_id, session_id)

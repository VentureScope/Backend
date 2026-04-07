"""
Chat API – HTTP CRUD endpoints + WebSocket endpoint.

Routes
------
POST   /api/chat/sessions                – create a new session
GET    /api/chat/sessions                – list sessions (paginated)
GET    /api/chat/sessions/{id}           – get session with full message history
PATCH  /api/chat/sessions/{id}           – rename session
DELETE /api/chat/sessions/{id}           – delete session

WS     /api/chat/ws/{session_id}?token=… – real-time chat

WebSocket protocol (JSON frames):
  Client → Server: { "message": "…" }
  Server → Client:
    { "event": "chunk",  "data": "…" }                   (streamed fragment)
    { "event": "done",   "message_id": "…" }              (reply complete)
    { "event": "error",  "detail": "…" }                  (on error)
    { "event": "notification", "data": { … } }            (pushed by AI)
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
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db, AsyncSessionLocal
from app.core.security import decode_access_token_with_details
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.repositories.token_repository import TokenRepository
from app.schemas.chat import (
    ChatSessionCreate,
    ChatSessionUpdate,
    ChatSessionResponse,
    ChatSessionWithMessages,
    ChatMessageResponse,
)
from app.services.chat_service import ChatService
from app.services.websocket_manager import ws_manager

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# HTTP – Session CRUD
# ──────────────────────────────────────────────────────────────

@router.post("/sessions", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: ChatSessionCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a new chat session for the authenticated user."""
    service = ChatService(db)
    session = await service.create_session(current_user.id, title=body.title)
    await db.commit()
    return session


@router.get("/sessions", response_model=list[ChatSessionResponse])
async def list_sessions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
):
    """List the current user's chat sessions, newest first."""
    service = ChatService(db)
    sessions, _ = await service.list_sessions(current_user.id, page=page, per_page=per_page)
    return sessions


@router.get("/sessions/{session_id}", response_model=ChatSessionWithMessages)
async def get_session(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get a specific session including its full message history."""
    service = ChatService(db)
    try:
        return await service.get_session(session_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/sessions/{session_id}", response_model=ChatSessionResponse)
async def rename_session(
    session_id: str,
    body: ChatSessionUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Rename a chat session."""
    service = ChatService(db)
    try:
        session = await service.rename_session(session_id, current_user.id, body.title)
        await db.commit()
        return session
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete a chat session and all its messages."""
    service = ChatService(db)
    try:
        await service.delete_session(session_id, current_user.id)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ──────────────────────────────────────────────────────────────
# WebSocket – Real-time chat
# ──────────────────────────────────────────────────────────────

async def _authenticate_ws(token: str) -> User | None:
    """
    Authenticate a WebSocket connection using a JWT passed as a query param.
    Returns the User ORM object or None if authentication fails.
    """
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


@router.websocket("/ws/{session_id}")
async def chat_websocket(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(..., description="JWT access token for authentication"),
):
    """
    Real-time chat WebSocket endpoint.

    Connect: ws://host/api/chat/ws/{session_id}?token=<JWT>

    Client sends:  { "message": "your question here" }
    Server sends:
      { "event": "chunk",  "data": "…" }       — token by token
      { "event": "done",   "message_id": "…" } — when reply is complete
      { "event": "error",  "detail": "…" }     — on any error
      { "event": "notification", "data": {…} } — pushed automatically
    """
    # 1. Authenticate before accepting connection
    user = await _authenticate_ws(token)
    if not user:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # 2. Register the connection
    await ws_manager.connect(user.id, session_id, websocket)

    try:
        while True:
            # 3. Wait for the next message from the client
            raw = await websocket.receive_text()

            try:
                payload = json.loads(raw)
                user_message = payload.get("message", "").strip()
                if not user_message:
                    await websocket.send_json(
                        {"event": "error", "detail": "Empty message"}
                    )
                    continue
            except (json.JSONDecodeError, AttributeError):
                await websocket.send_json(
                    {"event": "error", "detail": "Invalid JSON payload"}
                )
                continue

            # 4. Stream the LLM reply
            async with AsyncSessionLocal() as db:
                service = ChatService(db)

                async def send_chunk(chunk: str) -> None:
                    await websocket.send_json({"event": "chunk", "data": chunk})

                try:
                    assistant_msg = await service.stream_reply(
                        user=user,
                        session_id=session_id,
                        user_message=user_message,
                        on_chunk=send_chunk,
                    )
                    await db.commit()

                    # 5. Signal completion
                    await websocket.send_json(
                        {"event": "done", "message_id": assistant_msg.id}
                    )

                except ValueError as e:
                    await websocket.send_json({"event": "error", "detail": str(e)})
                except RuntimeError as e:
                    await websocket.send_json(
                        {"event": "error", "detail": "AI service error. Please try again."}
                    )
                    logger.error(f"Chat stream error: {e}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: user={user.id} session={session_id}")
    finally:
        ws_manager.disconnect(user.id, session_id)

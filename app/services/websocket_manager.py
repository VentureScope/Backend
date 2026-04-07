"""
WebSocket Connection Manager.

Tracks active WebSocket connections per user so that the notification
service can push real-time events (e.g. "new AI reply") to connected clients.
"""

import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    In-memory registry of active WebSocket connections.

    Layout:
        _connections: { user_id: { session_id: WebSocket } }

    A user can be connected to multiple sessions simultaneously
    (e.g. two browser tabs).
    """

    def __init__(self):
        # user_id -> { session_id -> WebSocket }
        self._connections: dict[str, dict[str, WebSocket]] = {}

    async def connect(self, user_id: str, session_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(user_id, {})[session_id] = ws
        logger.info(f"WS connected: user={user_id} session={session_id}")

    def disconnect(self, user_id: str, session_id: str) -> None:
        user_sessions = self._connections.get(user_id, {})
        user_sessions.pop(session_id, None)
        if not user_sessions:
            self._connections.pop(user_id, None)
        logger.info(f"WS disconnected: user={user_id} session={session_id}")

    async def send_text(self, user_id: str, session_id: str, text: str) -> None:
        """Send a text frame to a specific session."""
        ws = self._connections.get(user_id, {}).get(session_id)
        if ws:
            try:
                await ws.send_text(text)
            except Exception as e:
                logger.warning(f"WS send failed user={user_id} session={session_id}: {e}")
                self.disconnect(user_id, session_id)

    async def send_json(self, user_id: str, session_id: str, data: dict) -> None:
        """Send a JSON frame to a specific session."""
        ws = self._connections.get(user_id, {}).get(session_id)
        if ws:
            try:
                await ws.send_json(data)
            except Exception as e:
                logger.warning(f"WS JSON send failed user={user_id} session={session_id}: {e}")
                self.disconnect(user_id, session_id)

    async def broadcast_to_user(self, user_id: str, data: dict) -> None:
        """Broadcast a JSON event to all sessions belonging to a user."""
        sessions = dict(self._connections.get(user_id, {}))
        for session_id, ws in sessions.items():
            try:
                await ws.send_json(data)
            except Exception as e:
                logger.warning(f"WS broadcast failed session={session_id}: {e}")
                self.disconnect(user_id, session_id)

    def is_connected(self, user_id: str) -> bool:
        return bool(self._connections.get(user_id))


# Singleton instance shared across the application
ws_manager = ConnectionManager()

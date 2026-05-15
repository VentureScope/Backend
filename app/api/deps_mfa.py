"""
AAL (Authenticator Assurance Level) dependency for MFA-protected routes.

This module provides:
  - An in-process AAL session store (promote / revoke / query)
  - `require_aal2` FastAPI dependency
  - `get_aal_level` helper used by the /aal status endpoint

The store maps user_id -> expiry timestamp (epoch seconds).
Sessions are promoted on successful MFA verify and expire after 24 hours.
"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import Depends, HTTPException

from app.api.deps import get_current_user
from app.models.user import User

# ── In-process AAL store ──────────────────────────────────────────────────────
# Maps user_id -> aal2 expiry (time.time() + TTL)
# For multi-replica deployments this should be backed by Redis.

_AAL2_TTL_SECONDS = 60 * 60 * 24  # 24 hours
_aal2_sessions: dict[str, float] = {}


def _purge_expired() -> None:
    now = time.time()
    expired = [uid for uid, exp in _aal2_sessions.items() if exp < now]
    for uid in expired:
        del _aal2_sessions[uid]


def promote_to_aal2(user_id: str) -> None:
    """Promote a user session to aal2."""
    _purge_expired()
    _aal2_sessions[user_id] = time.time() + _AAL2_TTL_SECONDS


def revoke_aal2(user_id: str) -> None:
    """Revoke aal2 for a user (e.g. after disabling MFA)."""
    _aal2_sessions.pop(user_id, None)


def get_aal_level(user_id: str) -> str:
    """Return 'aal2' if the user has an active promoted session, else 'aal1'."""
    _purge_expired()
    exp = _aal2_sessions.get(user_id)
    if exp and exp > time.time():
        return "aal2"
    return "aal1"


# ── FastAPI dependency ────────────────────────────────────────────────────────


async def require_aal2(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    FastAPI dependency that enforces aal2.

    Apply to any route that requires the user to have completed an MFA
    challenge in the current session.

    Raises:
        401 – user is not authenticated (handled upstream by get_current_user)
        403 – user is authenticated but only at aal1
    """
    if get_aal_level(current_user.id) != "aal2":
        raise HTTPException(
            status_code=403,
            detail=(
                "MFA verification required. "
                "Please complete a TOTP challenge to access this resource."
            ),
        )
    return current_user

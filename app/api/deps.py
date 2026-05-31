import time
from typing import Annotated, Any

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token_with_details, TokenError
from app.repositories.user_repository import UserRepository
from app.repositories.token_repository import TokenRepository
from app.models.user import User

security = HTTPBearer(auto_error=False)

# ---------------------------------------------------------------------------
# Short-lived in-process TTL cache for auth lookups
#
# Keyed by JTI (blocklist check) and user_id (user row).
# TTL of 10 seconds is safe:
#   - Revocation (logout) tolerates a 10-second propagation delay.
#   - User profile/active-status changes are rare mid-session.
# On logout the JTI is explicitly evicted so revocation is immediate.
# ---------------------------------------------------------------------------

_AUTH_CACHE_TTL = 10  # seconds

# {jti: (expires_at, is_blocklisted: bool)}
_blocklist_cache: dict[str, tuple[float, bool]] = {}
# {user_id: (expires_at, User)}
_user_cache: dict[str, tuple[float, Any]] = {}


def _cache_get_blocklist(jti: str) -> bool | None:
    entry = _blocklist_cache.get(jti)
    if entry and time.monotonic() < entry[0]:
        return entry[1]
    return None


def _cache_set_blocklist(jti: str, value: bool) -> None:
    _blocklist_cache[jti] = (time.monotonic() + _AUTH_CACHE_TTL, value)


def _cache_get_user(user_id: str) -> Any | None:
    entry = _user_cache.get(user_id)
    if entry and time.monotonic() < entry[0]:
        return entry[1]
    return None


def _cache_set_user(user_id: str, user: Any) -> None:
    _user_cache[user_id] = (time.monotonic() + _AUTH_CACHE_TTL, user)


def invalidate_auth_cache(jti: str, user_id: str) -> None:
    """
    Evict both caches for a given token/user.
    Call this on logout so revocation is reflected immediately
    without waiting for the TTL to expire.
    """
    _blocklist_cache.pop(jti, None)
    _user_cache.pop(user_id, None)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Get the current authenticated user (must be active)."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Decode token and get detailed validation result
    token_result = decode_access_token_with_details(credentials.credentials)

    if not token_result.is_valid:
        # Provide specific error messages based on error type
        error_messages = {
            TokenError.EXPIRED: "Token has expired",
            TokenError.INVALID_SIGNATURE: "Invalid token signature",
            TokenError.MALFORMED: "Malformed token",
            TokenError.MISSING_CLAIMS: "Token missing required information",
        }

        error_detail = error_messages.get(token_result.error_type, "Invalid token")
        raise HTTPException(status_code=401, detail=error_detail)

    jti = token_result.payload.jti
    user_id = token_result.payload.sub

    # --- Blocklist check (cached) ---
    cached_blocklisted = _cache_get_blocklist(jti)
    if cached_blocklisted is None:
        token_repo = TokenRepository(db)
        cached_blocklisted = await token_repo.is_blocklisted(jti)
        _cache_set_blocklist(jti, cached_blocklisted)

    if cached_blocklisted:
        raise HTTPException(status_code=401, detail="Token has been revoked")

    # --- User lookup (cached) ---
    user = _cache_get_user(user_id)
    if user is None:
        repo = UserRepository(db)
        user = await repo.get_by_id(user_id)
        if user:
            _cache_set_user(user_id, user)

    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="User account is deactivated")
    return user


async def get_current_admin_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Get current user, ensuring they are an admin."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user

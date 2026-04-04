from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token_with_details, TokenError
from app.repositories.user_repository import UserRepository
from app.repositories.token_repository import TokenRepository
from app.models.user import User

security = HTTPBearer(auto_error=False)


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

    # Check if token has been revoked (logout)
    token_repo = TokenRepository(db)
    if await token_repo.is_blocklisted(token_result.payload.jti):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    repo = UserRepository(db)
    user = await repo.get_by_id(token_result.payload.sub)
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

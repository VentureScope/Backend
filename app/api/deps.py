from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token_full, TokenPayload
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

    # Decode token and get full payload including JTI
    token_payload = decode_access_token_full(credentials.credentials)
    if not token_payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Check if token has been revoked (logout)
    token_repo = TokenRepository(db)
    if await token_repo.is_blocklisted(token_payload.jti):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    repo = UserRepository(db)
    user = await repo.get_by_id(token_payload.sub)
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

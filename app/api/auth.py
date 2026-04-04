from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token_full
from app.schemas.user import UserCreate, UserLogin, UserResponse, Token
from app.services.auth_service import AuthService
from app.repositories.token_repository import TokenRepository

router = APIRouter()
security = HTTPBearer()


@router.post("/register", response_model=UserResponse)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    try:
        user = await service.register(data)
        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login", response_model=Token)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    try:
        token = await service.login(data)
        return Token(access_token=token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid email or password")


@router.post("/logout", status_code=200)
async def logout(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Logout the current user by invalidating their token.

    The token is added to a blocklist and will be rejected on subsequent requests.
    """
    token_payload = decode_access_token_full(credentials.credentials)
    if not token_payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    token_repo = TokenRepository(db)

    # Check if already logged out
    if await token_repo.is_blocklisted(token_payload.jti):
        raise HTTPException(status_code=400, detail="Token already invalidated")

    # Add token to blocklist
    await token_repo.add_to_blocklist(
        jti=token_payload.jti,
        user_id=token_payload.sub,
        expires_at=token_payload.exp,
    )
    await db.commit()

    return {"message": "Successfully logged out"}

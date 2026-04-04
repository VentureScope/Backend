from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token_with_details, TokenError
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

    token_repo = TokenRepository(db)

    # Check if already logged out
    if await token_repo.is_blocklisted(token_result.payload.jti):
        raise HTTPException(status_code=400, detail="Token already invalidated")

    # Add token to blocklist
    await token_repo.add_to_blocklist(
        jti=token_result.payload.jti,
        user_id=token_result.payload.sub,
        expires_at=token_result.payload.exp,
    )
    await db.commit()

    return {"message": "Successfully logged out"}

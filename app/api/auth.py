from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token_with_details, TokenError
from app.schemas.user import UserCreate, UserLogin, UserResponse, Token
from app.schemas.oauth import (
    OAuthLoginResponse,
    OAuthCallbackRequest,
    OAuthCallbackResponse,
    OAuthErrorResponse,
)
from app.services.auth_service import AuthService
from app.services.oauth_service import OAuthService
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


# ==================== OAuth Endpoints ====================


@router.get("/oauth/google/login", response_model=OAuthLoginResponse)
async def google_oauth_login(db: AsyncSession = Depends(get_db)):
    """
    Initiate Google OAuth login flow.

    Returns an authorization URL that the client should redirect the user to.
    """
    try:
        oauth_service = OAuthService(db)
        auth_url, state = await oauth_service.get_authorization_url("google")

        return OAuthLoginResponse(authorization_url=auth_url, state=state)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"OAuth initialization failed: {str(e)}"
        )


@router.post("/oauth/google/callback", response_model=OAuthCallbackResponse)
async def google_oauth_callback(
    callback_data: OAuthCallbackRequest, db: AsyncSession = Depends(get_db)
):
    """
    Handle Google OAuth callback.

    Exchanges authorization code for tokens and creates/logs in user.
    """
    try:
        oauth_service = OAuthService(db)

        # Exchange code for tokens and get/create user
        user, is_new_user = await oauth_service.authenticate_user(
            provider="google", code=callback_data.code, state=callback_data.state
        )

        # Generate JWT access token for the user
        from app.core.security import create_access_token

        access_token = create_access_token(subject=user.id)

        # Convert user to response format
        from app.schemas.user import UserResponse

        user_data = UserResponse.from_orm(user).dict()

        return OAuthCallbackResponse(
            access_token=access_token, token_type="bearer", user=user_data
        )

    except ValueError as e:
        # OAuth-specific errors (invalid state, code exchange failure, etc.)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Unexpected errors
        raise HTTPException(status_code=500, detail=f"OAuth callback failed: {str(e)}")


@router.get("/oauth/google/callback")
async def google_oauth_callback_get(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="State parameter for CSRF protection"),
    error: str = Query(None, description="Error from OAuth provider"),
    error_description: str = Query(None, description="Error description"),
    db: AsyncSession = Depends(get_db),
):
    """
    Handle Google OAuth callback via GET request (browser redirect).

    This endpoint handles the browser redirect from Google after user authorization.
    It can either return a success response or redirect to the frontend with tokens.
    """
    # Check for OAuth errors first
    if error:
        raise HTTPException(
            status_code=400, detail=f"OAuth error: {error}. {error_description or ''}"
        )

    try:
        # Use the same callback logic as the POST endpoint
        callback_data = OAuthCallbackRequest(code=code, state=state)
        result = await google_oauth_callback(callback_data, db)

        # In a real application, you might want to redirect to the frontend
        # with the token as a query parameter or set an HTTP-only cookie
        return {
            "message": "OAuth login successful",
            "access_token": result.access_token,
            "user": result.user,
        }

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth callback failed: {str(e)}")

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token_with_details, hash_password, TokenError
from app.schemas.user import UserCreate, UserLogin, UserResponse, Token
from app.schemas.oauth import (
    OAuthLoginResponse,
    OAuthCallbackRequest,
    OAuthCallbackResponse,
)
from app.schemas.otp import (
    OtpVerifyRequest,
    OtpVerifyResponse,
    OtpResendRequest,
    OtpResendResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    ReauthRequest,
    ReauthResponse,
    ReauthVerifyRequest,
)
from app.api.deps import get_current_user
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.oauth_service import OAuthService
from app.services.otp_service import (
    OTPService,
    OTPExpiredError,
    OTPInvalidError,
    OTPResendCooldownError,
    OTPResendLimitError,
    get_otp_service,
)
from app.repositories.token_repository import TokenRepository
from app.repositories.user_repository import UserRepository

router = APIRouter()
security = HTTPBearer()


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    otp_service: OTPService = Depends(get_otp_service),
):
    service = AuthService(db, otp_service=otp_service)
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
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid email or password")


@router.post("/verify-email", response_model=OtpVerifyResponse)
async def verify_email(
    data: OtpVerifyRequest,
    db: AsyncSession = Depends(get_db),
    otp_service: OTPService = Depends(get_otp_service),
):
    """Verify a user's email address using the OTP sent during registration."""
    repo = UserRepository(db)
    user = await repo.get_by_email(data.email)

    if not user or not user.is_active:
        raise HTTPException(status_code=404, detail="User not found.")

    if user.is_verified:
        raise HTTPException(status_code=400, detail="Email is already verified.")

    try:
        await otp_service.verify_otp(user, data.otp)
    except OTPExpiredError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OTPInvalidError as e:
        raise HTTPException(status_code=400, detail=str(e))

    user.is_verified = True
    await db.commit()

    return OtpVerifyResponse()


@router.post("/otp/resend", response_model=OtpResendResponse)
async def resend_otp(
    data: OtpResendRequest,
    db: AsyncSession = Depends(get_db),
    otp_service: OTPService = Depends(get_otp_service),
):
    """Resend the OTP verification email. Subject to rate-limiting."""
    repo = UserRepository(db)
    user = await repo.get_by_email(data.email)

    # Always return 200 even if user is not found — prevents email enumeration
    if not user or not user.is_active:
        return OtpResendResponse()

    if user.is_verified:
        raise HTTPException(status_code=400, detail="Email is already verified.")

    try:
        await otp_service.resend_otp(user)
    except OTPResendCooldownError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except OTPResendLimitError as e:
        raise HTTPException(status_code=429, detail=str(e))

    return OtpResendResponse()


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(
    data: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
    otp_service: OTPService = Depends(get_otp_service),
):
    """Request a password-reset code.

    Always returns 200 with a generic message regardless of whether the
    email exists.  This prevents user-enumeration attacks.
    """
    repo = UserRepository(db)
    user = await repo.get_by_email(data.email)

    # Silently succeed if user doesn't exist or is inactive
    if not user or not user.is_active:
        return ForgotPasswordResponse()

    # Don't allow password reset for OAuth-only accounts
    if user.password_hash is None:
        return ForgotPasswordResponse()

    try:
        await otp_service.send_password_reset_otp(user)
    except Exception:
        # Swallow errors to prevent enumeration; logged inside OTPService
        pass

    return ForgotPasswordResponse()


@router.post("/reset-password", response_model=ResetPasswordResponse)
async def reset_password(
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    otp_service: OTPService = Depends(get_otp_service),
):
    """Verify the reset code and set a new password."""
    repo = UserRepository(db)
    user = await repo.get_by_email(data.email)

    if not user or not user.is_active:
        raise HTTPException(status_code=404, detail="User not found.")

    if user.password_hash is None:
        raise HTTPException(
            status_code=400,
            detail="This account uses OAuth login. Password reset is not available.",
        )

    try:
        await otp_service.verify_password_reset_otp(user, data.otp)
    except OTPExpiredError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OTPInvalidError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # OTP valid — update password
    user.password_hash = hash_password(data.new_password)
    await db.commit()

    return ResetPasswordResponse()


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

    # Evict auth cache immediately so the revoked token is rejected on the
    # very next request rather than waiting for the 10-second TTL.
    from app.api.deps import invalidate_auth_cache
    invalidate_auth_cache(token_result.payload.jti, token_result.payload.sub)

    # Clear MFA/AAL2 status so they must re-verify on next login,
    # UNLESS they checked "Remember Me" during login.
    if not token_result.payload.remember:
        from app.api.deps_mfa import revoke_aal2
        revoke_aal2(token_result.payload.sub)

    return {"message": "Successfully logged out"}


# ==================== OAuth Endpoints ====================


async def _oauth_login(provider: str, db: AsyncSession) -> OAuthLoginResponse:
    """Initiate OAuth login flow and return provider authorization URL."""
    try:
        oauth_service = OAuthService(db)
        auth_url, state = await oauth_service.get_authorization_url(provider)

        return OAuthLoginResponse(authorization_url=auth_url, state=state)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"OAuth initialization failed: {str(e)}"
        )


async def _oauth_callback(
    provider: str, callback_data: OAuthCallbackRequest, db: AsyncSession
) -> OAuthCallbackResponse:
    """Handle OAuth callback by exchanging code and issuing app token."""
    try:
        oauth_service = OAuthService(db)

        # Exchange code for tokens and get/create user
        user, _ = await oauth_service.authenticate_user(
            provider=provider, code=callback_data.code, state=callback_data.state
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


async def _oauth_callback_get(
    provider: str,
    code: str,
    state: str,
    error: str | None,
    error_description: str | None,
    db: AsyncSession,
):
    """Handle browser OAuth redirects via GET callback."""
    if error:
        raise HTTPException(
            status_code=400, detail=f"OAuth error: {error}. {error_description or ''}"
        )

    try:
        callback_data = OAuthCallbackRequest(code=code, state=state)
        result = await _oauth_callback(provider, callback_data, db)

        return {
            "message": "OAuth login successful",
            "access_token": result.access_token,
            "user": result.user,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth callback failed: {str(e)}")


@router.get("/oauth/google/login", response_model=OAuthLoginResponse)
async def google_oauth_login(db: AsyncSession = Depends(get_db)):
    """Initiate Google OAuth login flow."""
    return await _oauth_login(provider="google", db=db)


@router.get("/oauth/github/login", response_model=OAuthLoginResponse)
async def github_oauth_login(db: AsyncSession = Depends(get_db)):
    """Initiate GitHub OAuth login flow."""
    return await _oauth_login(provider="github", db=db)


@router.get("/oauth/github/scope-upgrade", response_model=OAuthLoginResponse)
async def github_oauth_scope_upgrade(
    scopes: str = Query(
        "read:user,user:email,repo,read:org",
        description="Comma-separated GitHub scopes to request",
    ),
    db: AsyncSession = Depends(get_db),
):
    """Request an updated GitHub OAuth authorization with repo-level scopes."""
    requested_scopes = [scope.strip() for scope in scopes.split(",") if scope.strip()]
    oauth_service = OAuthService(db)
    auth_url, state = await oauth_service.get_authorization_url(
        provider="github", scopes=requested_scopes
    )
    return OAuthLoginResponse(authorization_url=auth_url, state=state)


@router.post("/oauth/google/callback", response_model=OAuthCallbackResponse)
async def google_oauth_callback(
    callback_data: OAuthCallbackRequest, db: AsyncSession = Depends(get_db)
):
    """Handle Google OAuth callback."""
    return await _oauth_callback(provider="google", callback_data=callback_data, db=db)


@router.post("/oauth/github/callback", response_model=OAuthCallbackResponse)
async def github_oauth_callback(
    callback_data: OAuthCallbackRequest, db: AsyncSession = Depends(get_db)
):
    """Handle GitHub OAuth callback."""
    return await _oauth_callback(provider="github", callback_data=callback_data, db=db)


@router.get("/oauth/google/callback")
async def google_oauth_callback_get(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="State parameter for CSRF protection"),
    error: str = Query(None, description="Error from OAuth provider"),
    error_description: str = Query(None, description="Error description"),
    db: AsyncSession = Depends(get_db),
):
    """Handle browser redirect callback for Google OAuth."""
    return await _oauth_callback_get(
        provider="google",
        code=code,
        state=state,
        error=error,
        error_description=error_description,
        db=db,
    )


@router.get("/oauth/github/callback")
async def github_oauth_callback_get(
    code: str = Query(..., description="Authorization code from GitHub"),
    state: str = Query(..., description="State parameter for CSRF protection"),
    error: str = Query(None, description="Error from OAuth provider"),
    error_description: str = Query(None, description="Error description"),
    db: AsyncSession = Depends(get_db),
):
    """Handle browser redirect callback for GitHub OAuth."""
    return await _oauth_callback_get(
        provider="github",
        code=code,
        state=state,
        error=error,
        error_description=error_description,
        db=db,
    )


# ==================== Re-authentication ====================


@router.post("/reauthenticate", response_model=ReauthResponse)
async def reauthenticate(
    data: ReauthRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    otp_service: OTPService = Depends(get_otp_service),
):
    """
    Initiate re-authentication for sensitive actions.
    If 'password' is provided, it verifies it and promotes to aal2.
    Otherwise, it sends an OTP to the user's email.
    """
    from app.api.deps_mfa import promote_to_aal2
    from app.core.security import verify_password

    if data.password:
        if not current_user.password_hash:
            raise HTTPException(
                status_code=400,
                detail="This account does not have a password. Please use email OTP.",
            )
        if not verify_password(data.password, current_user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid password")

        promote_to_aal2(current_user.id)
        return ReauthResponse(status="verified", message="Identity confirmed.")

    # No password — send OTP
    try:
        await otp_service.send_reauth_otp(current_user)
        return ReauthResponse(
            status="otp_sent", message="Verification code sent to your email."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send OTP: {str(e)}")


@router.post("/verify-reauthenticate", response_model=ReauthResponse)
async def verify_reauthenticate(
    data: ReauthVerifyRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    otp_service: OTPService = Depends(get_otp_service),
):
    """Verify a re-authentication OTP and promote to aal2."""
    from app.api.deps_mfa import promote_to_aal2

    try:
        await otp_service.verify_reauth_otp(current_user, data.otp)
        promote_to_aal2(current_user.id)
        return ReauthResponse(status="verified", message="Identity confirmed.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


"""
TOTP MFA API endpoints.

All routes live under /api/auth/mfa/ and are registered in main.py.

AAL levels
----------
This backend does not issue Supabase JWTs; it issues its own HS256 JWTs.
AAL is tracked as a session claim that is promoted after a successful MFA
verification via the session store (in-process dict mirroring the challenge
store in mfa_service.py).

The `require_aal2` dependency checks whether the current request session
has been promoted to aal2. The session is stored as a short-lived signed
token in the `X-MFA-Session` header that clients must include after a
successful verify_challenge call.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.services.mfa_service import MFAService
from app.schemas.mfa import (
    MFAEnrollResponse,
    MFAEnrollVerifyRequest,
    MFAEnrollVerifyResponse,
    MFAChallengeRequest,
    MFAChallengeResponse,
    MFAVerifyRequest,
    MFAVerifyResponse,
    MFAListFactorsResponse,
    MFAFactor,
    MFAUnenrollRequest,
    MFAUnenrollResponse,
    MFASyncResponse,
    MFADisableResponse,
)
from app.api.deps_mfa import require_aal2

router = APIRouter()


# ── Enrollment ─────────────────────────────────────────────────────────────────


@router.post("/enroll", response_model=MFAEnrollResponse)
async def mfa_enroll(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Start TOTP enrollment.

    Returns a QR code URI (otpauth://) and the plain-text base32 secret.
    The client renders the URI as a QR image (via a JS QR library or as
    an `<img src="...">` after encoding as a data URI using a QR API).
    The factor is NOT verified yet — the client must call /enroll/verify.
    """
    service = MFAService(db)
    try:
        result = await service.enroll(current_user.id, current_user.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return MFAEnrollResponse(
        factor_id=result["factor_id"],
        totp_uri=result["totp_uri"],
        secret=result["secret"],
    )


@router.post("/enroll/verify", response_model=MFAEnrollVerifyResponse)
async def mfa_enroll_verify(
    data: MFAEnrollVerifyRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Verify the first TOTP code after enrollment (challengeAndVerify).

    On success the factor is marked verified in the DB.  The client should
    then call POST /auth/mfa/sync to update the app-level mfa_enabled flag.
    """
    from app.api.deps_mfa import promote_to_aal2
    service = MFAService(db)
    try:
        await service.enroll_verify(current_user.id, data.factor_id, data.code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # After first verification, promote the session to aal2 so they can call /sync
    promote_to_aal2(current_user.id)

    return MFAEnrollVerifyResponse(
        verified=True,
        message="Factor verified. MFA session promoted to AAL2.",
    )


# ── Challenge / Verify ─────────────────────────────────────────────────────────


@router.post("/challenge", response_model=MFAChallengeResponse)
async def mfa_challenge(
    data: MFAChallengeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a login challenge for an enrolled TOTP factor."""
    service = MFAService(db)
    try:
        challenge_id = await service.create_challenge(current_user.id, data.factor_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return MFAChallengeResponse(challenge_id=challenge_id)


@router.post("/verify", response_model=MFAVerifyResponse)
async def mfa_verify(
    data: MFAVerifyRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Verify a TOTP challenge code.

    On success, promotes the session to aal2 by registering the user in
    the in-process AAL store. The response returns aal="aal2" to confirm
    the promotion.
    """
    from app.api.deps_mfa import promote_to_aal2

    service = MFAService(db)
    try:
        await service.verify_challenge(
            current_user.id, data.factor_id, data.challenge_id, data.code
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    promote_to_aal2(current_user.id)

    return MFAVerifyResponse(verified=True, aal="aal2")


# ── Factor list & unenroll ─────────────────────────────────────────────────────


@router.get("/factors", response_model=MFAListFactorsResponse)
async def mfa_list_factors(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Return all verified TOTP factors for the current user."""
    service = MFAService(db)
    factors_raw = await service.list_factors(current_user.id)
    factors = [
        MFAFactor(
            factor_id=f["factor_id"],
            friendly_name=f["friendly_name"],
            created_at=f["created_at"],
        )
        for f in factors_raw
    ]
    return MFAListFactorsResponse(factors=factors)


@router.post("/unenroll", response_model=MFAUnenrollResponse)
async def mfa_unenroll(
    data: MFAUnenrollRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Remove a single TOTP factor. Requires aal2."""
    _: User = await require_aal2(current_user)

    service = MFAService(db)
    deleted = await service.unenroll(current_user.id, data.factor_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Factor not found.")

    return MFAUnenrollResponse(factor_id=data.factor_id, deleted=True)


# ── App-DB sync / disable ──────────────────────────────────────────────────────


@router.post("/sync", response_model=MFASyncResponse)
async def mfa_sync(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Sync mfa_enabled=True in the app database after successful enrollment.
    Requires aal2 (the session must have been promoted by /verify).
    """
    _: User = await require_aal2(current_user)

    service = MFAService(db)
    if not await service.has_verified_factor(current_user.id):
        raise HTTPException(
            status_code=400,
            detail="No verified factor found. Complete enrollment first.",
        )

    now = datetime.now(timezone.utc)
    current_user.mfa_enabled = True
    current_user.mfa_enrolled_at = current_user.mfa_enrolled_at or now
    await db.commit()
    await db.refresh(current_user)

    return MFASyncResponse(
        mfa_enabled=True,
        enrolled_at=current_user.mfa_enrolled_at,
    )


@router.post("/disable", response_model=MFADisableResponse)
async def mfa_disable(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Unenroll all factors and set mfa_enabled=False in the app database.
    Requires aal2 to prevent unauthorized disabling.
    """
    from app.api.deps_mfa import revoke_aal2

    _: User = await require_aal2(current_user)

    service = MFAService(db)
    await service.unenroll_all(current_user.id)

    current_user.mfa_enabled = False
    current_user.mfa_enrolled_at = None
    await db.commit()

    revoke_aal2(current_user.id)

    return MFADisableResponse(mfa_enabled=False)


# ── AAL status ─────────────────────────────────────────────────────────────────


@router.get("/aal")
async def get_aal(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Return the current and next AAL for the authenticated user.

    currentLevel: aal1 always (JWT is valid).
    nextLevel:    aal2 if the user has a verified factor AND has not yet
                  completed an MFA challenge in this session.
    """
    from app.api.deps_mfa import get_aal_level

    service = MFAService(db)
    has_factor = await service.has_verified_factor(current_user.id)
    current_level = get_aal_level(current_user.id)

    next_level = "aal2" if has_factor and current_level == "aal1" else current_level

    return {
        "current_level": current_level,
        "next_level": next_level,
        "mfa_enabled": current_user.mfa_enabled,
        "enrolled_at": current_user.mfa_enrolled_at,
    }

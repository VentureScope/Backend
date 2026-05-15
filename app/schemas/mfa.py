"""
Pydantic schemas for TOTP MFA endpoints.
"""

from datetime import datetime
from pydantic import BaseModel


# ── Enroll ────────────────────────────────────────────────────────────────────

class MFAEnrollResponse(BaseModel):
    """Returned when a new TOTP factor is created.

    The client renders the QR code SVG as a data URI and displays the
    plain-text secret as a collapsible fallback.
    """

    factor_id: str
    totp_uri: str     # otpauth:// URI for QR code generation
    secret: str       # plain-text base-32 secret for manual entry
    issuer: str = "VentureScope"


# ── Challenge / Verify ────────────────────────────────────────────────────────

class MFAChallengeRequest(BaseModel):
    factor_id: str


class MFAChallengeResponse(BaseModel):
    challenge_id: str


class MFAVerifyRequest(BaseModel):
    factor_id: str
    challenge_id: str
    code: str         # 6-digit TOTP code


class MFAVerifyResponse(BaseModel):
    verified: bool
    aal: str          # "aal2" on success


# ── Enroll Verify (single-step challengeAndVerify equivalent) ─────────────────

class MFAEnrollVerifyRequest(BaseModel):
    factor_id: str
    code: str


class MFAEnrollVerifyResponse(BaseModel):
    verified: bool
    message: str


# ── Factor list ───────────────────────────────────────────────────────────────

class MFAFactor(BaseModel):
    factor_id: str
    friendly_name: str | None = None
    created_at: datetime


class MFAListFactorsResponse(BaseModel):
    factors: list[MFAFactor]


# ── Unenroll ──────────────────────────────────────────────────────────────────

class MFAUnenrollRequest(BaseModel):
    factor_id: str


class MFAUnenrollResponse(BaseModel):
    factor_id: str
    deleted: bool


# ── Sync / Disable (app-DB endpoints) ────────────────────────────────────────

class MFASyncResponse(BaseModel):
    mfa_enabled: bool
    enrolled_at: datetime | None


class MFADisableResponse(BaseModel):
    mfa_enabled: bool

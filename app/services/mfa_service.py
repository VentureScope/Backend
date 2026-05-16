"""
TOTP MFA service.

Manages TOTP factor lifecycle: enroll, challenge, verify, unenroll.

Storage strategy
----------------
TOTP secrets are stored in a dedicated ``mfa_factors`` table (created by
this module's helper) and are **never** returned after initial enrollment.
The application-level ``users.mfa_enabled`` / ``users.mfa_enrolled_at``
columns are updated by the sync/disable endpoints only after the client
confirms a successful verification.

Factor IDs are random UUIDs generated at enroll time. Each user may hold
up to MAX_FACTORS factors (default 10).

Challenge / verify
------------------
Challenges are ephemeral tokens stored in memory (or Redis if available)
with a short TTL. Because this project uses its own FastAPI backend (not
Supabase Auth), challenges are just signed, time-limited strings that bind
a factor_id to a pending verification attempt.  The verification step
checks the TOTP window (±1 step = 30 s drift tolerance).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import pyotp
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_FACTORS = 10
TOTP_ISSUER = "VentureScope"
CHALLENGE_TTL_SECONDS = 300  # 5 minutes


# ── In-process challenge store ────────────────────────────────────────────────
# Maps  challenge_id -> {"factor_id": str, "user_id": str, "expires_at": float}
# Fine for single-process deployments; replace with Redis for multi-replica.

_challenges: dict[str, dict[str, Any]] = {}


def _purge_expired_challenges() -> None:
    now = time.monotonic()
    expired = [k for k, v in _challenges.items() if v["expires_at"] < now]
    for k in expired:
        del _challenges[k]


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _ensure_factors_table(db: AsyncSession) -> None:
    """Create mfa_factors table if it doesn't exist.

    Using raw DDL so we don't need another Alembic migration just for the
    in-app factor store, which has no ORM relationships.
    """
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS mfa_factors (
                id            TEXT PRIMARY KEY,
                user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                secret        TEXT NOT NULL,
                friendly_name TEXT,
                verified      BOOLEAN NOT NULL DEFAULT FALSE,
                created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    await db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_mfa_factors_user_id ON mfa_factors(user_id)"
        )
    )
    await db.commit()


async def _count_factors(db: AsyncSession, user_id: str) -> int:
    result = await db.execute(
        text("SELECT COUNT(*) FROM mfa_factors WHERE user_id = :uid AND verified = TRUE"),
        {"uid": user_id},
    )
    return result.scalar_one()


# ── Public API ────────────────────────────────────────────────────────────────

class MFAService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # -- Enroll ----------------------------------------------------------------

    async def enroll(self, user_id: str, user_email: str) -> dict:
        """Create a new unverified TOTP factor and return QR data.

        Returns
        -------
        dict with keys: factor_id, totp_uri, secret
        """
        await _ensure_factors_table(self._db)

        verified_count = await _count_factors(self._db, user_id)
        if verified_count >= MAX_FACTORS:
            raise ValueError(f"Maximum of {MAX_FACTORS} MFA factors already enrolled.")

        # Generate a new TOTP secret
        secret = pyotp.random_base32()
        factor_id = str(uuid.uuid4())

        totp = pyotp.TOTP(secret, issuer=TOTP_ISSUER)
        totp_uri = totp.provisioning_uri(name=user_email, issuer_name=TOTP_ISSUER)

        await self._db.execute(
            text(
                """
                INSERT INTO mfa_factors (id, user_id, secret, verified)
                VALUES (:id, :user_id, :secret, FALSE)
                """
            ),
            {"id": factor_id, "user_id": user_id, "secret": secret},
        )
        await self._db.commit()

        logger.info(f"[mfa] New factor enrolled (unverified) for user={user_id} factor={factor_id}")

        return {
            "factor_id": factor_id,
            "totp_uri": totp_uri,
            "secret": secret,
        }

    # -- Enroll Verify (challengeAndVerify) ------------------------------------

    async def enroll_verify(
        self, user_id: str, factor_id: str, code: str, friendly_name: str | None = None
    ) -> bool:
        """Verify the first code after enrollment — marks factor as verified."""
        await _ensure_factors_table(self._db)

        result = await self._db.execute(
            text(
                "SELECT secret FROM mfa_factors WHERE id = :fid AND user_id = :uid AND verified = FALSE"
            ),
            {"fid": factor_id, "uid": user_id},
        )
        row = result.fetchone()
        if not row:
            raise ValueError("Factor not found or already verified.")

        totp = pyotp.TOTP(row.secret)
        if not totp.verify(code, valid_window=1):
            raise ValueError("Invalid or expired TOTP code.")

        await self._db.execute(
            text(
                "UPDATE mfa_factors SET verified = TRUE, friendly_name = :fname WHERE id = :fid"
            ),
            {"fid": factor_id, "fname": friendly_name},
        )
        await self._db.commit()

        logger.info(f"[mfa] Factor verified for user={user_id} factor={factor_id}")
        return True

    # -- Challenge -------------------------------------------------------------

    async def create_challenge(self, user_id: str, factor_id: str) -> str:
        """Create a short-lived challenge ID bound to the given factor."""
        await _ensure_factors_table(self._db)

        result = await self._db.execute(
            text(
                "SELECT id FROM mfa_factors WHERE id = :fid AND user_id = :uid AND verified = TRUE"
            ),
            {"fid": factor_id, "uid": user_id},
        )
        if not result.fetchone():
            raise ValueError("Factor not found or not verified.")

        _purge_expired_challenges()
        challenge_id = secrets.token_urlsafe(32)
        _challenges[challenge_id] = {
            "factor_id": factor_id,
            "user_id": user_id,
            "expires_at": time.monotonic() + CHALLENGE_TTL_SECONDS,
        }
        return challenge_id

    # -- Verify challenge -------------------------------------------------------

    async def verify_challenge(
        self, user_id: str, factor_id: str, challenge_id: str, code: str
    ) -> bool:
        """Verify a TOTP code against an active challenge."""
        _purge_expired_challenges()

        challenge = _challenges.get(challenge_id)
        if not challenge:
            raise ValueError("Challenge not found or expired.")
        if challenge["user_id"] != user_id or challenge["factor_id"] != factor_id:
            raise ValueError("Challenge mismatch.")
        if time.monotonic() > challenge["expires_at"]:
            del _challenges[challenge_id]
            raise ValueError("Challenge has expired.")

        # Fetch secret
        result = await self._db.execute(
            text(
                "SELECT secret FROM mfa_factors WHERE id = :fid AND user_id = :uid AND verified = TRUE"
            ),
            {"fid": factor_id, "uid": user_id},
        )
        row = result.fetchone()
        if not row:
            raise ValueError("Factor not found.")

        totp = pyotp.TOTP(row.secret)
        if not totp.verify(code, valid_window=1):
            raise ValueError("Invalid or expired TOTP code.")

        # Consume challenge
        del _challenges[challenge_id]
        logger.info(f"[mfa] Challenge verified for user={user_id} factor={factor_id}")
        return True

    # -- List factors -----------------------------------------------------------

    async def list_factors(self, user_id: str) -> list[dict]:
        await _ensure_factors_table(self._db)

        result = await self._db.execute(
            text(
                """
                SELECT id, friendly_name, created_at
                FROM mfa_factors
                WHERE user_id = :uid AND verified = TRUE
                ORDER BY created_at ASC
                """
            ),
            {"uid": user_id},
        )
        return [
            {
                "factor_id": row.id,
                "friendly_name": row.friendly_name,
                "created_at": row.created_at,
            }
            for row in result.fetchall()
        ]

    # -- Unenroll ---------------------------------------------------------------

    async def unenroll(self, user_id: str, factor_id: str) -> bool:
        await _ensure_factors_table(self._db)

        result = await self._db.execute(
            text(
                "DELETE FROM mfa_factors WHERE id = :fid AND user_id = :uid RETURNING id"
            ),
            {"fid": factor_id, "uid": user_id},
        )
        deleted = result.fetchone() is not None
        await self._db.commit()
        if deleted:
            logger.info(f"[mfa] Factor unenrolled for user={user_id} factor={factor_id}")
        return deleted

    # -- Unenroll all (used during disable flow) --------------------------------

    async def unenroll_all(self, user_id: str) -> int:
        await _ensure_factors_table(self._db)

        result = await self._db.execute(
            text("DELETE FROM mfa_factors WHERE user_id = :uid RETURNING id"),
            {"uid": user_id},
        )
        count = len(result.fetchall())
        await self._db.commit()
        logger.info(f"[mfa] All {count} factor(s) unenrolled for user={user_id}")
        return count

    # -- Check if user has any verified factor ----------------------------------

    async def has_verified_factor(self, user_id: str) -> bool:
        await _ensure_factors_table(self._db)
        count = await _count_factors(self._db, user_id)
        return count > 0

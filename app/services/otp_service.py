"""
OTP (One-Time Password) service for email verification.

Responsibilities:
  - Generate a cryptographically random 6-digit OTP.
  - Persist the OTP in Redis with a TTL (auto-expiry, no cron needed).
  - Enforce resend rate-limits (cooldown + hourly cap) via Redis counters.
  - Verify submitted OTP codes using constant-time comparison.
  - Render and dispatch HTML/plain-text verification emails.

Redis key layout:
  otp:{user_id}                    – the current OTP code (TTL = OTP_EXPIRE_MINUTES)
  otp_cooldown:{user_id}           – sentinel for per-resend cooldown (TTL = OTP_RESEND_COOLDOWN_SECONDS)
  otp_resend_count:{user_id}       – rolling hourly resend counter (TTL = 3600s)
"""

import logging
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import redis.asyncio as aioredis

from app.core.config import settings
from app.models.user import User
from app.services.email_service import get_email_provider, EmailDeliveryError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "email"


def _render_template(filename: str, context: dict) -> str:
    """Load a template file and substitute {{key}} placeholders."""
    template_path = _TEMPLATE_DIR / filename
    content = template_path.read_text(encoding="utf-8")
    for key, value in context.items():
        content = content.replace("{{" + key + "}}", str(value))
    return content


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class OTPError(Exception):
    """Base class for OTP-related errors."""


class OTPExpiredError(OTPError):
    """Raised when the submitted OTP has expired or does not exist."""


class OTPInvalidError(OTPError):
    """Raised when the submitted OTP code is wrong."""


class OTPResendCooldownError(OTPError):
    """Raised when a resend is requested before the cooldown has elapsed."""


class OTPResendLimitError(OTPError):
    """Raised when the hourly resend cap has been reached."""


# ---------------------------------------------------------------------------
# OTP Service
# ---------------------------------------------------------------------------


class OTPService:
    """
    Manages the full OTP lifecycle: generation, storage, verification,
    rate-limiting, and email dispatch.

    Args:
        redis_client: An async Redis client instance.
    """

    OTP_LENGTH = 6

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Key builders – email verification
    # ------------------------------------------------------------------

    def _otp_key(self, user_id: str) -> str:
        return f"otp:{user_id}"

    def _cooldown_key(self, user_id: str) -> str:
        return f"otp_cooldown:{user_id}"

    def _resend_count_key(self, user_id: str) -> str:
        return f"otp_resend_count:{user_id}"

    # ------------------------------------------------------------------
    # Key builders – password reset (separate namespace)
    # ------------------------------------------------------------------

    def _pwd_reset_key(self, user_id: str) -> str:
        return f"pwd_reset:{user_id}"

    def _pwd_reset_cooldown_key(self, user_id: str) -> str:
        return f"pwd_reset_cooldown:{user_id}"

    def _pwd_reset_count_key(self, user_id: str) -> str:
        return f"pwd_reset_count:{user_id}"

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _generate_code(self) -> str:
        """Return a zero-padded 6-digit numeric OTP."""
        return str(secrets.randbelow(10**self.OTP_LENGTH)).zfill(self.OTP_LENGTH)

    def _build_email_context(self, user: User, otp_code: str) -> dict:
        return {
            "full_name": user.full_name or user.email.split("@")[0],
            "otp_code": otp_code,
            "expire_minutes": str(settings.OTP_EXPIRE_MINUTES),
            "year": str(datetime.now(timezone.utc).year),
        }

    # ------------------------------------------------------------------
    # Core operations – email verification
    # ------------------------------------------------------------------

    async def _store_otp(self, user_id: str, code: str) -> None:
        """Persist OTP in Redis with TTL."""
        await self._redis.set(
            self._otp_key(user_id),
            code,
            ex=settings.OTP_EXPIRE_MINUTES * 60,
        )

    async def _send_otp_email(self, user: User, code: str) -> None:
        """Render templates and dispatch the verification email."""
        context = self._build_email_context(user, code)
        html_body = _render_template("otp_verification.html", context)
        text_body = _render_template("otp_verification.txt", context)

        provider = get_email_provider()
        await provider.send_email(
            to=user.email,
            subject="Verify your VentureScope email address",
            html=html_body,
            text=text_body,
        )

    async def send_otp(self, user: User) -> None:
        """
        Generate a fresh OTP, store it in Redis, and email it to the user.

        This is called during registration (no rate-limit check) and also
        by resend_otp() after the rate-limit guards pass.
        """
        code = self._generate_code()
        await self._store_otp(user.id, code)

        try:
            await self._send_otp_email(user, code)
        except EmailDeliveryError:
            # Do NOT delete the stored OTP – the user can still resend.
            logger.exception("Failed to send OTP email to user %s", user.id)
            raise

    async def resend_otp(self, user: User) -> None:
        """
        Resend a fresh OTP after enforcing rate-limit rules:
          1. Per-request cooldown (OTP_RESEND_COOLDOWN_SECONDS).
          2. Rolling-hour cap (OTP_MAX_RESENDS_PER_HOUR).

        Raises:
            OTPResendCooldownError: if called within the cooldown window.
            OTPResendLimitError:    if the hourly cap is exceeded.
        """
        # 1. Cooldown guard
        if await self._redis.exists(self._cooldown_key(user.id)):
            ttl = await self._redis.ttl(self._cooldown_key(user.id))
            raise OTPResendCooldownError(
                f"Please wait {ttl} seconds before requesting a new code."
            )

        # 2. Hourly cap guard
        count_key = self._resend_count_key(user.id)
        current_count = await self._redis.get(count_key)
        if current_count and int(current_count) >= settings.OTP_MAX_RESENDS_PER_HOUR:
            raise OTPResendLimitError(
                "Maximum resend attempts reached. Please try again in an hour."
            )

        # Guards passed — send fresh OTP
        await self.send_otp(user)

        # Set cooldown sentinel
        await self._redis.set(
            self._cooldown_key(user.id),
            "1",
            ex=settings.OTP_RESEND_COOLDOWN_SECONDS,
        )

        # Increment hourly counter (set TTL only on first increment)
        pipe = self._redis.pipeline()
        pipe.incr(count_key)
        pipe.expire(count_key, 3600, nx=True)  # only set TTL if key is new
        await pipe.execute()

    async def verify_otp(self, user: User, submitted_code: str) -> None:
        """
        Validate the submitted OTP against the stored code.

        On success:  deletes the Redis key (one-time use).
        On failure:  raises OTPExpiredError or OTPInvalidError.

        The caller is responsible for updating user.is_verified and
        committing the DB session.

        Raises:
            OTPExpiredError: if no OTP exists for this user (never sent or expired).
            OTPInvalidError: if the code does not match.
        """
        stored_code = await self._redis.get(self._otp_key(user.id))

        if stored_code is None:
            raise OTPExpiredError(
                "Verification code has expired or was never issued. "
                "Please request a new one."
            )

        # Decode bytes if Redis returns bytes
        if isinstance(stored_code, bytes):
            stored_code = stored_code.decode()

        # Constant-time comparison to prevent timing attacks
        if not secrets.compare_digest(stored_code, submitted_code.strip()):
            raise OTPInvalidError("Invalid verification code.")

        # One-time use: delete after successful verification
        await self._redis.delete(self._otp_key(user.id))
        # Also clear rate-limit keys so a re-register gets a clean slate
        await self._redis.delete(self._cooldown_key(user.id))
        await self._redis.delete(self._resend_count_key(user.id))

    # ------------------------------------------------------------------
    # Core operations – password reset
    # ------------------------------------------------------------------

    async def _send_password_reset_email(self, user: User, code: str) -> None:
        """Render password-reset templates and dispatch the email."""
        context = self._build_email_context(user, code)
        html_body = _render_template("password_reset.html", context)
        text_body = _render_template("password_reset.txt", context)

        provider = get_email_provider()
        await provider.send_email(
            to=user.email,
            subject="Reset your VentureScope password",
            html=html_body,
            text=text_body,
        )

    async def send_password_reset_otp(self, user: User) -> None:
        """
        Generate a fresh OTP for password reset, store it, and email it.

        Uses a separate Redis namespace (pwd_reset:*) so it doesn't
        interfere with email-verification OTPs.
        """
        code = self._generate_code()
        await self._redis.set(
            self._pwd_reset_key(user.id),
            code,
            ex=settings.OTP_EXPIRE_MINUTES * 60,
        )

        try:
            await self._send_password_reset_email(user, code)
        except EmailDeliveryError:
            logger.exception(
                "Failed to send password-reset email to user %s", user.id
            )
            raise

    async def resend_password_reset_otp(self, user: User) -> None:
        """
        Resend password-reset OTP with rate-limiting (same rules as
        email-verification resend but with its own counters).

        Raises:
            OTPResendCooldownError: if called within the cooldown window.
            OTPResendLimitError:    if the hourly cap is exceeded.
        """
        # 1. Cooldown guard
        if await self._redis.exists(self._pwd_reset_cooldown_key(user.id)):
            ttl = await self._redis.ttl(self._pwd_reset_cooldown_key(user.id))
            raise OTPResendCooldownError(
                f"Please wait {ttl} seconds before requesting a new code."
            )

        # 2. Hourly cap guard
        count_key = self._pwd_reset_count_key(user.id)
        current_count = await self._redis.get(count_key)
        if current_count and int(current_count) >= settings.OTP_MAX_RESENDS_PER_HOUR:
            raise OTPResendLimitError(
                "Maximum resend attempts reached. Please try again in an hour."
            )

        # Guards passed — send fresh OTP
        await self.send_password_reset_otp(user)

        # Set cooldown sentinel
        await self._redis.set(
            self._pwd_reset_cooldown_key(user.id),
            "1",
            ex=settings.OTP_RESEND_COOLDOWN_SECONDS,
        )

        # Increment hourly counter
        pipe = self._redis.pipeline()
        pipe.incr(count_key)
        pipe.expire(count_key, 3600, nx=True)
        await pipe.execute()

    async def verify_password_reset_otp(
        self, user: User, submitted_code: str
    ) -> None:
        """
        Validate the submitted password-reset OTP.

        On success the caller should hash and persist the new password.

        Raises:
            OTPExpiredError: if no reset code exists (never sent or expired).
            OTPInvalidError: if the code does not match.
        """
        stored_code = await self._redis.get(self._pwd_reset_key(user.id))

        if stored_code is None:
            raise OTPExpiredError(
                "Reset code has expired or was never issued. "
                "Please request a new one."
            )

        if isinstance(stored_code, bytes):
            stored_code = stored_code.decode()

        if not secrets.compare_digest(stored_code, submitted_code.strip()):
            raise OTPInvalidError("Invalid reset code.")

        # One-time use
        await self._redis.delete(self._pwd_reset_key(user.id))
        await self._redis.delete(self._pwd_reset_cooldown_key(user.id))
        await self._redis.delete(self._pwd_reset_count_key(user.id))


# ---------------------------------------------------------------------------
# Factory / dependency
# ---------------------------------------------------------------------------


def get_redis_client() -> aioredis.Redis:
    """Return a shared async Redis client from REDIS_URL.

    Handles the ``ssl_cert_reqs=CERT_NONE`` query parameter that Render
    Redis URLs commonly include.  redis-py >=5.x rejects this as a URL
    query-string param, so we strip it and pass the SSL configuration
    explicitly.
    """
    if not settings.REDIS_URL:
        raise ValueError("REDIS_URL must be configured for OTP storage.")

    url = settings.REDIS_URL
    parsed = urlparse(url)
    extra_kwargs: dict = {}

    # Handle SSL connections (rediss:// scheme)
    if parsed.scheme == "rediss":
        # Strip ssl_cert_reqs from query string if present
        qs = parse_qs(parsed.query)
        cert_req_value = qs.pop("ssl_cert_reqs", [None])[0]

        # Rebuild the URL without ssl_cert_reqs
        cleaned_query = urlencode(
            {k: v[0] for k, v in qs.items()}, doseq=False
        )
        parsed = parsed._replace(query=cleaned_query)
        url = urlunparse(parsed)

        
        if cert_req_value and "NONE" in cert_req_value.upper():
            extra_kwargs["ssl_cert_reqs"] = "none"
            extra_kwargs["ssl_check_hostname"] = False

    return aioredis.from_url(url, decode_responses=False, **extra_kwargs)


async def get_otp_service() -> OTPService:
    """
    FastAPI dependency that yields an OTPService backed by Redis.

    Usage in endpoints:
        otp_service: OTPService = Depends(get_otp_service)
    """
    client = get_redis_client()
    return OTPService(client)

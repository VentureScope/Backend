"""
JWT creation and verification, password hashing.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
from dataclasses import dataclass
from enum import Enum

from jose import JWTError, jwt, ExpiredSignatureError
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenError(Enum):
    """Token decoding error types for more specific error handling."""

    EXPIRED = "expired"
    INVALID_SIGNATURE = "invalid_signature"
    MALFORMED = "malformed"
    MISSING_CLAIMS = "missing_claims"


@dataclass
class TokenPayload:
    """Decoded JWT token payload."""

    sub: str  # Subject (user ID)
    jti: str  # JWT ID (unique token identifier)
    exp: datetime  # Expiration time


@dataclass
class TokenValidationResult:
    """Result of token validation with error details."""

    payload: TokenPayload | None
    error_type: TokenError | None
    error_message: str | None

    @property
    def is_valid(self) -> bool:
        return self.payload is not None and self.error_type is None


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(
    subject: str | Any, expires_delta: timedelta | None = None
) -> str:
    """
    Create a JWT access token with JTI for revocation support.

    Args:
        subject: The subject claim (typically user ID)
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(timezone.utc) + expires_delta
    jti = str(uuid4())  # Unique token ID for blocklist
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "jti": jti,
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> str | None:
    """
    Decode token and return subject (user ID) only.

    Legacy function for backward compatibility.
    Use decode_access_token_full() for full payload including JTI.
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        return payload.get("sub")
    except JWTError:
        return None


def decode_access_token_full(token: str) -> TokenPayload | None:
    """
    Decode token and return full payload including JTI.

    Args:
        token: JWT token string

    Returns:
        TokenPayload with sub, jti, exp or None if invalid
    """
    result = decode_access_token_with_details(token)
    return result.payload


def decode_access_token_with_details(token: str) -> TokenValidationResult:
    """
    Decode token and return detailed validation result.

    Args:
        token: JWT token string

    Returns:
        TokenValidationResult with payload or error details
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        sub = payload.get("sub")
        jti = payload.get("jti")
        exp = payload.get("exp")

        if not sub or not jti or not exp:
            return TokenValidationResult(
                payload=None,
                error_type=TokenError.MISSING_CLAIMS,
                error_message="Token missing required claims (sub, jti, or exp)",
            )

        # Convert exp timestamp to datetime
        exp_datetime = datetime.fromtimestamp(exp, tz=timezone.utc)

        token_payload = TokenPayload(sub=sub, jti=jti, exp=exp_datetime)
        return TokenValidationResult(
            payload=token_payload, error_type=None, error_message=None
        )

    except ExpiredSignatureError:
        return TokenValidationResult(
            payload=None,
            error_type=TokenError.EXPIRED,
            error_message="Token has expired",
        )
    except JWTError as e:
        # Check if it's a signature error
        if "signature" in str(e).lower():
            return TokenValidationResult(
                payload=None,
                error_type=TokenError.INVALID_SIGNATURE,
                error_message="Invalid token signature",
            )
        else:
            return TokenValidationResult(
                payload=None,
                error_type=TokenError.MALFORMED,
                error_message="Malformed token structure",
            )

import re

from pydantic import BaseModel, EmailStr, Field, field_validator


class OtpVerifyRequest(BaseModel):
    """Request body for POST /auth/verify-email."""

    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class OtpResendRequest(BaseModel):
    """Request body for POST /auth/otp/resend."""

    email: EmailStr


class OtpVerifyResponse(BaseModel):
    """Response body for a successful email verification."""

    message: str = "Email verified successfully."


class OtpResendResponse(BaseModel):
    """Response body for a successful OTP resend."""

    message: str = "Verification code sent. Please check your email."


# ==================== Password Reset Schemas ====================


class ForgotPasswordRequest(BaseModel):
    """Request body for POST /auth/forgot-password."""

    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    """Response body for a forgot-password request.

    Always returns the same message to prevent email enumeration.
    """

    message: str = "If an account with that email exists, a reset code has been sent."


class ResetPasswordRequest(BaseModel):
    """Request body for POST /auth/reset-password."""

    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(
        ...,
        min_length=8,
        description="New password — must contain uppercase, lowercase, a digit, and a special character",
    )

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, v: str) -> str:
        errors = []
        if not re.search(r"[A-Z]", v):
            errors.append("one uppercase letter")
        if not re.search(r"[a-z]", v):
            errors.append("one lowercase letter")
        if not re.search(r"\d", v):
            errors.append("one digit")
        if not re.search(r"[^A-Za-z0-9]", v):
            errors.append("one special character")
        if errors:
            raise ValueError(f"Password must contain {', '.join(errors)}.")
        return v


class ResetPasswordResponse(BaseModel):
    """Response body for a successful password reset."""

    message: str = "Password reset successfully. You can now sign in."

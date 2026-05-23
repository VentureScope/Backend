from datetime import datetime
from typing import Literal
import re

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

# Valid role values matching UserRole enum
RoleType = Literal["student", "professional", "b2b_client"]


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(
        ...,
        min_length=8,
        description="Password must be at least 8 characters and contain uppercase, lowercase, a digit, and a special character",
    )
    full_name: str | None = None
    github_username: str | None = None
    career_interest: str | None = None
    skills: list[str] | None = None
    role: RoleType = "professional"

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
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
            raise ValueError(
                f"Password must contain {', '.join(errors)}."
            )
        return v


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str | None
    github_username: str | None
    career_interest: str | None
    skills: list[str] | None
    cv_url: str | None
    profile_picture_url: str | None
    estudent_profile: str | None
    social_links: dict | None
    role: str
    is_active: bool
    is_admin: bool
    oauth_provider: str | None = None
    mfa_enabled: bool = False
    mfa_enrolled_at: datetime | None = None
    deactivated_at: datetime | None = None
    has_password: bool = False
    # Internal field to help populate has_password from ORM
    password_hash: str | None = Field(None, exclude=True)

    class Config:
        from_attributes = True

    @model_validator(mode="after")
    def set_has_password(self) -> "UserResponse":
        """Set has_password based on presence of password_hash."""
        if self.password_hash is not None:
            self.has_password = True
        return self


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = False


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ==================== Phase B: User Management Schemas ====================


class UserUpdate(BaseModel):
    """Schema for updating user profile (self-service)."""

    full_name: str | None = None
    github_username: str | None = None
    career_interest: str | None = None
    skills: list[str] | None = None
    estudent_profile: str | None = None

    class Config:
        from_attributes = True


class SkillsUpdate(BaseModel):
    """Schema for updating user skills."""

    skills: list[str] = Field(..., min_length=1, description="List of skills")


class CVUploadResponse(BaseModel):
    """Schema for CV upload response."""

    cv_url: str
    message: str


class ProfilePictureUploadResponse(BaseModel):
    """Schema for profile picture upload response."""

    profile_picture_url: str
    message: str


class PasswordChange(BaseModel):
    """Schema for changing password."""

    current_password: str = Field(..., description="Current password for verification")
    new_password: str = Field(
        ..., min_length=8, description="New password (min 8 characters)"
    )


class UserAdminUpdate(BaseModel):
    """Schema for admin updating any user."""

    full_name: str | None = None
    github_username: str | None = None
    career_interest: str | None = None
    skills: list[str] | None = None
    cv_url: str | None = None
    estudent_profile: str | None = None
    role: RoleType | None = None
    is_active: bool | None = None
    is_admin: bool | None = None


class UserListResponse(BaseModel):
    """Paginated list of users for admin endpoints."""

    items: list[UserResponse]
    total: int
    page: int
    per_page: int
    pages: int


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str
    detail: str | None = None

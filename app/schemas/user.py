from typing import Literal

from pydantic import BaseModel, EmailStr, Field

# Valid role values matching UserRole enum
RoleType = Literal["student", "professional", "b2b_client"]


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(
        ..., min_length=8, description="Password must be at least 8 characters"
    )
    full_name: str | None = None
    github_username: str | None = None
    career_interest: str | None = None
    skills: list[str] | None = None
    role: RoleType = "professional"


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str | None
    github_username: str | None
    career_interest: str | None
    skills: list[str] | None
    cv_url: str | None
    estudent_profile: str | None
    role: str
    is_active: bool
    is_admin: bool

    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    email: EmailStr
    password: str


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

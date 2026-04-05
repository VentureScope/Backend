"""
User Management API Endpoints - Phase B Implementation.
Handles user profile operations (self-service).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.user import (
    UserResponse,
    UserUpdate,
    PasswordChange,
    MessageResponse,
)
from app.services.user_service import UserService

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Get current user's profile."""
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_current_user_profile(
    data: UserUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update current user's profile.

    Allows updating:
    - full_name
    - github_username
    - career_interest
    """
    service = UserService(db)
    try:
        updated_user = await service.update_profile(current_user.id, data)
        await db.commit()
        return updated_user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/me/password", response_model=MessageResponse)
async def change_password(
    data: PasswordChange,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Change current user's password.

    Requires current password for verification.
    New password must be at least 8 characters.
    """
    service = UserService(db)
    try:
        await service.change_password(current_user.id, data)
        await db.commit()
        return MessageResponse(
            message="Password changed successfully",
            detail="Please use your new password for future logins",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class DeleteAccountRequest(BaseModel):
    """Request body for account deletion."""

    password: str


@router.delete("/me", response_model=MessageResponse)
async def delete_current_user_account(
    data: DeleteAccountRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Delete current user's account (soft delete).

    Requires password verification for security.
    The account will be deactivated, not permanently deleted.
    Contact support to reactivate or permanently delete your data.
    """
    service = UserService(db)
    try:
        await service.delete_account(current_user.id, data.password)
        await db.commit()
        return MessageResponse(
            message="Account deleted successfully",
            detail="Your account has been deactivated. Contact support to restore.",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

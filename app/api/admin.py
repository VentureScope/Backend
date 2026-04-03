"""
Admin API Endpoints - Phase B Implementation.
Handles admin-only user management operations.
"""

from typing import Annotated
import math

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.user import (
    UserResponse,
    UserAdminUpdate,
    UserListResponse,
    MessageResponse,
)
from app.services.user_service import UserService

router = APIRouter()

# UUID v4 pattern for path parameter validation
UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"


@router.get("/users", response_model=UserListResponse)
async def list_users(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(10, ge=1, le=100, description="Items per page"),
    include_inactive: bool = Query(False, description="Include deactivated users"),
):
    """
    List all users with pagination (admin only).

    - **page**: Page number (default: 1)
    - **per_page**: Items per page, max 100 (default: 10)
    - **include_inactive**: Include deactivated users (default: False)
    """
    service = UserService(db)
    users, total = await service.list_users(
        page=page, per_page=per_page, include_inactive=include_inactive
    )

    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        per_page=per_page,
        pages=math.ceil(total / per_page) if total > 0 else 0,
    )


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: Annotated[str, Path(description="User UUID", pattern=UUID_PATTERN)],
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get a specific user by ID (admin only)."""
    service = UserService(db)
    user = await service.admin_get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: Annotated[str, Path(description="User UUID", pattern=UUID_PATTERN)],
    data: UserAdminUpdate,
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update any user (admin only).

    Can update:
    - full_name
    - github_username
    - career_interest
    - role
    - is_active
    - is_admin
    """
    # Prevent admin from demoting themselves
    if user_id == current_admin.id and data.is_admin is False:
        raise HTTPException(
            status_code=400, detail="Cannot remove your own admin privileges"
        )

    # Prevent admin from deactivating themselves
    if user_id == current_admin.id and data.is_active is False:
        raise HTTPException(
            status_code=400,
            detail="Cannot deactivate your own account via admin endpoint",
        )

    service = UserService(db)
    try:
        updated_user = await service.admin_update_user(user_id, data)
        await db.commit()
        return updated_user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/users/{user_id}", response_model=MessageResponse)
async def delete_user(
    user_id: Annotated[str, Path(description="User UUID", pattern=UUID_PATTERN)],
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    hard_delete: bool = Query(False, description="Permanently delete user"),
):
    """
    Delete a user (admin only).

    By default uses soft delete (deactivates the account).
    Set hard_delete=true to permanently remove the user.

    Cannot delete yourself.
    """
    if user_id == current_admin.id:
        raise HTTPException(
            status_code=400, detail="Cannot delete your own account via admin endpoint"
        )

    service = UserService(db)
    try:
        await service.admin_delete_user(user_id, hard_delete=hard_delete)
        await db.commit()

        if hard_delete:
            return MessageResponse(
                message="User permanently deleted",
                detail="User data has been removed from the system",
            )
        return MessageResponse(
            message="User deactivated", detail="User account has been deactivated"
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/users/{user_id}/reactivate", response_model=UserResponse)
async def reactivate_user(
    user_id: Annotated[str, Path(description="User UUID", pattern=UUID_PATTERN)],
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Reactivate a deactivated user (admin only)."""
    service = UserService(db)
    try:
        user = await service.admin_reactivate_user(user_id)
        await db.commit()
        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

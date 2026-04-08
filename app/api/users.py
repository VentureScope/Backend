"""
User Management API Endpoints - Phase B Implementation.
Handles user profile operations (self-service).
"""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.user import (
    UserResponse,
    UserUpdate,
    PasswordChange,
    MessageResponse,
    SkillsUpdate,
    CVUploadResponse,
)
from app.models.github_sync_snapshot import GitHubSyncSnapshot
from app.schemas.oauth import GitHubProfileSyncResponse, GitHubSyncedDataResponse
from app.services.user_service import UserService
from app.services.oauth_service import OAuthService
from app.services.s3_service import S3UploadError

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
    - skills
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


@router.get("/me/github/sync", response_model=GitHubProfileSyncResponse)
async def sync_github_profile(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Sync the current user's GitHub profile into VentureScope.

    If the user is not connected via GitHub OAuth yet, the response includes
    an authorization URL that starts the GitHub OAuth flow.
    If the connected token is missing repo-level access, the response includes
    an updated authorization URL to request broader scopes.
    """
    service = OAuthService(db)
    try:
        result = await service.get_github_profile_sync_status(current_user.id)
        return GitHubProfileSyncResponse.model_validate(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GitHub sync failed: {str(e)}")


@router.get("/me/github/synced-data", response_model=GitHubSyncedDataResponse)
async def get_github_synced_data(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get persisted GitHub sync snapshot data for the current user."""
    result = await db.execute(
        select(GitHubSyncSnapshot).where(GitHubSyncSnapshot.user_id == current_user.id)
    )
    snapshot = result.scalar_one_or_none()

    if not snapshot:
        raise HTTPException(
            status_code=404,
            detail=(
                "No GitHub synced data found for user. "
                "Run /api/users/me/github/sync first."
            ),
        )

    return GitHubSyncedDataResponse(
        github_username=snapshot.github_username,
        repositories=json.loads(snapshot.repositories_json or "[]"),
        contributions=json.loads(snapshot.contributions_json or "{}"),
        organizations=json.loads(snapshot.organizations_json or "[]"),
        synced_at=snapshot.synced_at.isoformat(),
    )


@router.put("/me/skills", response_model=UserResponse)
async def update_skills(
    data: SkillsUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update current user's skills.

    Skills should be a list of strings representing the user's professional skills.
    This will update the user's embedding for better recommendations.
    """
    service = UserService(db)
    try:
        updated_user = await service.update_skills(current_user.id, data)
        await db.commit()
        return updated_user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/me/cv", response_model=CVUploadResponse)
async def upload_cv(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(..., description="CV file (PDF, DOC, DOCX)"),
):
    """
    Upload a CV for the current user.

    Allowed file types: PDF, DOC, DOCX
    Maximum file size: 10MB

    The CV will be stored in S3 and the URL will be saved in the database.
    The user's embedding will be updated to include CV information.
    """
    service = UserService(db)

    # Validate content type
    allowed_types = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: PDF, DOC, DOCX",
        )

    try:
        file_content = await file.read()
        cv_url = await service.upload_cv(
            user_id=current_user.id,
            file_content=file_content,
            filename=file.filename,
            content_type=file.content_type,
        )
        await db.commit()
        return CVUploadResponse(
            cv_url=cv_url,
            message="CV uploaded successfully",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except S3UploadError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/me/cv", response_model=MessageResponse)
async def delete_cv(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Delete the current user's CV.

    This will remove the CV from S3 and clear the CV URL from the database.
    The user's embedding will be updated.
    """
    service = UserService(db)
    try:
        await service.delete_cv(current_user.id)
        await db.commit()
        return MessageResponse(
            message="CV deleted successfully",
            detail="Your CV has been removed",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/me/cv/url")
async def get_cv_url(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    expiration: int = 3600,
):
    """
    Get a presigned URL for downloading the user's CV.

    The presigned URL will be valid for the specified expiration time (default: 1 hour).
    """
    service = UserService(db)
    presigned_url = await service.get_cv_presigned_url(
        current_user.id, expiration=expiration
    )

    if not presigned_url:
        raise HTTPException(
            status_code=404,
            detail="No CV found for this user",
        )

    return {"url": presigned_url}

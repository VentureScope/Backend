"""
API endpoints for academic transcript management.
"""

from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.services.transcript_service import TranscriptService
from app.schemas.academic_transcript import (
    TranscriptCreate,
    TranscriptResponse,
    TranscriptListResponse,
    TranscriptUploadResponse,
)
from app.schemas.transcript_config import GradeRecommendation
from app.core.rate_limit import transcript_upload_limiter

router = APIRouter(prefix="/api/transcripts", tags=["transcripts"])


@router.post(
    "/", response_model=TranscriptUploadResponse, status_code=status.HTTP_201_CREATED
)
async def upload_transcript(
    data: TranscriptCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Upload a new academic transcript.

    Creates a new version of the transcript and performs the following:
    - Validates all GPA values against your configured grading scale
    - Ensures student_id consistency across uploads
    - Automatically deletes old versions (keeps latest 3)
    - Returns upload metadata including version number

    Rate limit: 10 uploads per hour per user.

    **Validation:**
    - At least one semester is required
    - SGPA and CGPA must not exceed your configured GPA scale
    - Student ID must match existing transcripts (if any exist)
    - Credit hours must be positive
    - Grade points must be non-negative (or null)
    """
    # Check rate limit
    transcript_upload_limiter.check_rate_limit(current_user.id)

    try:
        service = TranscriptService(db)
        transcript, versions_deleted, is_first_upload = await service.create_transcript(
            current_user.id, data
        )

        # Convert to response with additional metadata
        response_data = TranscriptUploadResponse(
            id=transcript.id,
            user_id=transcript.user_id,
            student_id=transcript.student_id,
            version=transcript.version,
            uploaded_at=transcript.uploaded_at,
            created_at=transcript.created_at,
            updated_at=transcript.updated_at,
            transcript_data=data.transcript_data,
            is_first_upload=is_first_upload,
            versions_deleted=versions_deleted,
        )

        return response_data

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/", response_model=TranscriptListResponse)
async def list_transcripts(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get all transcript versions for the current user.

    Returns all versions (up to 3) ordered by version number descending (newest first).
    Each version represents a separate upload with its own timestamp.
    """
    service = TranscriptService(db)
    transcripts = await service.get_user_transcripts(current_user.id)

    return TranscriptListResponse(transcripts=transcripts, total_count=len(transcripts))


@router.get("/latest", response_model=TranscriptResponse)
async def get_latest_transcript(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get the latest transcript version for the current user.

    Returns the most recently uploaded transcript.
    Useful for Chrome extension to fetch current data without listing all versions.
    """
    service = TranscriptService(db)
    transcript = await service.get_latest_transcript(current_user.id)

    if transcript is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No transcripts found. Please upload a transcript first.",
        )

    return transcript


@router.post("/recommend-config", response_model=GradeRecommendation)
async def recommend_grading_config(
    data: TranscriptCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get recommended grading configuration based on transcript data.

    Analyzes the grades in your transcript and suggests the most appropriate
    grading system preset (e.g., US 4.0 Scale, European 10-Point, etc.).

    **Note:** This is a read-only operation and doesn't upload the transcript.
    Use this before uploading to ensure you have the correct grading configuration.

    Returns:
    - Detected grades from your transcript
    - Recommended preset name
    - Confidence level (high/medium/low)
    - Explanation for the recommendation
    - Complete suggested configuration
    """
    service = TranscriptService(db)
    recommendation = await service.get_grade_recommendation(current_user.id, data)
    return recommendation


@router.get("/{transcript_id}", response_model=TranscriptResponse)
async def get_transcript(
    transcript_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get a specific transcript by ID.

    You can only access your own transcripts.
    """
    try:
        service = TranscriptService(db)
        transcript = await service.get_transcript_by_id(transcript_id, current_user.id)
        return transcript
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/{transcript_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transcript(
    transcript_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Delete a specific transcript version.

    **Note:** Transcripts are immutable after upload.
    To update data, upload a new version instead of modifying existing ones.
    """
    try:
        service = TranscriptService(db)
        await service.delete_transcript(transcript_id, current_user.id)
        return None
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_transcripts(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Delete all transcript versions for the current user.

    **Warning:** This operation cannot be undone.
    All transcript data will be permanently deleted.
    """
    service = TranscriptService(db)
    await service.delete_all_transcripts(current_user.id)
    return None

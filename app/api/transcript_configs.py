"""
API endpoints for transcript configuration management.
"""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.services.transcript_config_service import TranscriptConfigService
from app.schemas.transcript_config import (
    TranscriptConfigUpdate,
    TranscriptConfigResponse,
    GradingPresetsResponse,
)

router = APIRouter(prefix="/api/transcript-configs", tags=["transcript-configs"])


@router.get("/", response_model=TranscriptConfigResponse)
async def get_config(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get current user's transcript configuration.

    Auto-creates default configuration (US 4.0 Scale) if none exists.
    """
    service = TranscriptConfigService(db)
    config = await service.get_or_create_default(current_user.id)
    return config


@router.put("/", response_model=TranscriptConfigResponse)
async def update_config(
    data: TranscriptConfigUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update current user's transcript configuration.

    Creates new configuration if none exists.
    Validates that:
    - GPA scale is positive and <= 100
    - Grading schema is not empty
    - Grade display order matches schema keys
    """
    service = TranscriptConfigService(db)

    # Validate that display order contains all schema keys
    schema_keys = set(data.grading_schema.keys())
    display_keys = set(data.grade_display_order)

    if schema_keys != display_keys:
        missing_in_display = schema_keys - display_keys
        extra_in_display = display_keys - schema_keys

        error_msg = "grade_display_order must contain exactly the same grades as grading_schema. "
        if missing_in_display:
            error_msg += f"Missing in display order: {', '.join(missing_in_display)}. "
        if extra_in_display:
            error_msg += f"Extra in display order: {', '.join(extra_in_display)}."

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error_msg
        )

    config = await service.update_config(current_user.id, data)
    return config


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
async def reset_config(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Reset configuration to default (US 4.0 Scale).

    Deletes current configuration and recreates with default values.
    """
    service = TranscriptConfigService(db)
    await service.reset_to_default(current_user.id)
    return None


@router.get("/presets", response_model=GradingPresetsResponse)
async def get_presets():
    """
    Get available grading system presets.

    Returns a list of predefined grading configurations including:
    - US 4.0 Scale (Standard)
    - US 5.0 Scale (Weighted)
    - European 10-Point Scale
    - UK Classification System
    - Percentage-Based (100-Point)

    These can be used directly to configure the user's grading system.
    """
    return TranscriptConfigService.get_presets()

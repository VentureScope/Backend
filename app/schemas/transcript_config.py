"""
Pydantic schemas for TranscriptConfig API requests and responses.
"""

from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class TranscriptConfigBase(BaseModel):
    """Base schema for transcript configuration."""

    gpa_scale: float = Field(
        gt=0, le=100, description="Maximum GPA value (e.g., 4.0, 5.0, 10.0)"
    )
    grading_schema: Dict[str, Optional[float]] = Field(
        description="Mapping of grade strings to GPA values. Use null for non-GPA grades (W, IP, etc.)"
    )
    grade_display_order: List[str] = Field(
        description="Ordered list of grade strings for UI display"
    )

    @field_validator("grading_schema")
    @classmethod
    def validate_grading_schema(
        cls, v: Dict[str, Optional[float]]
    ) -> Dict[str, Optional[float]]:
        """Validate that grading schema is not empty and values are valid."""
        if not v:
            raise ValueError("grading_schema cannot be empty")

        for grade, gpa_value in v.items():
            if not grade or not isinstance(grade, str):
                raise ValueError("Grade keys must be non-empty strings")

            if gpa_value is not None:
                if not isinstance(gpa_value, (int, float)):
                    raise ValueError(
                        f"GPA value for grade '{grade}' must be a number or null"
                    )
                if gpa_value < 0:
                    raise ValueError(
                        f"GPA value for grade '{grade}' cannot be negative"
                    )

        return v

    @field_validator("grade_display_order")
    @classmethod
    def validate_grade_display_order(cls, v: List[str], info) -> List[str]:
        """Validate that display order matches grading schema keys."""
        if not v:
            raise ValueError("grade_display_order cannot be empty")

        # Check for duplicates
        if len(v) != len(set(v)):
            raise ValueError("grade_display_order contains duplicate grades")

        return v


class TranscriptConfigCreate(TranscriptConfigBase):
    """Schema for creating a new transcript configuration."""

    pass


class TranscriptConfigUpdate(TranscriptConfigBase):
    """Schema for updating an existing transcript configuration."""

    pass


class TranscriptConfigResponse(TranscriptConfigBase):
    """Schema for transcript configuration responses."""

    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GradingPreset(BaseModel):
    """Schema for a grading system preset."""

    name: str = Field(description="Display name of the grading system")
    description: str = Field(description="Brief description of when to use this system")
    gpa_scale: float
    grading_schema: Dict[str, Optional[float]]
    grade_display_order: List[str]


class GradingPresetsResponse(BaseModel):
    """Schema for listing available grading presets."""

    presets: List[GradingPreset]


class GradeRecommendation(BaseModel):
    """Schema for recommended grading configuration based on detected grades."""

    detected_grades: List[str] = Field(
        description="Unique grades found in uploaded transcript"
    )
    recommended_preset: str = Field(description="Name of recommended preset")
    confidence: str = Field(description="Confidence level: high, medium, low")
    reason: str = Field(description="Explanation for the recommendation")
    suggested_config: GradingPreset = Field(
        description="Complete suggested configuration"
    )

"""
Pydantic schemas for AcademicTranscript API requests and responses.
Includes nested validation matching the e-student JSON schema.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class CourseSchema(BaseModel):
    """Individual course within a semester."""

    code: str = Field(description="Course code (e.g., CS101)")
    title: str = Field(description="Course title")
    credit_hours: float = Field(gt=0, description="Credit hours for the course")
    grade: str = Field(description="Letter grade received (e.g., A, B+, IP, W, -)")
    points: Optional[float] = Field(
        None, description="Grade points earned (null for non-graded courses)"
    )

    @field_validator("points")
    @classmethod
    def validate_points(cls, v: Optional[float]) -> Optional[float]:
        """Ensure points are non-negative if provided."""
        if v is not None and v < 0:
            raise ValueError("points cannot be negative")
        return v


class SemesterSummarySchema(BaseModel):
    """Summary statistics for a single semester."""

    credit_hours: float = Field(ge=0, description="Total credit hours for the semester")
    points: float = Field(
        default=0, ge=0, description="Total grade points for the semester"
    )
    sgpa: float = Field(ge=0, description="Semester GPA")
    academic_status: Optional[str] = Field(
        None, description="Academic standing (e.g., Good Standing, Warning)"
    )


class CumulativeSummarySchema(BaseModel):
    """Cumulative summary up to and including this semester."""

    credit_hours: float = Field(ge=0, description="Total credit hours earned to date")
    points: float = Field(
        default=0, ge=0, description="Total grade points earned to date"
    )
    cgpa: float = Field(ge=0, description="Cumulative GPA")


class SemesterSchema(BaseModel):
    """Complete data for one academic semester."""

    academic_year: str = Field(
        pattern=r"^\d{4}/\d{4}$",
        description="Academic year in format YYYY/YYYY (e.g., 2023/2024)",
    )
    semester: str = Field(
        description="Semester name (e.g., First Semester, Second Semester, Summer)"
    )
    year_level: Optional[str] = Field(
        None, description="Year level (e.g., First Year, Sophomore)"
    )
    courses: List[CourseSchema] = Field(
        description="List of courses taken in this semester"
    )
    semester_summary: SemesterSummarySchema = Field(
        description="Semester performance summary"
    )
    cumulative_summary: CumulativeSummarySchema = Field(
        description="Cumulative performance summary"
    )


class TranscriptDataSchema(BaseModel):
    """Complete transcript data structure."""

    student_id: Optional[str] = Field(
        None, description="Student ID from e-student profile"
    )
    semesters: List[SemesterSchema] = Field(description="List of academic semesters")

    @field_validator("semesters")
    @classmethod
    def validate_semesters_not_empty(
        cls, v: List[SemesterSchema]
    ) -> List[SemesterSchema]:
        """Ensure at least one semester is provided."""
        if not v:
            raise ValueError("At least one semester is required")
        return v


class TranscriptCreate(BaseModel):
    """Schema for creating a new transcript (upload)."""

    transcript_data: TranscriptDataSchema = Field(
        description="Complete transcript data from e-student"
    )


class TranscriptResponse(BaseModel):
    """Schema for transcript API responses."""

    id: str
    user_id: str
    student_id: Optional[str]
    version: int
    uploaded_at: datetime
    created_at: datetime
    updated_at: datetime
    transcript_data: TranscriptDataSchema

    model_config = {"from_attributes": True}


class TranscriptListResponse(BaseModel):
    """Schema for listing multiple transcript versions."""

    transcripts: List[TranscriptResponse]
    total_count: int = Field(
        description="Total number of transcript versions for this user"
    )


class TranscriptUploadResponse(TranscriptResponse):
    """Extended response for upload operations with additional metadata."""

    is_first_upload: bool = Field(
        description="Whether this is the user's first transcript upload"
    )
    versions_deleted: int = Field(
        default=0, description="Number of old versions deleted during cleanup"
    )

"""
Pydantic schemas for Experience model.
"""

from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


class ExperienceCreate(BaseModel):
    """Schema for adding a new work experience."""

    job_title: str = Field(..., min_length=1, max_length=255)
    company: str = Field(..., min_length=1, max_length=255)
    start_date: datetime
    end_date: datetime | None = None  # None = current job
    description: str | None = None
    skills_used: list[str] | None = None


class ExperienceUpdate(BaseModel):
    """Schema for updating an existing experience."""

    job_title: str | None = None
    company: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    description: str | None = None
    skills_used: list[str] | None = None


class ExperienceResponse(BaseModel):
    """Schema for returning experience data."""

    id: str
    job_title: str
    company: str
    start_date: datetime
    end_date: datetime | None
    description: str | None
    skills_used: list[str] | None
    created_at: datetime

    class Config:
        from_attributes = True

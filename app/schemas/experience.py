"""
Pydantic schemas for Experience model.
"""

from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from typing import Any, Optional
import json


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

    @field_validator('skills_used', mode='before')
    @classmethod
    def parse_skills_used(cls, v: Any) -> list[str] | None:
        """Handle both JSON strings and actual lists from DB."""
        if v is None:
            return None
        if isinstance(v, str):
            # Handle JSON string from old VARCHAR data
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                return None
        return v

    class Config:
        from_attributes = True

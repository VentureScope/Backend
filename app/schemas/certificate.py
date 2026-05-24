"""
Pydantic schemas for Certificate model.
"""

from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl


class CertificateCreate(BaseModel):
    """Schema for adding a new certificate."""
    name: str = Field(..., min_length=1, max_length=500)
    issuer: str = Field(..., min_length=1, max_length=255)
    credential_id: str | None = Field(None, max_length=255)
    credential_url: str | None = Field(None, max_length=1000)
    issue_date: datetime | None = None
    expiry_date: datetime | None = None   # None = does not expire
    description: str | None = None


class CertificateUpdate(BaseModel):
    """Schema for updating an existing certificate — all fields optional."""
    name: str | None = Field(None, min_length=1, max_length=500)
    issuer: str | None = Field(None, min_length=1, max_length=255)
    credential_id: str | None = None
    credential_url: str | None = None
    issue_date: datetime | None = None
    expiry_date: datetime | None = None
    description: str | None = None


class CertificateResponse(BaseModel):
    """Schema for returning certificate data."""
    id: str
    user_id: str
    name: str
    issuer: str
    credential_id: str | None = None
    credential_url: str | None = None
    issue_date: datetime | None = None
    expiry_date: datetime | None = None
    description: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

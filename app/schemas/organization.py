"""
Pydantic schemas for Organization feature.
"""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, HttpUrl, field_validator


# ---------------------------------------------------------------------------
# Sub-schemas
# ---------------------------------------------------------------------------

class GitHubOrgEntry(BaseModel):
    name: str
    url: str | None = None


class GitHubRepoEntry(BaseModel):
    name: str
    url: str | None = None


# ---------------------------------------------------------------------------
# Organization create / update
# ---------------------------------------------------------------------------

class OrganizationCreate(BaseModel):
    legal_name: str
    display_name: str
    tagline: str | None = None
    description: str | None = None
    industry: str | None = None
    core_services: list[str] | None = None
    website_url: str | None = None
    linkedin_url: str | None = None
    github_orgs: list[GitHubOrgEntry] | None = None
    github_repos: list[GitHubRepoEntry] | None = None


class OrganizationUpdate(BaseModel):
    display_name: str | None = None
    tagline: str | None = None
    description: str | None = None
    industry: str | None = None
    core_services: list[str] | None = None
    website_url: str | None = None
    linkedin_url: str | None = None
    github_orgs: list[GitHubOrgEntry] | None = None
    github_repos: list[GitHubRepoEntry] | None = None


# ---------------------------------------------------------------------------
# Member output
# ---------------------------------------------------------------------------

class OrgMemberOut(BaseModel):
    user_id: str
    full_name: str | None = None
    email: str
    profile_picture_url: str | None = None
    role: str
    skills: list[str] | None = None
    career_interest: str | None = None
    joined_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Organization list item (compact)
# ---------------------------------------------------------------------------

class OrganizationListItem(BaseModel):
    id: str
    display_name: str
    legal_name: str
    logo_url: str | None = None
    industry: str | None = None
    member_count: int = 0
    my_role: str  # "owner" | "member"
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Organization full detail
# ---------------------------------------------------------------------------

class OrganizationOut(BaseModel):
    id: str
    owner_id: str
    legal_name: str
    display_name: str
    tagline: str | None = None
    logo_url: str | None = None
    description: str | None = None
    industry: str | None = None
    core_services: list[str] | None = None
    website_url: str | None = None
    linkedin_url: str | None = None
    github_orgs: list[dict] | None = None
    github_repos: list[dict] | None = None
    created_at: datetime
    updated_at: datetime
    # Computed fields
    my_role: str  # "owner" | "member"
    member_count: int = 0
    top_skills: list[str] = []
    top_career_interests: list[str] = []
    members: list[OrgMemberOut] = []

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Invite create / output
# ---------------------------------------------------------------------------

class OrgInviteCreate(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v:
            raise ValueError("Invalid email address")
        return v


class OrgInviteOut(BaseModel):
    id: str
    organization_id: str
    email: str
    status: str
    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class AcceptInviteRequest(BaseModel):
    token: str


# ---------------------------------------------------------------------------
# Org roadmap schemas
# ---------------------------------------------------------------------------

class OrgRoadmapAssign(BaseModel):
    """Request body for assigning/generating a roadmap for the org."""
    trend_name: str
    goal: str | None = None


class MemberRoadmapProgress(BaseModel):
    user_id: str
    full_name: str | None = None
    steps_completed: int
    total_steps: int
    completion_percentage: float


class OrgRoadmapOut(BaseModel):
    id: str                    # organization_roadmap link id
    roadmap_id: str
    title: str
    trend_name: str | None = None
    goal: str | None = None
    total_weeks: int
    summary: str | None = None
    # Aggregate across all org members
    total_members: int
    members_completed: int       # count with 100%
    members_in_progress: int     # count with 0% < x < 100%
    aggregate_completion_percentage: float
    per_member_progress: list[MemberRoadmapProgress] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class OrgRoadmapListItem(BaseModel):
    id: str
    roadmap_id: str
    title: str
    trend_name: str | None = None
    total_weeks: int
    total_members: int
    aggregate_completion_percentage: float
    created_at: datetime

    model_config = {"from_attributes": True}

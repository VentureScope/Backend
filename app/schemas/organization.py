"""
Pydantic schemas for Organization feature.
"""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Sub-schemas
# ---------------------------------------------------------------------------

class GitHubOrgEntry(BaseModel):
    name: str
    url: str | None = None


class GitHubRepoEntry(BaseModel):
    name: str
    url: str | None = None


class ProductEntry(BaseModel):
    name: str
    type: str | None = None          # e.g. "SaaS", "API", "Mobile App"
    url: str | None = None
    repos: list[str] = []            # linked repo names


class CustomField(BaseModel):
    id: str
    label: str
    value: str


# ---------------------------------------------------------------------------
# Organization create / update
# ---------------------------------------------------------------------------

class OrganizationCreate(BaseModel):
    # Identity
    legal_name: str
    display_name: str
    # Branding
    tagline: str | None = None
    description: str | None = None
    # Industry & services
    industry: str | None = None
    core_services: list[str] | None = None
    tech_stacks: list[str] | None = None
    # Web & social
    website_url: str | None = None
    linkedin_url: str | None = None
    twitter_url: str | None = None
    # Developer ecosystem
    github_orgs: list[GitHubOrgEntry] | None = None
    github_repos: list[GitHubRepoEntry] | None = None
    # Extended company info
    headquarters: str | None = None
    founded_year: int | None = None
    company_size: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    mission_statement: str | None = None
    products: list[ProductEntry] | None = None
    custom_fields: list[CustomField] | None = None


class OrganizationUpdate(BaseModel):
    display_name: str | None = None
    tagline: str | None = None
    description: str | None = None
    industry: str | None = None
    core_services: list[str] | None = None
    tech_stacks: list[str] | None = None
    website_url: str | None = None
    linkedin_url: str | None = None
    twitter_url: str | None = None
    github_orgs: list[GitHubOrgEntry] | None = None
    github_repos: list[GitHubRepoEntry] | None = None
    headquarters: str | None = None
    founded_year: int | None = None
    company_size: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    mission_statement: str | None = None
    products: list[ProductEntry] | None = None
    custom_fields: list[CustomField] | None = None


# ---------------------------------------------------------------------------
# Member output
# ---------------------------------------------------------------------------

class OrgMemberOut(BaseModel):
    user_id: str
    full_name: str | None = None
    email: str
    profile_picture_url: str | None = None
    role: str                               # owner | admin | member
    job_title: str | None = None            # team/job title (e.g. "Frontend Engineer")
    skills: list[str] | None = None
    career_interest: str | None = None
    github_username: str | None = None      # for developer insight panel
    roadmaps_enrolled: int = 0             # roadmaps taking
    roadmaps_created: int = 0              # roadmaps created in this org
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
    my_role: str                            # owner | admin | member
    pending_invites_count: int = 0         # badge on org list
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
    tech_stacks: list[str] | None = None
    website_url: str | None = None
    linkedin_url: str | None = None
    twitter_url: str | None = None
    github_orgs: list[dict] | None = None
    github_repos: list[dict] | None = None
    headquarters: str | None = None
    founded_year: int | None = None
    company_size: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    mission_statement: str | None = None
    products: list[dict] | None = None
    custom_fields: list[dict] | None = None
    created_at: datetime
    updated_at: datetime
    # Computed fields
    my_role: str                            # owner | admin | member
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
    team_role: str | None = None            # free-text job title e.g. "Frontend Engineer"

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
    team_role: str | None = None
    status: str
    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class AcceptInviteRequest(BaseModel):
    token: str


class DeclineInviteRequest(BaseModel):
    token: str


class MyInviteOut(BaseModel):
    """Invite visible in the user's platform inbox."""
    id: str
    organization_id: str
    organization_name: str
    organization_logo: str | None = None
    organization_industry: str | None = None
    team_role: str | None = None            # job title the inviter assigned
    inviter_name: str | None = None         # who sent the invite
    token: str
    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class InvitePreviewOut(BaseModel):
    """
    Returned by GET /invites/preview?token=... before the user accepts.
    Allows the accept page to show org details + team role.
    """
    id: str
    organization_id: str
    organization_name: str
    organization_logo: str | None = None
    organization_industry: str | None = None
    organization_description: str | None = None
    team_role: str | None = None
    inviter_name: str | None = None
    expires_at: datetime
    is_valid: bool


# ---------------------------------------------------------------------------
# Org roadmap schemas
# ---------------------------------------------------------------------------

class OrgRoadmapAssign(BaseModel):
    """Request body for assigning/generating a roadmap for the org."""
    trend_name: str
    goal: str | None = None


class MyEnrollment(BaseModel):
    """Current user's enrollment and progress on a specific roadmap."""
    enrolled: bool
    steps_completed: int = 0
    total_steps: int = 0
    completion_percentage: float = 0.0


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
    # Creator info (fixes "created by me" filter)
    created_by_user_id: str | None = None
    created_by_name: str | None = None
    # Aggregate across all org members
    total_members: int
    members_completed: int
    members_in_progress: int
    aggregate_completion_percentage: float
    per_member_progress: list[MemberRoadmapProgress] = []
    # Current user's own enrollment/progress
    my_enrollment: MyEnrollment | None = None
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
    # Creator info
    created_by_user_id: str | None = None
    created_by_name: str | None = None
    # Current user's enrollment
    my_enrollment: MyEnrollment | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Member role update
# ---------------------------------------------------------------------------

class MemberRoleUpdate(BaseModel):
    """PATCH /api/organizations/{orgId}/members/{userId} — change access role."""
    role: Literal["admin", "member"]        # owner role cannot be set via this endpoint

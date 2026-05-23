from datetime import datetime
from typing import Literal
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Valid step progress statuses
# ---------------------------------------------------------------------------

StepStatus = Literal["not_started", "in_progress", "completed"]


# ---------------------------------------------------------------------------
# Sub-schemas
# ---------------------------------------------------------------------------

class ResourceOut(BaseModel):
    id: str
    title: str
    url: str | None = None
    resource_type: str | None = None
    source: str | None = None
    # Resource-level completion state (per user)
    completed: bool = False
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class StepProgressOut(BaseModel):
    status: str
    completed_at: datetime | None = None
    notes: str | None = None

    model_config = {"from_attributes": True}


class StepOut(BaseModel):
    id: str
    week_number: int
    topic: str
    description: str | None = None
    status: str
    resources: list[ResourceOut] = []
    progress: StepProgressOut | None = None
    # Step-level resource completion stats
    resources_completed: int = 0
    total_resources: int = 0
    resource_completion_pct: float = 0.0

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Roadmap list item  (shown in GET /api/roadmaps)
# ---------------------------------------------------------------------------

class RoadmapListItem(BaseModel):
    id: str
    title: str
    trend_name: str | None = None
    total_weeks: int
    status: str
    created_at: datetime
    # Progress stats
    steps_completed: int = 0
    total_steps: int = 0
    completion_percentage: float = 0.0

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Full roadmap detail  (shown in GET /api/roadmaps/{id} and POST /generate)
# ---------------------------------------------------------------------------

class RoadmapOut(BaseModel):
    id: str
    title: str
    trend_name: str | None = None
    goal: str | None = None
    total_weeks: int
    status: str
    created_at: datetime
    steps: list[StepOut] = []
    # Auto-computed summary
    summary: str | None = None
    # Progress stats
    steps_completed: int = 0
    total_steps: int = 0
    completion_percentage: float = 0.0

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class RoadmapGenerateRequest(BaseModel):
    trend_name: str
    goal: str | None = None


class StepProgressUpdate(BaseModel):
    status: StepStatus
    notes: str | None = None


class ResourceToggleRequest(BaseModel):
    """Body for POST /api/roadmaps/resources/{resource_id}/toggle"""
    completed: bool


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class StepProgressUpdateOut(BaseModel):
    """
    Returned after PATCH /api/roadmaps/steps/{step_id}/progress (manual override).
    Includes updated step state AND roadmap-level stats.
    """
    step_id: str
    status: str
    completed_at: datetime | None = None
    notes: str | None = None
    # Roadmap-level aggregates (auto-updated)
    roadmap_status: str
    steps_completed: int
    total_steps: int
    completion_percentage: float


class ResourceToggleOut(BaseModel):
    """
    Returned after POST /api/roadmaps/resources/{resource_id}/toggle.
    Contains everything the frontend needs to update all progress bars
    in a single response — no additional calls required.
    """
    resource_id: str
    completed: bool
    completed_at: datetime | None = None
    # Step-level stats (auto-derived from resource completion)
    step_id: str
    step_status: str                  # not_started | in_progress | completed
    resources_completed: int
    total_resources: int
    resource_completion_pct: float    # step-level %
    # Roadmap-level stats (auto-derived from step completion)
    roadmap_status: str
    steps_completed: int
    total_steps: int
    completion_percentage: float      # roadmap-level %

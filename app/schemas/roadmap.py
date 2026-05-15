from datetime import datetime
from pydantic import BaseModel


class ResourceOut(BaseModel):
    id: str
    title: str
    url: str | None = None
    resource_type: str | None = None
    source: str | None = None

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

    model_config = {"from_attributes": True}


class RoadmapOut(BaseModel):
    id: str
    title: str
    trend_name: str | None = None
    goal: str | None = None
    total_weeks: int
    status: str
    created_at: datetime
    steps: list[StepOut] = []

    model_config = {"from_attributes": True}


class RoadmapGenerateRequest(BaseModel):
    trend_name: str
    goal: str | None = None


class RoadmapListItem(BaseModel):
    id: str
    title: str
    trend_name: str | None = None
    total_weeks: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class StepProgressUpdate(BaseModel):
    status: str
    notes: str | None = None

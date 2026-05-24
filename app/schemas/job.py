from datetime import datetime
from pydantic import BaseModel


class TrendingCareer(BaseModel):
    name: str
    job_count: int
    company_count: int
    growth_pct: float | None = None

    model_config = {"from_attributes": True}


class InDemandSkill(BaseModel):
    skill: str
    demand: int

    model_config = {"from_attributes": True}


class JobStats(BaseModel):
    total_jobs: int
    unique_companies: int
    unique_categories: int
    date_range: list[datetime | None] | None = None

    model_config = {"from_attributes": True}


class JobForecast(BaseModel):
    normalized_title: str
    forecast_date: str
    predicted_count: float
    lower_bound: float | None = None
    upper_bound: float | None = None

    model_config = {"from_attributes": True}


class JobMatch(BaseModel):
    id: str
    job_title: str
    company_name: str
    normalized_title: str
    city: str | None = None
    job_type: str | None = None
    distance: float | None = None

    model_config = {"from_attributes": True}

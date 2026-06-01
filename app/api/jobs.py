import time
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.job_repository import JobRepository
from app.schemas.job import (
    TrendingCareer,
    InDemandSkill,
    JobStats,
    JobMatch,
    JobForecast,
)
from app.services.supabase_service import get_supabase_service

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# ---------------------------------------------------------------------------
# In-process TTL cache for public jobs endpoints
#
# Job data is batch-ingested at most daily, so a 10-minute cache is safe.
# Forecasts are also static between ML pipeline runs — cache per role key.
# The cache is intentionally simple (no lock) because a thundering-herd
# on startup is acceptable: a few extra DB calls beat the complexity of
# async locks here.
# ---------------------------------------------------------------------------

_JOBS_CACHE_TTL = 600  # 10 minutes


class _TTLCache:
    def __init__(self, ttl: int) -> None:
        self._ttl = ttl
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry and time.monotonic() - entry[0] < self._ttl:
            return entry[1]
        return None

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.monotonic(), value)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)


_jobs_cache = _TTLCache(ttl=_JOBS_CACHE_TTL)


@router.get("/trending", response_model=list[TrendingCareer])
async def get_trending(
    period: int = Query(30, description="Days to look back"),
    limit: int = Query(10, description="Number of trending careers"),
    db: AsyncSession = Depends(get_db),
):
    cache_key = f"trending:{period}:{limit}"
    cached = _jobs_cache.get(cache_key)
    if cached is not None:
        return cached
    repo = JobRepository(db)
    result = await repo.get_trending(period_days=period, limit=limit)
    _jobs_cache.set(cache_key, result)
    return result


@router.get("/in-demand-skills", response_model=list[InDemandSkill])
async def get_in_demand_skills(
    limit: int = Query(20, description="Number of skills"),
    period: int = Query(90, description="Days to look back"),
    db: AsyncSession = Depends(get_db),
):
    cache_key = f"in-demand-skills:{limit}:{period}"
    cached = _jobs_cache.get(cache_key)
    if cached is not None:
        return cached
    repo = JobRepository(db)
    result = await repo.get_in_demand_skills(limit=limit, period_days=period)
    _jobs_cache.set(cache_key, result)
    return result


@router.get("/stats", response_model=JobStats)
async def get_job_stats(
    period: int = Query(90, description="Days to look back"),
    db: AsyncSession = Depends(get_db),
):
    cache_key = f"stats:{period}"
    cached = _jobs_cache.get(cache_key)
    if cached is not None:
        return cached
    repo = JobRepository(db)
    result = await repo.get_stats(period_days=period)
    _jobs_cache.set(cache_key, result)
    return result


@router.get("/by-category", response_model=list[dict])
async def get_jobs_by_category(
    category: str = Query(..., description="Category name"),
    limit: int = Query(20),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    repo = JobRepository(db)
    jobs = await repo.get_by_category(category, limit=limit, offset=offset)
    return [
        {
            "id": j.id,
            "job_title": j.job_title,
            "company_name": j.company_name,
            "normalized_title": j.normalized_title,
            "city": j.city,
            "job_type": j.job_type,
            "posted_date": j.posted_date,
        }
        for j in jobs
    ]


@router.get("/forecasts", response_model=list[JobForecast])
async def get_job_forecasts(
    role: str | None = Query(None, description="Filter by normalized title (e.g. 'Software Engineer')"),
):
    """Return ensemble job demand forecasts (averaged across Prophet and LSTM models).
    Each row predicts the number of job postings for a role in a future month.
    Responses are cached for 10 minutes to absorb the N+1 pattern from roadmap
    generation, which fires one request per trending role (up to 12 concurrent).
    """
    cache_key = f"forecasts:{role or '__all__'}"
    cached = _jobs_cache.get(cache_key)
    if cached is not None:
        return cached
    svc = get_supabase_service()
    result = await svc.get_job_forecasts(normalized_title=role)
    _jobs_cache.set(cache_key, result)
    return result


@router.get("/match-profile", response_model=list[JobMatch])
async def match_user_profile(
    limit: int = Query(10),
):
    # TODO: re-enable when user embeddings (768) and job embeddings (384) are aligned.
    # Auth dependency removed to avoid 2 wasted DB queries on every call to a dead endpoint.
    return []

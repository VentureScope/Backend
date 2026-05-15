from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.job_repository import JobRepository
from app.schemas.job import (
    TrendingCareer,
    InDemandSkill,
    JobStats,
    JobMatch,
)
from app.models.user import User
from app.api.deps import get_current_user

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/trending", response_model=list[TrendingCareer])
async def get_trending(
    period: int = Query(30, description="Days to look back"),
    limit: int = Query(10, description="Number of trending careers"),
    db: AsyncSession = Depends(get_db),
):
    repo = JobRepository(db)
    return await repo.get_trending(period_days=period, limit=limit)


@router.get("/in-demand-skills", response_model=list[InDemandSkill])
async def get_in_demand_skills(
    limit: int = Query(20, description="Number of skills"),
    db: AsyncSession = Depends(get_db),
):
    repo = JobRepository(db)
    return await repo.get_in_demand_skills(limit=limit)


@router.get("/stats", response_model=JobStats)
async def get_job_stats(
    db: AsyncSession = Depends(get_db),
):
    repo = JobRepository(db)
    return await repo.get_stats()


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


@router.get("/match-profile", response_model=list[JobMatch])
async def match_user_profile(
    limit: int = Query(10),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # TODO: re-enable when user embeddings (768) and job embeddings (384) are aligned
    raise HTTPException(status_code=501, detail="Match profile temporarily disabled")

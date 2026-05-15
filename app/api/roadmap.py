from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.schemas.roadmap import (
    RoadmapOut,
    RoadmapGenerateRequest,
    RoadmapListItem,
    StepOut,
    StepProgressUpdate,
    ResourceOut,
    StepProgressOut,
)
from app.api.deps import get_current_user
from app.services.roadmap_service import RoadmapService

router = APIRouter(prefix="/api/roadmaps", tags=["roadmaps"])


@router.get("", response_model=list[RoadmapListItem])
async def list_roadmaps(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = RoadmapService(db)
    roadmaps = await service.list_for_user(current_user.id)
    return [
        RoadmapListItem(
            id=r.id,
            title=r.title,
            trend_name=r.trend_name,
            total_weeks=r.total_weeks,
            status=r.status,
            created_at=r.created_at,
        )
        for r in roadmaps
    ]


@router.get("/{roadmap_id}", response_model=RoadmapOut)
async def get_roadmap(
    roadmap_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = RoadmapService(db)
    roadmap = await service.get_roadmap(roadmap_id, current_user.id)
    if not roadmap:
        raise HTTPException(status_code=404, detail="Roadmap not found")
    return _build_roadmap_out(roadmap, current_user.id)


@router.post("/generate", response_model=RoadmapOut)
async def create_roadmap(
    req: RoadmapGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = RoadmapService(db)
    roadmap = await service.generate_and_save(
        user_id=current_user.id,
        trend_name=req.trend_name,
        goal=req.goal,
        user_skills=current_user.skills,
    )
    return _build_roadmap_out(roadmap, current_user.id)


@router.patch("/steps/{step_id}/progress")
async def update_step_progress(
    step_id: str,
    req: StepProgressUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = RoadmapService(db)
    return await service.update_step_progress(
        user_id=current_user.id,
        step_id=step_id,
        status=req.status,
        notes=req.notes,
    )


def _build_roadmap_out(roadmap, user_id: str) -> RoadmapOut:
    steps_out = []
    for step in roadmap.steps:
        progress_obj = None
        for p in step.progress:
            if p.user_id == user_id:
                progress_obj = StepProgressOut(
                    status=p.status,
                    completed_at=p.completed_at,
                    notes=p.notes,
                )
                break

        steps_out.append(
            StepOut(
                id=step.id,
                week_number=step.week_number,
                topic=step.topic,
                description=step.description,
                status=step.status,
                resources=[
                    ResourceOut(
                        id=r.id,
                        title=r.title,
                        url=r.url,
                        resource_type=r.resource_type,
                        source=r.source,
                    )
                    for r in step.resources
                ],
                progress=progress_obj,
            )
        )

    return RoadmapOut(
        id=roadmap.id,
        title=roadmap.title,
        trend_name=roadmap.trend_name,
        goal=roadmap.goal,
        total_weeks=roadmap.total_weeks,
        status=roadmap.status,
        created_at=roadmap.created_at,
        steps=sorted(steps_out, key=lambda s: s.week_number),
    )

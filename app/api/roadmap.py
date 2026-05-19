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
    StepProgressUpdateOut,
    ResourceOut,
    StepProgressOut,
)
from app.api.deps import get_current_user
from app.services.roadmap_service import RoadmapService

router = APIRouter(prefix="/api/roadmaps", tags=["roadmaps"])


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=list[RoadmapListItem])
async def list_roadmaps(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all roadmaps for the current user with completion stats."""
    service = RoadmapService(db)
    roadmaps = await service.list_for_user(current_user.id)
    return [_build_list_item(r, current_user.id) for r in roadmaps]


@router.get("/{roadmap_id}", response_model=RoadmapOut)
async def get_roadmap(
    roadmap_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single roadmap with full step details, resources, and progress."""
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
    """Generate a new AI-powered learning roadmap."""
    service = RoadmapService(db)
    roadmap = await service.generate_and_save(
        user_id=current_user.id,
        trend_name=req.trend_name,
        goal=req.goal,
        user_skills=current_user.skills,
    )
    return _build_roadmap_out(roadmap, current_user.id)


@router.patch("/steps/{step_id}/progress", response_model=StepProgressUpdateOut)
async def update_step_progress(
    step_id: str,
    req: StepProgressUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update progress for a single roadmap step.

    - Valid statuses: `not_started`, `in_progress`, `completed`
    - Automatically updates the parent roadmap status:
      - All steps completed → roadmap `completed`
      - Any step started   → roadmap `in_progress`
      - All not started    → roadmap `not_started`
    - Returns updated step state + roadmap-level completion stats.
    """
    service = RoadmapService(db)
    return await service.update_step_progress(
        user_id=current_user.id,
        step_id=step_id,
        status=req.status,
        notes=req.notes,
    )


# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------

def _build_progress_stats(roadmap, user_id: str) -> tuple[int, int, float]:
    """
    Returns (steps_completed, total_steps, completion_percentage).
    Works with both list (steps + progress loaded) and detail views.
    """
    total = len(roadmap.steps)
    if total == 0:
        return 0, 0, 0.0

    completed = 0
    for step in roadmap.steps:
        for p in step.progress:
            if p.user_id == user_id:
                if p.status == "completed":
                    completed += 1
                break

    percentage = round(completed / total * 100, 1)
    return completed, total, percentage


def _build_summary(roadmap) -> str:
    """
    Auto-compute a human-readable summary from the roadmap's steps.
    e.g. "8-week roadmap covering: Python Basics, Data Structures, OOP, ..."
    """
    sorted_steps = sorted(roadmap.steps, key=lambda s: s.week_number)
    topics = [s.topic for s in sorted_steps]

    if not topics:
        return f"{roadmap.total_weeks}-week learning roadmap for {roadmap.trend_name or 'your target career'}."

    MAX_TOPICS = 5
    if len(topics) <= MAX_TOPICS:
        topics_text = ", ".join(topics)
    else:
        topics_text = ", ".join(topics[:MAX_TOPICS]) + f", and {len(topics) - MAX_TOPICS} more"

    return (
        f"{roadmap.total_weeks}-week roadmap covering: {topics_text}. "
        f"Goal: {roadmap.goal or 'Master ' + (roadmap.trend_name or 'the target career')}."
    )


def _build_list_item(roadmap, user_id: str) -> RoadmapListItem:
    steps_completed, total_steps, percentage = _build_progress_stats(roadmap, user_id)
    return RoadmapListItem(
        id=roadmap.id,
        title=roadmap.title,
        trend_name=roadmap.trend_name,
        total_weeks=roadmap.total_weeks,
        status=roadmap.status,
        created_at=roadmap.created_at,
        steps_completed=steps_completed,
        total_steps=total_steps,
        completion_percentage=percentage,
    )


def _build_roadmap_out(roadmap, user_id: str) -> RoadmapOut:
    steps_completed, total_steps, percentage = _build_progress_stats(roadmap, user_id)
    summary = _build_summary(roadmap)

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
        summary=summary,
        steps_completed=steps_completed,
        total_steps=total_steps,
        completion_percentage=percentage,
    )

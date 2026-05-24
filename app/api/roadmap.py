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
    ResourceToggleRequest,
    ResourceToggleOut,
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
    """
    Generate a new AI-powered learning roadmap.

    Set `use_market_trends: true` to generate a future-focused roadmap
    based on emerging and projected market trends instead of current demand.
    The `trend_mode` field in the response ("current" or "future") tells
    the frontend which mode was used, so it can badge/label the roadmap.
    """
    service = RoadmapService(db)
    roadmap = await service.generate_and_save(
        user_id=current_user.id,
        trend_name=req.trend_name,
        goal=req.goal,
        user_skills=current_user.skills,
        use_market_trends=req.use_market_trends,
    )
    return _build_roadmap_out(roadmap, current_user.id)


@router.post("/resources/{resource_id}/toggle", response_model=ResourceToggleOut)
async def toggle_resource_progress(
    resource_id: str,
    req: ResourceToggleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Check or uncheck a resource for the current user.

    Automatically cascades upward:
    - Updates the parent step status:
        0 resources done   → not_started
        some resources done → in_progress
        all resources done  → completed
    - Updates the roadmap overall status accordingly.

    Returns all updated stats in one response so the frontend can
    refresh all progress bars without additional calls.

    Works for both personal roadmaps and org team roadmaps.
    """
    service = RoadmapService(db)
    return await service.toggle_resource(
        user_id=current_user.id,
        resource_id=resource_id,
        completed=req.completed,
    )


@router.patch("/steps/{step_id}/progress", response_model=StepProgressUpdateOut)
async def update_step_progress(
    step_id: str,
    req: StepProgressUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Manually override a step's status (not_started | in_progress | completed).

    When set to 'completed' → all resources in the step are also marked complete.
    When set to 'not_started' → all resource progress for the step is cleared.
    This keeps the resource checkboxes in sync with the manual override.

    Prefer using POST /resources/{id}/toggle for the normal checkbox flow.
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

def _get_resource_completion(resource, user_id: str) -> tuple[bool, object]:
    """Return (completed, completed_at) for a resource for a specific user."""
    for rp in (resource.resource_progress or []):
        if rp.user_id == user_id:
            return rp.completed, rp.completed_at
    return False, None


def _build_step_resource_stats(step, user_id: str) -> tuple[int, int, float]:
    """Return (resources_completed, total_resources, resource_completion_pct) for a step."""
    total = len(step.resources)
    if total == 0:
        return 0, 0, 0.0
    completed = sum(
        1 for r in step.resources
        if any(rp.user_id == user_id and rp.completed for rp in r.resource_progress)
    )
    pct = round(completed / total * 100, 1)
    return completed, total, pct


def _build_progress_stats(roadmap, user_id: str) -> tuple[int, int, float]:
    """Returns (steps_completed, total_steps, completion_percentage)."""
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
    Return the summary for a roadmap.

    Priority:
    1. skill_gap_summary — LLM-generated, personalized skill gap analysis
       stored at generation time. This is the richest and most useful summary.
    2. Auto-computed fallback — plain topic list for older roadmaps that
       predate the skill_gap_summary column.
    """
    # Primary: use the LLM-generated skill gap analysis if available
    skill_gap = getattr(roadmap, "skill_gap_summary", None)
    if skill_gap and skill_gap.strip():
        return skill_gap.strip()

    # Fallback: compute from step topics (for roadmaps generated before this feature)
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
        trend_mode=getattr(roadmap, "trend_mode", "current"),
        steps_completed=steps_completed,
        total_steps=total_steps,
        completion_percentage=percentage,
    )


def _build_roadmap_out(roadmap, user_id: str) -> RoadmapOut:
    steps_completed, total_steps, percentage = _build_progress_stats(roadmap, user_id)
    summary = _build_summary(roadmap)

    steps_out = []
    for step in roadmap.steps:
        # Step-level progress object
        progress_obj = None
        for p in step.progress:
            if p.user_id == user_id:
                progress_obj = StepProgressOut(
                    status=p.status,
                    completed_at=p.completed_at,
                    notes=p.notes,
                )
                break

        # Per-resource completion state
        resources_out = []
        for r in step.resources:
            is_completed, completed_at = _get_resource_completion(r, user_id)
            resources_out.append(
                ResourceOut(
                    id=r.id,
                    title=r.title,
                    url=r.url,
                    resource_type=r.resource_type,
                    source=r.source,
                    completed=is_completed,
                    completed_at=completed_at,
                )
            )

        # Step-level resource stats
        res_completed, res_total, res_pct = _build_step_resource_stats(step, user_id)

        steps_out.append(
            StepOut(
                id=step.id,
                week_number=step.week_number,
                topic=step.topic,
                description=step.description,
                status=step.status,
                resources=resources_out,
                progress=progress_obj,
                resources_completed=res_completed,
                total_resources=res_total,
                resource_completion_pct=res_pct,
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
        skill_gap_summary=getattr(roadmap, "skill_gap_summary", None),
        trend_mode=getattr(roadmap, "trend_mode", "current"),
        steps_completed=steps_completed,
        total_steps=total_steps,
        completion_percentage=percentage,
    )

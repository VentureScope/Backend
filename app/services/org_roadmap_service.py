"""
Organization roadmap service.

Shared roadmaps: one LearningRoadmap linked to the org, each member
tracks their own step progress via existing LearningRoadmapProgress.
"""

import logging
from statistics import mean

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.organization_repository import OrganizationRepository
from app.repositories.roadmap_repository import RoadmapRepository

logger = logging.getLogger(__name__)


class OrgRoadmapService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = OrganizationRepository(db)
        self.roadmap_repo = RoadmapRepository(db)

    # ------------------------------------------------------------------
    # Assign (generate + link) a roadmap to the org
    # ------------------------------------------------------------------

    async def assign_roadmap(
        self,
        org_id: str,
        owner_id: str,
        trend_name: str,
        goal: str | None,
    ) -> dict:
        if not await self.repo.is_owner(org_id, owner_id):
            raise HTTPException(status_code=403, detail="Only the organization owner can add roadmaps.")

        org = await self.repo.get_by_id(org_id)
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found.")

        # Generate via existing RoadmapService
        from app.services.roadmap_service import RoadmapService
        roadmap_svc = RoadmapService(self.db)

        # Aggregate org member skills to pass as context
        all_skills = list({
            skill
            for m in (org.members or [])
            for skill in (m.user.skills or [])
        })

        roadmap = await roadmap_svc.generate_and_save(
            user_id=owner_id,
            trend_name=trend_name,
            goal=goal,
            user_skills=all_skills or None,
        )

        # Link roadmap to org
        org_roadmap = await self.repo.create_org_roadmap(
            org_id=org_id,
            roadmap_id=roadmap.id,
            created_by=owner_id,
        )

        # Auto-create LearningRoadmapProgress for every member
        members = await self.repo.list_members(org_id)
        for member in members:
            if member.user_id == owner_id:
                continue  # owner already has progress created by RoadmapService
            for step in roadmap.steps:
                existing = await self.roadmap_repo.get_progress(member.user_id, step.id)
                if not existing:
                    await self.roadmap_repo.create_progress({
                        "user_id": member.user_id,
                        "step_id": step.id,
                        "status": "not_started",
                    })

        await self.db.commit()

        # Reload with full data
        org_roadmap = await self.repo.get_org_roadmap(org_id, roadmap.id)
        members_fresh = await self.repo.list_members(org_id)
        return self._build_org_roadmap_out(org_roadmap, members_fresh)

    # ------------------------------------------------------------------
    # List org roadmaps
    # ------------------------------------------------------------------

    async def list_org_roadmaps(self, org_id: str, user_id: str) -> list[dict]:
        if not await self.repo.is_member(org_id, user_id):
            raise HTTPException(status_code=403, detail="You are not a member of this organization.")

        org_roadmaps = await self.repo.list_org_roadmaps(org_id)
        members = await self.repo.list_members(org_id)

        result = []
        for org_roadmap in org_roadmaps:
            r = org_roadmap.roadmap
            total_steps = len(r.steps)
            if total_steps == 0:
                agg_pct = 0.0
            else:
                pcts = []
                for member in members:
                    completed = sum(
                        1 for step in r.steps
                        if any(
                            p.user_id == member.user_id and p.status == "completed"
                            for p in step.progress
                        )
                    )
                    pcts.append(round(completed / total_steps * 100, 1))
                agg_pct = round(mean(pcts), 1) if pcts else 0.0

            result.append({
                "id": org_roadmap.id,
                "roadmap_id": r.id,
                "title": r.title,
                "trend_name": r.trend_name,
                "total_weeks": r.total_weeks,
                "total_members": len(members),
                "aggregate_completion_percentage": agg_pct,
                "created_at": org_roadmap.created_at,
            })

        return result

    # ------------------------------------------------------------------
    # Get single org roadmap with per-member progress
    # ------------------------------------------------------------------

    async def get_org_roadmap(self, org_id: str, roadmap_id: str, user_id: str) -> dict:
        if not await self.repo.is_member(org_id, user_id):
            raise HTTPException(status_code=403, detail="You are not a member of this organization.")

        org_roadmap = await self.repo.get_org_roadmap(org_id, roadmap_id)
        if not org_roadmap:
            raise HTTPException(status_code=404, detail="Roadmap not found in this organization.")

        members = await self.repo.list_members(org_id)
        return self._build_org_roadmap_out(org_roadmap, members)

    # ------------------------------------------------------------------
    # Remove roadmap from org
    # ------------------------------------------------------------------

    async def remove_org_roadmap(self, org_id: str, roadmap_id: str, owner_id: str) -> None:
        if not await self.repo.is_owner(org_id, owner_id):
            raise HTTPException(status_code=403, detail="Only the organization owner can remove roadmaps.")

        org_roadmap = await self.repo.get_org_roadmap(org_id, roadmap_id)
        if not org_roadmap:
            raise HTTPException(status_code=404, detail="Roadmap not found in this organization.")

        await self.repo.delete_org_roadmap(org_id, roadmap_id)
        await self.db.commit()

    # ------------------------------------------------------------------
    # Builder helper
    # ------------------------------------------------------------------

    def _build_org_roadmap_out(self, org_roadmap, members: list) -> dict:
        r = org_roadmap.roadmap
        total_steps = len(r.steps)

        per_member = []
        for member in members:
            if total_steps == 0:
                pct = 0.0
                completed_count = 0
            else:
                completed_count = sum(
                    1 for step in r.steps
                    if any(
                        p.user_id == member.user_id and p.status == "completed"
                        for p in step.progress
                    )
                )
                pct = round(completed_count / total_steps * 100, 1)

            per_member.append({
                "user_id": member.user_id,
                "full_name": member.user.full_name,
                "steps_completed": completed_count,
                "total_steps": total_steps,
                "completion_percentage": pct,
            })

        all_pcts = [m["completion_percentage"] for m in per_member]
        agg_pct = round(mean(all_pcts), 1) if all_pcts else 0.0
        members_completed = sum(1 for p in all_pcts if p == 100.0)
        members_in_progress = sum(1 for p in all_pcts if 0 < p < 100)

        # Build summary from step topics
        sorted_steps = sorted(r.steps, key=lambda s: s.week_number)
        topics = [s.topic for s in sorted_steps]
        MAX = 5
        if len(topics) <= MAX:
            topics_text = ", ".join(topics)
        else:
            topics_text = ", ".join(topics[:MAX]) + f" and {len(topics) - MAX} more"
        summary = (
            f"{r.total_weeks}-week roadmap covering: {topics_text}. "
            f"Goal: {r.goal or 'Master ' + (r.trend_name or 'the target career')}."
            if topics else None
        )

        return {
            "id": org_roadmap.id,
            "roadmap_id": r.id,
            "title": r.title,
            "trend_name": r.trend_name,
            "goal": r.goal,
            "total_weeks": r.total_weeks,
            "summary": summary,
            "total_members": len(members),
            "members_completed": members_completed,
            "members_in_progress": members_in_progress,
            "aggregate_completion_percentage": agg_pct,
            "per_member_progress": per_member,
            "created_at": org_roadmap.created_at,
        }

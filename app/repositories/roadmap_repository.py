from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import uuid

from app.models.roadmap import (
    LearningRoadmap,
    LearningRoadmapStep,
    LearningRoadmapStepResource,
    LearningRoadmapProgress,
)


class RoadmapRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_by_user(self, user_id: str) -> list[LearningRoadmap]:
        """
        List all roadmaps for a user, eagerly loading steps and their
        progress rows so completion stats can be computed without extra
        queries.
        """
        result = await self.db.execute(
            select(LearningRoadmap)
            .where(LearningRoadmap.user_id == user_id)
            .options(
                selectinload(LearningRoadmap.steps)
                .selectinload(LearningRoadmapStep.progress),
            )
            .order_by(LearningRoadmap.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(
        self, roadmap_id: str, user_id: str
    ) -> LearningRoadmap | None:
        result = await self.db.execute(
            select(LearningRoadmap)
            .where(
                LearningRoadmap.id == roadmap_id,
                LearningRoadmap.user_id == user_id,
            )
            .options(
                selectinload(LearningRoadmap.steps)
                .selectinload(LearningRoadmapStep.resources),
                selectinload(LearningRoadmap.steps)
                .selectinload(LearningRoadmapStep.progress),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id_any_user(self, roadmap_id: str) -> LearningRoadmap | None:
        """
        Fetch a roadmap by ID without user ownership check.
        Used internally by update_step_progress to reload roadmap stats.
        """
        result = await self.db.execute(
            select(LearningRoadmap)
            .where(LearningRoadmap.id == roadmap_id)
            .options(
                selectinload(LearningRoadmap.steps)
                .selectinload(LearningRoadmapStep.progress),
            )
        )
        return result.scalar_one_or_none()

    async def create_roadmap(self, data: dict) -> LearningRoadmap:
        roadmap = LearningRoadmap(
            id=str(uuid.uuid4()),
            user_id=data["user_id"],
            title=data["title"],
            trend_name=data.get("trend_name"),
            goal=data.get("goal"),
            total_weeks=data["total_weeks"],
            status=data.get("status", "not_started"),
        )
        self.db.add(roadmap)
        await self.db.flush()
        return roadmap

    async def create_step(self, data: dict) -> LearningRoadmapStep:
        step = LearningRoadmapStep(
            id=str(uuid.uuid4()),
            roadmap_id=data["roadmap_id"],
            week_number=data["week_number"],
            topic=data["topic"],
            description=data.get("description"),
            status=data.get("status", "pending"),
        )
        self.db.add(step)
        await self.db.flush()
        return step

    async def create_resource(self, data: dict) -> LearningRoadmapStepResource:
        resource = LearningRoadmapStepResource(
            id=str(uuid.uuid4()),
            step_id=data["step_id"],
            title=data["title"],
            url=data.get("url"),
            resource_type=data.get("resource_type"),
            source=data.get("source", "llm_generated"),
        )
        self.db.add(resource)
        return resource

    async def create_progress(self, data: dict) -> LearningRoadmapProgress:
        progress = LearningRoadmapProgress(
            id=str(uuid.uuid4()),
            user_id=data["user_id"],
            step_id=data["step_id"],
            status=data.get("status", "not_started"),
        )
        self.db.add(progress)
        return progress

    async def get_progress(
        self, user_id: str, step_id: str
    ) -> LearningRoadmapProgress | None:
        result = await self.db.execute(
            select(LearningRoadmapProgress).where(
                LearningRoadmapProgress.user_id == user_id,
                LearningRoadmapProgress.step_id == step_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_progress(
        self,
        progress: LearningRoadmapProgress,
        status: str,
        notes: str | None = None,
    ) -> LearningRoadmapProgress:
        progress.status = status
        if status == "completed":
            progress.completed_at = datetime.now(timezone.utc)
        else:
            # Clear completed_at if reverting from completed
            progress.completed_at = None
        if notes is not None:
            progress.notes = notes
        return progress

    async def update_roadmap_status(
        self, roadmap_id: str, status: str
    ) -> None:
        """Update the overall status of a roadmap."""
        result = await self.db.execute(
            select(LearningRoadmap).where(LearningRoadmap.id == roadmap_id)
        )
        roadmap = result.scalar_one_or_none()
        if roadmap:
            roadmap.status = status

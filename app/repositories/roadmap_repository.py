from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload
import uuid

from app.models.roadmap import (
    LearningRoadmap,
    LearningRoadmapStep,
    LearningRoadmapStepResource,
    LearningRoadmapProgress,
    LearningRoadmapResourceProgress,
)


class RoadmapRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Roadmap queries — all eagerly load resource_progress alongside resources
    # ------------------------------------------------------------------

    async def list_by_user(self, user_id: str) -> list[LearningRoadmap]:
        """
        List all roadmaps for a user, eagerly loading steps, progress,
        resources, and resource_progress so completion stats can be
        computed without extra queries.
        """
        result = await self.db.execute(
            select(LearningRoadmap)
            .where(LearningRoadmap.user_id == user_id)
            .options(
                selectinload(LearningRoadmap.steps)
                .selectinload(LearningRoadmapStep.progress),
                selectinload(LearningRoadmap.steps)
                .selectinload(LearningRoadmapStep.resources)
                .selectinload(LearningRoadmapStepResource.resource_progress),
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
                .selectinload(LearningRoadmapStep.resources)
                .selectinload(LearningRoadmapStepResource.resource_progress),
                selectinload(LearningRoadmap.steps)
                .selectinload(LearningRoadmapStep.progress),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id_any_user(self, roadmap_id: str) -> LearningRoadmap | None:
        """
        Fetch a roadmap by ID without user ownership check.
        Used internally by toggle_resource and update_step_progress.
        """
        result = await self.db.execute(
            select(LearningRoadmap)
            .where(LearningRoadmap.id == roadmap_id)
            .options(
                selectinload(LearningRoadmap.steps)
                .selectinload(LearningRoadmapStep.progress),
                selectinload(LearningRoadmap.steps)
                .selectinload(LearningRoadmapStep.resources)
                .selectinload(LearningRoadmapStepResource.resource_progress),
            )
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # CRUD helpers
    # ------------------------------------------------------------------

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
            progress.completed_at = None
        if notes is not None:
            progress.notes = notes
        return progress

    async def update_roadmap_status(self, roadmap_id: str, status: str) -> None:
        result = await self.db.execute(
            select(LearningRoadmap).where(LearningRoadmap.id == roadmap_id)
        )
        roadmap = result.scalar_one_or_none()
        if roadmap:
            roadmap.status = status

    # ------------------------------------------------------------------
    # Resource — fetch helpers
    # ------------------------------------------------------------------

    async def get_resource(self, resource_id: str) -> LearningRoadmapStepResource | None:
        """Fetch a resource by ID, loading its parent step."""
        result = await self.db.execute(
            select(LearningRoadmapStepResource)
            .where(LearningRoadmapStepResource.id == resource_id)
        )
        return result.scalar_one_or_none()

    async def get_step(self, step_id: str) -> LearningRoadmapStep | None:
        """Fetch a step with its resources (for counting)."""
        result = await self.db.execute(
            select(LearningRoadmapStep)
            .where(LearningRoadmapStep.id == step_id)
            .options(
                selectinload(LearningRoadmapStep.resources)
                .selectinload(LearningRoadmapStepResource.resource_progress),
            )
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Resource progress — new methods
    # ------------------------------------------------------------------

    async def get_resource_progress(
        self, user_id: str, resource_id: str
    ) -> LearningRoadmapResourceProgress | None:
        result = await self.db.execute(
            select(LearningRoadmapResourceProgress).where(
                LearningRoadmapResourceProgress.user_id == user_id,
                LearningRoadmapResourceProgress.resource_id == resource_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_resource_progress(
        self,
        user_id: str,
        resource_id: str,
        step_id: str,
        completed: bool,
    ) -> LearningRoadmapResourceProgress:
        """
        Atomically insert or update resource progress using PostgreSQL
        INSERT ... ON CONFLICT DO UPDATE. This prevents the race condition
        where SELECT returns None but the row already exists in the DB,
        causing a UniqueViolationError on INSERT.
        """
        now = datetime.now(timezone.utc)

        stmt = (
            pg_insert(LearningRoadmapResourceProgress)
            .values(
                id=str(uuid.uuid4()),
                user_id=user_id,
                resource_id=resource_id,
                step_id=step_id,
                completed=completed,
                completed_at=now if completed else None,
            )
            .on_conflict_do_update(
                constraint="uq_user_resource_progress",
                set_={
                    "completed": completed,
                    "completed_at": now if completed else None,
                },
            )
            .returning(LearningRoadmapResourceProgress)
        )

        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.scalar_one()

    async def get_resource_progress_for_step(
        self, user_id: str, step_id: str
    ) -> list[LearningRoadmapResourceProgress]:
        """Return all resource progress rows for a user in a specific step."""
        result = await self.db.execute(
            select(LearningRoadmapResourceProgress).where(
                LearningRoadmapResourceProgress.user_id == user_id,
                LearningRoadmapResourceProgress.step_id == step_id,
            )
        )
        return list(result.scalars().all())

    async def clear_resource_progress_for_step(
        self, user_id: str, step_id: str
    ) -> None:
        """Delete all resource progress rows for a user in a step (used by manual override)."""
        await self.db.execute(
            delete(LearningRoadmapResourceProgress).where(
                LearningRoadmapResourceProgress.user_id == user_id,
                LearningRoadmapResourceProgress.step_id == step_id,
            )
        )
        await self.db.flush()

    async def mark_all_resources_in_step(
        self, user_id: str, step_id: str, resources: list[LearningRoadmapStepResource], completed: bool
    ) -> None:
        """
        Set all resources in a step to completed=True or False.
        Used by the manual step override to keep resource state in sync.
        """
        for resource in resources:
            await self.upsert_resource_progress(
                user_id=user_id,
                resource_id=resource.id,
                step_id=step_id,
                completed=completed,
            )

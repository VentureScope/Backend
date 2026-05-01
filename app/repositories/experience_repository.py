"""
Repository for Experience CRUD operations.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models.experience import Experience
from typing import list


class ExperienceRepository:
    """Data access layer for experiences."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, experience_id: str) -> Experience | None:
        """Get experience by ID."""
        result = await self.db.execute(
            select(Experience).where(Experience.id == experience_id)
        )
        return result.scalar_one_or_none()

    async def get_by_user(self, user_id: str) -> list[Experience]:
        """Get all experiences for a user."""
        result = await self.db.execute(
            select(Experience)
            .where(Experience.user_id == user_id)
            .order_by(Experience.start_date.desc())
        )
        return list(result.scalars().all())

    async def create(self, data: dict) -> Experience:
        """Create a new experience entry."""
        from app.models.experience import Experience
        import uuid

        exp = Experience(
            id=str(uuid.uuid4()),
            user_id=data["user_id"],
            job_title=data["job_title"],
            company=data["company"],
            start_date=data["start_date"],
            end_date=data.get("end_date"),
            description=data.get("description"),
            skills_used=data.get("skills_used"),
        )
        self.db.add(exp)
        await self.db.flush()
        return exp

    async def update(self, exp: Experience, data: dict) -> Experience:
        """Update an existing experience."""
        for key, value in data.items():
            if hasattr(exp, key) and value is not None:
                setattr(exp, key, value)
        await self.db.flush()
        return exp

    async def delete(self, experience_id: str) -> bool:
        """Delete an experience by ID."""
        result = await self.db.execute(
            delete(Experience).where(Experience.id == experience_id)
        )
        return result.rowcount > 0

    async def delete_all_for_user(self, user_id: str) -> int:
        """Delete all experiences for a user."""
        result = await self.db.execute(
            delete(Experience).where(Experience.user_id == user_id)
        )
        return result.rowcount

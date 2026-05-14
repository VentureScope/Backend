from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from app.models.resume import Resume


class ResumeRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user_id: str, target_role: str, data: dict) -> Resume:
        resume = Resume(
            id=str(uuid.uuid4()),
            user_id=user_id,
            target_role=target_role,
            professional_summary=data.get("professional_summary"),
            skills=data.get("skills"),
            experience=data.get("experience"),
            education=data.get("education"),
            projects=data.get("projects"),
            certifications=data.get("certifications"),
            trending_skills_highlighted=data.get("trending_skills_highlighted"),
        )
        self.db.add(resume)
        await self.db.flush()
        return resume

    async def list_by_user(self, user_id: str) -> list[Resume]:
        result = await self.db.execute(
            select(Resume)
            .where(Resume.user_id == user_id)
            .order_by(Resume.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, resume_id: str, user_id: str) -> Resume | None:
        result = await self.db.execute(
            select(Resume).where(
                Resume.id == resume_id,
                Resume.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

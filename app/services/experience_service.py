"""
Experience management service.
"""

from datetime import datetime
from typing import list

from app.models.experience import Experience
from app.repositories.experience_repository import ExperienceRepository
from app.schemas.experience import ExperienceCreate, ExperienceUpdate


class ExperienceService:
    """Service for managing work experiences."""

    def __init__(self, db):
        self.db = db
        self.repo = ExperienceRepository(db)
        self.knowledge_service = None  # Lazy loaded

    async def get_all_for_user(self, user_id: str) -> list[Experience]:
        """Get all experiences for a user."""
        return await self.repo.get_by_user(user_id)

    async def create_experience(
        self, user_id: str, data: ExperienceCreate
    ) -> Experience:
        """Add a new work experience."""
        exp_data = data.model_dump()
        exp_data["user_id"] = user_id
        exp = await self.repo.create(exp_data)

        # Create knowledge chunk for this experience
        await self._create_experience_knowledge(
            user_id, exp
        )

        return exp

    async def update_experience(
        self, experience_id: str, data: ExperienceUpdate
    ) -> Experience | None:
        """Update an existing experience."""
        exp = await self.repo.get_by_id(experience_id)
        if not exp:
            return None

        update_data = data.model_dump(exclude_unset=True)
        exp = await self.repo.update(exp, update_data)

        # Re-create knowledge chunk
        await self._create_experience_knowledge(
            exp.user_id, exp
        )

        return exp

    async def delete_experience(self, experience_id: str) -> bool:
        """Delete an experience and its knowledge chunks."""
        exp = await self.repo.get_by_id(experience_id)
        if not exp:
            return False

        user_id = exp.user_id

        # Delete knowledge chunks for this experience
        await self._delete_experience_knowledge(
            user_id, experience_id
        )

        return await self.repo.delete(experience_id)

    async def _create_experience_knowledge(
        self, user_id: str, exp: Experience
    ) -> None:
        """Create a knowledge chunk from experience data."""
        if not self.knowledge_service:
            from app.services.knowledge_service import KnowledgeService
            self.knowledge_service = KnowledgeService(self.db)

        # Build content string
        content_parts = [
            f"{exp.job_title} at {exp.company}",
        ]
        if exp.start_date:
            start = exp.start_date.strftime("%b %Y")
            end = exp.end_date.strftime("%b %Y") if exp.end_date else "Present"
            content_parts[0] += f" ({start} – {end})"

        if exp.description:
            content_parts.append(exp.description)

        if exp.skills_used:
            content_parts.append(f"Skills: {', '.join(exp.skills_used)}")

        content = "\n".join(content_parts)

        # Create knowledge chunk with source_type="experience"
        await self.knowledge_service.ingest_knowledge(
            user_id=user_id,
            content=content,
            source_type="experience",
        )

    async def _delete_experience_knowledge(
        self, user_id: str, experience_id: str
    ) -> None:
        """Delete knowledge chunks for this experience."""
        from app.models.user_knowledge import UserKnowledge

        await self.db.execute(
            UserKnowledge.__table__.delete().where(
                (UserKnowledge.user_id == user_id)
                & (UserKnowledge.source_type == "experience")
            )
        )

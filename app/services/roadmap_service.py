import asyncio
import json
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.hosted_llm import HostedLLM
from app.core.config import settings
from app.repositories.roadmap_repository import RoadmapRepository
from app.repositories.job_repository import JobRepository
from app.models.roadmap import LearningRoadmap

ROADMAP_SYSTEM_PROMPT = """You are a career advisor. Generate a personalized learning roadmap.

Based on the user's current skills, the trending career they selected, and market demand data, create a structured week-by-week learning roadmap.

The roadmap must be valid JSON with this exact structure:
{
  "title": "string - roadmap title",
  "total_weeks": 12,
  "steps": [
    {
      "week_number": 1,
      "topic": "string - week topic",
      "description": "string - what to learn this week",
      "resources": [
        {
          "title": "string - resource name",
          "url": "string - URL if known, or empty string",
          "resource_type": "course|article|video|documentation|project",
          "source": "llm_generated"
        }
      ]
    }
  ]
}

Generate 8-12 weeks. Each week must have 2-4 resources. Return ONLY valid JSON, no markdown or explanation."""


class RoadmapService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = RoadmapRepository(db)
        self.job_repo = JobRepository(db)

    async def list_for_user(self, user_id: str) -> list[LearningRoadmap]:
        return await self.repo.list_by_user(user_id)

    async def get_roadmap(
        self, roadmap_id: str, user_id: str
    ) -> LearningRoadmap | None:
        return await self.repo.get_by_id(roadmap_id, user_id)

    async def generate_and_save(
        self,
        user_id: str,
        trend_name: str,
        goal: str | None,
        user_skills: list[str] | None,
    ) -> LearningRoadmap:
        trends = await self.job_repo.get_trending(limit=10)
        trend_stats = None
        for t in trends:
            if t["name"].lower() == trend_name.lower():
                trend_stats = t
                break

        roadmap_data = await self._call_llm(
            user_skills=user_skills,
            trend_name=trend_name,
            trend_stats=trend_stats,
            goal=goal,
        )

        roadmap = await self.repo.create_roadmap({
            "user_id": user_id,
            "title": roadmap_data.get("title", f"Roadmap to {trend_name}"),
            "trend_name": trend_name,
            "goal": goal,
            "total_weeks": roadmap_data.get("total_weeks", 12),
        })

        for step_data in roadmap_data.get("steps", []):
            step = await self.repo.create_step({
                "roadmap_id": roadmap.id,
                "week_number": step_data.get("week_number", 1),
                "topic": step_data["topic"],
                "description": step_data.get("description"),
            })

            for res_data in step_data.get("resources", []):
                await self.repo.create_resource({
                    "step_id": step.id,
                    "title": res_data["title"],
                    "url": res_data.get("url"),
                    "resource_type": res_data.get("resource_type"),
                    "source": res_data.get("source", "llm_generated"),
                })

            await self.repo.create_progress({
                "user_id": user_id,
                "step_id": step.id,
            })

        await self.db.commit()

        loaded = await self.repo.get_by_id(roadmap.id, user_id)
        return loaded

    async def update_step_progress(
        self, user_id: str, step_id: str, status: str, notes: str | None = None
    ) -> dict:
        progress = await self.repo.get_progress(user_id, step_id)
        if not progress:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Progress not found")

        await self.repo.update_progress(progress, status, notes)
        await self.db.commit()
        return {
            "status": progress.status,
            "completed_at": progress.completed_at,
        }

    async def _call_llm(
        self,
        user_skills: list[str] | None,
        trend_name: str,
        trend_stats: dict | None,
        goal: str | None,
    ) -> dict:
        skills_data = []
        try:
            pass
        except Exception:
            pass

        user_skills_text = ", ".join(user_skills) if user_skills else "not specified"
        trend_stats_text = ""
        if trend_stats:
            trend_stats_text = (
                f"\nTrend stats: {trend_stats.get('job_count', 'N/A')} jobs listed, "
                f"{trend_stats.get('growth_pct', 'N/A')}% growth"
            )

        user_prompt = (
            f"Generate a learning roadmap for a user who wants to become a {trend_name}.\n"
            f"Goal: {goal or 'Become a ' + trend_name}\n"
            f"User's current skills: {user_skills_text}"
            f"{trend_stats_text}\n\n"
            f"Generate a comprehensive roadmap that bridges the gap between "
            f"the user's current skills and the target career."
        )

        full_prompt = f"{ROADMAP_SYSTEM_PROMPT}\n\n{user_prompt}"

        llm = HostedLLM(
            model=settings.CHAT_MODEL_NAME,
            temperature=0.7,
            max_tokens=4000,
        )
        response = await asyncio.to_thread(llm.invoke, full_prompt)

        cleaned = self._clean_response(response)
        return json.loads(cleaned)

    @staticmethod
    def _clean_response(content: str) -> str:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:].strip()
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()
        return cleaned.strip()

import asyncio
import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from typing import Any

from app.services.hosted_llm import HostedLLM
from app.services.search_service import perform_web_search
from app.core.config import settings
from app.repositories.roadmap_repository import RoadmapRepository
from app.repositories.job_repository import JobRepository
from app.models.roadmap import LearningRoadmap

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompts — current vs future trend mode
# ---------------------------------------------------------------------------

_BASE_RULES = """
Rules:
- You MUST call the `perform_web_search` tool BEFORE generating the JSON to find working, real URLs.
- Generates up to 8 weeks. Each week must have exactly 2 resources.
- Return ONLY valid JSON, no markdown or explanation.
- The skill_gap_summary must be 2-4 sentences that: (1) identify the key skills the user is missing
  for the target role based on their current skills, (2) explain how the roadmap addresses those gaps,
  and (3) highlight any strengths the user already has. Be specific — name the actual skills.

The roadmap must be valid JSON with this exact structure:
{
  "title": "string - roadmap title",
  "total_weeks": 8,
  "skill_gap_summary": "string - 2-4 sentence personalized skill gap analysis",
  "steps": [
    {
      "week_number": 1,
      "topic": "string - week topic",
      "description": "string - what to learn this week",
      "resources": [
        {
          "title": "string - resource name",
          "url": "string - real URL found via web search",
          "resource_type": "course|article|video|documentation|project",
          "source": "llm_generated"
        }
      ]
    }
  ]
}"""

CURRENT_TREND_SYSTEM_PROMPT = (
    "You are a career advisor generating a personalized learning roadmap "
    "based on CURRENT market demand. Focus on skills and tools that are "
    "in high demand RIGHT NOW in job postings. Prioritize established, "
    "proven technologies that employers are actively hiring for today."
    + _BASE_RULES
)

FUTURE_TREND_SYSTEM_PROMPT = (
    "You are a career advisor generating a personalized learning roadmap "
    "based on FUTURE and EMERGING market trends. Focus on skills and tools "
    "that are gaining momentum and will be in high demand in the next 1-3 years. "
    "Prioritize cutting-edge technologies, AI/ML integrations, and emerging "
    "frameworks that forward-thinking companies are beginning to adopt. "
    "Use web search to identify the latest industry forecasts and emerging tech trends."
    + _BASE_RULES
)


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
        use_market_trends: bool = False,
        # Org context (optional — only passed when generating for an org)
        org_profile: dict | None = None,
        role_skills: list[str] | None = None,
    ) -> LearningRoadmap:
        """
        Generate and persist a learning roadmap.

        Args:
            user_id:           The user who owns/initiated the roadmap.
            trend_name:        Career/role name (e.g. "Backend Developer").
            goal:              User-defined goal string.
            user_skills:       Skills of the individual user.
            use_market_trends: False = current demand, True = future/emerging trends.
            org_profile:       Dict with org context (name, industry, description,
                               core_services, tech_stacks). Passed from org roadmaps.
            role_skills:       Aggregated skills of org members in the same role.
                               Used to calibrate difficulty/focus for the team.
        """
        trend_mode = "future" if use_market_trends else "current"

        # Fetch market stats for the trend
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
            use_market_trends=use_market_trends,
            org_profile=org_profile,
            role_skills=role_skills,
        )

        roadmap = await self.repo.create_roadmap({
            "user_id": user_id,
            "title": roadmap_data.get("title", f"Roadmap to {trend_name}"),
            "trend_name": trend_name,
            "goal": goal,
            "total_weeks": roadmap_data.get("total_weeks", 8),
            "trend_mode": trend_mode,
            "skill_gap_summary": roadmap_data.get("skill_gap_summary"),
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

    # ------------------------------------------------------------------
    # Resource toggle — primary progress mechanism
    # ------------------------------------------------------------------

    async def toggle_resource(
        self, user_id: str, resource_id: str, completed: bool
    ) -> dict:
        """Check or uncheck a single resource. Auto-cascades to step and roadmap status."""
        from fastapi import HTTPException
        from sqlalchemy import select
        from app.models.roadmap import LearningRoadmapStep

        resource = await self.repo.get_resource(resource_id)
        if not resource:
            raise HTTPException(status_code=404, detail="Resource not found.")

        step_id = resource.step_id

        rp = await self.repo.upsert_resource_progress(
            user_id=user_id,
            resource_id=resource_id,
            step_id=step_id,
            completed=completed,
        )

        step = await self.repo.get_step(step_id)
        if not step:
            raise HTTPException(status_code=404, detail="Step not found.")

        total_resources = len(step.resources)

        completed_resources = sum(
            1 for r in step.resources
            if any(p.user_id == user_id and p.completed for p in r.resource_progress)
        )

        if completed_resources == 0:
            new_step_status = "not_started"
        elif completed_resources < total_resources:
            new_step_status = "in_progress"
        else:
            new_step_status = "completed"

        step_progress = await self.repo.get_progress(user_id, step_id)
        if step_progress:
            await self.repo.update_progress(step_progress, new_step_status)
        else:
            await self.repo.create_progress({
                "user_id": user_id,
                "step_id": step_id,
                "status": new_step_status,
            })

        roadmap = await self.repo.get_by_id_any_user(step.roadmap_id)
        roadmap_status = "not_started"
        steps_completed = 0
        total_steps = 0

        if roadmap:
            total_steps = len(roadmap.steps)
            progress_statuses = []
            for s in roadmap.steps:
                for p in s.progress:
                    if p.user_id == user_id:
                        progress_statuses.append(
                            new_step_status if s.id == step_id else p.status
                        )
                        break
                else:
                    progress_statuses.append("not_started")

            steps_completed = progress_statuses.count("completed")

            if total_steps > 0 and steps_completed == total_steps:
                roadmap_status = "completed"
            elif any(s in ("in_progress", "completed") for s in progress_statuses):
                roadmap_status = "in_progress"
            else:
                roadmap_status = "not_started"

            await self.repo.update_roadmap_status(step.roadmap_id, roadmap_status)

        await self.db.commit()

        return {
            "resource_id": resource_id,
            "completed": rp.completed,
            "completed_at": rp.completed_at,
            "step_id": step_id,
            "step_status": new_step_status,
            "resources_completed": completed_resources,
            "total_resources": total_resources,
            "resource_completion_pct": round(completed_resources / total_resources * 100, 1) if total_resources else 0.0,
            "roadmap_status": roadmap_status,
            "steps_completed": steps_completed,
            "total_steps": total_steps,
            "completion_percentage": round(steps_completed / total_steps * 100, 1) if total_steps else 0.0,
        }

    # ------------------------------------------------------------------
    # Step progress — manual override
    # ------------------------------------------------------------------

    async def update_step_progress(
        self, user_id: str, step_id: str, status: str, notes: str | None = None
    ) -> dict:
        from fastapi import HTTPException
        from sqlalchemy import select

        valid_statuses = {"not_started", "in_progress", "completed"}
        if status not in valid_statuses:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status '{status}'. Must be one of: {', '.join(sorted(valid_statuses))}",
            )

        progress = await self.repo.get_progress(user_id, step_id)
        if not progress:
            raise HTTPException(status_code=404, detail="Progress not found")

        await self.repo.update_progress(progress, status, notes)

        # Sync resource progress with manual override
        from app.models.roadmap import LearningRoadmapStep
        step_for_sync_result = await self.db.execute(
            select(LearningRoadmapStep).where(LearningRoadmapStep.id == step_id)
        )
        step_for_sync = step_for_sync_result.scalar_one_or_none()
        if step_for_sync:
            step_with_resources = await self.repo.get_step(step_id)
            if step_with_resources:
                if status == "completed":
                    await self.repo.mark_all_resources_in_step(
                        user_id=user_id,
                        step_id=step_id,
                        resources=step_with_resources.resources,
                        completed=True,
                    )
                elif status == "not_started":
                    await self.repo.clear_resource_progress_for_step(user_id, step_id)

        from app.models.roadmap import LearningRoadmapStep
        step_result = await self.db.execute(
            select(LearningRoadmapStep).where(LearningRoadmapStep.id == step_id)
        )
        step = step_result.scalar_one_or_none()

        roadmap_status = "not_started"
        steps_completed = 0
        total_steps = 0

        if step:
            roadmap = await self.repo.get_by_id_any_user(step.roadmap_id)
            if roadmap:
                total_steps = len(roadmap.steps)
                progress_statuses = []
                for s in roadmap.steps:
                    for p in s.progress:
                        if p.user_id == user_id:
                            progress_statuses.append(
                                status if s.id == step_id else p.status
                            )
                            break
                    else:
                        progress_statuses.append("not_started")

                steps_completed = progress_statuses.count("completed")

                if total_steps > 0 and steps_completed == total_steps:
                    roadmap_status = "completed"
                elif any(s in ("in_progress", "completed") for s in progress_statuses):
                    roadmap_status = "in_progress"
                else:
                    roadmap_status = "not_started"

                await self.repo.update_roadmap_status(step.roadmap_id, roadmap_status)

        await self.db.commit()

        return {
            "step_id": step_id,
            "status": progress.status,
            "completed_at": progress.completed_at,
            "notes": progress.notes,
            "roadmap_status": roadmap_status,
            "steps_completed": steps_completed,
            "total_steps": total_steps,
            "completion_percentage": round(steps_completed / total_steps * 100, 1) if total_steps else 0.0,
        }

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    async def _call_llm(
        self,
        user_skills: list[str] | None,
        trend_name: str,
        trend_stats: dict | None,
        goal: str | None,
        use_market_trends: bool = False,
        org_profile: dict | None = None,
        role_skills: list[str] | None = None,
    ) -> dict:
        """
        Build the LLM prompt with:
        - Individual or team skills
        - Company profile context (for org roadmaps)
        - Role-based peer skills (skills of teammates in the same role)
        - Market trend mode (current or future)
        """
        user_skills_text = ", ".join(user_skills) if user_skills else "not specified"

        trend_stats_text = ""
        if trend_stats:
            trend_stats_text = (
                f"\nCurrent market data: {trend_stats.get('job_count', 'N/A')} active job postings, "
                f"{trend_stats.get('growth_pct', 'N/A')}% growth."
            )

        # --- Company / org profile context ---
        org_context_text = ""
        if org_profile:
            parts = []
            if org_profile.get("name"):
                parts.append(f"Company: {org_profile['name']}")
            if org_profile.get("industry"):
                parts.append(f"Industry: {org_profile['industry']}")
            if org_profile.get("description"):
                parts.append(f"Description: {org_profile['description']}")
            if org_profile.get("core_services"):
                services = org_profile["core_services"]
                if isinstance(services, list):
                    parts.append(f"Core services: {', '.join(str(s) for s in services)}")
            if org_profile.get("tech_stacks"):
                stacks = org_profile["tech_stacks"]
                if isinstance(stacks, list):
                    parts.append(f"Tech stack in use: {', '.join(str(s) for s in stacks)}")
            if parts:
                org_context_text = "\nCompany context:\n" + "\n".join(f"  - {p}" for p in parts)

        # --- Role-based peer skills context ---
        role_skills_text = ""
        if role_skills:
            role_skills_text = (
                f"\nSkills of teammates in the same role: {', '.join(role_skills)}. "
                "Use this to calibrate the roadmap difficulty — cover gaps but don't repeat what the team already knows well."
            )

        # --- Trend mode instruction ---
        trend_mode_instruction = (
            "\nFocus on FUTURE and EMERGING trends: identify skills that will be critical "
            "in the next 1-3 years. Search for '2025 2026 future trends' and 'emerging technologies' "
            "for this role."
            if use_market_trends
            else "\nFocus on CURRENT market demand: skills that are actively required in job postings today."
        )

        user_prompt = (
            f"Generate a learning roadmap for a user targeting the role: {trend_name}.\n"
            f"Goal: {goal or 'Become a proficient ' + trend_name}\n"
            f"User's current skills: {user_skills_text}"
            f"{trend_stats_text}"
            f"{org_context_text}"
            f"{role_skills_text}"
            f"{trend_mode_instruction}\n\n"
            f"Generate a comprehensive week-by-week roadmap that bridges the gap between "
            f"the user's current skills and the target role. Use web search to find real, "
            f"working resource URLs before generating the JSON."
        )

        system_prompt = (
            FUTURE_TREND_SYSTEM_PROMPT if use_market_trends
            else CURRENT_TREND_SYSTEM_PROMPT
        )

        llm = HostedLLM(
            model=settings.CHAT_MODEL_NAME,
            temperature=0.7,
            max_tokens=4000,
        )

        agent = create_react_agent(
            model=llm,
            tools=[perform_web_search],
            prompt=system_prompt,
        )

        messages = [HumanMessage(content=user_prompt)]
        result = await agent.ainvoke({"messages": messages})

        final_content = ""
        for msg in reversed(result["messages"]):
            if getattr(msg, "content", "") and "{" in str(msg.content):
                final_content = msg.content
                break

        if not final_content:
            final_content = result["messages"][-1].content

        cleaned = self._clean_response(final_content)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error("Roadmap JSON parse error. Raw: %s", cleaned[:500])
            raise e

    @staticmethod
    def _clean_response(content: Any) -> str:
        if hasattr(content, "content"):
            content = content.content

        cleaned = str(content).strip()

        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[-1]
            if "```" in cleaned:
                cleaned = cleaned.split("```")[0]
        elif "```" in cleaned:
            parts = cleaned.split("```")
            if len(parts) >= 3:
                cleaned = parts[1]
                if "\n" in cleaned:
                    first_line = cleaned.split("\n", 1)[0].strip()
                    if not first_line.startswith("{") and not first_line.startswith("["):
                        cleaned = cleaned.split("\n", 1)[1]

        return cleaned.strip()

import asyncio
import json
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from typing import Any
from collections.abc import Sequence

from app.services.hosted_llm import HostedLLM
from app.services.search_service import perform_web_search
from app.core.config import settings
from app.repositories.roadmap_repository import RoadmapRepository
from app.repositories.job_repository import JobRepository
from app.models.roadmap import LearningRoadmap

ROADMAP_SYSTEM_PROMPT = """You are a career advisor. Generate a personalized learning roadmap.

You MUST use the provided web search tool to find real, working, up-to-date links for the resources (courses, articles, documentation, videos) you recommend. Do not invent or hallucinate URLs.

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

Generates up to 8 weeks. Each week must have exactly 2 resources. 

CRITICAL INSTRUCTION FOR URLs: 
You MUST call the `perform_web_search` tool BEFORE generating the JSON to find working, real URLs (e.g., links to Udemy, Coursera, freeCodeCamp, official docs) for every resource you intend to include. Do NOT output empty strings for URLs. Wait for the tool to return results, then use those links in your final JSON output. Return ONLY valid JSON, no markdown or explanation."""


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
            f"the user's current skills and the target career. Please look up real resources to include as links."
        )

        llm = HostedLLM(
            model=settings.CHAT_MODEL_NAME,
            temperature=0.7,
            max_tokens=4000,
        )
        
        agent = create_react_agent(
            model=llm,
            tools=[perform_web_search],
            prompt=ROADMAP_SYSTEM_PROMPT
        )
        
        messages = [HumanMessage(content=user_prompt)]
        
        # Increase timeout or try to give it more time if it uses multiple tool calls
        result = await agent.ainvoke({"messages": messages})
        
        import re
        # Find the last message from the assistant that actually contains the JSON
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
            # If it still fails, the LLM probably got cut off via token limit
            # or the model output invalid JSON escaping. Log the error.
            print(f"JSON Parsing Error. Raw content: {cleaned}")
            raise e

    @staticmethod
    def _clean_response(content: Any) -> str:
        if hasattr(content, "content"):  # In case an AIMessage object slips through
            content = content.content
            
        cleaned = str(content).strip()
        
        # Handle ```json ... ``` blocks
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[-1]
            if "```" in cleaned:
                cleaned = cleaned.split("```")[0]
        elif "```" in cleaned:
            # Handle generic ``` ... ``` blocks
            parts = cleaned.split("```")
            if len(parts) >= 3:
                cleaned = parts[1]
                # Sometimes the first line is language name, strip it
                if "\n" in cleaned:
                    first_line = cleaned.split("\n", 1)[0].strip()
                    if not first_line.startswith("{") and not first_line.startswith("["):
                        cleaned = cleaned.split("\n", 1)[1]
                        
        return cleaned.strip()

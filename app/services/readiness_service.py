"""
Career Readiness Score Service.

Computes a personalized readiness score (0-100) for a user based on:
  - Their current skills
  - Their career interest (or best-fit role inferred from skills + market trends)
  - Real market demand data from the jobs database

Uses the LLM for contextual analysis (understands skill equivalences, career paths).
Results are cached on the user profile and invalidated when skills/career change
or after 24 hours — avoiding a costly LLM call on every request.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.repositories.job_repository import JobRepository
from app.services.hosted_llm import HostedLLM
from app.services.search_service import perform_web_search
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

logger = logging.getLogger(__name__)

CACHE_TTL_HOURS = 24

READINESS_SYSTEM_PROMPT = """You are a career readiness analyst with deep knowledge of
the tech job market. Given a user's current skills and their target career role,
analyze the gap and return a structured JSON readiness assessment.

Important guidelines:
- Understand skill equivalences (e.g. FastAPI ≈ Flask ≈ Django for web frameworks,
  React ≈ Vue ≈ Angular for frontend, etc.)
- Consider transferable skills — a Python developer moving to ML already knows the language
- Be honest but encouraging — score should reflect realistic market readiness
- Use web search to verify what skills are CURRENTLY required for this specific role
- Score levels: Beginner (0-30), Developing (31-60), Intermediate (61-80), Advanced (81-100)

Return ONLY valid JSON with this exact structure — no markdown, no explanation:
{
  "overall_score": <integer 0-100>,
  "level": "<Beginner|Developing|Intermediate|Advanced>",
  "matched_skills": ["skills the user has that are relevant to this role"],
  "missing_skills": ["critical skills the user is missing for this role"],
  "transferable_skills": ["user skills that partially apply but need deepening"],
  "top_recommendations": [
    "Specific actionable step 1",
    "Specific actionable step 2",
    "Specific actionable step 3"
  ],
  "market_context": {
    "role_demand": "<low|medium|high|very_high>",
    "top_required_skills": ["top 5 skills employers want for this role right now"]
  },
  "summary": "2-3 sentence honest, personalized assessment of the user's readiness"
}"""


def _is_cache_valid(user: User) -> bool:
    """
    Check if the cached readiness score is still valid.
    Invalidated if: skills changed, career_interest changed, or >24 hours old.
    """
    cache = getattr(user, "readiness_cache", None)
    if not cache:
        return False

    try:
        # Check skills snapshot
        cached_skills = set(cache.get("skills_snapshot") or [])
        current_skills = set(user.skills or [])
        if cached_skills != current_skills:
            return False

        # Check career interest
        if cache.get("career_used") != (user.career_interest or ""):
            return False

        # Check TTL
        cached_at_str = cache.get("cached_at")
        if not cached_at_str:
            return False
        cached_at = datetime.fromisoformat(cached_at_str)
        if datetime.now(timezone.utc) - cached_at > timedelta(hours=CACHE_TTL_HOURS):
            return False

        return True
    except Exception:
        return False


class ReadinessService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.job_repo = JobRepository(db)

    async def get_score(self, user: User) -> dict:
        """
        Get the career readiness score for a user.
        Returns cached result if valid, otherwise recomputes via LLM.
        """
        # Return cached result if still valid
        if _is_cache_valid(user):
            logger.info("Returning cached readiness score for user %s", user.id)
            cache = user.readiness_cache
            return {
                "career_interest": cache.get("career_used"),
                "overall_score": cache["overall_score"],
                "level": cache["level"],
                "matched_skills": cache.get("matched_skills", []),
                "missing_skills": cache.get("missing_skills", []),
                "transferable_skills": cache.get("transferable_skills", []),
                "top_recommendations": cache.get("top_recommendations", []),
                "market_context": cache.get("market_context", {}),
                "summary": cache.get("summary", ""),
                "cached": True,
                "cached_at": cache.get("cached_at"),
            }

        # Compute fresh score
        result = await self._compute_score(user)

        # Persist cache
        cache_payload = {
            **result,
            "career_used": result["career_interest"],
            "skills_snapshot": list(user.skills or []),
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }
        user.readiness_cache = cache_payload

        # Flush to DB (caller commits via get_db auto-commit)
        await self.db.flush()

        result["cached"] = False
        result["cached_at"] = cache_payload["cached_at"]
        return result

    async def _compute_score(self, user: User) -> dict:
        """Call the LLM to compute a fresh readiness score."""

        # 1. Determine the career target
        career_target = user.career_interest

        # Fetch trending roles + in-demand skills from DB
        trending_roles = await self.job_repo.get_trending(limit=10)
        in_demand_skills = await self.job_repo.get_in_demand_skills(limit=30)

        trending_role_names = [t["name"] for t in trending_roles if t.get("name")]
        in_demand_skill_names = [s["skill"] for s in in_demand_skills]

        # If no career interest → ask LLM to infer from skills + trending roles
        if not career_target:
            career_target = await self._infer_career(
                user_skills=list(user.skills or []),
                trending_roles=trending_role_names,
            )
            logger.info(
                "Inferred career '%s' for user %s (no career_interest set)",
                career_target,
                user.id,
            )

        # 2. Find market stats for this role
        market_stats = None
        for t in trending_roles:
            if t.get("name", "").lower() == career_target.lower():
                market_stats = t
                break

        # 3. Build LLM prompt
        user_skills_text = ", ".join(user.skills) if user.skills else "No skills listed"
        market_skills_text = ", ".join(in_demand_skill_names[:20]) if in_demand_skill_names else "not available"
        market_stats_text = ""
        if market_stats:
            market_stats_text = (
                f"\nCurrent market data for '{career_target}': "
                f"{market_stats.get('job_count', 'N/A')} active job postings, "
                f"{market_stats.get('growth_pct', 'N/A')}% growth."
            )

        user_prompt = (
            f"Analyze the career readiness of a user targeting: {career_target}\n\n"
            f"User's current skills: {user_skills_text}\n"
            f"Top in-demand skills across the market right now: {market_skills_text}"
            f"{market_stats_text}\n\n"
            f"Use web search to verify what specific skills are currently required for "
            f"'{career_target}' roles in job postings. Then compute the readiness score "
            f"and return the full JSON assessment."
        )

        # 4. Call LLM
        llm = HostedLLM(
            model=settings.CHAT_MODEL_NAME,
            temperature=0.3,
            max_tokens=2000,
        )

        agent = create_react_agent(
            model=llm,
            tools=[perform_web_search],
            prompt=READINESS_SYSTEM_PROMPT,
        )

        messages = [HumanMessage(content=user_prompt)]
        result = await agent.ainvoke({"messages": messages})

        # 5. Parse response
        final_content = ""
        for msg in reversed(result["messages"]):
            if getattr(msg, "content", "") and "{" in str(msg.content):
                final_content = msg.content
                break

        if not final_content:
            final_content = result["messages"][-1].content

        parsed = self._parse_response(final_content)
        parsed["career_interest"] = career_target
        return parsed

    async def _infer_career(
        self, user_skills: list[str], trending_roles: list[str]
    ) -> str:
        """
        Ask the LLM to pick the best-fit career from trending roles
        given the user's skills. Used when career_interest is not set.
        """
        if not user_skills:
            return trending_roles[0] if trending_roles else "Software Engineer"

        skills_text = ", ".join(user_skills)
        roles_text = ", ".join(trending_roles[:10]) if trending_roles else "Software Engineer"

        llm = HostedLLM(
            model=settings.CHAT_MODEL_NAME,
            temperature=0.1,
            max_tokens=50,
        )

        prompt = (
            f"A user has these skills: {skills_text}\n"
            f"From these trending roles: {roles_text}\n"
            f"Which single role is the best match for their skills? "
            f"Reply with ONLY the role name, nothing else."
        )

        try:
            response = await asyncio.to_thread(llm.invoke, prompt)
            content = response.content if hasattr(response, "content") else str(response)
            inferred = content.strip().strip('"').strip("'")
            # Validate it's one of the trending roles (or close to one)
            inferred_lower = inferred.lower()
            for role in trending_roles:
                if role.lower() in inferred_lower or inferred_lower in role.lower():
                    return role
            return inferred or (trending_roles[0] if trending_roles else "Software Engineer")
        except Exception as e:
            logger.warning("Career inference failed: %s", e)
            return trending_roles[0] if trending_roles else "Software Engineer"

    @staticmethod
    def _parse_response(content: Any) -> dict:
        """Parse and validate the LLM JSON response."""
        if hasattr(content, "content"):
            content = content.content

        text = str(content).strip()

        # Strip markdown fences
        if "```json" in text:
            text = text.split("```json", 1)[-1]
            if "```" in text:
                text = text.split("```", 1)[0]
        elif "```" in text:
            parts = text.split("```")
            if len(parts) >= 3:
                inner = parts[1]
                if "\n" in inner:
                    first = inner.split("\n", 1)[0].strip()
                    if not first.startswith("{"):
                        inner = inner.split("\n", 1)[1]
                text = inner

        try:
            data = json.loads(text.strip())
        except json.JSONDecodeError as e:
            logger.error("Readiness score JSON parse error: %s | Raw: %s", e, text[:300])
            # Return a safe fallback so the endpoint doesn't 500
            return {
                "overall_score": 0,
                "level": "Unknown",
                "matched_skills": [],
                "missing_skills": [],
                "transferable_skills": [],
                "top_recommendations": ["Set your career interest and skills on your profile for an accurate analysis."],
                "market_context": {"role_demand": "unknown", "top_required_skills": []},
                "summary": "Could not compute score — please try again.",
            }

        # Ensure all expected keys exist with safe defaults
        data.setdefault("overall_score", 0)
        data.setdefault("level", "Unknown")
        data.setdefault("matched_skills", [])
        data.setdefault("missing_skills", [])
        data.setdefault("transferable_skills", [])
        data.setdefault("top_recommendations", [])
        data.setdefault("market_context", {})
        data.setdefault("summary", "")

        # Clamp score to valid range
        data["overall_score"] = max(0, min(100, int(data["overall_score"])))

        return data

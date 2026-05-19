"""
Resume generation service.

Knowledge base is the source of truth for education and project context.
The LLM is given only what the user has actually saved; missing sections
produce warnings rather than hallucinations or crashes.
"""

import asyncio
import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.hosted_llm import HostedLLM
from app.repositories.resume_repository import ResumeRepository
from app.repositories.experience_repository import ExperienceRepository
from app.repositories.job_repository import JobRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

RESUME_SYSTEM_PROMPT = """You are a professional resume writer. Generate a structured resume in JSON format.

The resume must be valid JSON with this exact structure:
{
  "professional_summary": "string - 2-3 sentence professional summary tailored to the target role",
  "skills": {
    "technical": ["skill1", "skill2"],
    "soft": ["skill1", "skill2"]
  },
  "experience": [
    {
      "company": "string",
      "role": "string",
      "duration": "string or null",
      "highlights": ["bullet point 1", "bullet point 2"]
    }
  ],
  "education": [
    {
      "institution": "string",
      "degree": "string",
      "field": "string or null",
      "year": "string or null"
    }
  ],
  "projects": [
    {
      "name": "string",
      "description": "string or null",
      "technologies": ["tech1", "tech2"]
    }
  ],
  "certifications": [
    {
      "name": "string",
      "issuer": "string or null",
      "year": "string or null"
    }
  ],
  "trending_skills_highlighted": ["skills from market that match this role"]
}

Rules:
- Use ONLY the information provided. Never fabricate experience, education, or qualifications.
- If a section's data is marked as "not available", return an empty array [] for that section.
- Rewrite experience highlights to emphasise skills relevant to the target role.
- Highlight trending market skills that match the user's existing profile.
- Return ONLY valid JSON, no markdown fences or explanation text."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ResumeService:
    def __init__(self, db: AsyncSession, user_id: str):
        self.db = db
        self.user_id = user_id
        self.resume_repo = ResumeRepository(db)
        self.experience_repo = ExperienceRepository(db)
        self.job_repo = JobRepository(db)
        self.knowledge_repo = KnowledgeRepository(db)
        self.user_repo = UserRepository(db)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def generate_and_save(self, target_role: str) -> dict:
        """
        Build a resume from the user's knowledge base and profile, call the
        LLM, persist the result, and return it with any informational warnings.
        """
        # 1. Load static user data (no embedding needed)
        user = await self.user_repo.get_by_id(self.user_id)
        if not user:
            raise ValueError("User not found.")

        experiences = await self.experience_repo.get_by_user(self.user_id)
        skills_data = await self.job_repo.get_in_demand_skills(limit=15)
        trending_skills = [s["skill"] for s in skills_data]

        # 2. Embed the target role for knowledge-base retrieval
        query_embedding = await self._embed_query(target_role)

        # 3. Retrieve relevant knowledge chunks via vector search
        education_chunks: list[str] = []
        project_chunks: list[str] = []
        profile_chunks: list[str] = []

        if query_embedding:
            edu_results = await self.knowledge_repo.search_by_sources(
                user_id=self.user_id,
                query_embedding=query_embedding,
                source_types=["transcript_course"],
                limit=12,
            )
            education_chunks = [c.content for c in edu_results]

            proj_results = await self.knowledge_repo.search_by_sources(
                user_id=self.user_id,
                query_embedding=query_embedding,
                source_types=["resume", "github_repo"],
                limit=10,
            )
            project_chunks = [c.content for c in proj_results]

            prof_results = await self.knowledge_repo.search_by_sources(
                user_id=self.user_id,
                query_embedding=query_embedding,
                source_types=["profile"],
                limit=5,
            )
            profile_chunks = [c.content for c in prof_results]
        else:
            # Embedding service unavailable — fall back to plain fetch for
            # education at least (no ordering guarantee but better than nothing)
            logger.warning(
                "Embedding service unavailable for user %s — falling back to "
                "plain knowledge fetch for resume generation.",
                self.user_id,
            )
            raw = await self.knowledge_repo.get_all_by_user_and_sources(
                user_id=self.user_id,
                source_types=["transcript_course"],
            )
            education_chunks = [c.content for c in raw[:12]]

        # 4. Build warnings for sections with no data
        warnings: list[str] = _build_warnings(
            user=user,
            experiences=experiences,
            education_chunks=education_chunks,
            project_chunks=project_chunks,
        )

        # 5. Compose user profile context dict for the prompt
        user_profile = _build_user_profile(
            user=user,
            experiences=experiences,
            education_chunks=education_chunks,
            project_chunks=project_chunks,
            profile_chunks=profile_chunks,
        )

        # 6. Call LLM
        raw_response = await self._call_llm(user_profile, trending_skills, target_role)

        # 7. Parse — robust, never crashes on bad LLM output
        resume_data = _parse_llm_response(raw_response)

        # 8. Persist
        resume = await self.resume_repo.create(self.user_id, target_role, resume_data)
        await self.db.commit()

        return {
            "id": resume.id,
            "user_id": resume.user_id,
            "target_role": resume.target_role,
            "professional_summary": resume.professional_summary,
            "skills": resume.skills,
            "experience": resume.experience,
            "education": resume.education,
            "projects": resume.projects,
            "certifications": resume.certifications,
            "trending_skills_highlighted": resume.trending_skills_highlighted,
            "created_at": resume.created_at,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # Embedding helper (async-safe, never raises)
    # ------------------------------------------------------------------

    async def _embed_query(self, text: str) -> list[float] | None:
        """
        Embed *text* using whichever provider is configured.
        Returns None if the embedding service is unavailable so callers can
        degrade gracefully instead of crashing.
        """
        try:
            from app.services.embedding_service import get_embedding_service
            service = get_embedding_service()
            # Both BertEmbeddingService and HostedEmbeddingService are sync
            embedding = await asyncio.to_thread(service.generate_embedding, text)
            return embedding
        except Exception as exc:
            logger.warning("Failed to generate embedding for resume query: %s", exc)
            return None

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    async def _call_llm(
        self,
        user_profile: dict,
        trending_skills: list[str],
        target_role: str,
    ) -> str:
        # --- Work experience block ---
        experiences_text = ""
        for exp in user_profile.get("experiences", []):
            experiences_text += (
                f"- {exp.get('job_title', '')} at {exp.get('company', '')} "
                f"({exp.get('start_date', '')} - {exp.get('end_date', 'present')}): "
                f"{exp.get('description', '')}\n"
            )

        # --- Education block (from transcript knowledge chunks) ---
        education_text = "\n".join(user_profile.get("education_context", [])) or "not available"

        # --- Projects block (from CV + GitHub knowledge chunks) ---
        projects_text = "\n".join(user_profile.get("project_context", [])) or "not available"

        # --- Profile / skills context ---
        profile_text = "\n".join(user_profile.get("profile_context", [])) or ""

        user_prompt = f"""Generate a resume for a {target_role} position.

Target role: {target_role}
Candidate name: {user_profile.get("full_name") or "Not provided"}
Candidate skills (from profile): {", ".join(user_profile.get("skills") or []) or "not specified"}
Candidate career interest: {user_profile.get("career_interest") or "not specified"}

Additional profile context:
{profile_text or "None"}

Work experience:
{experiences_text.strip() or "No experience listed"}

Education context (from academic transcript):
{education_text}

Projects / CV / GitHub context:
{projects_text}

Market trending skills for this role: {", ".join(trending_skills[:10]) or "not specified"}

Instructions:
- Use the education context above to fill the education[] array. If it says "not available", return education: [].
- Use the projects context above to fill the projects[] array. If it says "not available", return projects: [].
- Do NOT invent institutions, degrees, or projects that are not mentioned in the context.
- Generate a professional resume that highlights the candidate's relevant experience and marketable skills."""

        full_prompt = f"{RESUME_SYSTEM_PROMPT}\n\n{user_prompt}"

        llm = HostedLLM(
            model=settings.CHAT_MODEL_NAME,
            temperature=0.4,   # lower temperature = more faithful to facts
            max_tokens=4000,
        )
        return await asyncio.to_thread(llm.invoke, full_prompt)


# ---------------------------------------------------------------------------
# Pure helper functions (no DB access, easy to unit-test)
# ---------------------------------------------------------------------------

def _build_user_profile(
    user,
    experiences: list,
    education_chunks: list[str],
    project_chunks: list[str],
    profile_chunks: list[str],
) -> dict:
    """Assemble a plain dict that the prompt builder can consume."""
    return {
        "full_name": user.full_name,
        "skills": user.skills or [],
        "career_interest": user.career_interest,
        "experiences": [
            {
                "job_title": e.job_title,
                "company": e.company,
                "start_date": str(e.start_date.date()) if e.start_date else "",
                "end_date": str(e.end_date.date()) if e.end_date else "present",
                "description": e.description or "",
            }
            for e in experiences
        ],
        # Raw knowledge-base text chunks passed directly to the prompt
        "education_context": education_chunks,
        "project_context": project_chunks,
        "profile_context": profile_chunks,
    }


def _build_warnings(
    user,
    experiences: list,
    education_chunks: list[str],
    project_chunks: list[str],
) -> list[str]:
    """
    Return human-readable warnings for every section that has no data.
    The resume is still generated — these are informational notices for the
    frontend to surface to the user.
    """
    warnings: list[str] = []

    if not education_chunks:
        warnings.append(
            "Education section is empty. Upload your academic transcript at "
            "/api/transcripts to include your education details in the resume."
        )

    if not experiences:
        warnings.append(
            "Work experience section is empty. Add your work experiences at "
            "/api/users/me/experiences to include them in the resume."
        )

    if not project_chunks:
        warnings.append(
            "No projects or CV data found. Upload your CV at /api/users/me/cv "
            "or sync your GitHub profile to include projects in the resume."
        )

    if not (user.skills or []):
        warnings.append(
            "No skills found on your profile. Update your skills at "
            "/api/users/me/skills so the resume can highlight your technical abilities."
        )

    return warnings


def _parse_llm_response(content: Any) -> dict:
    """
    Parse the LLM response into a dict.

    Strategy:
    1. Strip markdown fences if present.
    2. Attempt json.loads.
    3. On failure raise a ValueError with a clear message (caught by the route
       and returned as a 422 to the client, not a bare 500).
    4. After parsing, ensure every expected key exists with a safe default so
       the repository layer never receives a partial dict that would leave DB
       columns as NULL unexpectedly.
    """
    cleaned = _strip_markdown(content)

    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(
            f"The AI returned a response that could not be parsed as JSON. "
            f"Please try again. Detail: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            "The AI returned an unexpected response format. Please try again."
        )

    # Ensure all expected keys are present with safe defaults
    data.setdefault("professional_summary", None)
    data.setdefault("skills", {"technical": [], "soft": []})
    data.setdefault("experience", [])
    data.setdefault("education", [])
    data.setdefault("projects", [])
    data.setdefault("certifications", [])
    data.setdefault("trending_skills_highlighted", [])

    return data


def _strip_markdown(content: Any) -> str:
    """Remove ```json ... ``` or ``` ... ``` fences from LLM output."""
    if hasattr(content, "content"):
        content = content.content

    text = str(content).strip()

    if "```json" in text:
        text = text.split("```json", 1)[-1]
        if "```" in text:
            text = text.split("```", 1)[0]
    elif "```" in text:
        parts = text.split("```")
        if len(parts) >= 3:
            inner = parts[1]
            # Strip leading language tag (e.g. "json\n{...")
            if "\n" in inner:
                first_line = inner.split("\n", 1)[0].strip()
                if not first_line.startswith("{") and not first_line.startswith("["):
                    inner = inner.split("\n", 1)[1]
            text = inner

    return text.strip()

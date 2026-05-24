"""
Resume generation service.

Knowledge base is the source of truth for education and project context.
The LLM is given only what the user has actually saved; missing sections
produce warnings rather than hallucinations or crashes.

The generated resume follows ATS (Applicant Tracking System) best practices:
- Keyword-optimized for the target role
- Action-verb bullet points with quantifiable results
- Clean section structure that ATS parsers can read
- Trending skills from real market data embedded naturally
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
# ATS-Optimized System Prompt
# ---------------------------------------------------------------------------

RESUME_SYSTEM_PROMPT = """You are an expert resume writer and ATS (Applicant Tracking System) optimization specialist.
Your goal is to generate a resume that:
1. Passes ATS screening systems used by 98% of Fortune 500 companies
2. Is tailored precisely to the target role with relevant keywords
3. Uses strong action verbs and quantifiable achievements
4. Highlights skills that match current market demand for the role

ATS OPTIMIZATION RULES (follow strictly):
- Use standard section names: Professional Summary, Skills, Experience, Education, Projects, Certifications
- Incorporate the exact job title and key role-related keywords naturally throughout
- Start every experience bullet with a strong action verb (Led, Built, Developed, Implemented, Optimized, etc.)
- Include metrics/numbers in experience highlights wherever data allows (e.g. "Improved API response time by 40%")
- Match skills listed to those commonly required for the target role based on market data
- Professional summary must mention the target role title and 2-3 top relevant skills
- For technical skills: list actual technologies, frameworks, tools — not vague terms
- Soft skills should be role-relevant (e.g. for backend dev: "Problem-solving", "Technical communication")

CONTEXT UNDERSTANDING RULES:
- Read all provided context carefully — education, experience, projects, profile
- Never fabricate information not mentioned in the context
- If a section's data is "not available", return an empty array [] for that section
- Extract implicit skills from experience descriptions (e.g. if they worked at a startup, infer "agile", "cross-functional collaboration")
- Reframe experience descriptions to match the target role's requirements
- Identify transferable skills between different roles/industries

The resume must be valid JSON with this exact structure:
{
  "professional_summary": "3-4 sentence ATS-optimized summary mentioning the target role title and top skills. Start with the candidate's strongest qualification.",
  "ats_score_hint": "Brief note about main ATS keywords included (not shown to user, for internal use)",
  "skills": {
    "technical": ["specific tool/framework/language skill1", "skill2"],
    "soft": ["role-relevant soft skill1", "skill2"]
  },
  "experience": [
    {
      "company": "string",
      "role": "string — use the most relevant/senior title",
      "duration": "Month Year – Month Year or Present",
      "highlights": [
        "Action verb + what you did + measurable impact (e.g. Built REST API using FastAPI serving 10k+ requests/day)",
        "Another achievement with metrics where possible"
      ]
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
      "description": "1-2 sentence description with technologies and impact",
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
  "trending_skills_highlighted": ["market-demand skills from provided data that match this candidate's profile"]
}

Return ONLY valid JSON, no markdown fences or explanation text."""


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
    # Generate and save
    # ------------------------------------------------------------------

    async def generate_and_save(self, target_role: str) -> dict:
        """
        Build a resume from the user's knowledge base and profile, call the
        LLM, persist the result, and return it with any informational warnings.
        """
        user = await self.user_repo.get_by_id(self.user_id)
        if not user:
            raise ValueError("User not found.")

        experiences = await self.experience_repo.get_by_user(self.user_id)
        skills_data = await self.job_repo.get_in_demand_skills(limit=20)
        trending_skills = [s["skill"] for s in skills_data]

        # Embed the target role for knowledge-base retrieval
        query_embedding = await self._embed_query(target_role)

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

        warnings: list[str] = _build_warnings(
            user=user,
            experiences=experiences,
            education_chunks=education_chunks,
            project_chunks=project_chunks,
        )

        user_profile = _build_user_profile(
            user=user,
            experiences=experiences,
            education_chunks=education_chunks,
            project_chunks=project_chunks,
            profile_chunks=profile_chunks,
        )

        raw_response = await self._call_llm(user_profile, trending_skills, target_role)
        resume_data = _parse_llm_response(raw_response)

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
            "updated_at": resume.updated_at,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # Update resume (partial patch)
    # ------------------------------------------------------------------

    async def update_resume(self, resume_id: str, update_data: dict) -> dict:
        """
        Partially update a resume. Only fields present in update_data are changed.
        Raises ValueError if the resume is not found or doesn't belong to this user.
        """
        resume = await self.resume_repo.get_by_id(resume_id, self.user_id)
        if not resume:
            raise ValueError("Resume not found.")

        updated = await self.resume_repo.update(resume, update_data)
        await self.db.commit()

        return {
            "id": updated.id,
            "user_id": updated.user_id,
            "target_role": updated.target_role,
            "professional_summary": updated.professional_summary,
            "skills": updated.skills,
            "experience": updated.experience,
            "education": updated.education,
            "projects": updated.projects,
            "certifications": updated.certifications,
            "trending_skills_highlighted": updated.trending_skills_highlighted,
            "created_at": updated.created_at,
            "updated_at": updated.updated_at,
            "warnings": [],
        }

    # ------------------------------------------------------------------
    # Delete resume
    # ------------------------------------------------------------------

    async def delete_resume(self, resume_id: str) -> None:
        """Delete a resume. Raises ValueError if not found."""
        resume = await self.resume_repo.get_by_id(resume_id, self.user_id)
        if not resume:
            raise ValueError("Resume not found.")
        await self.resume_repo.delete(resume)
        await self.db.commit()

    # ------------------------------------------------------------------
    # Embedding helper
    # ------------------------------------------------------------------

    async def _embed_query(self, text: str) -> list[float] | None:
        try:
            from app.services.embedding_service import get_embedding_service
            service = get_embedding_service()
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
        experiences_text = ""
        for exp in user_profile.get("experiences", []):
            experiences_text += (
                f"- {exp.get('job_title', '')} at {exp.get('company', '')} "
                f"({exp.get('start_date', '')} - {exp.get('end_date', 'present')}): "
                f"{exp.get('description', '')}\n"
            )

        education_text = "\n".join(user_profile.get("education_context", [])) or "not available"
        projects_text = "\n".join(user_profile.get("project_context", [])) or "not available"
        profile_text = "\n".join(user_profile.get("profile_context", [])) or ""

        user_prompt = f"""Generate an ATS-optimized resume for a {target_role} position.

=== CANDIDATE INFORMATION ===
Target role: {target_role}
Candidate name: {user_profile.get("full_name") or "Not provided"}
Current skills: {", ".join(user_profile.get("skills") or []) or "not specified"}
Career interest: {user_profile.get("career_interest") or "not specified"}

=== ADDITIONAL PROFILE CONTEXT ===
{profile_text or "None"}

=== WORK EXPERIENCE ===
{experiences_text.strip() or "No experience listed"}

=== EDUCATION (from academic transcript) ===
{education_text}

=== PROJECTS / CV / GITHUB CONTEXT ===
{projects_text}

=== MARKET DEMAND DATA ===
Top in-demand skills for {target_role} right now: {", ".join(trending_skills[:15]) or "not specified"}

=== ATS OPTIMIZATION INSTRUCTIONS ===
1. Include "{target_role}" in the professional summary
2. Weave in these high-demand skills naturally where the candidate's background supports it: {", ".join(trending_skills[:8])}
3. Use strong action verbs for all experience bullets (Built, Developed, Implemented, Led, Optimized, Architected, etc.)
4. Add quantifiable metrics to experience bullets where context suggests them
5. Extract implicit technical skills from the experience descriptions
6. Education: use ONLY what's in the education context. If "not available", return education: []
7. Projects: use ONLY what's in the projects context. If "not available", return projects: []
8. Do NOT invent or fabricate any information not mentioned in the context above"""

        full_prompt = f"{RESUME_SYSTEM_PROMPT}\n\n{user_prompt}"

        llm = HostedLLM(
            model=settings.CHAT_MODEL_NAME,
            temperature=0.3,
            max_tokens=4000,
        )
        return await asyncio.to_thread(llm.invoke, full_prompt)


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------

def _build_user_profile(
    user,
    experiences: list,
    education_chunks: list[str],
    project_chunks: list[str],
    profile_chunks: list[str],
) -> dict:
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
    cleaned = _strip_markdown(content)

    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(
            f"The AI returned a response that could not be parsed as JSON. "
            f"Please try again. Detail: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError("The AI returned an unexpected response format. Please try again.")

    # Remove internal-only fields before persisting
    data.pop("ats_score_hint", None)

    data.setdefault("professional_summary", None)
    data.setdefault("skills", {"technical": [], "soft": []})
    data.setdefault("experience", [])
    data.setdefault("education", [])
    data.setdefault("projects", [])
    data.setdefault("certifications", [])
    data.setdefault("trending_skills_highlighted", [])

    return data


def _strip_markdown(content: Any) -> str:
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
            if "\n" in inner:
                first_line = inner.split("\n", 1)[0].strip()
                if not first_line.startswith("{") and not first_line.startswith("["):
                    inner = inner.split("\n", 1)[1]
            text = inner

    return text.strip()

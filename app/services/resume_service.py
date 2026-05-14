import asyncio
import json
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.hosted_llm import HostedLLM
from app.repositories.resume_repository import ResumeRepository
from app.repositories.experience_repository import ExperienceRepository
from app.repositories.job_repository import JobRepository

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
- Rewrite experience highlights to emphasize skills relevant to the target role
- Never fabricate experience or qualifications
- Highlight trending market skills that match the user's profile
- Return ONLY valid JSON, no markdown or explanation"""


class ResumeService:
    def __init__(self, db: AsyncSession, user_id: str):
        self.db = db
        self.user_id = user_id
        self.resume_repo = ResumeRepository(db)
        self.experience_repo = ExperienceRepository(db)
        self.job_repo = JobRepository(db)

    async def generate_and_save(self, target_role: str) -> dict:
        experiences = await self.experience_repo.get_by_user(self.user_id)
        skills_data = await self.job_repo.get_in_demand_skills(limit=15)
        trending_skills = [s["skill"] for s in skills_data]

        user_profile = {
            "skills": [],
            "experiences": [
                {
                    "job_title": e.job_title,
                    "company": e.company,
                    "start_date": str(e.start_date.date()) if e.start_date else "",
                    "end_date": str(e.end_date.date()) if e.end_date else "present",
                    "description": e.description,
                }
                for e in experiences
            ],
            "education": "not specified",
            "projects": "not specified",
        }

        raw = await self._call_llm(user_profile, trending_skills, target_role)
        cleaned = _clean_llm_response(raw)
        resume_data = json.loads(cleaned)

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
        }

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

        user_prompt = f"""Generate a resume for a {target_role} position.

Target role: {target_role}
User's skills: {', '.join(user_profile.get('skills', []) or [])}
User's education: {user_profile.get('education', 'not specified')}
User's projects: {user_profile.get('projects', 'not specified')}

User's work experience:
{experiences_text or 'No experience listed'}

Market trending skills for this role: {', '.join(trending_skills[:10]) or 'not specified'}

Generate a professional resume that highlights the user's relevant experience and marketable skills."""

        full_prompt = f"{RESUME_SYSTEM_PROMPT}\n\n{user_prompt}"

        llm = HostedLLM(
            model=settings.CHAT_MODEL_NAME,
            temperature=0.7,
            max_tokens=4000,
        )
        return await asyncio.to_thread(llm.invoke, full_prompt)


def _clean_llm_response(content: str) -> str:
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

from datetime import datetime
from pydantic import BaseModel


class SkillSection(BaseModel):
    technical: list[str] = []
    soft: list[str] = []


class ExperienceSection(BaseModel):
    company: str
    role: str
    duration: str | None = None
    highlights: list[str] = []


class EducationSection(BaseModel):
    institution: str
    degree: str
    field: str | None = None
    year: str | None = None


class ProjectSection(BaseModel):
    name: str
    description: str | None = None
    technologies: list[str] = []


class CertificationSection(BaseModel):
    name: str
    issuer: str | None = None
    year: str | None = None


class ResumeContent(BaseModel):
    professional_summary: str | None = None
    skills: SkillSection | None = None
    experience: list[ExperienceSection] = []
    education: list[EducationSection] = []
    projects: list[ProjectSection] = []
    certifications: list[CertificationSection] = []
    trending_skills_highlighted: list[str] = []


class ResumeOut(BaseModel):
    id: str
    user_id: str
    target_role: str
    professional_summary: str | None = None
    skills: SkillSection | None = None
    experience: list[ExperienceSection] = []
    education: list[EducationSection] = []
    projects: list[ProjectSection] = []
    certifications: list[CertificationSection] = []
    trending_skills_highlighted: list[str] = []
    created_at: datetime
    # Informational messages for missing profile sections (not an error)
    warnings: list[str] = []


class ResumeGenerateRequest(BaseModel):
    target_role: str

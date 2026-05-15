from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.schemas.resume import ResumeOut, ResumeGenerateRequest
from app.api.deps import get_current_user
from app.services.resume_service import ResumeService
from app.repositories.resume_repository import ResumeRepository

router = APIRouter(prefix="/api/resume", tags=["resume"])


@router.post("/generate", response_model=ResumeOut)
async def create_resume(
    req: ResumeGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        service = ResumeService(db, current_user.id)
        return await service.generate_and_save(target_role=req.target_role)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate resume: {str(e)}",
        )


@router.get("", response_model=list[ResumeOut])
async def list_resumes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = ResumeRepository(db)
    resumes = await repo.list_by_user(current_user.id)
    return [
        ResumeOut(
            id=r.id,
            user_id=r.user_id,
            target_role=r.target_role,
            professional_summary=r.professional_summary,
            skills=r.skills,
            experience=r.experience or [],
            education=r.education or [],
            projects=r.projects or [],
            certifications=r.certifications or [],
            trending_skills_highlighted=r.trending_skills_highlighted or [],
            created_at=r.created_at,
        )
        for r in resumes
    ]


@router.get("/{resume_id}", response_model=ResumeOut)
async def get_resume(
    resume_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = ResumeRepository(db)
    resume = await repo.get_by_id(resume_id, current_user.id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return ResumeOut(
        id=resume.id,
        user_id=resume.user_id,
        target_role=resume.target_role,
        professional_summary=resume.professional_summary,
        skills=resume.skills,
        experience=resume.experience or [],
        education=resume.education or [],
        projects=resume.projects or [],
        certifications=resume.certifications or [],
        trending_skills_highlighted=resume.trending_skills_highlighted or [],
        created_at=resume.created_at,
    )

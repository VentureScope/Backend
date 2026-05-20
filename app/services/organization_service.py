"""
Organization service — core CRUD, aggregate stats, logo upload.
"""

import logging
import uuid
from collections import Counter
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.organization import Organization
from app.repositories.organization_repository import OrganizationRepository
from app.schemas.organization import OrganizationCreate, OrganizationUpdate

logger = logging.getLogger(__name__)


class OrganizationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = OrganizationRepository(db)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_organization(self, owner_id: str, data: OrganizationCreate) -> Organization:
        # Check legal_name uniqueness
        existing = await self.repo.get_by_legal_name(data.legal_name)
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"An organization with legal name '{data.legal_name}' already exists.",
            )

        org = await self.repo.create({
            "id": str(uuid.uuid4()),
            "owner_id": owner_id,
            "legal_name": data.legal_name,
            "display_name": data.display_name,
            "tagline": data.tagline,
            "description": data.description,
            "industry": data.industry,
            "core_services": data.core_services,
            "website_url": data.website_url,
            "linkedin_url": data.linkedin_url,
            "github_orgs": [g.model_dump() for g in data.github_orgs] if data.github_orgs else None,
            "github_repos": [r.model_dump() for r in data.github_repos] if data.github_repos else None,
        })

        # Add creator as owner member
        await self.repo.add_member(org.id, owner_id, role="owner")
        await self.db.commit()

        # Queue embedding generation in background
        from app.tasks.org_embedding_task import generate_org_embedding
        generate_org_embedding.delay(org.id)

        # Reload with members and return as dict with computed fields
        loaded = await self.repo.get_by_id(org.id)
        return self._build_org_out(loaded, owner_id)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_organization(self, org_id: str, user_id: str) -> dict:
        org = await self.repo.get_by_id(org_id)
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found.")

        member = await self.repo.get_member(org_id, user_id)
        if not member:
            raise HTTPException(status_code=403, detail="You are not a member of this organization.")

        return self._build_org_out(org, user_id)

    async def list_organizations(self, user_id: str) -> list[dict]:
        orgs = await self.repo.list_by_user(user_id)
        result = []
        for org in orgs:
            member = next((m for m in org.members if m.user_id == user_id), None)
            my_role = member.role if member else "member"
            result.append({
                "id": org.id,
                "display_name": org.display_name,
                "legal_name": org.legal_name,
                "logo_url": org.logo_url,
                "industry": org.industry,
                "member_count": len(org.members),
                "my_role": my_role,
                "created_at": org.created_at,
            })
        return result

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_organization(self, org_id: str, owner_id: str, data: OrganizationUpdate) -> dict:
        if not await self.repo.is_owner(org_id, owner_id):
            raise HTTPException(status_code=403, detail="Only the organization owner can update settings.")

        org = await self.repo.get_by_id(org_id)
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found.")

        update_data = data.model_dump(exclude_unset=True)

        # Serialize nested objects
        if "github_orgs" in update_data and update_data["github_orgs"]:
            update_data["github_orgs"] = [
                g.model_dump() if hasattr(g, "model_dump") else g
                for g in update_data["github_orgs"]
            ]
        if "github_repos" in update_data and update_data["github_repos"]:
            update_data["github_repos"] = [
                r.model_dump() if hasattr(r, "model_dump") else r
                for r in update_data["github_repos"]
            ]

        org = await self.repo.update(org, update_data)
        await self.db.commit()

        # Re-embed org with updated profile
        from app.tasks.org_embedding_task import generate_org_embedding
        generate_org_embedding.delay(org_id)

        return self._build_org_out(org, owner_id)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_organization(self, org_id: str, owner_id: str) -> None:
        if not await self.repo.is_owner(org_id, owner_id):
            raise HTTPException(status_code=403, detail="Only the organization owner can delete the organization.")

        org = await self.repo.get_by_id(org_id)
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found.")

        # Delete logo from S3 if exists
        if org.logo_url:
            try:
                from app.services.s3_service import get_s3_service
                s3 = get_s3_service()
                await s3.delete_file(org.logo_url)
            except Exception as e:
                logger.warning("Failed to delete org logo from S3: %s", e)

        await self.repo.delete(org)
        await self.db.commit()

    # ------------------------------------------------------------------
    # Logo upload
    # ------------------------------------------------------------------

    async def upload_logo(
        self,
        org_id: str,
        owner_id: str,
        file_content: bytes,
        filename: str,
        content_type: str,
    ) -> str:
        if not await self.repo.is_owner(org_id, owner_id):
            raise HTTPException(status_code=403, detail="Only the organization owner can upload a logo.")

        org = await self.repo.get_by_id(org_id)
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found.")

        from app.services.s3_service import get_s3_service
        s3 = get_s3_service()

        # Delete old logo
        if org.logo_url:
            try:
                await s3.delete_file(org.logo_url)
            except Exception:
                pass

        logo_url = await s3.upload_profile_picture(
            user_id=f"org_{org_id}",
            file_content=file_content,
            filename=filename,
            content_type=content_type,
        )

        await self.repo.update(org, {"logo_url": logo_url})
        await self.db.commit()
        return logo_url

    async def delete_logo(self, org_id: str, owner_id: str) -> None:
        if not await self.repo.is_owner(org_id, owner_id):
            raise HTTPException(status_code=403, detail="Only the organization owner can delete the logo.")

        org = await self.repo.get_by_id(org_id)
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found.")

        if org.logo_url:
            try:
                from app.services.s3_service import get_s3_service
                s3 = get_s3_service()
                await s3.delete_file(org.logo_url)
            except Exception as e:
                logger.warning("Failed to delete org logo: %s", e)

            await self.repo.update(org, {"logo_url": None})
            await self.db.commit()

    # ------------------------------------------------------------------
    # Aggregate builder
    # ------------------------------------------------------------------

    def _build_org_out(self, org: Organization, user_id: str) -> dict:
        members = org.members or []
        member_obj = next((m for m in members if m.user_id == user_id), None)
        my_role = member_obj.role if member_obj else "member"

        # Aggregate skills
        all_skills = [
            skill
            for m in members
            for skill in (m.user.skills or [])
        ]
        top_skills = [skill for skill, _ in Counter(all_skills).most_common(10)]

        # Aggregate career interests
        all_interests = [
            m.user.career_interest
            for m in members
            if m.user.career_interest
        ]
        top_career_interests = [i for i, _ in Counter(all_interests).most_common(5)]

        members_out = [
            {
                "user_id": m.user_id,
                "full_name": m.user.full_name,
                "email": m.user.email,
                "profile_picture_url": m.user.profile_picture_url,
                "role": m.role,
                "skills": m.user.skills,
                "career_interest": m.user.career_interest,
                "joined_at": m.joined_at,
            }
            for m in members
        ]

        return {
            "id": org.id,
            "owner_id": org.owner_id,
            "legal_name": org.legal_name,
            "display_name": org.display_name,
            "tagline": org.tagline,
            "logo_url": org.logo_url,
            "description": org.description,
            "industry": org.industry,
            "core_services": org.core_services,
            "website_url": org.website_url,
            "linkedin_url": org.linkedin_url,
            "github_orgs": org.github_orgs,
            "github_repos": org.github_repos,
            "created_at": org.created_at,
            "updated_at": org.updated_at,
            "my_role": my_role,
            "member_count": len(members),
            "top_skills": top_skills,
            "top_career_interests": top_career_interests,
            "members": members_out,
        }

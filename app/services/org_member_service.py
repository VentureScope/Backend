"""
Organization member management service.
"""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.organization_repository import OrganizationRepository


class OrgMemberService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = OrganizationRepository(db)

    async def list_members(self, org_id: str, user_id: str) -> list[dict]:
        if not await self.repo.is_member(org_id, user_id):
            raise HTTPException(status_code=403, detail="You are not a member of this organization.")

        members = await self.repo.list_members(org_id)
        return [
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

    async def remove_member(self, org_id: str, owner_id: str, target_user_id: str) -> None:
        if not await self.repo.is_owner(org_id, owner_id):
            raise HTTPException(status_code=403, detail="Only the organization owner can remove members.")

        if owner_id == target_user_id:
            raise HTTPException(
                status_code=400,
                detail="Owner cannot remove themselves. Delete the organization instead.",
            )

        member = await self.repo.get_member(org_id, target_user_id)
        if not member:
            raise HTTPException(status_code=404, detail="Member not found in this organization.")

        await self.repo.remove_member(org_id, target_user_id)
        await self.db.commit()

        # Re-embed org — member aggregate changed
        from app.tasks.org_embedding_task import generate_org_embedding
        generate_org_embedding.delay(org_id)

    async def leave_organization(self, org_id: str, user_id: str) -> None:
        member = await self.repo.get_member(org_id, user_id)
        if not member:
            raise HTTPException(status_code=404, detail="You are not a member of this organization.")

        if member.role == "owner":
            raise HTTPException(
                status_code=400,
                detail="Organization owner cannot leave. Delete the organization or transfer ownership first.",
            )

        await self.repo.remove_member(org_id, user_id)
        await self.db.commit()

        # Re-embed org — member aggregate changed
        from app.tasks.org_embedding_task import generate_org_embedding
        generate_org_embedding.delay(org_id)

"""
Repository for all Organization-related database operations.
"""

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.organization import (
    Organization,
    OrganizationMember,
    OrganizationInvite,
    OrganizationRoadmap,
)
from app.models.roadmap import LearningRoadmap, LearningRoadmapStep, LearningRoadmapProgress


class OrganizationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Organization CRUD
    # ------------------------------------------------------------------

    async def create(self, data: dict) -> Organization:
        org = Organization(**data)
        self.db.add(org)
        await self.db.flush()
        return org

    async def get_by_id(self, org_id: str) -> Organization | None:
        result = await self.db.execute(
            select(Organization)
            .where(Organization.id == org_id)
            .options(
                selectinload(Organization.members)
                .selectinload(OrganizationMember.user),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_legal_name(self, legal_name: str) -> Organization | None:
        result = await self.db.execute(
            select(Organization).where(Organization.legal_name == legal_name)
        )
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: str) -> list[Organization]:
        """Return all orgs where the user is a member (owner or member)."""
        result = await self.db.execute(
            select(Organization)
            .join(
                OrganizationMember,
                OrganizationMember.organization_id == Organization.id,
            )
            .where(OrganizationMember.user_id == user_id)
            .options(
                selectinload(Organization.members)
                .selectinload(OrganizationMember.user),
            )
            .order_by(Organization.created_at.desc())
        )
        return list(result.scalars().unique().all())

    async def update(self, org: Organization, data: dict) -> Organization:
        for key, value in data.items():
            if value is not None:
                setattr(org, key, value)
        await self.db.flush()
        return org

    async def delete(self, org: Organization) -> None:
        await self.db.delete(org)
        await self.db.flush()

    # ------------------------------------------------------------------
    # Membership
    # ------------------------------------------------------------------

    async def get_member(self, org_id: str, user_id: str) -> OrganizationMember | None:
        result = await self.db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_member(self, org_id: str, user_id: str, role: str = "member") -> OrganizationMember:
        member = OrganizationMember(
            organization_id=org_id,
            user_id=user_id,
            role=role,
        )
        self.db.add(member)
        await self.db.flush()
        return member

    async def remove_member(self, org_id: str, user_id: str) -> None:
        await self.db.execute(
            delete(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == user_id,
            )
        )
        await self.db.flush()

    async def list_members(self, org_id: str) -> list[OrganizationMember]:
        result = await self.db.execute(
            select(OrganizationMember)
            .where(OrganizationMember.organization_id == org_id)
            .options(selectinload(OrganizationMember.user))
            .order_by(OrganizationMember.joined_at.asc())
        )
        return list(result.scalars().all())

    async def is_member(self, org_id: str, user_id: str) -> bool:
        member = await self.get_member(org_id, user_id)
        return member is not None

    async def is_owner(self, org_id: str, user_id: str) -> bool:
        member = await self.get_member(org_id, user_id)
        return member is not None and member.role == "owner"

    # ------------------------------------------------------------------
    # Invites
    # ------------------------------------------------------------------

    async def create_invite(self, data: dict) -> OrganizationInvite:
        invite = OrganizationInvite(**data)
        self.db.add(invite)
        await self.db.flush()
        return invite

    async def get_invite_by_token(self, token: str) -> OrganizationInvite | None:
        result = await self.db.execute(
            select(OrganizationInvite)
            .where(OrganizationInvite.token == token)
            .options(selectinload(OrganizationInvite.organization))
        )
        return result.scalar_one_or_none()

    async def get_invite_by_id(self, invite_id: str, org_id: str) -> OrganizationInvite | None:
        result = await self.db.execute(
            select(OrganizationInvite).where(
                OrganizationInvite.id == invite_id,
                OrganizationInvite.organization_id == org_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_pending_invite(self, org_id: str, email: str) -> OrganizationInvite | None:
        """Get any existing pending invite for this email in this org."""
        result = await self.db.execute(
            select(OrganizationInvite).where(
                OrganizationInvite.organization_id == org_id,
                OrganizationInvite.email == email,
                OrganizationInvite.status == "pending",
            )
        )
        return result.scalar_one_or_none()

    async def list_invites(self, org_id: str) -> list[OrganizationInvite]:
        result = await self.db.execute(
            select(OrganizationInvite)
            .where(
                OrganizationInvite.organization_id == org_id,
                OrganizationInvite.status == "pending",
            )
            .order_by(OrganizationInvite.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_invite_status(self, invite: OrganizationInvite, status: str) -> None:
        invite.status = status
        await self.db.flush()

    # ------------------------------------------------------------------
    # Org Roadmaps
    # ------------------------------------------------------------------

    async def create_org_roadmap(self, org_id: str, roadmap_id: str, created_by: str) -> OrganizationRoadmap:
        org_roadmap = OrganizationRoadmap(
            organization_id=org_id,
            roadmap_id=roadmap_id,
            created_by=created_by,
        )
        self.db.add(org_roadmap)
        await self.db.flush()
        return org_roadmap

    async def list_org_roadmaps(self, org_id: str) -> list[OrganizationRoadmap]:
        result = await self.db.execute(
            select(OrganizationRoadmap)
            .where(OrganizationRoadmap.organization_id == org_id)
            .options(
                selectinload(OrganizationRoadmap.roadmap)
                .selectinload(LearningRoadmap.steps)
                .selectinload(LearningRoadmapStep.progress),
            )
            .order_by(OrganizationRoadmap.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_org_roadmap(self, org_id: str, roadmap_id: str) -> OrganizationRoadmap | None:
        result = await self.db.execute(
            select(OrganizationRoadmap)
            .where(
                OrganizationRoadmap.organization_id == org_id,
                OrganizationRoadmap.roadmap_id == roadmap_id,
            )
            .options(
                selectinload(OrganizationRoadmap.roadmap)
                .selectinload(LearningRoadmap.steps)
                .selectinload(LearningRoadmapStep.progress),
            )
        )
        return result.scalar_one_or_none()

    async def delete_org_roadmap(self, org_id: str, roadmap_id: str) -> None:
        await self.db.execute(
            delete(OrganizationRoadmap).where(
                OrganizationRoadmap.organization_id == org_id,
                OrganizationRoadmap.roadmap_id == roadmap_id,
            )
        )
        await self.db.flush()

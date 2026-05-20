"""
Organization API endpoints.

Prefix: /api/organizations
"""

import asyncio
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.api.deps import get_current_user
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationOut,
    OrganizationListItem,
    OrgMemberOut,
    OrgInviteCreate,
    OrgInviteOut,
    AcceptInviteRequest,
    OrgRoadmapAssign,
    OrgRoadmapOut,
    OrgRoadmapListItem,
)
from app.services.organization_service import OrganizationService
from app.services.org_member_service import OrgMemberService
from app.services.org_invite_service import OrgInviteService
from app.services.org_roadmap_service import OrgRoadmapService

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


# ---------------------------------------------------------------------------
# Semantic search / discovery
# ---------------------------------------------------------------------------

@router.get("/search", response_model=list[OrganizationListItem])
async def search_organizations(
    q: str = Query(..., min_length=2, description="Natural language search query"),
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Semantic similarity search across organizations.
    Returns organizations ranked by how closely they match the query,
    filtered to only orgs the current user is a member of.
    """
    from app.services.embedding_service import get_embedding_service
    from app.models.organization import Organization, OrganizationMember

    try:
        embedding_service = get_embedding_service()
        query_embedding = await asyncio.to_thread(
            embedding_service.generate_embedding, q
        )
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail="Embedding service unavailable. Try again later.",
        )

    # Search only within orgs the user belongs to
    result = await db.execute(
        select(Organization)
        .join(
            OrganizationMember,
            OrganizationMember.organization_id == Organization.id,
        )
        .where(
            OrganizationMember.user_id == current_user.id,
            Organization.embedding.is_not(None),
        )
        .order_by(Organization.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )
    orgs = list(result.scalars().unique().all())

    # Build list items
    output = []
    for org in orgs:
        member = next(
            (m for m in (org.members or []) if m.user_id == current_user.id),
            None,
        )
        my_role = member.role if member else "member"
        # Load members count if not loaded
        member_count = len(org.members) if org.members else 0
        output.append(
            OrganizationListItem(
                id=org.id,
                display_name=org.display_name,
                legal_name=org.legal_name,
                logo_url=org.logo_url,
                industry=org.industry,
                member_count=member_count,
                my_role=my_role,
                created_at=org.created_at,
            )
        )
    return output


# ---------------------------------------------------------------------------
# Organization CRUD
# ---------------------------------------------------------------------------

@router.post("", response_model=OrganizationOut, status_code=201)
async def create_organization(
    data: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new organization. The creator becomes the owner."""
    svc = OrganizationService(db)
    return await svc.create_organization(current_user.id, data)


@router.get("", response_model=list[OrganizationListItem])
async def list_my_organizations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all organizations the current user belongs to (owner or member)."""
    svc = OrganizationService(db)
    return await svc.list_organizations(current_user.id)


@router.get("/{org_id}", response_model=OrganizationOut)
async def get_organization(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get full organization profile including aggregated member stats."""
    svc = OrganizationService(db)
    return await svc.get_organization(org_id, current_user.id)


@router.patch("/{org_id}", response_model=OrganizationOut)
async def update_organization(
    org_id: str,
    data: OrganizationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update organization settings. Owner only."""
    svc = OrganizationService(db)
    return await svc.update_organization(org_id, current_user.id, data)


@router.delete("/{org_id}", status_code=204)
async def delete_organization(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete the organization and all its data. Owner only."""
    svc = OrganizationService(db)
    await svc.delete_organization(org_id, current_user.id)


# ---------------------------------------------------------------------------
# Logo
# ---------------------------------------------------------------------------

@router.post("/{org_id}/logo", status_code=200)
async def upload_logo(
    org_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload organization logo (JPG/PNG/WEBP, max 5MB). Owner only."""
    allowed_types = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Allowed: JPG, PNG, WEBP.",
        )

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds 5MB limit.")

    svc = OrganizationService(db)
    logo_url = await svc.upload_logo(
        org_id=org_id,
        owner_id=current_user.id,
        file_content=content,
        filename=file.filename or "logo",
        content_type=file.content_type,
    )
    return {"logo_url": logo_url}


@router.delete("/{org_id}/logo", status_code=204)
async def delete_logo(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete organization logo. Owner only."""
    svc = OrganizationService(db)
    await svc.delete_logo(org_id, current_user.id)


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------

@router.get("/{org_id}/members", response_model=list[OrgMemberOut])
async def list_members(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all members of an organization."""
    svc = OrgMemberService(db)
    return await svc.list_members(org_id, current_user.id)


@router.delete("/{org_id}/members/{user_id}", status_code=204)
async def remove_member(
    org_id: str,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a member from the organization. Owner only."""
    svc = OrgMemberService(db)
    await svc.remove_member(org_id, current_user.id, user_id)


@router.delete("/{org_id}/leave", status_code=204)
async def leave_organization(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Leave an organization. Owner cannot leave (must delete instead)."""
    svc = OrgMemberService(db)
    await svc.leave_organization(org_id, current_user.id)


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------

@router.post("/{org_id}/invites", response_model=OrgInviteOut, status_code=201)
async def send_invite(
    org_id: str,
    data: OrgInviteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send an email invitation to join the organization. Owner only."""
    svc = OrgInviteService(db)
    return await svc.send_invite(org_id, current_user.id, data.email)


@router.get("/{org_id}/invites", response_model=list[OrgInviteOut])
async def list_invites(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all pending invitations for the organization. Owner only."""
    svc = OrgInviteService(db)
    return await svc.list_invites(org_id, current_user.id)


@router.delete("/{org_id}/invites/{invite_id}", status_code=204)
async def cancel_invite(
    org_id: str,
    invite_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel a pending invitation. Owner only."""
    svc = OrgInviteService(db)
    await svc.cancel_invite(org_id, current_user.id, invite_id)


@router.post("/invites/accept")
async def accept_invite(
    data: AcceptInviteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Accept an organization invitation using the token from the invite email.
    The authenticated user's email must match the invited email.
    """
    svc = OrgInviteService(db)
    return await svc.accept_invite(data.token, current_user.id)


# ---------------------------------------------------------------------------
# Team Roadmaps
# ---------------------------------------------------------------------------

@router.post("/{org_id}/roadmaps", response_model=OrgRoadmapOut, status_code=201)
async def assign_roadmap(
    org_id: str,
    data: OrgRoadmapAssign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate and assign a learning roadmap to the organization.
    All current members will have their progress automatically initialized.
    Owner only.
    """
    svc = OrgRoadmapService(db)
    return await svc.assign_roadmap(
        org_id=org_id,
        owner_id=current_user.id,
        trend_name=data.trend_name,
        goal=data.goal,
    )


@router.get("/{org_id}/roadmaps", response_model=list[OrgRoadmapListItem])
async def list_org_roadmaps(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all roadmaps assigned to the organization with aggregate completion %."""
    svc = OrgRoadmapService(db)
    return await svc.list_org_roadmaps(org_id, current_user.id)


@router.get("/{org_id}/roadmaps/{roadmap_id}", response_model=OrgRoadmapOut)
async def get_org_roadmap(
    org_id: str,
    roadmap_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific org roadmap with per-member progress breakdown."""
    svc = OrgRoadmapService(db)
    return await svc.get_org_roadmap(org_id, roadmap_id, current_user.id)


@router.delete("/{org_id}/roadmaps/{roadmap_id}", status_code=204)
async def remove_org_roadmap(
    org_id: str,
    roadmap_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a roadmap from the organization. Owner only."""
    svc = OrgRoadmapService(db)
    await svc.remove_org_roadmap(org_id, roadmap_id, current_user.id)

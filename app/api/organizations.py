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
    DeclineInviteRequest,
    MyInviteOut,
    InvitePreviewOut,
    MemberRoleUpdate,
    OrgRoadmapAssign,
    OrgRoadmapOut,
    OrgRoadmapListItem,
)
from app.services.organization_service import OrganizationService
from app.services.org_member_service import OrgMemberService
from app.services.org_invite_service import OrgInviteService
from app.services.org_roadmap_service import OrgRoadmapService

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


# ===========================================================================
# Semantic search / discovery
# ===========================================================================

@router.get("/search", response_model=list[OrganizationListItem])
async def search_organizations(
    q: str = Query(..., min_length=2, description="Natural language search query"),
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Semantic similarity search across organizations the current user belongs to."""
    from app.services.embedding_service import get_embedding_service
    from app.models.organization import Organization, OrganizationMember

    try:
        embedding_service = get_embedding_service()
        query_embedding = await asyncio.to_thread(embedding_service.generate_embedding, q)
    except Exception:
        raise HTTPException(status_code=503, detail="Embedding service unavailable. Try again later.")

    result = await db.execute(
        select(Organization)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(
            OrganizationMember.user_id == current_user.id,
            Organization.embedding.is_not(None),
        )
        .order_by(Organization.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )
    orgs = list(result.scalars().unique().all())

    output = []
    for org in orgs:
        member = next((m for m in (org.members or []) if m.user_id == current_user.id), None)
        output.append(OrganizationListItem(
            id=org.id,
            display_name=org.display_name,
            legal_name=org.legal_name,
            logo_url=org.logo_url,
            industry=org.industry,
            member_count=len(org.members) if org.members else 0,
            my_role=member.role if member else "member",
            created_at=org.created_at,
        ))
    return output


# ===========================================================================
# Invite — user-scoped (no org_id) — must be before /{org_id} routes
# ===========================================================================

@router.get("/invites/my-invites", response_model=list[MyInviteOut])
async def get_my_invites(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List all pending org invitations sent to the current user's email.
    Powers the /organization/invites inbox page and the pending badge on org list.
    """
    svc = OrgInviteService(db)
    return await svc.get_my_invites(current_user.id)


@router.get("/invites/preview", response_model=InvitePreviewOut)
async def preview_invite(
    token: str = Query(..., description="Invite token from email link"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Preview org details for an invite before accepting (N2).
    Shows org name, logo, team role, and inviter so the user knows what they're joining.
    """
    svc = OrgInviteService(db)
    return await svc.preview_invite(token)


@router.post("/invites/accept")
async def accept_invite(
    data: AcceptInviteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Accept an org invitation. User's email must match the invite."""
    svc = OrgInviteService(db)
    return await svc.accept_invite(data.token, current_user.id)


@router.post("/invites/decline")
async def decline_invite(
    data: DeclineInviteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Explicitly decline an org invitation (N3)."""
    svc = OrgInviteService(db)
    return await svc.decline_invite(data.token, current_user.id)


# ===========================================================================
# Organization CRUD
# ===========================================================================

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
    """List all organizations the current user belongs to."""
    svc = OrganizationService(db)
    return await svc.list_organizations(current_user.id)


@router.get("/{org_id}", response_model=OrganizationOut)
async def get_organization(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get full org profile including aggregated member stats and all extended fields."""
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
    """Permanently delete the organization. Owner only (N6)."""
    svc = OrganizationService(db)
    await svc.delete_organization(org_id, current_user.id)


# ===========================================================================
# Logo
# ===========================================================================

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
        raise HTTPException(status_code=400, detail="Invalid file type. Allowed: JPG, PNG, WEBP.")
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds 5MB limit.")
    svc = OrganizationService(db)
    logo_url = await svc.upload_logo(
        org_id=org_id, owner_id=current_user.id,
        file_content=content, filename=file.filename or "logo",
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


# ===========================================================================
# Members
# ===========================================================================

@router.get("/{org_id}/members", response_model=list[OrgMemberOut])
async def list_members(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all members with skills, github_username, job_title, and roadmap counts."""
    svc = OrgMemberService(db)
    return await svc.list_members(org_id, current_user.id)


@router.patch("/{org_id}/members/{user_id}", status_code=200)
async def update_member_role(
    org_id: str,
    user_id: str,
    data: MemberRoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change a member's org access role (admin | member). Owner only (N5)."""
    svc = OrgMemberService(db)
    return await svc.update_member_role(org_id, current_user.id, user_id, data.role)


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


# ===========================================================================
# Invitations (org-scoped, owner actions)
# ===========================================================================

@router.post("/{org_id}/invites", response_model=OrgInviteOut, status_code=201)
async def send_invite(
    org_id: str,
    data: OrgInviteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send an email invitation with optional team_role. Owner only."""
    svc = OrgInviteService(db)
    return await svc.send_invite(org_id, current_user.id, data.email, data.team_role)


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


@router.post("/{org_id}/invites/{invite_id}/resend", status_code=200)
async def resend_invite(
    org_id: str,
    invite_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Resend a pending invite email (N4). Owner only."""
    svc = OrgInviteService(db)
    return await svc.resend_invite(org_id, current_user.id, invite_id)


# ===========================================================================
# Team Roadmaps
# ===========================================================================

@router.post("/{org_id}/roadmaps", response_model=OrgRoadmapOut, status_code=201)
async def assign_roadmap(
    org_id: str,
    data: OrgRoadmapAssign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate and assign a team roadmap. Any org member can create (not just owner).
    Progress is auto-initialized for all current members.
    """
    svc = OrgRoadmapService(db)
    return await svc.assign_roadmap(
        org_id=org_id,
        user_id=current_user.id,
        trend_name=data.trend_name,
        goal=data.goal,
    )


@router.get("/{org_id}/roadmaps", response_model=list[OrgRoadmapListItem])
async def list_org_roadmaps(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List org roadmaps with aggregate completion %, creator info, and current user's enrollment.
    Use created_by_user_id to power the 'Created by me' filter on the frontend.
    """
    svc = OrgRoadmapService(db)
    return await svc.list_org_roadmaps(org_id, current_user.id)


@router.get("/{org_id}/roadmaps/{roadmap_id}", response_model=OrgRoadmapOut)
async def get_org_roadmap(
    org_id: str,
    roadmap_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific org roadmap with per-member progress and current user's enrollment."""
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


@router.post("/{org_id}/roadmaps/{roadmap_id}/enroll", status_code=200)
async def enroll_in_roadmap(
    org_id: str,
    roadmap_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Enroll current user on a shared team roadmap (N7).
    Initializes per-step progress records. Returns 403 if not an org member.
    """
    svc = OrgRoadmapService(db)
    return await svc.enroll_member(org_id, roadmap_id, current_user.id)


@router.post("/{org_id}/roadmaps/{roadmap_id}/fork", status_code=201)
async def fork_roadmap(
    org_id: str,
    roadmap_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a persistent personal copy of a team roadmap (N8).
    Replaces sessionStorage fork — survives refresh and works cross-device.
    """
    svc = OrgRoadmapService(db)
    return await svc.fork_roadmap(org_id, roadmap_id, current_user.id)

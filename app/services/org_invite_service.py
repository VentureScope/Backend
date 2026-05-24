"""
Organization invitation service — send, accept, decline, cancel, resend, preview.
"""

import logging
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "email"


def _render_template(filename: str, context: dict) -> str:
    template_path = _TEMPLATE_DIR / filename
    content = template_path.read_text(encoding="utf-8")
    for key, value in context.items():
        content = content.replace("{{" + key + "}}", str(value))
    return content


class OrgInviteService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = OrganizationRepository(db)
        self.user_repo = UserRepository(db)

    # ------------------------------------------------------------------
    # Send invite
    # ------------------------------------------------------------------

    async def send_invite(
        self, org_id: str, owner_id: str, email: str, team_role: str | None = None
    ) -> dict:
        if not await self.repo.is_owner(org_id, owner_id):
            raise HTTPException(status_code=403, detail="Only the organization owner can send invites.")

        org = await self.repo.get_by_id(org_id)
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found.")

        # Check if email already belongs to an existing member
        existing_user = await self.user_repo.get_by_email(email)
        if existing_user and await self.repo.is_member(org_id, existing_user.id):
            raise HTTPException(
                status_code=409,
                detail="This user is already a member of the organization.",
            )

        # Cancel any existing pending invite for this email
        existing_invite = await self.repo.get_pending_invite(org_id, email)
        if existing_invite:
            await self.repo.update_invite_status(existing_invite, "cancelled")

        # Get inviter details
        inviter = await self.user_repo.get_by_id(owner_id)
        inviter_name = (inviter.full_name or inviter.email) if inviter else "Someone"

        # Create invite
        invite = await self.repo.create_invite({
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "invited_by": owner_id,
            "email": email,
            "team_role": team_role,
        })

        await self.db.commit()

        # Send email
        await self._dispatch_invite_email(invite, org, inviter_name)

        return {
            "id": invite.id,
            "organization_id": invite.organization_id,
            "email": invite.email,
            "team_role": invite.team_role,
            "status": invite.status,
            "expires_at": invite.expires_at,
            "created_at": invite.created_at,
        }

    async def _dispatch_invite_email(self, invite, org, inviter_name: str) -> None:
        from datetime import datetime, timezone
        invite_url = f"{settings.FRONTEND_URL}/dashboard/organization/invites/accept?token={invite.token}"
        try:
            from app.services.email_service import get_email_provider
            provider = get_email_provider()
            context = {
                "inviter_name": inviter_name,
                "org_name": org.display_name,
                "invite_url": invite_url,
                "expire_hours": "48",
                "team_role": invite.team_role or "",
                "team_role_line": (
                    f'<p style="margin: 8px 0 0; font-size: 13px; color: #6b7280;">Role: <strong style="color: #374151;">{invite.team_role}</strong></p>'
                    if invite.team_role else ""
                ),
                "team_role_txt": (
                    f"Your role: {invite.team_role}\n"
                    if invite.team_role else ""
                ),
                "year": str(datetime.now(timezone.utc).year),
            }
            html_body = _render_template("org_invite.html", context)
            text_body = _render_template("org_invite.txt", context)
            await provider.send_email(
                to=invite.email,
                subject=f"You've been invited to join {org.display_name} on VentureScope",
                html=html_body,
                text=text_body,
            )
        except Exception as e:
            logger.warning("Failed to send invite email to %s: %s", invite.email, e)

    # ------------------------------------------------------------------
    # Accept invite
    # ------------------------------------------------------------------

    async def accept_invite(self, token: str, user_id: str) -> dict:
        invite = await self.repo.get_invite_by_token(token)
        if not invite:
            raise HTTPException(status_code=404, detail="Invite not found or already used.")

        if not invite.is_valid():
            raise HTTPException(
                status_code=410,
                detail="This invite has expired or has already been used.",
            )

        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")

        if user.email.lower() != invite.email.lower():
            raise HTTPException(
                status_code=403,
                detail="This invite was sent to a different email address.",
            )

        if await self.repo.is_member(invite.organization_id, user_id):
            await self.repo.update_invite_status(invite, "accepted")
            await self.db.commit()
            raise HTTPException(status_code=409, detail="You are already a member of this organization.")

        # Capture org info before commit (avoids expired object access after commit)
        org_id = invite.organization_id
        org_name = invite.organization.display_name
        team_role = invite.team_role

        # Add member — carry over team_role as job_title
        member = await self.repo.add_member(org_id, user_id, role="member")
        if team_role and hasattr(member, "job_title"):
            member.job_title = team_role

        # Update invite status to accepted
        invite.status = "accepted"
        await self.db.flush()
        await self.db.commit()

        # Verify the status was actually persisted
        await self.db.refresh(invite)
        if invite.status != "accepted":
            logger.error("Invite status failed to update for invite %s", invite.id)

        # Re-embed org — new member's skills now part of the aggregate
        try:
            from app.tasks.org_embedding_task import generate_org_embedding
            generate_org_embedding.delay(org_id)
        except Exception as e:
            logger.warning("Failed to dispatch org embedding task: %s", e)

        return {
            "message": f"Successfully joined {org_name}.",
            "organization_id": org_id,
            "organization_name": org_name,
            "team_role": team_role,
        }

    # ------------------------------------------------------------------
    # Decline invite (N3)
    # ------------------------------------------------------------------

    async def decline_invite(self, token: str, user_id: str) -> dict:
        invite = await self.repo.get_invite_by_token(token)
        if not invite:
            raise HTTPException(status_code=404, detail="Invite not found.")

        if not invite.is_valid():
            raise HTTPException(status_code=410, detail="This invite has already expired or been used.")

        user = await self.user_repo.get_by_id(user_id)
        if not user or user.email.lower() != invite.email.lower():
            raise HTTPException(status_code=403, detail="This invite was sent to a different email address.")

        await self.repo.update_invite_status(invite, "declined")
        await self.db.commit()
        return {"message": "Invitation declined."}

    # ------------------------------------------------------------------
    # Cancel invite (owner action)
    # ------------------------------------------------------------------

    async def cancel_invite(self, org_id: str, owner_id: str, invite_id: str) -> None:
        if not await self.repo.is_owner(org_id, owner_id):
            raise HTTPException(status_code=403, detail="Only the organization owner can cancel invites.")

        invite = await self.repo.get_invite_by_id(invite_id, org_id)
        if not invite:
            raise HTTPException(status_code=404, detail="Invite not found.")

        if invite.status != "pending":
            raise HTTPException(status_code=400, detail=f"Cannot cancel an invite with status '{invite.status}'.")

        await self.repo.update_invite_status(invite, "cancelled")
        await self.db.commit()

    # ------------------------------------------------------------------
    # Resend invite (N4)
    # ------------------------------------------------------------------

    async def resend_invite(self, org_id: str, owner_id: str, invite_id: str) -> dict:
        if not await self.repo.is_owner(org_id, owner_id):
            raise HTTPException(status_code=403, detail="Only the organization owner can resend invites.")

        invite = await self.repo.get_invite_by_id(invite_id, org_id)
        if not invite:
            raise HTTPException(status_code=404, detail="Invite not found.")

        if invite.status != "pending":
            raise HTTPException(status_code=400, detail=f"Can only resend pending invites. Current status: '{invite.status}'.")

        org = await self.repo.get_by_id(org_id)
        inviter = await self.user_repo.get_by_id(owner_id)
        inviter_name = (inviter.full_name or inviter.email) if inviter else "Someone"

        await self._dispatch_invite_email(invite, org, inviter_name)
        return {
            "id": invite.id,
            "email": invite.email,
            "team_role": invite.team_role,
            "message": f"Invite resent to {invite.email}.",
        }

    # ------------------------------------------------------------------
    # Preview invite — before accepting (N2)
    # ------------------------------------------------------------------

    async def preview_invite(self, token: str) -> dict:
        """
        Return org details for an invite token — used on the accept page
        to show a preview before the user confirms joining.
        No auth required; sensitive info is not leaked (token itself is the secret).
        """
        invite = await self.repo.get_invite_by_token(token)
        if not invite:
            raise HTTPException(status_code=404, detail="Invite not found.")

        inviter = await self.user_repo.get_by_id(invite.invited_by)
        inviter_name = (inviter.full_name or inviter.email) if inviter else None
        org = invite.organization

        return {
            "id": invite.id,
            "organization_id": invite.organization_id,
            "organization_name": org.display_name,
            "organization_logo": org.logo_url,
            "organization_industry": org.industry,
            "organization_description": org.description,
            "team_role": invite.team_role,
            "inviter_name": inviter_name,
            "expires_at": invite.expires_at,
            "is_valid": invite.is_valid(),
        }

    # ------------------------------------------------------------------
    # Get user's pending invites (N1)
    # ------------------------------------------------------------------

    async def get_my_invites(self, user_id: str) -> list[dict]:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")

        invites = await self.repo.get_invites_by_email(user.email)

        result = []
        for i in invites:
            inviter = await self.user_repo.get_by_id(i.invited_by) if i.invited_by else None
            inviter_name = (inviter.full_name or inviter.email) if inviter else None
            result.append({
                "id": i.id,
                "organization_id": i.organization_id,
                "organization_name": i.organization.display_name,
                "organization_logo": i.organization.logo_url,
                "organization_industry": i.organization.industry,
                "team_role": i.team_role,
                "inviter_name": inviter_name,
                "token": i.token,
                "expires_at": i.expires_at,
                "created_at": i.created_at,
            })
        return result

    # ------------------------------------------------------------------
    # List invites (owner view)
    # ------------------------------------------------------------------

    async def list_invites(self, org_id: str, owner_id: str) -> list[dict]:
        if not await self.repo.is_owner(org_id, owner_id):
            raise HTTPException(status_code=403, detail="Only the organization owner can view invites.")

        invites = await self.repo.list_invites(org_id)
        return [
            {
                "id": i.id,
                "organization_id": i.organization_id,
                "email": i.email,
                "team_role": i.team_role,
                "status": i.status,
                "expires_at": i.expires_at,
                "created_at": i.created_at,
            }
            for i in invites
        ]

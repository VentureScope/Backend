"""
Organization invitation service — send, accept, cancel invites.
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

    async def send_invite(self, org_id: str, owner_id: str, email: str) -> dict:
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
        })

        await self.db.commit()

        # Send email
        invite_url = f"{settings.FRONTEND_URL}/organizations/invite/accept?token={invite.token}"
        try:
            from app.services.email_service import get_email_provider
            provider = get_email_provider()
            html_body = _render_template("org_invite.html", {
                "inviter_name": inviter_name,
                "org_name": org.display_name,
                "invite_url": invite_url,
                "expire_hours": "48",
            })
            text_body = _render_template("org_invite.txt", {
                "inviter_name": inviter_name,
                "org_name": org.display_name,
                "invite_url": invite_url,
                "expire_hours": "48",
            })
            await provider.send_email(
                to=email,
                subject=f"You've been invited to join {org.display_name} on VentureScope",
                html=html_body,
                text=text_body,
            )
        except Exception as e:
            logger.warning("Failed to send invite email to %s: %s", email, e)
            # Don't fail the request — invite is created, email may retry

        return {
            "id": invite.id,
            "organization_id": invite.organization_id,
            "email": invite.email,
            "status": invite.status,
            "expires_at": invite.expires_at,
            "created_at": invite.created_at,
        }

    async def accept_invite(self, token: str, user_id: str) -> dict:
        invite = await self.repo.get_invite_by_token(token)
        if not invite:
            raise HTTPException(status_code=404, detail="Invite not found or already used.")

        if not invite.is_valid():
            raise HTTPException(
                status_code=410,
                detail="This invite has expired or has already been used.",
            )

        # Verify the accepting user's email matches the invite
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")

        if user.email.lower() != invite.email.lower():
            raise HTTPException(
                status_code=403,
                detail="This invite was sent to a different email address.",
            )

        # Check not already a member
        if await self.repo.is_member(invite.organization_id, user_id):
            await self.repo.update_invite_status(invite, "accepted")
            await self.db.commit()
            raise HTTPException(
                status_code=409,
                detail="You are already a member of this organization.",
            )

        # Add member
        await self.repo.add_member(invite.organization_id, user_id, role="member")
        await self.repo.update_invite_status(invite, "accepted")
        await self.db.commit()

        # Re-embed org — new member's skills now part of the aggregate
        from app.tasks.org_embedding_task import generate_org_embedding
        generate_org_embedding.delay(invite.organization_id)

        return {
            "message": f"Successfully joined {invite.organization.display_name}.",
            "organization_id": invite.organization_id,
            "organization_name": invite.organization.display_name,
        }

    async def cancel_invite(self, org_id: str, owner_id: str, invite_id: str) -> None:
        if not await self.repo.is_owner(org_id, owner_id):
            raise HTTPException(status_code=403, detail="Only the organization owner can cancel invites.")

        invite = await self.repo.get_invite_by_id(invite_id, org_id)
        if not invite:
            raise HTTPException(status_code=404, detail="Invite not found.")

        if invite.status != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel an invite with status '{invite.status}'.",
            )

        await self.repo.update_invite_status(invite, "cancelled")
        await self.db.commit()

    async def list_invites(self, org_id: str, owner_id: str) -> list[dict]:
        if not await self.repo.is_owner(org_id, owner_id):
            raise HTTPException(status_code=403, detail="Only the organization owner can view invites.")

        invites = await self.repo.list_invites(org_id)
        return [
            {
                "id": i.id,
                "organization_id": i.organization_id,
                "email": i.email,
                "status": i.status,
                "expires_at": i.expires_at,
                "created_at": i.created_at,
            }
            for i in invites
        ]

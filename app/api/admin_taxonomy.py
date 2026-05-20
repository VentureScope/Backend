"""
Admin Taxonomy endpoints — Phase 2 (Backend repo).

Routes (all under /api/admin, mounted in main.py):

  GET   /taxonomy/unmatched            List unmatched_roles (Supabase)
  PATCH /taxonomy/unmatched/{id}       Accept or decline an unmatched role
  GET   /taxonomy/roles                List canonical taxonomy_roles (local DB)
"""

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin_user
from app.core.database import get_db
from app.models.taxonomy_role import TaxonomyRole
from app.models.user import User
from app.services.supabase_service import SupabaseService, get_supabase_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class UnmatchedRolePatch(BaseModel):
    status: str = Field(
        ...,
        pattern=r"^(accepted|declined)$",
        description="New status: 'accepted' or 'declined'",
    )


# ---------------------------------------------------------------------------
# Unmatched roles
# ---------------------------------------------------------------------------


@router.get("/taxonomy/unmatched")
async def list_unmatched_roles(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    status: str | None = Query(None, description="Filter by status: pending | accepted | declined"),
    sort_by: str = Query("occurrences", description="Sort column: occurrences | first_seen_at | cleaned_title"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """
    List unmatched job title roles from Supabase, sorted and paginated.
    """
    svc: SupabaseService = get_supabase_service()
    try:
        return await svc.list_unmatched_roles(
            status=status, sort_by=sort_by, page=page, per_page=per_page
        )
    except Exception as exc:
        logger.error("list_unmatched_roles error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))


@router.patch("/taxonomy/unmatched/{role_id}")
async def patch_unmatched_role(
    role_id: int,
    data: UnmatchedRolePatch,
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """
    Accept or decline an unmatched role.

    On **accept**:
    - Updates status in Supabase unmatched_roles table
    - Creates a TaxonomyRole row in the local Backend DB so
      title_normalization.py can read it at runtime

    On **decline**:
    - Updates status in Supabase only (no local DB entry)
    """
    svc = get_supabase_service()

    # Fetch the current row to validate it exists and get title info
    try:
        role = await svc.get_unmatched_role(role_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    if not role:
        raise HTTPException(status_code=404, detail="Unmatched role not found")

    if role.get("status") != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Role is already '{role['status']}' — only pending roles can be updated",
        )

    # Update status in Supabase
    try:
        updated = await svc.patch_unmatched_role_status(role_id, data.status)
    except Exception as exc:
        logger.error("patch_unmatched_role_status error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))

    if not updated:
        raise HTTPException(status_code=502, detail="Failed to update status in Supabase")

    # On accept → write to local taxonomy_roles table
    if data.status == "accepted":
        cleaned_title: str = role.get("cleaned_title", "").strip()
        normalized_title = cleaned_title.lower()

        # Upsert — skip if the normalized_title already exists
        existing = await db.execute(
            select(TaxonomyRole).where(
                TaxonomyRole.normalized_title == normalized_title
            )
        )
        if existing.scalar_one_or_none() is None:
            taxonomy_role = TaxonomyRole(
                id=str(uuid.uuid4()),
                title=cleaned_title,
                normalized_title=normalized_title,
                source_unmatched_id=str(role_id),
                accepted_by=current_admin.email,
            )
            db.add(taxonomy_role)
            await db.commit()
            logger.info(
                "Admin %s accepted taxonomy role: '%s'",
                current_admin.email,
                normalized_title,
            )

    return {
        "id": role_id,
        "status": data.status,
        "cleaned_title": role.get("cleaned_title"),
        "accepted_by": current_admin.email if data.status == "accepted" else None,
    }


# ---------------------------------------------------------------------------
# Canonical taxonomy roles (local DB)
# ---------------------------------------------------------------------------


@router.get("/taxonomy/roles")
async def list_taxonomy_roles(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    """
    List all canonical roles from the local taxonomy_roles table.
    These are roles that have been accepted by an admin and are used
    by title_normalization.py at runtime.
    """
    from sqlalchemy import func, select

    # Total count
    count_result = await db.execute(select(func.count()).select_from(TaxonomyRole))
    total = count_result.scalar_one()

    # Paginated rows
    offset = (page - 1) * per_page
    rows_result = await db.execute(
        select(TaxonomyRole)
        .order_by(TaxonomyRole.normalized_title)
        .offset(offset)
        .limit(per_page)
    )
    roles = rows_result.scalars().all()

    return {
        "items": [
            {
                "id": r.id,
                "title": r.title,
                "normalized_title": r.normalized_title,
                "category": r.category,
                "accepted_by": r.accepted_by,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in roles
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }

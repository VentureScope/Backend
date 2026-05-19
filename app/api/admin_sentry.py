"""
Admin Sentry endpoints — Phase 2 (Backend repo).

Routes (under /api/admin, mounted in main.py):

  GET  /sentry/summary       Proxy Sentry API — 5-min cached summary (is_admin)
  POST /sentry-webhook       Receive Sentry alert webhooks (HMAC only, no is_admin)

Rate limiting on the webhook endpoint uses the same custom in-process
RateLimiter already present in app/core/rate_limit.py.
"""

import hashlib
import hmac
import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin_user
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import RateLimiter
from app.models.admin_notification import AdminNotification
from app.models.user import User
from app.services.sentry_service import SentryServiceError, get_sentry_service

logger = logging.getLogger(__name__)

router = APIRouter()

# 60 requests / minute per source IP for the public webhook endpoint
# Key: remote address (string), Window: 60 s
_webhook_limiter = RateLimiter(max_requests=60, window_seconds=60)


# ---------------------------------------------------------------------------
# HMAC helpers
# ---------------------------------------------------------------------------


def _verify_sentry_hmac(body: bytes, sentry_hook_signature: str | None) -> None:
    """
    Verify Sentry's HMAC-SHA256 webhook signature.
    Header format: sentry-hook-signature: sha256=<hex digest>
    """
    secret = settings.SENTRY_WEBHOOK_SECRET
    if not secret:
        logger.warning("SENTRY_WEBHOOK_SECRET not set — skipping webhook HMAC verification")
        return

    if not sentry_hook_signature:
        raise HTTPException(
            status_code=401, detail="Missing sentry-hook-signature header"
        )

    expected = "sha256=" + hmac.new(
        secret.encode(), body, digestmod=hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, sentry_hook_signature):
        raise HTTPException(
            status_code=401, detail="Invalid Sentry webhook signature"
        )


# ---------------------------------------------------------------------------
# GET /sentry/summary
# ---------------------------------------------------------------------------


@router.get("/sentry/summary")
async def get_sentry_summary(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
) -> dict[str, Any]:
    """
    Proxy the Sentry API and return a summary for the admin dashboard.

    Results are cached for 5 minutes server-side.

    Response includes:
      - unresolved_24h
      - trend_delta
      - top_issues (list)
      - p95_latency_ms
      - apdex
      - seven_day_sparkline
      - deep-links to sentry.io
    """
    sentry = get_sentry_service()
    try:
        return await sentry.get_summary()
    except SentryServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    except Exception as exc:
        logger.error("get_sentry_summary error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))


# ---------------------------------------------------------------------------
# POST /sentry-webhook
# ---------------------------------------------------------------------------


@router.post("/sentry-webhook", status_code=201)
async def receive_sentry_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    sentry_hook_signature: Annotated[str | None, Header(alias="sentry-hook-signature")] = None,
) -> dict[str, Any]:
    """
    Receive Sentry alert webhook notifications.

    Security:
      - HMAC-SHA256 verified via sentry-hook-signature header
      - Rate limited to 60 requests/minute per IP (in-process)
      - No is_admin guard (Sentry calls this directly)

    Stored to admin_notifications with source='sentry'.
    """
    # Rate limit by remote IP
    client_ip = request.client.host if request.client else "unknown"
    _webhook_limiter.check_rate_limit(client_ip)

    body_bytes = await request.body()
    _verify_sentry_hmac(body_bytes, sentry_hook_signature)

    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Sentry webhook envelope: action + data.issue
    action: str = payload.get("action", "triggered")
    issue: dict = payload.get("data", {}).get("issue", {})

    event_type = f"sentry_{action}"
    title = issue.get("title", "Sentry alert")
    culprit = issue.get("culprit", "")
    level = issue.get("level", "error")
    times_seen = issue.get("count", 0)
    last_seen = issue.get("lastSeen", "")
    permalink = issue.get("permalink", "")

    body_text = (
        f"[{level.upper()}] {culprit or title} — "
        f"seen {times_seen} time(s), last at {last_seen}"
    )

    metadata = {
        "sentry_issue_id": issue.get("id"),
        "level": level,
        "culprit": culprit,
        "times_seen": times_seen,
        "last_seen": last_seen,
        "permalink": permalink,
        "action": action,
    }

    notification = AdminNotification(
        id=str(uuid.uuid4()),
        source="sentry",
        event_type=event_type,
        title=title,
        body=body_text,
        is_read=False,
        metadata_=metadata,
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)

    # Invalidate Sentry summary cache so next load reflects new data
    get_sentry_service().invalidate_cache()

    logger.info(
        "Sentry webhook stored: action=%s, issue=%s, level=%s",
        action,
        issue.get("id"),
        level,
    )
    return {"id": notification.id, "status": "stored"}

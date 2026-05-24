"""
Admin ML endpoints — Phase 2 (Backend repo).

Routes (all under /api/admin, mounted in main.py):

  GET  /ml/runs                   List ml_training_runs (Supabase)
  GET  /ml/runs/{run_id}          Single training run
  POST /ml/deploy/{run_id}        Deploy a model (Supabase + DO Spaces)
  POST /ml/trigger                Trigger monthly_training_pipeline via Airflow
  POST /notifications             Receive HMAC-signed pipeline webhook from CareerCompass
"""

import asyncio
import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin_user
from app.core.config import settings
from app.core.database import get_db
from app.models.admin_notification import AdminNotification
from app.models.user import User
from app.services.airflow_service import AirflowServiceError, get_airflow_service
from app.services.spaces_service import get_spaces_client
from app.services.supabase_service import SupabaseService, get_supabase_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _verify_pipeline_hmac(body: bytes, signature_header: str | None) -> None:
    """Raise 401 if the X-Pipeline-Signature HMAC-SHA256 doesn't match."""
    secret = settings.PIPELINE_WEBHOOK_SECRET
    if not secret:
        if settings.ENVIRONMENT == "production":
            raise HTTPException(
                status_code=500,
                detail="PIPELINE_WEBHOOK_SECRET is not configured on this server",
            )
        logger.warning("PIPELINE_WEBHOOK_SECRET not set — skipping HMAC verification (dev only)")
        return

    if not signature_header:
        raise HTTPException(status_code=401, detail="Missing X-Pipeline-Signature header")

    expected = "sha256=" + hmac.new(
        secret.encode(), body, digestmod=hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status_code=401, detail="Invalid pipeline webhook signature")


def _push_model_to_production_sync(staging_key: str) -> str:
    """
    Copy a model file from models/staging/ → models/production/ in DO Spaces.
    Returns the production key. Runs synchronously — call via asyncio.to_thread().
    """
    production_key = staging_key.replace("models/staging/", "models/production/", 1)
    client = get_spaces_client()
    try:
        client.copy_object(
            Bucket=settings.DO_SPACES_BUCKET,
            CopySource={"Bucket": settings.DO_SPACES_BUCKET, "Key": staging_key},
            Key=production_key,
        )
    except ClientError as exc:
        logger.error("DO Spaces copy failed: %s", exc)
        raise RuntimeError(f"Failed to copy model to production in DO Spaces: {exc.response['Error']['Code']}")
    return production_key


# ---------------------------------------------------------------------------
# ML run list
# ---------------------------------------------------------------------------


@router.get("/ml/runs")
async def list_ml_runs(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    status: str | None = Query(None, description="Filter by status, e.g. 'awaiting_review'"),
    model_type: str | None = Query(None, description="Filter by model_type, e.g. 'prophet'"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """
    List ML training runs from Supabase, paginated and filterable.

    Statuses: training | awaiting_review | deployed | superseded | failed
    """
    svc: SupabaseService = get_supabase_service()
    try:
        return await svc.list_ml_training_runs(
            status=status, model_type=model_type, page=page, per_page=per_page
        )
    except Exception as exc:
        logger.error("list_ml_runs error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/ml/runs/{run_id}")
async def get_ml_run(
    run_id: str,
    current_admin: Annotated[User, Depends(get_current_admin_user)],
) -> dict[str, Any]:
    """Return a single ML training run with full metrics."""
    svc = get_supabase_service()
    try:
        run = await svc.get_ml_training_run(run_id)
    except Exception as exc:
        logger.error("get_ml_run error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))

    if not run:
        raise HTTPException(status_code=404, detail="Training run not found")
    return run


# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------


@router.post("/ml/deploy/{run_id}", status_code=200)
async def deploy_ml_run(
    run_id: str,
    current_admin: Annotated[User, Depends(get_current_admin_user)],
) -> dict[str, Any]:
    """
    Deploy a training run:
    1. Validate run exists and is in 'awaiting_review' status
    2. Copy model from models/staging/ → models/production/ in DO Spaces
    3. Set status='deployed', deployed_at, deployed_by on the run
    4. Supersede all other deployed runs for the same model_type
    """
    svc = get_supabase_service()

    try:
        run = await svc.get_ml_training_run(run_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    if not run:
        raise HTTPException(status_code=404, detail="Training run not found")

    if run.get("status") != "awaiting_review":
        raise HTTPException(
            status_code=400,
            detail=f"Run is in status '{run['status']}' — only awaiting_review runs can be deployed.",
        )

    # Push model file to production in DO Spaces
    staging_key = run.get("staging_pkl_key", "")
    if not staging_key:
        raise HTTPException(
            status_code=400,
            detail="This training run has no staging artifact (staging_pkl_key is empty) — cannot deploy.",
        )
    if not settings.DO_SPACES_BUCKET or not settings.DO_SPACES_ENDPOINT:
        raise HTTPException(status_code=503, detail="DO Spaces is not configured on this server.")
    try:
        await asyncio.to_thread(_push_model_to_production_sync, staging_key)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    admin_email = current_admin.email

    try:
        await svc.update_ml_training_run_status(
            run_id,
            status="deployed",
            deployed_at=now,
            deployed_by=admin_email,
        )
        model_type = run.get("model_type", "")
        if model_type:
            await svc.supersede_other_runs(run_id, model_type)
    except Exception as exc:
        logger.error("deploy_ml_run status update error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))

    # Check if the other model type is also deployed — warn if not
    # (ensemble view only averages when both prophet + lstm are deployed)
    # Only meaningful for the two known ensemble model types.
    warning = None
    if model_type in ("prophet", "lstm"):
        other_model = "lstm" if model_type == "prophet" else "prophet"
        try:
            pool = await svc._get_pool_direct()
            other_deployed = await pool.fetchval(
                "SELECT COUNT(*) FROM ml_training_runs WHERE model_type = $1 AND status = 'deployed'",
                other_model,
            )
        except Exception:
            other_deployed = None

        if other_deployed is not None and other_deployed == 0:
            warning = (
                f"Only '{model_type}' is deployed. "
                f"Deploy a '{other_model}' run too so the ensemble averages both models. "
                f"Until then, /api/jobs/forecasts serves {model_type} predictions only."
            )

    logger.info("Admin %s deployed run %s (model_type=%s)", admin_email, run_id, model_type)
    response = {
        "message": "Model deployed successfully",
        "run_id": run_id,
        "deployed_by": admin_email,
        "deployed_at": now_iso,
    }
    if warning:
        response["warning"] = warning
    return response


# ---------------------------------------------------------------------------
# Trigger training
# ---------------------------------------------------------------------------


@router.post("/ml/trigger", status_code=202)
async def trigger_training(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
) -> dict[str, Any]:
    """
    Trigger the monthly_training_pipeline DAG via the Airflow REST API.
    Returns the new dag_run object.
    """
    airflow = get_airflow_service()
    try:
        dag_run = await airflow.trigger_training_pipeline(
            triggered_by=current_admin.email
        )
    except AirflowServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    except Exception as exc:
        logger.error("trigger_training error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))

    return {
        "message": "Training pipeline triggered",
        "dag_run": dag_run,
        "triggered_by": current_admin.email,
    }


# ---------------------------------------------------------------------------
# Pipeline notification webhook (CareerCompass → Backend)
# ---------------------------------------------------------------------------


@router.post("/notifications", status_code=201)
async def receive_pipeline_notification(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_pipeline_signature: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """
    Receive an HMAC-signed notification from the CareerCompass pipeline.

    No is_admin guard — the endpoint is authenticated via HMAC-SHA256
    using PIPELINE_WEBHOOK_SECRET.

    Expected JSON body:
    {
      "event_type": "training_complete",
      "title": "Prophet model trained",
      "body": "Accuracy: 0.92 — awaiting review",
      "metadata": { "run_id": "...", "model_type": "prophet", ... }
    }
    """
    body_bytes = await request.body()
    _verify_pipeline_hmac(body_bytes, x_pipeline_signature)

    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type = str(payload.get("event_type", "pipeline_event"))[:100]
    title = str(payload.get("title", "Pipeline notification"))[:255]
    body_text = str(payload.get("body", ""))[:10_000]
    metadata = payload.get("metadata")

    notification = AdminNotification(
        id=str(uuid.uuid4()),
        source="pipeline",
        event_type=event_type,
        title=title,
        body=body_text,
        is_read=False,
        metadata_=metadata,
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)

    logger.info("Pipeline notification stored: event_type=%s", event_type)
    return {"id": notification.id, "status": "stored"}


# ---------------------------------------------------------------------------
# Notification feed (read + mark-as-read)
# ---------------------------------------------------------------------------


@router.get("/notifications-feed")
async def list_admin_notifications(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    source: str | None = Query(None, description="Filter by source: pipeline | sentry"),
    unread_only: bool = Query(False, description="Return only unread notifications"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """
    List stored admin notifications (pipeline alerts + Sentry webhooks),
    newest first. Supports filtering by source and read status.
    """
    from sqlalchemy import func, select

    stmt = select(AdminNotification)
    if source:
        stmt = stmt.where(AdminNotification.source == source)
    if unread_only:
        stmt = stmt.where(AdminNotification.is_read.is_(False))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    offset = (page - 1) * per_page
    rows = (
        await db.execute(
            stmt.order_by(desc(AdminNotification.created_at)).offset(offset).limit(per_page)
        )
    ).scalars().all()

    return {
        "items": [
            {
                "id": n.id,
                "source": n.source,
                "event_type": n.event_type,
                "title": n.title,
                "body": n.body,
                "is_read": n.is_read,
                "metadata": n.metadata_,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in rows
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "unread_count": sum(1 for n in rows if not n.is_read),
    }


@router.patch("/notifications-feed/{notification_id}/read", status_code=200)
async def mark_notification_read(
    notification_id: str,
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Mark a single notification as read."""
    result = await db.execute(
        select(AdminNotification).where(AdminNotification.id == notification_id)
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.is_read = True
    await db.commit()
    return {"id": notification_id, "is_read": True}


@router.patch("/notifications-feed/mark-all-read", status_code=200)
async def mark_all_notifications_read(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    source: str | None = Query(None, description="Only mark this source as read: pipeline | sentry"),
) -> dict[str, Any]:
    """Mark all (or all from a given source) notifications as read."""
    from sqlalchemy import update

    stmt = (
        update(AdminNotification)
        .where(AdminNotification.is_read.is_(False))
        .values(is_read=True)
    )
    if source:
        stmt = stmt.where(AdminNotification.source == source)

    result = await db.execute(stmt)
    await db.commit()
    return {"marked_read": result.rowcount}

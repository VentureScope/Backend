"""
Admin ML endpoints — Phase 2 (Backend repo).

Routes (all under /api/admin, mounted in main.py):

  GET  /ml/runs                   List ml_training_runs (Supabase)
  GET  /ml/runs/{run_id}          Single training run
  POST /ml/deploy/{run_id}        Deploy a model (Supabase + DO Spaces)
  POST /ml/trigger                Trigger monthly_training_pipeline via Airflow
  POST /notifications             Receive HMAC-signed pipeline webhook from CareerCompass
"""

import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin_user
from app.core.config import settings
from app.core.database import get_db
from app.models.admin_notification import AdminNotification
from app.models.user import User
from app.services.airflow_service import AirflowServiceError, get_airflow_service
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
        # If no secret is configured, skip verification (dev mode)
        logger.warning("PIPELINE_WEBHOOK_SECRET not set — skipping HMAC verification")
        return

    if not signature_header:
        raise HTTPException(status_code=401, detail="Missing X-Pipeline-Signature header")

    expected = "sha256=" + hmac.new(
        secret.encode(), body, digestmod=hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status_code=401, detail="Invalid pipeline webhook signature")


def _get_spaces_client():
    """Return a boto3 S3 client pointed at DO Spaces."""
    return boto3.client(
        "s3",
        region_name=settings.DO_SPACES_REGION,
        endpoint_url=settings.DO_SPACES_ENDPOINT,
        aws_access_key_id=settings.DO_SPACES_KEY,
        aws_secret_access_key=settings.DO_SPACES_SECRET,
    )


def _push_model_to_production(staging_key: str) -> str:
    """
    Copy a model file from models/staging/ → models/production/ in DO Spaces.
    Returns the production key.
    """
    if not staging_key or not settings.DO_SPACES_BUCKET:
        raise HTTPException(
            status_code=503,
            detail="DO Spaces is not configured or staging_pkl_key is missing.",
        )

    production_key = staging_key.replace("models/staging/", "models/production/", 1)
    client = _get_spaces_client()
    try:
        client.copy_object(
            Bucket=settings.DO_SPACES_BUCKET,
            CopySource={"Bucket": settings.DO_SPACES_BUCKET, "Key": staging_key},
            Key=production_key,
        )
    except ClientError as exc:
        logger.error("DO Spaces copy failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to copy model to production in DO Spaces: {exc}",
        )
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

    if run.get("status") not in ("awaiting_review", "training"):
        raise HTTPException(
            status_code=400,
            detail=f"Run is in status '{run['status']}' — only awaiting_review runs can be deployed.",
        )

    # Push model file to production in DO Spaces
    staging_key = run.get("staging_pkl_key", "")
    if staging_key:
        _push_model_to_production(staging_key)

    now_iso = datetime.now(timezone.utc).isoformat()
    admin_email = current_admin.email

    try:
        await svc.update_ml_training_run_status(
            run_id,
            status="deployed",
            deployed_at=now_iso,
            deployed_by=admin_email,
        )
        model_type = run.get("model_type", "")
        if model_type:
            await svc.supersede_other_runs(run_id, model_type)
    except Exception as exc:
        logger.error("deploy_ml_run status update error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))

    logger.info("Admin %s deployed run %s (model_type=%s)", admin_email, run_id, model_type)
    return {
        "message": "Model deployed successfully",
        "run_id": run_id,
        "deployed_by": admin_email,
        "deployed_at": now_iso,
    }


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

    event_type = payload.get("event_type", "pipeline_event")
    title = payload.get("title", "Pipeline notification")
    body_text = payload.get("body", "")
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

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


def _deploy_to_production_sync(staging_key: str) -> str:
    """
    Promote a model's staging artifacts to production in DO Spaces.

    Production layout (one YYYY-MM folder, always exactly 3 files):
        models/production/YYYY-MM/forecasts_prophet.csv
        models/production/YYYY-MM/forecasts_lstm.csv
        models/production/YYYY-MM/metrics.json

    Steps:
    1. Wipe ALL of models/production/ — only one run should ever be in production.
    2. Copy forecast CSV to models/production/YYYY-MM/forecasts_{model_type}.csv.
    3. Copy shared metrics.json to models/production/YYYY-MM/metrics.json
       (idempotent — both prophet and lstm deploy tasks do this; last-write wins).

    Returns the production forecast CSV key.
    Runs synchronously — call via asyncio.to_thread().
    """
    client = get_spaces_client()
    bucket = settings.DO_SPACES_BUCKET

    # Extract model_type and run_yearmonth from staging key
    # e.g. "models/staging/2026-05/prophet/forecasts.csv"
    staging_parts = staging_key.split("/")
    model_type    = staging_parts[3] if len(staging_parts) > 3 else None
    run_yearmonth = staging_parts[2] if len(staging_parts) > 2 else None

    # Normalize the source key: legacy rows historically pointed at
    # model artifacts that no longer exist. Always resolve to the canonical
    # forecasts.csv for this model/run regardless of what the DB stored.
    canonical_key = (
        f"models/staging/{run_yearmonth}/{model_type}/forecasts.csv"
        if run_yearmonth and model_type
        else staging_key
    )
    source_key = staging_key
    if not staging_key.endswith("forecasts.csv"):
        source_key = canonical_key

    # ── Pre-flight: verify the source forecast CSV exists BEFORE wiping prod ──
    # This prevents a bad/stale key from emptying production with nothing to
    # put back. Try the stored key, then fall back to the canonical path.
    resolved_key = None
    for candidate in (source_key, canonical_key):
        try:
            client.head_object(Bucket=bucket, Key=candidate)
            resolved_key = candidate
            break
        except ClientError:
            continue
    if not resolved_key:
        raise RuntimeError(
            f"Forecast CSV not found in staging for {model_type} ({run_yearmonth}). "
            f"Tried '{source_key}' and '{canonical_key}'. "
            f"The training run's staging artifacts may have been deleted — "
            f"re-run the training pipeline for this instance."
        )

    production_forecast_key = f"models/production/{run_yearmonth}/forecasts_{model_type}.csv"

    # ── Step 1: Wipe models/production/ entirely so only this run remains ────
    paginator = client.get_paginator("list_objects_v2")
    old_keys = [
        obj["Key"]
        for page in paginator.paginate(Bucket=bucket, Prefix="models/production/")
        for obj in page.get("Contents", [])
    ]
    if old_keys:
        client.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": k} for k in old_keys]},
        )
        logger.info("_deploy_to_production: wiped %d old production files", len(old_keys))

    # ── Step 2: Copy forecast CSV ─────────────────────────────────────────────
    try:
        client.copy_object(
            Bucket=bucket,
            CopySource={"Bucket": bucket, "Key": resolved_key},
            Key=production_forecast_key,
        )
        logger.info("_deploy_to_production: %s -> %s", resolved_key, production_forecast_key)
    except ClientError as exc:
        logger.error("DO Spaces copy failed: %s", exc)
        raise RuntimeError(
            f"Failed to copy forecast CSV to production: {exc.response['Error']['Code']}"
        )

    # ── Step 3: Copy shared metrics.json (idempotent) ────────────────────────
    if run_yearmonth:
        metrics_staging_key = f"models/staging/{run_yearmonth}/metrics.json"
        metrics_prod_key    = f"models/production/{run_yearmonth}/metrics.json"
        try:
            client.copy_object(
                Bucket=bucket,
                CopySource={"Bucket": bucket, "Key": metrics_staging_key},
                Key=metrics_prod_key,
            )
            logger.info("_deploy_to_production: %s -> %s", metrics_staging_key, metrics_prod_key)
        except ClientError:
            logger.warning(
                "_deploy_to_production: no metrics.json at %s (skipped)", metrics_staging_key
            )

    return production_forecast_key


async def _do_deploy(run_id: str, run: dict, admin_email: str, svc: Any) -> dict[str, Any]:
    """
    Shared deploy logic used by both deploy (awaiting_review) and redeploy (superseded).
    Copies staging forecast CSV + metadata to production (wiping old production files first),
    marks run as deployed, supersedes others.
    Returns the response dict (may include a warning key).

    Bundle constraint: both prophet and lstm must come from the same training
    instance (same run_yearmonth). Deploying a model whose partner is already
    deployed from a different run_yearmonth is rejected with 400 — it would
    corrupt the shared metrics.json and produce an incoherent ensemble.
    """
    model_type    = run.get("model_type", "")
    run_yearmonth = run.get("run_yearmonth", "")

    # ── Pre-flight: bundle consistency check (before any writes) ─────────────
    if model_type in ("prophet", "lstm"):
        other_model = "lstm" if model_type == "prophet" else "prophet"
        try:
            pool = await svc._get_pool_direct()
            other_row = await pool.fetchrow(
                "SELECT run_id, run_yearmonth FROM ml_training_runs "
                "WHERE model_type = $1 AND status = 'deployed' LIMIT 1",
                other_model,
            )
        except Exception:
            other_row = None

        if other_row and other_row["run_yearmonth"] and run_yearmonth:
            if other_row["run_yearmonth"] != run_yearmonth:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Bundle mismatch: '{other_model}' is already deployed from training "
                        f"instance '{other_row['run_yearmonth']}', but this '{model_type}' run "
                        f"is from '{run_yearmonth}'. Both models must come from the same "
                        f"training instance to keep the forecast bundle consistent. "
                        f"Redeploy the '{other_model}' from '{run_yearmonth}' first, then "
                        f"redeploy this run — or use the Redeploy action on both together."
                    ),
                )

    staging_key = run.get("staging_forecast_key", "")
    if not staging_key:
        raise HTTPException(
            status_code=400,
            detail="This training run has no staging forecast CSV (staging_forecast_key is empty) — cannot deploy.",
        )
    if not settings.DO_SPACES_BUCKET or not settings.DO_SPACES_ENDPOINT:
        raise HTTPException(status_code=503, detail="DO Spaces is not configured on this server.")
    try:
        await asyncio.to_thread(_deploy_to_production_sync, staging_key)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    now = datetime.now(timezone.utc)
    try:
        await svc.update_ml_training_run_status(
            run_id,
            status="deployed",
            deployed_at=now,
            deployed_by=admin_email,
        )
        if model_type:
            await svc.supersede_other_runs(run_id, model_type)
    except Exception as exc:
        logger.error("_do_deploy status update error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))

    # ── Post-deploy: warn if partner not yet deployed ─────────────────────────
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
                f"Deploy the matching '{other_model}' run from the same training instance "
                f"({run_yearmonth}) so the ensemble averages both models correctly."
            )

    response: dict[str, Any] = {
        "message": "Model deployed successfully",
        "run_id": run_id,
        "deployed_by": admin_email,
        "deployed_at": now.isoformat(),
    }
    if warning:
        response["warning"] = warning
    return response


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
    Deploy a training run that is in 'awaiting_review' status:
    1. Copy forecast CSV from models/staging/ → models/production/ in DO Spaces
    2. Set status='deployed', deployed_at, deployed_by on the run
    3. Supersede all other deployed runs for the same model_type
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
            detail=f"Run is in status '{run['status']}' — only awaiting_review runs can be deployed. Use /redeploy for superseded runs.",
        )

    logger.info("Admin %s deploying run %s (model_type=%s)", current_admin.email, run_id, run.get("model_type"))
    return await _do_deploy(run_id, run, current_admin.email, svc)


@router.post("/ml/redeploy/{run_id}", status_code=200)
async def redeploy_ml_run(
    run_id: str,
    current_admin: Annotated[User, Depends(get_current_admin_user)],
) -> dict[str, Any]:
    """
    Redeploy a previously superseded training run.
    Useful for rolling back to an older model or reactivating a run that was
    superseded by a newer one that turned out to be worse.

    Same mechanics as deploy but accepts 'superseded' status instead of
    'awaiting_review'. The previously deployed run for the same model_type
    will be superseded.
    """
    svc = get_supabase_service()
    try:
        run = await svc.get_ml_training_run(run_id)
    except Exception as exc:
        logger.error("redeploy_ml_run fetch error: %s", exc)
        raise HTTPException(status_code=502, detail=f"Could not fetch training run: {exc}")

    if not run:
        raise HTTPException(status_code=404, detail="Training run not found")
    if run.get("status") != "superseded":
        raise HTTPException(
            status_code=400,
            detail=f"Run is in status '{run['status']}' — only superseded runs can be redeployed. Use /deploy for awaiting_review runs.",
        )

    logger.info("Admin %s redeploying superseded run %s (model_type=%s)", current_admin.email, run_id, run.get("model_type"))
    result = await _do_deploy(run_id, run, current_admin.email, svc)
    result["message"] = "Model redeployed successfully"
    return result


@router.post("/ml/deploy-bundle/{run_yearmonth}", status_code=200)
async def deploy_bundle(
    run_yearmonth: str,
    current_admin: Annotated[User, Depends(get_current_admin_user)],
) -> dict[str, Any]:
    """
    Deploy BOTH models (prophet + lstm) from a single training instance together.

    This is the correct way to deploy — both models share one metrics.json and
    feed a single ensemble, so they must always be deployed as a unit from the
    same run_yearmonth.

    Accepts runs in either 'awaiting_review' or 'superseded' status.
    Deploys each model in turn (bypassing the per-model bundle mismatch guard,
    since deploying the whole bundle is what keeps them consistent).
    """
    svc = get_supabase_service()

    # Fetch both runs for this training instance
    try:
        pool = await svc._get_pool_direct()
        rows = await pool.fetch(
            "SELECT run_id, model_type, status FROM ml_training_runs "
            "WHERE run_yearmonth = $1 AND model_type IN ('prophet', 'lstm') "
            "AND status IN ('awaiting_review', 'superseded', 'deployed')",
            run_yearmonth,
        )
    except Exception as exc:
        logger.error("deploy_bundle fetch error: %s", exc)
        raise HTTPException(status_code=502, detail=f"Could not fetch training runs: {exc}")

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No deployable runs found for training instance '{run_yearmonth}'.",
        )

    # Only act on runs that are not already deployed
    to_deploy = [dict(r) for r in rows if r["status"] in ("awaiting_review", "superseded")]
    if not to_deploy:
        return {
            "message": f"Bundle '{run_yearmonth}' is already fully deployed.",
            "run_yearmonth": run_yearmonth,
            "deployed_runs": [],
        }

    deployed_runs: list[str] = []
    now = datetime.now(timezone.utc)
    admin_email = current_admin.email

    for r in to_deploy:
        run_id     = r["run_id"]
        model_type = r["model_type"]
        full_run   = await svc.get_ml_training_run(run_id)
        if not full_run:
            continue

        staging_key = full_run.get("staging_forecast_key", "")
        if not staging_key:
            raise HTTPException(
                status_code=400,
                detail=f"Run '{run_id}' has no staging forecast CSV — cannot deploy bundle.",
            )

        # Copy artifacts to production (skips the per-model mismatch guard)
        try:
            await asyncio.to_thread(_deploy_to_production_sync, staging_key)
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

        # Update DB status + supersede the previous run of this model_type
        try:
            await svc.update_ml_training_run_status(
                run_id, status="deployed", deployed_at=now, deployed_by=admin_email,
            )
            await svc.supersede_other_runs(run_id, model_type)
        except Exception as exc:
            logger.error("deploy_bundle status update error: %s", exc)
            raise HTTPException(status_code=502, detail=str(exc))

        deployed_runs.append(run_id)

    logger.info(
        "Admin %s deployed bundle %s (%d models)", admin_email, run_yearmonth, len(deployed_runs)
    )
    return {
        "message": f"Deployed bundle '{run_yearmonth}' ({len(deployed_runs)} models)",
        "run_yearmonth": run_yearmonth,
        "deployed_by": admin_email,
        "deployed_at": now.isoformat(),
        "deployed_runs": deployed_runs,
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

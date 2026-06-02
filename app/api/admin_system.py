"""
Admin System endpoints — Phase 2 (Backend repo).

Routes (all under /api/admin, mounted in main.py):

  GET /system/pipeline-status    Last run state for ETL + training DAGs
  GET /system/pipeline-runs      ETL run history (7 days) + task durations
  GET /system/storage            DO Spaces model file listing + total size
"""

import asyncio
import logging
from typing import Annotated, Any

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_admin_user
from app.core.config import settings
from app.models.user import User
from app.services.airflow_service import AirflowServiceError, get_airflow_service
from app.services.spaces_service import get_spaces_client

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pipeline status
# ---------------------------------------------------------------------------


@router.get("/system/pipeline-status")
async def get_pipeline_status(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
) -> dict[str, Any]:
    """
    Return the last run state for both the ETL and training DAGs.

    Response shape:
    {
      "etl":      { dag_run fields … },
      "training": { dag_run fields … }
    }
    """
    airflow = get_airflow_service()
    try:
        return await airflow.get_pipeline_status()
    except AirflowServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    except Exception as exc:
        logger.error("get_pipeline_status error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))


# ---------------------------------------------------------------------------
# Pipeline run history
# ---------------------------------------------------------------------------


@router.get("/system/pipeline-runs")
async def get_pipeline_runs(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
    days: int = Query(7, ge=1, le=90, description="Number of days of history (1–90)"),
) -> dict[str, Any]:
    """
    Return ETL dag_run history for the last N days plus task durations
    for the most recent run.

    Consumed by Recharts on the /admin/pipeline frontend page.
    """
    airflow = get_airflow_service()
    try:
        return await airflow.get_etl_run_history(days=days)
    except AirflowServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    except Exception as exc:
        logger.error("get_pipeline_runs error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))


# ---------------------------------------------------------------------------
# Storage health (DO Spaces)
# ---------------------------------------------------------------------------


@router.get("/system/storage")
async def get_storage_health(
    current_admin: Annotated[User, Depends(get_current_admin_user)],
) -> dict[str, Any]:
    """
    Return DO Spaces model storage health:
    - staging model files
    - production model files
    - total size in bytes
    - last modified timestamp

    Requires DO_SPACES_BUCKET and DO_SPACES_ENDPOINT to be configured.
    """
    if not settings.DO_SPACES_BUCKET or not settings.DO_SPACES_ENDPOINT:
        raise HTTPException(
            status_code=503,
            detail="DO Spaces is not configured (DO_SPACES_BUCKET / DO_SPACES_ENDPOINT missing)",
        )

    client = get_spaces_client()
    bucket = settings.DO_SPACES_BUCKET

    def _list_prefix(prefix: str) -> list[dict[str, Any]]:
        try:
            paginator = client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
            files: list[dict] = []
            for page in pages:
                for obj in page.get("Contents", []):
                    files.append(
                        {
                            "key": obj["Key"],
                            "size_bytes": obj["Size"],
                            "last_modified": obj["LastModified"].isoformat(),
                        }
                    )
            return files
        except ClientError as exc:
            logger.error("DO Spaces list error (prefix=%s): %s", prefix, exc)
            return []

    staging_files, production_files = await asyncio.gather(
        asyncio.to_thread(_list_prefix, "models/staging/"),
        asyncio.to_thread(_list_prefix, "models/production/"),
    )

    def _count_runs(files: list[dict], prefix: str) -> int:
        """Count unique YYYY-MM run folders under a prefix.
        e.g. models/staging/2026-05/lstm/forecasts.csv → '2026-05'
        """
        folders = set()
        for f in files:
            # strip prefix, take the first path segment = YYYY-MM
            relative = f["key"][len(prefix):]
            segment = relative.split("/")[0]
            if segment:
                folders.add(segment)
        return len(folders)

    all_files = staging_files + production_files
    total_bytes = sum(f["size_bytes"] for f in all_files)
    last_modified = max(
        (f["last_modified"] for f in all_files), default=None
    )

    return {
        "bucket": bucket,
        "staging": {
            "count": len(staging_files),
            "runs": _count_runs(staging_files, "models/staging/"),
            "files": staging_files,
        },
        "production": {
            "count": len(production_files),
            "runs": _count_runs(production_files, "models/production/"),
            "files": production_files,
        },
        "total_size_bytes": total_bytes,
        "last_modified": last_modified,
    }

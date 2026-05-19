"""
AirflowService — wrapper around the Airflow REST API v1.

Uses a dedicated service account (AIRFLOW_SERVICE_ACCOUNT_USER /
AIRFLOW_SERVICE_ACCOUNT_PASSWORD) so we never expose the Airflow
admin credentials to the general backend.

All methods are async (httpx AsyncClient).
"""

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# DAG IDs used in the platform
ETL_DAG_ID = "job_data_pipeline"
TRAINING_DAG_ID = "monthly_training_pipeline"


class AirflowServiceError(Exception):
    """Raised when the Airflow API returns an unexpected response."""

    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code


class AirflowService:
    """
    Thin async client for the Airflow REST API.

    Raises AirflowServiceError on HTTP errors so callers can map them
    to appropriate HTTP responses.
    """

    def __init__(self) -> None:
        self._base_url = settings.AIRFLOW_API_URL.rstrip("/")
        self._auth = (
            settings.AIRFLOW_SERVICE_ACCOUNT_USER,
            settings.AIRFLOW_SERVICE_ACCOUNT_PASSWORD,
        )

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            auth=self._auth,
            timeout=15,
            headers={"Content-Type": "application/json"},
        )

    def _require_config(self) -> None:
        if not self._base_url or not self._auth[0]:
            raise AirflowServiceError(
                "Airflow API is not configured. "
                "Set AIRFLOW_API_URL, AIRFLOW_SERVICE_ACCOUNT_USER, "
                "and AIRFLOW_SERVICE_ACCOUNT_PASSWORD.",
                status_code=503,
            )

    # ------------------------------------------------------------------
    # Pipeline status (last run)
    # ------------------------------------------------------------------

    async def get_last_dag_run(self, dag_id: str) -> dict[str, Any]:
        """
        Return the most recent dag_run for the given dag_id.
        Returns dict with keys: dag_id, run_id, state, start_date, end_date, etc.
        """
        self._require_config()
        async with self._client() as client:
            resp = await client.get(
                f"/dags/{dag_id}/dagRuns",
                params={"limit": 1, "order_by": "-start_date"},
            )
            if resp.status_code == 404:
                raise AirflowServiceError(f"DAG '{dag_id}' not found", status_code=404)
            if resp.status_code != 200:
                raise AirflowServiceError(
                    f"Airflow API error {resp.status_code}: {resp.text}",
                    status_code=502,
                )
            data = resp.json()
            runs = data.get("dag_runs", [])
            return runs[0] if runs else {}

    async def get_pipeline_status(self) -> dict[str, Any]:
        """
        Return the last run state for both the ETL and training DAGs.
        Used by GET /api/admin/system/pipeline-status.
        """
        etl = await self.get_last_dag_run(ETL_DAG_ID)
        training = await self.get_last_dag_run(TRAINING_DAG_ID)
        return {
            "etl": etl,
            "training": training,
        }

    # ------------------------------------------------------------------
    # Pipeline run history (7 days) + task durations
    # ------------------------------------------------------------------

    async def get_etl_run_history(self, days: int = 7) -> dict[str, Any]:
        """
        Return dag_run history for the ETL DAG (last N days) plus
        task durations for the most recent run.
        Used by GET /api/admin/system/pipeline-runs.
        """
        self._require_config()
        async with self._client() as client:
            # Dag run history
            history_resp = await client.get(
                f"/dags/{ETL_DAG_ID}/dagRuns",
                params={"limit": days * 3, "order_by": "-start_date"},
            )
            if history_resp.status_code != 200:
                raise AirflowServiceError(
                    f"Airflow history error: {history_resp.status_code}",
                    status_code=502,
                )
            dag_runs = history_resp.json().get("dag_runs", [])

            # Task durations for the latest run
            task_durations: list[dict] = []
            if dag_runs:
                latest_run_id = dag_runs[0]["dag_run_id"]
                tasks_resp = await client.get(
                    f"/dags/{ETL_DAG_ID}/dagRuns/{latest_run_id}/taskInstances",
                )
                if tasks_resp.status_code == 200:
                    task_durations = tasks_resp.json().get("task_instances", [])

            return {
                "dag_id": ETL_DAG_ID,
                "dag_runs": dag_runs,
                "latest_run_task_durations": task_durations,
            }

    # ------------------------------------------------------------------
    # Trigger training
    # ------------------------------------------------------------------

    async def trigger_training_pipeline(
        self, triggered_by: str
    ) -> dict[str, Any]:
        """
        Trigger the monthly_training_pipeline DAG manually.
        Returns the new dag_run object from Airflow.
        """
        self._require_config()
        async with self._client() as client:
            resp = await client.post(
                f"/dags/{TRAINING_DAG_ID}/dagRuns",
                json={"conf": {"triggered_by": triggered_by}},
            )
            if resp.status_code not in (200, 201):
                raise AirflowServiceError(
                    f"Failed to trigger DAG: {resp.status_code} — {resp.text}",
                    status_code=502,
                )
            return resp.json()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_airflow_service: AirflowService | None = None


def get_airflow_service() -> AirflowService:
    global _airflow_service
    if _airflow_service is None:
        _airflow_service = AirflowService()
    return _airflow_service

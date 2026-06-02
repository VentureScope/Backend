"""
SupabaseService — async wrapper for Supabase PostgreSQL queries (CareerCompass data).

Performs both reads (ML runs, taxonomy, overview stats) and writes
(status updates on ml_training_runs and unmatched_roles).

Uses asyncpg directly (no ORM) so it can share the same asyncio loop
as the rest of FastAPI without a second SQLAlchemy engine.

Connection pool is opened lazily and re-used for the lifetime of the
process. Configure via SUPABASE_URL env var:

  SUPABASE_URL=postgresql://<user>:<password>@<host>:5432/postgres
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

import asyncpg

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection pool (lazy init)
# ---------------------------------------------------------------------------

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()


async def _get_pool() -> asyncpg.Pool:
    """Return (or create) the shared asyncpg connection pool."""
    global _pool
    if _pool is not None:
        return _pool

    async with _pool_lock:
        if _pool is not None:
            return _pool

        dsn = settings.SUPABASE_URL
        if not dsn:
            raise RuntimeError(
                "SUPABASE_URL is not configured. "
                "Set it to the Supabase PostgreSQL connection string."
            )

        _pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=1,
            max_size=5,
            command_timeout=15,
            max_inactive_connection_lifetime=60,  # recycle idle connections after 60s
        )
        logger.info("Supabase asyncpg pool created (min=1, max=5)")
        return _pool


async def close_pool() -> None:
    """Gracefully close the pool (call from app lifespan shutdown)."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Supabase asyncpg pool closed")


async def _reset_pool() -> None:
    """Close and reset the pool so the next call recreates it.
    Called when a connection error suggests the pool is in a broken state."""
    global _pool
    if _pool:
        try:
            await _pool.close()
        except Exception:
            logger.exception(
                "Failed to close asyncpg pool during reset; continuing with pool reset"
            )
        _pool = None
        logger.warning("Supabase asyncpg pool reset due to connection error")


# ---------------------------------------------------------------------------
# SupabaseService
# ---------------------------------------------------------------------------


class SupabaseService:
    """
    Read-only query helper for Supabase (CareerCompass) tables.

    All methods are async and return plain dicts / lists of dicts so
    that routers can serialize them directly with FastAPI.
    """

    async def _get_pool_direct(self):
        """Expose pool directly for ad-hoc queries in endpoints."""
        return await _get_pool()

    # ------------------------------------------------------------------
    # ML pipeline
    # ------------------------------------------------------------------

    async def list_ml_training_runs(
        self,
        *,
        status: str | None = None,
        model_type: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict[str, Any]:
        """
        Return paginated rows from ml_training_runs.
        Columns: run_id, dag_id, model_type, status, accuracy, f1_score,
                 auc_roc, record_count, months_covered, class_balance
                 (JSON with class_balance + cv_mae_by_role + cv_rmse_by_role),
                 created_at, deployed_at, deployed_by
        """
        pool = await _get_pool()

        filters: list[str] = []
        params: list[Any] = []

        if status:
            params.append(status)
            filters.append(f"status = ${len(params)}")
        if model_type:
            params.append(model_type)
            filters.append(f"model_type = ${len(params)}")

        where = f"WHERE {' AND '.join(filters)}" if filters else ""

        # Total count
        count_sql = f"SELECT COUNT(*) FROM ml_training_runs {where}"
        total = await pool.fetchval(count_sql, *params)

        # Paginated rows
        offset = (page - 1) * per_page
        params.extend([per_page, offset])
        rows_sql = f"""
            SELECT run_id, dag_id, model_type, run_yearmonth, status,
                   accuracy, f1_score, auc_roc, record_count, months_covered,
                   model_size_bytes, staging_forecast_key, class_balance,
                   created_at, deployed_at, deployed_by,
                   notification_sent_at
            FROM ml_training_runs
            {where}
            ORDER BY created_at DESC
            LIMIT ${len(params) - 1} OFFSET ${len(params)}
        """
        rows = await pool.fetch(rows_sql, *params)
        return {
            "items": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
        }

    async def get_ml_training_run(self, run_id: str) -> dict[str, Any] | None:
        """Return a single ml_training_runs row by run_id.
        Retries once on connection error to handle stale pool connections."""
        for attempt in range(2):
            try:
                pool = await _get_pool()
                row = await pool.fetchrow(
                    "SELECT * FROM ml_training_runs WHERE run_id = $1", run_id
                )
                return dict(row) if row else None
            except (asyncpg.InterfaceError, asyncpg.ConnectionDoesNotExistError, OSError) as exc:
                logger.warning("get_ml_training_run: connection error (attempt %d): %s", attempt + 1, exc)
                await _reset_pool()
                if attempt == 1:
                    raise

    async def update_ml_training_run_status(
        self,
        run_id: str,
        *,
        status: str,
        deployed_at: datetime | None = None,
        deployed_by: str | None = None,
    ) -> None:
        """Update status (and optional deploy fields) on a training run."""
        pool = await _get_pool()
        if deployed_at and deployed_by:
            await pool.execute(
                """
                UPDATE ml_training_runs
                SET status = $1, deployed_at = $2, deployed_by = $3
                WHERE run_id = $4
                """,
                status,
                deployed_at,
                deployed_by,
                run_id,
            )
        else:
            await pool.execute(
                "UPDATE ml_training_runs SET status = $1 WHERE run_id = $2",
                status,
                run_id,
            )

    async def supersede_other_runs(self, run_id: str, model_type: str) -> None:
        """Mark all other deployed runs for the same model_type as superseded."""
        pool = await _get_pool()
        await pool.execute(
            """
            UPDATE ml_training_runs
            SET status = 'superseded'
            WHERE model_type = $1 AND run_id <> $2 AND status = 'deployed'
            """,
            model_type,
            run_id,
        )

    # ------------------------------------------------------------------
    # Taxonomy / unmatched roles
    # ------------------------------------------------------------------

    async def list_unmatched_roles(
        self,
        *,
        status: str | None = None,
        sort_by: str = "occurrences",
        page: int = 1,
        per_page: int = 50,
    ) -> dict[str, Any]:
        """Return paginated rows from unmatched_roles."""
        pool = await _get_pool()

        allowed_sort = {"occurrences", "first_seen_at", "last_seen_at", "cleaned_title"}
        if sort_by not in allowed_sort:
            sort_by = "occurrences"

        filters: list[str] = []
        params: list[Any] = []

        if status:
            params.append(status)
            filters.append(f"status = ${len(params)}")

        where = f"WHERE {' AND '.join(filters)}" if filters else ""

        total = await pool.fetchval(
            f"SELECT COUNT(*) FROM unmatched_roles {where}", *params
        )

        offset = (page - 1) * per_page
        params.extend([per_page, offset])
        rows = await pool.fetch(
            f"""
            SELECT id, raw_title, cleaned_title, confidence, best_match,
                   method_used, source, occurrences, first_seen_at,
                   last_seen_at, status
            FROM unmatched_roles
            {where}
            ORDER BY {sort_by} DESC
            LIMIT ${len(params) - 1} OFFSET ${len(params)}
            """,
            *params,
        )
        return {
            "items": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
        }

    async def get_unmatched_role(self, role_id: int) -> dict[str, Any] | None:
        """Return a single unmatched_roles row by id."""
        pool = await _get_pool()
        row = await pool.fetchrow(
            "SELECT * FROM unmatched_roles WHERE id = $1", role_id
        )
        return dict(row) if row else None

    async def patch_unmatched_role_status(
        self, role_id: int, new_status: str
    ) -> dict[str, Any] | None:
        """Update status to 'accepted' or 'declined'."""
        pool = await _get_pool()
        row = await pool.fetchrow(
            """
            UPDATE unmatched_roles
            SET status = $1
            WHERE id = $2
            RETURNING *
            """,
            new_status,
            role_id,
        )
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Job forecasts (ensemble of Prophet + LSTM predictions)
    # ------------------------------------------------------------------

    async def get_job_forecasts(
        self,
        *,
        normalized_title: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return ensemble forecast rows (averaged across Prophet and LSTM).
        Optionally filter by a specific normalized_title.
        """
        pool = await _get_pool()

        if normalized_title:
            rows = await pool.fetch(
                """
                SELECT normalized_title, forecast_date, predicted_count,
                       lower_bound, upper_bound
                FROM job_forecasts_ensemble
                WHERE normalized_title = $1
                ORDER BY forecast_date
                """,
                normalized_title,
            )
        else:
            rows = await pool.fetch(
                """
                SELECT normalized_title, forecast_date, predicted_count,
                       lower_bound, upper_bound
                FROM job_forecasts_ensemble
                ORDER BY normalized_title, forecast_date
                """
            )

        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Overview / stats (used by frontend summary cards)
    # ------------------------------------------------------------------

    async def get_overview_stats(self) -> dict[str, Any]:
        """
        Returns lightweight counts consumed by the frontend /admin/overview cards.
        """
        pool = await _get_pool()
        ml_pending = await pool.fetchval(
            "SELECT COUNT(*) FROM ml_training_runs WHERE status = 'awaiting_review'"
        )
        tax_pending = await pool.fetchval(
            "SELECT COUNT(*) FROM unmatched_roles WHERE status = 'pending'"
        )
        return {
            "ml_awaiting_review": ml_pending or 0,
            "taxonomy_pending": tax_pending or 0,
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_supabase_service: SupabaseService | None = None


def get_supabase_service() -> SupabaseService:
    global _supabase_service
    if _supabase_service is None:
        _supabase_service = SupabaseService()
    return _supabase_service

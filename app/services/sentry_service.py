"""
SentryService — proxy client for the Sentry REST API.

Auth token (SENTRY_AUTH_TOKEN) is kept server-side and never sent
to the browser.  All data is returned as plain dicts for FastAPI to
serialize.

A 5-minute in-process cache avoids hammering the Sentry API on every
admin page load.
"""

import asyncio
import logging
import time
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SENTRY_API_BASE = "https://sentry.io/api/0"
_CACHE_TTL = 300  # 5 minutes


class SentryServiceError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Simple in-process TTL cache
# ---------------------------------------------------------------------------

class _TTLCache:
    def __init__(self, ttl: int) -> None:
        self._ttl = ttl
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry and time.monotonic() - entry[0] < self._ttl:
            return entry[1]
        return None

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.monotonic(), value)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)


_cache = _TTLCache(ttl=_CACHE_TTL)


# ---------------------------------------------------------------------------
# SentryService
# ---------------------------------------------------------------------------


class SentryService:
    """
    Fetches error counts, trends, top issues, and performance stats
    from the Sentry REST API and caches results for 5 minutes.
    """

    def __init__(self) -> None:
        self._org = settings.SENTRY_ORG_SLUG
        self._project = settings.SENTRY_PROJECT_SLUG
        self._token = settings.SENTRY_AUTH_TOKEN

    def _require_config(self) -> None:
        if not self._token or not self._org or not self._project:
            raise SentryServiceError(
                "Sentry is not configured. "
                "Set SENTRY_AUTH_TOKEN, SENTRY_ORG_SLUG, SENTRY_PROJECT_SLUG.",
                status_code=503,
            )

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=SENTRY_API_BASE,
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=15,
        )

    # ------------------------------------------------------------------
    # Summary (cached 5 min) — used by GET /api/admin/sentry/summary
    # ------------------------------------------------------------------

    async def get_summary(self) -> dict[str, Any]:
        """
        Return a combined summary for the admin dashboard:
          - unresolved_24h: error count in last 24 h
          - trend_delta: delta vs prior 24 h (positive = more errors)
          - top_issues: list[{id, title, times_seen, last_seen, culprit}]
          - p95_latency_ms: backend p95 transaction duration
          - apdex: satisfaction metric
          - 7_day_sparkline: list[{date, count}]
        """
        cached = _cache.get("summary")
        if cached is not None:
            return cached

        self._require_config()
        result = await self._fetch_summary()
        _cache.set("summary", result)
        return result

    async def _fetch_summary(self) -> dict[str, Any]:
        async with self._client() as client:
            # Fire all 4 Sentry API calls concurrently
            issues_resp, stats_resp, perf_resp, prior_resp = await asyncio.gather(
                client.get(
                    f"/organizations/{self._org}/issues/",
                    params={
                        "project": self._project,
                        "query": "is:unresolved",
                        "statsPeriod": "24h",
                        "limit": 5,
                        "sort": "freq",
                    },
                ),
                client.get(
                    f"/organizations/{self._org}/stats_v2/",
                    params={
                        "project": self._project,
                        "field": "count()",
                        "interval": "1d",
                        "statsPeriod": "7d",
                        "category": "error",
                        "outcome": "accepted",
                    },
                ),
                client.get(
                    f"/organizations/{self._org}/events/",
                    params={
                        "project": self._project,
                        "field": ["p95(transaction.duration)", "apdex()"],
                        "query": "event.type:transaction server_name:backend-api",
                        "statsPeriod": "24h",
                        "per_page": 1,
                    },
                ),
                client.get(
                    f"/organizations/{self._org}/stats_v2/",
                    params={
                        "project": self._project,
                        "field": "count()",
                        "interval": "24h",
                        "statsPeriod": "48h",
                        "category": "error",
                        "outcome": "accepted",
                    },
                ),
            )

        # --- Parse issues ---
        if issues_resp.status_code != 200:
            raise SentryServiceError(
                f"Sentry issues API error: {issues_resp.status_code}",
            )
        issues_data = issues_resp.json()
        top_issues = [
            {
                "id": i["id"],
                "title": i.get("title", ""),
                "culprit": i.get("culprit", ""),
                "times_seen": i.get("count", 0),
                "last_seen": i.get("lastSeen", ""),
                "permalink": i.get("permalink", ""),
                "level": i.get("level", "error"),
                "server_name": (i.get("tags") or {}).get("server_name", ""),
            }
            for i in issues_data
        ]
        unresolved_24h = sum(int(i.get("count", 0)) for i in issues_data)

        # --- Parse 7-day sparkline ---
        sparkline: list[dict] = []
        if stats_resp.status_code == 200:
            stats_data = stats_resp.json()
            intervals = stats_data.get("intervals", [])
            groups = stats_data.get("groups", [])
            if groups:
                totals = groups[0].get("totals", {}).get("count()", [])
                sparkline = [
                    {"date": intervals[i], "count": totals[i]}
                    for i in range(min(len(intervals), len(totals)))
                ]

        # --- Parse performance ---
        p95_latency_ms: float | None = None
        apdex: float | None = None
        if perf_resp.status_code == 200:
            perf_data = perf_resp.json()
            perf_rows = perf_data.get("data", [])
            if perf_rows:
                row = perf_rows[0]
                p95_latency_ms = row.get("p95(transaction.duration)")
                apdex = row.get("apdex()")

        # --- Parse trend delta ---
        trend_delta: int | None = None
        if prior_resp.status_code == 200:
            prior_data = prior_resp.json()
            prior_groups = prior_data.get("groups", [])
            if prior_groups:
                prior_totals = prior_groups[0].get("totals", {}).get("count()", [])
                if len(prior_totals) >= 2:
                    trend_delta = int(prior_totals[-1]) - int(prior_totals[-2])

        return {
            "unresolved_24h": unresolved_24h,
            "trend_delta": trend_delta,
            "top_issues": top_issues,
            "p95_latency_ms": p95_latency_ms,
            "apdex": apdex,
            "seven_day_sparkline": sparkline,
            "sentry_issues_url": (
                f"https://sentry.io/organizations/{self._org}/issues/"
                f"?project={self._project}"
            ),
            "sentry_performance_url": (
                f"https://sentry.io/organizations/{self._org}/performance/"
            ),
            "sentry_alerts_url": (
                f"https://sentry.io/organizations/{self._org}/alerts/"
            ),
        }

    def invalidate_cache(self) -> None:
        _cache.invalidate("summary")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_sentry_service: SentryService | None = None


def get_sentry_service() -> SentryService:
    global _sentry_service
    if _sentry_service is None:
        _sentry_service = SentryService()
    return _sentry_service

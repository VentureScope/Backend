"""
Integration tests for Phase 2 super-admin dashboard endpoints.

Coverage:
  POST /api/admin/notifications          (pipeline webhook receiver)
  POST /api/admin/sentry-webhook         (Sentry webhook receiver)
  GET  /api/admin/taxonomy/roles         (local DB — no external deps)
  GET  /api/admin/taxonomy/unmatched     (mocked SupabaseService)
  PATCH /api/admin/taxonomy/unmatched/{id}  (mocked Supabase + local DB write)
  GET  /api/admin/ml/runs                (mocked SupabaseService)
  GET  /api/admin/ml/runs/{run_id}       (mocked SupabaseService)
  POST /api/admin/ml/deploy/{run_id}     (mocked SupabaseService + mocked boto3)
  POST /api/admin/ml/trigger             (mocked AirflowService)
  GET  /api/admin/system/pipeline-status (mocked AirflowService)
  GET  /api/admin/system/pipeline-runs   (mocked AirflowService)
  GET  /api/admin/system/storage         (mocked boto3)
  GET  /api/admin/sentry/summary         (mocked SentryService)

External services are always mocked — no real Supabase / Airflow / Sentry / Spaces.

NOTE: The shared `db_session` fixture in conftest.py calls Base.metadata.create_all
which fails here because pgvector is not installed in this PostgreSQL 18 instance.
We override it with a module-local fixture that only creates the tables this test
module needs (no Vector columns).
"""

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.admin_notification import AdminNotification
from app.models.taxonomy_role import TaxonomyRole
from app.models.token_blocklist import TokenBlocklist
from app.models.user import User

import os
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://venturescope:venturescope@localhost:5432/venturescope_test",
)

# Raw DDL for the tables we need — avoids pgvector entirely.
# The `users` table replaces VECTOR(384) with TEXT so pgvector is not required.
_CREATE_TABLES_SQL = """
DROP TABLE IF EXISTS admin_notifications CASCADE;
DROP TABLE IF EXISTS taxonomy_roles CASCADE;
DROP TABLE IF EXISTS token_blocklist CASCADE;
DROP TABLE IF EXISTS users CASCADE;

CREATE TABLE users (
    id              VARCHAR(36)  PRIMARY KEY,
    email           VARCHAR(255) NOT NULL UNIQUE,
    password_hash   VARCHAR(255),
    full_name       VARCHAR(255),
    profile_picture_url VARCHAR(500),
    github_username VARCHAR(255),
    career_interest VARCHAR(500),
    skills          JSON,
    cv_url          VARCHAR(1000),
    estudent_profile VARCHAR(1000),
    embedding       TEXT,
    embedding_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    social_links    VARCHAR(2000),
    oauth_provider  VARCHAR(50),
    oauth_id        VARCHAR(255),
    email_verified  BOOLEAN NOT NULL DEFAULT FALSE,
    role            VARCHAR(32) NOT NULL DEFAULT 'professional',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    is_admin        BOOLEAN NOT NULL DEFAULT FALSE,
    is_verified     BOOLEAN NOT NULL DEFAULT FALSE,
    mfa_enabled     BOOLEAN NOT NULL DEFAULT FALSE,
    mfa_enrolled_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE token_blocklist (
    id         SERIAL PRIMARY KEY,
    jti        VARCHAR(36) NOT NULL UNIQUE,
    user_id    VARCHAR(36) REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE admin_notifications (
    id         VARCHAR(36) PRIMARY KEY,
    source     VARCHAR(50) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    title      VARCHAR(255) NOT NULL,
    body       TEXT NOT NULL,
    is_read    BOOLEAN NOT NULL DEFAULT FALSE,
    metadata   JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE taxonomy_roles (
    id                 VARCHAR(36) PRIMARY KEY,
    title              VARCHAR(255) NOT NULL,
    normalized_title   VARCHAR(255) NOT NULL UNIQUE,
    category           VARCHAR(100),
    source_unmatched_id VARCHAR(36),
    accepted_by        VARCHAR(255),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_DROP_TABLES_SQL = """
DROP TABLE IF EXISTS admin_notifications CASCADE;
DROP TABLE IF EXISTS taxonomy_roles CASCADE;
DROP TABLE IF EXISTS token_blocklist CASCADE;
DROP TABLE IF EXISTS users CASCADE;
"""


# ---------------------------------------------------------------------------
# Module-local fixtures — override conftest fixtures for this file only
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Creates only the tables this module needs via raw DDL (no pgvector required).
    Drops them after each test for isolation.
    """
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        for stmt in _CREATE_TABLES_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await conn.execute(text(stmt))

    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        for stmt in _DROP_TABLES_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await conn.execute(text(stmt))

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    admin = User(
        email="admin@venturescope.example.com",
        password_hash=hash_password("AdminPass123!"),
        full_name="Admin User",
        role="professional",
        is_active=True,
        is_admin=True,
        email_verified=True,
        is_verified=True,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest_asyncio.fixture
async def authenticated_admin(client: AsyncClient, admin_user: User, db_session: AsyncSession) -> dict:
    await db_session.commit()
    response = await client.post(
        "/api/auth/login",
        json={"email": admin_user.email, "password": "AdminPass123!"},
    )
    assert response.status_code == 200, f"Admin login failed: {response.json()}"
    token_data = response.json()
    return {
        "id": admin_user.id,
        "email": admin_user.email,
        "full_name": admin_user.full_name,
        "is_admin": admin_user.is_admin,
        "access_token": token_data["access_token"],
        "headers": {"Authorization": f"Bearer {token_data['access_token']}"},
    }


@pytest_asyncio.fixture
async def authenticated_user(client: AsyncClient, db_session: AsyncSession) -> dict:
    """A regular (non-admin) user for 403 tests."""
    user = User(
        email="regular@venturescope.example.com",
        password_hash=hash_password("UserPass123!"),
        full_name="Regular User",
        role="professional",
        is_active=True,
        is_admin=False,
        email_verified=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    response = await client.post(
        "/api/auth/login",
        json={"email": user.email, "password": "UserPass123!"},
    )
    assert response.status_code == 200
    token_data = response.json()
    return {
        "id": user.id,
        "email": user.email,
        "access_token": token_data["access_token"],
        "headers": {"Authorization": f"Bearer {token_data['access_token']}"},
    }

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pipeline_sig(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, digestmod=hashlib.sha256).hexdigest()
    return "sha256=" + digest


def _make_sentry_sig(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, digestmod=hashlib.sha256).hexdigest()
    return "sha256=" + digest


PIPELINE_SECRET = "test-pipeline-secret"
SENTRY_SECRET = "test-sentry-secret"

# ---------------------------------------------------------------------------
# Fixture: patch HMAC secrets at settings level
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def patch_secrets(monkeypatch):
    """Inject deterministic webhook secrets for all tests in this module."""
    monkeypatch.setattr("app.api.admin_ml.settings.PIPELINE_WEBHOOK_SECRET", PIPELINE_SECRET)
    monkeypatch.setattr("app.api.admin_sentry.settings.SENTRY_WEBHOOK_SECRET", SENTRY_SECRET)


# ===========================================================================
# POST /api/admin/notifications  — pipeline webhook receiver
# ===========================================================================


@pytest.mark.integration
class TestPipelineWebhook:
    async def test_valid_webhook_stored_in_db(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        payload = {
            "event_type": "training_complete",
            "title": "Prophet model trained",
            "body": "Accuracy: 0.92 — awaiting review",
            "metadata": {"run_id": "run-abc", "model_type": "prophet"},
        }
        body_bytes = json.dumps(payload).encode()
        sig = _make_pipeline_sig(PIPELINE_SECRET, body_bytes)

        response = await client.post(
            "/api/admin/notifications",
            content=body_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Pipeline-Signature": sig,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["status"] == "stored"

        # Verify DB row was actually persisted
        from sqlalchemy import select
        result = await db_session.execute(
            select(AdminNotification).where(AdminNotification.id == data["id"])
        )
        notif = result.scalar_one_or_none()
        assert notif is not None
        assert notif.source == "pipeline"
        assert notif.event_type == "training_complete"
        assert notif.title == "Prophet model trained"
        assert notif.is_read is False
        assert notif.metadata_["run_id"] == "run-abc"

    async def test_missing_signature_returns_401(self, client: AsyncClient):
        payload = {"event_type": "test", "title": "T", "body": "B"}
        response = await client.post(
            "/api/admin/notifications",
            json=payload,
        )
        assert response.status_code == 401

    async def test_invalid_signature_returns_401(self, client: AsyncClient):
        payload = {"event_type": "test", "title": "T", "body": "B"}
        body_bytes = json.dumps(payload).encode()

        response = await client.post(
            "/api/admin/notifications",
            content=body_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Pipeline-Signature": "sha256=badhex",
            },
        )
        assert response.status_code == 401

    async def test_tampered_body_returns_401(self, client: AsyncClient):
        original = b'{"event_type": "training_complete", "title": "T", "body": "B"}'
        sig = _make_pipeline_sig(PIPELINE_SECRET, original)
        tampered = b'{"event_type": "malicious", "title": "T", "body": "B"}'

        response = await client.post(
            "/api/admin/notifications",
            content=tampered,
            headers={
                "Content-Type": "application/json",
                "X-Pipeline-Signature": sig,
            },
        )
        assert response.status_code == 401

    async def test_webhook_with_minimal_payload(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Webhook with only required fields (no metadata) should succeed."""
        payload = {"event_type": "etl_failed", "title": "ETL failed", "body": "DAG timed out"}
        body_bytes = json.dumps(payload).encode()
        sig = _make_pipeline_sig(PIPELINE_SECRET, body_bytes)

        response = await client.post(
            "/api/admin/notifications",
            content=body_bytes,
            headers={"Content-Type": "application/json", "X-Pipeline-Signature": sig},
        )
        assert response.status_code == 201

        from sqlalchemy import select
        result = await db_session.execute(
            select(AdminNotification).where(AdminNotification.id == response.json()["id"])
        )
        notif = result.scalar_one()
        assert notif.metadata_ is None


# ===========================================================================
# POST /api/admin/sentry-webhook  — Sentry alert receiver
# ===========================================================================


@pytest.mark.integration
class TestSentryWebhook:
    async def test_valid_webhook_stored_in_db(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        payload = {
            "action": "triggered",
            "data": {
                "issue": {
                    "id": "sentry-issue-001",
                    "title": "ValueError: something broke",
                    "culprit": "app/services/chat_service.py in run",
                    "level": "error",
                    "count": "42",
                    "lastSeen": "2026-05-19T10:00:00Z",
                    "permalink": "https://sentry.io/issues/sentry-issue-001/",
                }
            },
        }
        body_bytes = json.dumps(payload).encode()
        sig = _make_sentry_sig(SENTRY_SECRET, body_bytes)

        response = await client.post(
            "/api/admin/sentry-webhook",
            content=body_bytes,
            headers={
                "Content-Type": "application/json",
                "sentry-hook-signature": sig,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "stored"

        from sqlalchemy import select
        result = await db_session.execute(
            select(AdminNotification).where(AdminNotification.id == data["id"])
        )
        notif = result.scalar_one_or_none()
        assert notif is not None
        assert notif.source == "sentry"
        assert notif.event_type == "sentry_triggered"
        assert "ValueError" in notif.title
        assert notif.metadata_["sentry_issue_id"] == "sentry-issue-001"
        assert notif.metadata_["level"] == "error"
        assert notif.is_read is False

    async def test_missing_signature_returns_401(self, client: AsyncClient):
        response = await client.post(
            "/api/admin/sentry-webhook",
            json={"action": "triggered", "data": {}},
        )
        assert response.status_code == 401

    async def test_invalid_signature_returns_401(self, client: AsyncClient):
        body = b'{"action": "triggered", "data": {}}'
        response = await client.post(
            "/api/admin/sentry-webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "sentry-hook-signature": "sha256=wrongdigest",
            },
        )
        assert response.status_code == 401

    async def test_empty_issue_data_stored_gracefully(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Sentry webhook with no issue body should still store without crashing."""
        payload = {"action": "resolved", "data": {}}
        body_bytes = json.dumps(payload).encode()
        sig = _make_sentry_sig(SENTRY_SECRET, body_bytes)

        response = await client.post(
            "/api/admin/sentry-webhook",
            content=body_bytes,
            headers={"Content-Type": "application/json", "sentry-hook-signature": sig},
        )
        assert response.status_code == 201


# ===========================================================================
# GET /api/admin/taxonomy/roles  — local DB, no external deps
# ===========================================================================


@pytest.mark.integration
class TestTaxonomyRoles:
    async def test_empty_list_when_no_roles(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        response = await client.get(
            "/api/admin/taxonomy/roles",
            headers=authenticated_admin["headers"],
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    async def test_lists_inserted_roles(
        self,
        client: AsyncClient,
        authenticated_admin: dict,
        db_session: AsyncSession,
    ):
        role = TaxonomyRole(
            id=str(uuid.uuid4()),
            title="Data Scientist",
            normalized_title="data scientist",
            accepted_by="admin@example.com",
        )
        db_session.add(role)
        await db_session.commit()

        response = await client.get(
            "/api/admin/taxonomy/roles",
            headers=authenticated_admin["headers"],
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["normalized_title"] == "data scientist"

    async def test_non_admin_gets_403(
        self, client: AsyncClient, authenticated_user: dict
    ):
        response = await client.get(
            "/api/admin/taxonomy/roles",
            headers=authenticated_user["headers"],
        )
        assert response.status_code == 403

    async def test_unauthenticated_gets_401(self, client: AsyncClient):
        response = await client.get("/api/admin/taxonomy/roles")
        assert response.status_code == 401


# ===========================================================================
# GET /api/admin/taxonomy/unmatched  (mocked SupabaseService)
# ===========================================================================


@pytest.mark.integration
class TestTaxonomyUnmatched:
    async def test_list_returns_supabase_data(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        mock_data = {
            "items": [
                {
                    "id": 1,
                    "cleaned_title": "ML Ops Engineer",
                    "occurrences": 15,
                    "confidence": 0.75,
                    "best_match": "Machine Learning Engineer",
                    "status": "pending",
                    "first_seen_at": "2026-05-01T00:00:00Z",
                    "last_seen_at": "2026-05-18T00:00:00Z",
                    "raw_title": "MLOps Eng",
                    "method_used": "fuzzy",
                    "source": "etl",
                }
            ],
            "total": 1,
            "page": 1,
            "per_page": 50,
        }

        with patch(
            "app.api.admin_taxonomy.get_supabase_service",
            return_value=MagicMock(
                list_unmatched_roles=AsyncMock(return_value=mock_data)
            ),
        ):
            response = await client.get(
                "/api/admin/taxonomy/unmatched",
                headers=authenticated_admin["headers"],
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["cleaned_title"] == "ML Ops Engineer"

    async def test_non_admin_gets_403(
        self, client: AsyncClient, authenticated_user: dict
    ):
        response = await client.get(
            "/api/admin/taxonomy/unmatched",
            headers=authenticated_user["headers"],
        )
        assert response.status_code == 403

    async def test_supabase_error_returns_502(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        with patch(
            "app.api.admin_taxonomy.get_supabase_service",
            return_value=MagicMock(
                list_unmatched_roles=AsyncMock(side_effect=Exception("connection refused"))
            ),
        ):
            response = await client.get(
                "/api/admin/taxonomy/unmatched",
                headers=authenticated_admin["headers"],
            )
        assert response.status_code == 502


# ===========================================================================
# PATCH /api/admin/taxonomy/unmatched/{id}
# ===========================================================================


@pytest.mark.integration
class TestTaxonomyPatch:
    def _mock_supabase(self, role: dict, updated: dict):
        svc = MagicMock()
        svc.get_unmatched_role = AsyncMock(return_value=role)
        svc.patch_unmatched_role_status = AsyncMock(return_value=updated)
        return svc

    async def test_accept_writes_taxonomy_role_to_local_db(
        self,
        client: AsyncClient,
        authenticated_admin: dict,
        db_session: AsyncSession,
    ):
        role = {
            "id": 1,
            "cleaned_title": "AI Product Manager",
            "status": "pending",
            "occurrences": 5,
        }
        updated = {**role, "status": "accepted"}

        with patch(
            "app.api.admin_taxonomy.get_supabase_service",
            return_value=self._mock_supabase(role, updated),
        ):
            response = await client.patch(
                "/api/admin/taxonomy/unmatched/1",
                json={"status": "accepted"},
                headers=authenticated_admin["headers"],
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert data["cleaned_title"] == "AI Product Manager"
        assert data["accepted_by"] == authenticated_admin["email"]

        # Verify taxonomy_role was written to local DB
        from sqlalchemy import select
        result = await db_session.execute(
            select(TaxonomyRole).where(TaxonomyRole.normalized_title == "ai product manager")
        )
        tax_role = result.scalar_one_or_none()
        assert tax_role is not None
        assert tax_role.title == "AI Product Manager"
        assert tax_role.accepted_by == authenticated_admin["email"]

    async def test_decline_does_not_write_taxonomy_role(
        self,
        client: AsyncClient,
        authenticated_admin: dict,
        db_session: AsyncSession,
    ):
        role = {"id": 2, "cleaned_title": "Social Media Guru", "status": "pending"}
        updated = {**role, "status": "declined"}

        with patch(
            "app.api.admin_taxonomy.get_supabase_service",
            return_value=self._mock_supabase(role, updated),
        ):
            response = await client.patch(
                "/api/admin/taxonomy/unmatched/2",
                json={"status": "declined"},
                headers=authenticated_admin["headers"],
            )

        assert response.status_code == 200
        assert response.json()["status"] == "declined"

        # No taxonomy_role should exist
        from sqlalchemy import select
        result = await db_session.execute(select(TaxonomyRole))
        assert result.scalars().all() == []

    async def test_accept_already_non_pending_returns_400(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        role = {"id": 3, "cleaned_title": "Some Role", "status": "accepted"}

        with patch(
            "app.api.admin_taxonomy.get_supabase_service",
            return_value=MagicMock(get_unmatched_role=AsyncMock(return_value=role)),
        ):
            response = await client.patch(
                "/api/admin/taxonomy/unmatched/3",
                json={"status": "accepted"},
                headers=authenticated_admin["headers"],
            )
        assert response.status_code == 400

    async def test_not_found_returns_404(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        with patch(
            "app.api.admin_taxonomy.get_supabase_service",
            return_value=MagicMock(get_unmatched_role=AsyncMock(return_value=None)),
        ):
            response = await client.patch(
                "/api/admin/taxonomy/unmatched/999",
                json={"status": "accepted"},
                headers=authenticated_admin["headers"],
            )
        assert response.status_code == 404

    async def test_invalid_status_value_returns_422(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        response = await client.patch(
            "/api/admin/taxonomy/unmatched/1",
            json={"status": "banana"},
            headers=authenticated_admin["headers"],
        )
        assert response.status_code == 422

    async def test_accept_idempotent_for_duplicate_normalized_title(
        self,
        client: AsyncClient,
        authenticated_admin: dict,
        db_session: AsyncSession,
    ):
        """
        Accepting the same cleaned_title twice should not raise a unique constraint
        error — the second accept is silently skipped.
        """
        # Pre-insert a taxonomy role with the same normalized_title
        existing = TaxonomyRole(
            id=str(uuid.uuid4()),
            title="Data Engineer",
            normalized_title="data engineer",
            accepted_by="prev@admin.com",
        )
        db_session.add(existing)
        await db_session.commit()

        role = {"id": 10, "cleaned_title": "Data Engineer", "status": "pending"}
        updated = {**role, "status": "accepted"}

        with patch(
            "app.api.admin_taxonomy.get_supabase_service",
            return_value=self._mock_supabase(role, updated),
        ):
            response = await client.patch(
                "/api/admin/taxonomy/unmatched/10",
                json={"status": "accepted"},
                headers=authenticated_admin["headers"],
            )

        assert response.status_code == 200
        # Still only one taxonomy_role row
        from sqlalchemy import func, select
        count = await db_session.execute(
            select(func.count()).select_from(TaxonomyRole)
        )
        assert count.scalar_one() == 1


# ===========================================================================
# GET /api/admin/ml/runs  (mocked SupabaseService)
# ===========================================================================


@pytest.mark.integration
class TestMLRuns:
    def _mock_svc(self, runs_data: dict, single_run: dict | None = None):
        svc = MagicMock()
        svc.list_ml_training_runs = AsyncMock(return_value=runs_data)
        svc.get_ml_training_run = AsyncMock(return_value=single_run)
        return svc

    async def test_list_returns_paginated_runs(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        mock_data = {
            "items": [
                {
                    "run_id": "run-001",
                    "model_type": "prophet",
                    "status": "awaiting_review",
                    "accuracy": 0.91,
                    "f1_score": 0.88,
                    "auc_roc": 0.95,
                    "created_at": "2026-05-18T10:00:00Z",
                }
            ],
            "total": 1,
            "page": 1,
            "per_page": 20,
        }

        with patch(
            "app.api.admin_ml.get_supabase_service",
            return_value=self._mock_svc(mock_data),
        ):
            response = await client.get(
                "/api/admin/ml/runs", headers=authenticated_admin["headers"]
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["run_id"] == "run-001"
        assert data["items"][0]["status"] == "awaiting_review"

    async def test_list_passes_filters_to_service(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        svc = MagicMock()
        svc.list_ml_training_runs = AsyncMock(
            return_value={"items": [], "total": 0, "page": 1, "per_page": 20}
        )

        with patch("app.api.admin_ml.get_supabase_service", return_value=svc):
            await client.get(
                "/api/admin/ml/runs?status=deployed&model_type=lstm&page=2&per_page=5",
                headers=authenticated_admin["headers"],
            )

        svc.list_ml_training_runs.assert_called_once_with(
            status="deployed", model_type="lstm", page=2, per_page=5
        )

    async def test_get_single_run_returns_detail(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        run = {
            "run_id": "run-detail-001",
            "model_type": "lstm",
            "status": "deployed",
            "accuracy": 0.93,
        }

        with patch(
            "app.api.admin_ml.get_supabase_service",
            return_value=self._mock_svc({}, single_run=run),
        ):
            response = await client.get(
                "/api/admin/ml/runs/run-detail-001",
                headers=authenticated_admin["headers"],
            )

        assert response.status_code == 200
        assert response.json()["run_id"] == "run-detail-001"

    async def test_get_nonexistent_run_returns_404(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        with patch(
            "app.api.admin_ml.get_supabase_service",
            return_value=self._mock_svc({}, single_run=None),
        ):
            response = await client.get(
                "/api/admin/ml/runs/nonexistent",
                headers=authenticated_admin["headers"],
            )
        assert response.status_code == 404

    async def test_non_admin_gets_403(
        self, client: AsyncClient, authenticated_user: dict
    ):
        response = await client.get(
            "/api/admin/ml/runs", headers=authenticated_user["headers"]
        )
        assert response.status_code == 403


# ===========================================================================
# POST /api/admin/ml/deploy/{run_id}
# ===========================================================================


@pytest.mark.integration
class TestMLDeploy:
    def _supabase_with_run(self, run: dict):
        svc = MagicMock()
        svc.get_ml_training_run = AsyncMock(return_value=run)
        svc.update_ml_training_run_status = AsyncMock()
        svc.supersede_other_runs = AsyncMock()
        # Bundle pre-flight check queries the pool for a deployed partner model;
        # default to "no partner deployed" so single-model deploys aren't blocked.
        pool = MagicMock()
        pool.fetchrow = AsyncMock(return_value=None)
        pool.fetchval = AsyncMock(return_value=0)
        svc._get_pool_direct = AsyncMock(return_value=pool)
        return svc

    async def test_deploy_run_without_forecast_key_returns_400(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        """A run with no staging_forecast_key cannot be deployed."""
        run = {
            "run_id": "run-deploy-001",
            "model_type": "prophet",
            "status": "awaiting_review",
            "run_yearmonth": "2026-05",
            "staging_forecast_key": "",  # empty — rejected
        }

        with patch("app.api.admin_ml.get_supabase_service", return_value=self._supabase_with_run(run)):
            response = await client.post(
                "/api/admin/ml/deploy/run-deploy-001",
                headers=authenticated_admin["headers"],
            )

        assert response.status_code == 400
        assert "forecast" in response.json()["detail"].lower()

    async def test_deploy_already_deployed_returns_400(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        run = {"run_id": "run-already", "model_type": "prophet", "status": "deployed", "run_yearmonth": "2026-05", "staging_forecast_key": ""}

        with patch("app.api.admin_ml.get_supabase_service", return_value=self._supabase_with_run(run)):
            response = await client.post(
                "/api/admin/ml/deploy/run-already",
                headers=authenticated_admin["headers"],
            )
        assert response.status_code == 400
        assert "deployed" in response.json()["detail"]

    async def test_deploy_nonexistent_run_returns_404(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        svc = MagicMock()
        svc.get_ml_training_run = AsyncMock(return_value=None)

        with patch("app.api.admin_ml.get_supabase_service", return_value=svc):
            response = await client.post(
                "/api/admin/ml/deploy/ghost-run",
                headers=authenticated_admin["headers"],
            )
        assert response.status_code == 404

    async def test_deploy_copies_forecast_to_production(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        """When staging_forecast_key is set, the forecast CSV is copied to the
        flat production path models/production/{ym}/forecasts_{model}.csv."""
        run = {
            "run_id": "run-with-key",
            "model_type": "prophet",
            "status": "awaiting_review",
            "run_yearmonth": "2026-05",
            "staging_forecast_key": "models/staging/2026-05/prophet/forecasts.csv",
        }

        with patch("app.api.admin_ml.get_supabase_service", return_value=self._supabase_with_run(run)), \
             patch("app.api.admin_ml.settings") as mock_settings, \
             patch("app.api.admin_ml.get_spaces_client") as mock_client_fn:

            mock_settings.DO_SPACES_BUCKET = "venturescope-bucket"
            mock_settings.DO_SPACES_ENDPOINT = "https://lon1.digitaloceanspaces.com"
            mock_settings.DO_SPACES_REGION = "lon1"
            mock_settings.DO_SPACES_KEY = "key"
            mock_settings.DO_SPACES_SECRET = "secret"
            mock_settings.PIPELINE_WEBHOOK_SECRET = PIPELINE_SECRET

            mock_s3 = MagicMock()
            mock_s3.head_object = MagicMock()  # pre-flight: source exists
            mock_s3.copy_object = MagicMock()
            mock_s3.delete_objects = MagicMock()
            # paginator returns no existing production files to wipe
            mock_paginator = MagicMock()
            mock_paginator.paginate.return_value = []
            mock_s3.get_paginator.return_value = mock_paginator
            mock_client_fn.return_value = mock_s3

            response = await client.post(
                "/api/admin/ml/deploy/run-with-key",
                headers=authenticated_admin["headers"],
            )

        assert response.status_code == 200
        # forecast CSV copied to the flat production path
        copied_keys = [c.kwargs["Key"] for c in mock_s3.copy_object.call_args_list]
        assert "models/production/2026-05/forecasts_prophet.csv" in copied_keys

    async def test_non_admin_gets_403(
        self, client: AsyncClient, authenticated_user: dict
    ):
        response = await client.post(
            "/api/admin/ml/deploy/any-run",
            headers=authenticated_user["headers"],
        )
        assert response.status_code == 403


# ===========================================================================
# POST /api/admin/ml/trigger  (mocked AirflowService)
# ===========================================================================


@pytest.mark.integration
class TestMLTrigger:
    async def test_trigger_returns_202_with_dag_run(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        dag_run_data = {
            "dag_run_id": "manual__2026-05-19T12:00:00",
            "state": "queued",
            "dag_id": "monthly_training_pipeline",
        }
        mock_airflow = MagicMock()
        mock_airflow.trigger_training_pipeline = AsyncMock(return_value=dag_run_data)

        with patch("app.api.admin_ml.get_airflow_service", return_value=mock_airflow):
            response = await client.post(
                "/api/admin/ml/trigger",
                headers=authenticated_admin["headers"],
            )

        assert response.status_code == 202
        data = response.json()
        assert data["dag_run"]["state"] == "queued"
        assert data["triggered_by"] == authenticated_admin["email"]

    async def test_airflow_not_configured_returns_503(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        from app.services.airflow_service import AirflowServiceError

        mock_airflow = MagicMock()
        mock_airflow.trigger_training_pipeline = AsyncMock(
            side_effect=AirflowServiceError("Not configured", status_code=503)
        )

        with patch("app.api.admin_ml.get_airflow_service", return_value=mock_airflow):
            response = await client.post(
                "/api/admin/ml/trigger",
                headers=authenticated_admin["headers"],
            )
        assert response.status_code == 503

    async def test_non_admin_gets_403(
        self, client: AsyncClient, authenticated_user: dict
    ):
        response = await client.post(
            "/api/admin/ml/trigger", headers=authenticated_user["headers"]
        )
        assert response.status_code == 403


# ===========================================================================
# GET /api/admin/system/pipeline-status  (mocked AirflowService)
# ===========================================================================


@pytest.mark.integration
class TestSystemPipelineStatus:
    async def test_returns_etl_and_training_status(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        status_data = {
            "etl": {"dag_id": "job_data_pipeline", "state": "success"},
            "training": {"dag_id": "monthly_training_pipeline", "state": "running"},
        }
        mock_airflow = MagicMock()
        mock_airflow.get_pipeline_status = AsyncMock(return_value=status_data)

        with patch("app.api.admin_system.get_airflow_service", return_value=mock_airflow):
            response = await client.get(
                "/api/admin/system/pipeline-status",
                headers=authenticated_admin["headers"],
            )

        assert response.status_code == 200
        data = response.json()
        assert data["etl"]["state"] == "success"
        assert data["training"]["state"] == "running"

    async def test_airflow_error_returns_502(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        from app.services.airflow_service import AirflowServiceError

        mock_airflow = MagicMock()
        mock_airflow.get_pipeline_status = AsyncMock(
            side_effect=AirflowServiceError("Bad gateway", status_code=502)
        )

        with patch("app.api.admin_system.get_airflow_service", return_value=mock_airflow):
            response = await client.get(
                "/api/admin/system/pipeline-status",
                headers=authenticated_admin["headers"],
            )
        assert response.status_code == 502

    async def test_non_admin_gets_403(
        self, client: AsyncClient, authenticated_user: dict
    ):
        response = await client.get(
            "/api/admin/system/pipeline-status",
            headers=authenticated_user["headers"],
        )
        assert response.status_code == 403


# ===========================================================================
# GET /api/admin/system/pipeline-runs  (mocked AirflowService)
# ===========================================================================


@pytest.mark.integration
class TestSystemPipelineRuns:
    async def test_returns_dag_runs_and_task_durations(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        runs_data = {
            "dag_id": "job_data_pipeline",
            "dag_runs": [
                {"dag_run_id": "run-1", "state": "success", "start_date": "2026-05-18T08:00:00Z"},
                {"dag_run_id": "run-2", "state": "failed",  "start_date": "2026-05-17T08:00:00Z"},
            ],
            "latest_run_task_durations": [
                {"task_id": "extract", "duration": 120.5},
                {"task_id": "transform", "duration": 45.2},
            ],
        }
        mock_airflow = MagicMock()
        mock_airflow.get_etl_run_history = AsyncMock(return_value=runs_data)

        with patch("app.api.admin_system.get_airflow_service", return_value=mock_airflow):
            response = await client.get(
                "/api/admin/system/pipeline-runs",
                headers=authenticated_admin["headers"],
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["dag_runs"]) == 2
        assert len(data["latest_run_task_durations"]) == 2

    async def test_days_param_forwarded_to_service(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        svc = MagicMock()
        svc.get_etl_run_history = AsyncMock(
            return_value={"dag_id": "job_data_pipeline", "dag_runs": [], "latest_run_task_durations": []}
        )

        with patch("app.api.admin_system.get_airflow_service", return_value=svc):
            await client.get(
                "/api/admin/system/pipeline-runs?days=14",
                headers=authenticated_admin["headers"],
            )

        svc.get_etl_run_history.assert_called_once_with(days=14)


# ===========================================================================
# GET /api/admin/system/storage  (mocked boto3)
# ===========================================================================


@pytest.mark.integration
class TestSystemStorage:
    async def test_returns_staging_and_production_files(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        mock_paginator = MagicMock()
        mock_paginator.paginate.side_effect = [
            # staging call
            iter([{"Contents": [
                {"Key": "models/staging/2026-05/prophet/forecasts.csv", "Size": 500000,
                 "LastModified": datetime(2026, 5, 18, tzinfo=timezone.utc)}
            ]}]),
            # production call
            iter([{"Contents": [
                {"Key": "models/production/2026-05/forecasts_prophet.csv", "Size": 500000,
                 "LastModified": datetime(2026, 5, 17, tzinfo=timezone.utc)}
            ]}]),
        ]
        mock_s3 = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator

        with patch("app.api.admin_system.settings") as mock_settings, \
             patch("app.api.admin_system.get_spaces_client", return_value=mock_s3):

            mock_settings.DO_SPACES_BUCKET = "vs-bucket"
            mock_settings.DO_SPACES_ENDPOINT = "https://lon1.digitaloceanspaces.com"
            mock_settings.DO_SPACES_REGION = "lon1"
            mock_settings.DO_SPACES_KEY = "key"
            mock_settings.DO_SPACES_SECRET = "secret"

            response = await client.get(
                "/api/admin/system/storage",
                headers=authenticated_admin["headers"],
            )

        assert response.status_code == 200
        data = response.json()
        assert "staging" in data
        assert "production" in data
        assert data["total_size_bytes"] == 1000000
        assert data["bucket"] == "vs-bucket"

    async def test_not_configured_returns_503(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        with patch("app.api.admin_system.settings") as mock_settings:
            mock_settings.DO_SPACES_BUCKET = ""
            mock_settings.DO_SPACES_ENDPOINT = ""

            response = await client.get(
                "/api/admin/system/storage",
                headers=authenticated_admin["headers"],
            )
        assert response.status_code == 503

    async def test_non_admin_gets_403(
        self, client: AsyncClient, authenticated_user: dict
    ):
        response = await client.get(
            "/api/admin/system/storage",
            headers=authenticated_user["headers"],
        )
        assert response.status_code == 403


# ===========================================================================
# GET /api/admin/sentry/summary  (mocked SentryService)
# ===========================================================================


@pytest.mark.integration
class TestSentrySummary:
    async def test_returns_cached_summary(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        summary = {
            "unresolved_24h": 7,
            "trend_delta": 3,
            "top_issues": [
                {"id": "i1", "title": "TypeError", "times_seen": 42, "last_seen": "2026-05-19T09:00:00Z"}
            ],
            "p95_latency_ms": 230.5,
            "apdex": 0.92,
            "seven_day_sparkline": [{"date": "2026-05-13", "count": 12}],
            "sentry_issues_url": "https://sentry.io/organizations/vs/issues/",
            "sentry_performance_url": "https://sentry.io/organizations/vs/performance/",
            "sentry_alerts_url": "https://sentry.io/organizations/vs/alerts/",
        }
        mock_sentry = MagicMock()
        mock_sentry.get_summary = AsyncMock(return_value=summary)

        with patch("app.api.admin_sentry.get_sentry_service", return_value=mock_sentry):
            response = await client.get(
                "/api/admin/sentry/summary",
                headers=authenticated_admin["headers"],
            )

        assert response.status_code == 200
        data = response.json()
        assert data["unresolved_24h"] == 7
        assert data["trend_delta"] == 3
        assert data["p95_latency_ms"] == 230.5
        assert data["apdex"] == 0.92
        assert len(data["top_issues"]) == 1
        assert "sentry_issues_url" in data

    async def test_sentry_not_configured_returns_503(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        from app.services.sentry_service import SentryServiceError

        mock_sentry = MagicMock()
        mock_sentry.get_summary = AsyncMock(
            side_effect=SentryServiceError("Not configured", status_code=503)
        )

        with patch("app.api.admin_sentry.get_sentry_service", return_value=mock_sentry):
            response = await client.get(
                "/api/admin/sentry/summary",
                headers=authenticated_admin["headers"],
            )
        assert response.status_code == 503

    async def test_non_admin_gets_403(
        self, client: AsyncClient, authenticated_user: dict
    ):
        response = await client.get(
            "/api/admin/sentry/summary",
            headers=authenticated_user["headers"],
        )
        assert response.status_code == 403

    async def test_unauthenticated_gets_401(self, client: AsyncClient):
        response = await client.get("/api/admin/sentry/summary")
        assert response.status_code == 401

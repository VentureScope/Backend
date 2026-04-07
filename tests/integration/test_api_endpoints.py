"""Integration tests for API endpoints."""

import json
import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock

from app.core.security import create_access_token
from app.models.github_sync_snapshot import GitHubSyncSnapshot
from app.models.oauth_account import OAuthAccount
from app.models.user import User


@pytest.mark.integration
class TestHealthEndpoint:
    """Test health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Test health endpoint returns OK status."""
        response = await client.get("/api/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@pytest.mark.integration
class TestAuthEndpoints:
    """Test authentication endpoints."""

    @pytest.mark.asyncio
    async def test_register_success(self, client: AsyncClient, user_data):
        """Test successful user registration."""
        response = await client.post("/api/auth/register", json=user_data)

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "id" in data
        assert data["email"] == user_data["email"]
        assert data["full_name"] == user_data["full_name"]
        assert data["career_interest"] == user_data["career_interest"]
        assert data["role"] == user_data["role"]
        assert "password" not in data  # Password should not be in response

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client: AsyncClient, user_data):
        """Test registration fails with duplicate email."""
        # First registration
        response1 = await client.post("/api/auth/register", json=user_data)
        assert response1.status_code == 200

        # Second registration with same email
        response2 = await client.post("/api/auth/register", json=user_data)
        assert response2.status_code == 400
        assert "Email already registered" in response2.json()["detail"]

    @pytest.mark.asyncio
    async def test_register_invalid_email(self, client: AsyncClient, user_data):
        """Test registration fails with invalid email format."""
        user_data["email"] = "invalid-email"

        response = await client.post("/api/auth/register", json=user_data)
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_register_missing_required_fields(self, client: AsyncClient):
        """Test registration fails with missing required fields."""
        incomplete_data = {"email": "test@example.com"}  # Missing password

        response = await client.post("/api/auth/register", json=incomplete_data)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_minimal_data(self, client: AsyncClient):
        """Test registration with minimal required data."""
        minimal_data = {"email": "minimal@example.com", "password": "Test123!"}

        response = await client.post("/api/auth/register", json=minimal_data)
        assert response.status_code == 200

        data = response.json()
        assert data["email"] == minimal_data["email"]
        assert data["full_name"] is None
        assert data["career_interest"] is None
        assert data["role"] == "professional"  # Default role

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient, user_data):
        """Test successful user login."""
        # First register a user
        register_response = await client.post("/api/auth/register", json=user_data)
        assert register_response.status_code == 200

        # Then login
        login_data = {"email": user_data["email"], "password": user_data["password"]}

        response = await client.post("/api/auth/login", json=login_data)
        assert response.status_code == 200

        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 0

    @pytest.mark.asyncio
    async def test_login_invalid_email(self, client: AsyncClient):
        """Test login fails with non-existent email."""
        login_data = {"email": "nonexistent@example.com", "password": "Test123!"}

        response = await client.post("/api/auth/login", json=login_data)
        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient, user_data):
        """Test login fails with wrong password."""
        # First register a user
        register_response = await client.post("/api/auth/register", json=user_data)
        assert register_response.status_code == 200

        # Try login with wrong password
        login_data = {"email": user_data["email"], "password": "WrongPassword123!"}

        response = await client.post("/api/auth/login", json=login_data)
        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_login_invalid_email_format(self, client: AsyncClient):
        """Test login fails with invalid email format."""
        login_data = {"email": "invalid-email", "password": "Test123!"}

        response = await client.post("/api/auth/login", json=login_data)
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_login_missing_fields(self, client: AsyncClient):
        """Test login fails with missing required fields."""
        login_data = {"email": "test@example.com"}  # Missing password

        response = await client.post("/api/auth/login", json=login_data)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_github_oauth_login_success(self, client: AsyncClient):
        """Test GitHub OAuth login endpoint returns authorization URL."""
        with patch(
            "app.api.auth.OAuthService.get_authorization_url",
            new=AsyncMock(
                return_value=(
                    "https://github.com/login/oauth/authorize?client_id=test",
                    "test_state_123",
                )
            ),
        ):
            response = await client.get("/api/auth/oauth/github/login")

        assert response.status_code == 200
        data = response.json()
        assert data["authorization_url"].startswith(
            "https://github.com/login/oauth/authorize"
        )
        assert data["state"] == "test_state_123"

    @pytest.mark.asyncio
    async def test_github_oauth_callback_success(self, client: AsyncClient):
        """Test GitHub OAuth callback exchanges code and returns app token."""
        mock_user = User(
            id="123e4567-e89b-12d3-a456-426614174000",
            email="oauth-user@example.com",
            full_name="OAuth User",
            role="professional",
            is_active=True,
            is_admin=False,
        )

        with patch(
            "app.api.auth.OAuthService.authenticate_user",
            new=AsyncMock(return_value=(mock_user, True)),
        ):
            response = await client.post(
                "/api/auth/oauth/github/callback",
                json={"code": "github_auth_code", "state": "valid_state"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["token_type"] == "bearer"
        assert "access_token" in data
        assert data["user"]["email"] == "oauth-user@example.com"

    @pytest.mark.asyncio
    async def test_github_oauth_callback_error_from_provider(self, client: AsyncClient):
        """Test GitHub OAuth GET callback returns 400 on provider error."""
        response = await client.get(
            "/api/auth/oauth/github/callback",
            params={"code": "ignored", "state": "ignored", "error": "access_denied"},
        )

        assert response.status_code == 400
        assert "OAuth error" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_github_oauth_scope_upgrade(self, client: AsyncClient):
        """Test GitHub OAuth scope-upgrade endpoint returns a fresh authorization URL."""
        with patch(
            "app.api.auth.OAuthService.get_authorization_url",
            new=AsyncMock(
                return_value=(
                    "https://github.com/login/oauth/authorize?client_id=test&scope=repo",
                    "upgrade_state_123",
                )
            ),
        ):
            response = await client.get(
                "/api/auth/oauth/github/scope-upgrade",
                params={"scopes": "read:user,user:email,repo"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["authorization_url"].startswith(
            "https://github.com/login/oauth/authorize"
        )
        assert data["state"] == "upgrade_state_123"

    @pytest.mark.asyncio
    async def test_github_profile_sync_requires_oauth(self, client: AsyncClient, user_data):
        """Test profile sync asks for GitHub OAuth when the user is not connected."""
        register_response = await client.post("/api/auth/register", json=user_data)
        assert register_response.status_code == 200

        login_response = await client.post(
            "/api/auth/login",
            json={"email": user_data["email"], "password": user_data["password"]},
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        with patch(
            "app.api.users.OAuthService.get_github_profile_sync_status",
            new=AsyncMock(
                return_value={
                    "status": "authorization_required",
                    "message": "Connect GitHub to sync profile data.",
                    "github_connected": False,
                    "required_scopes": ["read:user", "user:email", "repo"],
                    "authorization_url": "https://github.com/login/oauth/authorize?client_id=test",
                    "state": "sync_state_123",
                    "repositories": [],
                    "contributions": None,
                }
            ),
        ):
            response = await client.get(
                "/api/users/me/github/sync",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "authorization_required"
        assert data["github_connected"] is False
        assert data["state"] == "sync_state_123"

    @pytest.mark.asyncio
    async def test_github_profile_sync_scope_upgrade(self, client: AsyncClient, user_data):
        """Test profile sync returns an upgrade URL when repo scope is missing."""
        register_response = await client.post("/api/auth/register", json=user_data)
        assert register_response.status_code == 200

        login_response = await client.post(
            "/api/auth/login",
            json={"email": user_data["email"], "password": user_data["password"]},
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        with patch(
            "app.api.users.OAuthService.get_github_profile_sync_status",
            new=AsyncMock(
                return_value={
                    "status": "scope_upgrade_required",
                    "message": "GitHub access is connected, but repo-level permissions are required.",
                    "github_connected": True,
                    "required_scopes": ["read:user", "user:email", "repo"],
                    "authorization_url": "https://github.com/login/oauth/authorize?client_id=test&scope=read:user+user:email+repo",
                    "state": "upgrade_state_456",
                    "repositories": [],
                    "contributions": None,
                }
            ),
        ):
            response = await client.get(
                "/api/users/me/github/sync",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "scope_upgrade_required"
        assert data["github_connected"] is True
        assert data["required_scopes"] == ["read:user", "user:email", "repo"]

    @pytest.mark.asyncio
    async def test_github_profile_sync_persists_snapshot(
        self, client: AsyncClient, db_session
    ):
        """Test successful GitHub sync stores fetched payload in snapshot table."""
        user = User(
            id="8e529c0f-9b74-4dc7-89d3-30f3f6a1e901",
            email="sync-persist@example.com",
            password_hash="not-used",
            full_name="Sync Persist",
            role="professional",
            is_active=True,
            is_admin=False,
        )
        db_session.add(user)
        await db_session.flush()

        oauth_account = OAuthAccount(
            user_id=user.id,
            provider="github",
            provider_account_id="136518123",
            provider_email=user.email,
            access_token="test-github-token",
            provider_data=json.dumps(
                {
                    "profile": {"login": "syncpersist"},
                    "granted_scopes": ["read:user", "user:email", "repo", "read:org"],
                    "synced_at": "2026-04-06T20:30:00+00:00",
                }
            ),
        )
        db_session.add(oauth_account)
        await db_session.commit()

        token = create_access_token(subject=user.id)

        with patch(
            "app.services.oauth_service.OAuthService._fetch_github_profile_sync_data",
            new=AsyncMock(
                return_value={
                    "github_username": "syncpersist",
                    "full_name": "Sync Persist Updated",
                    "profile_picture_url": "https://avatars.githubusercontent.com/u/136518123?v=4",
                    "bio": "Testing snapshot persistence",
                    "repositories": [
                        {
                            "name": "repo-a",
                            "description": "test",
                            "stargazer_count": 2,
                            "fork_count": 1,
                            "is_private": False,
                            "is_fork": False,
                            "pushed_at": "2026-04-06T20:30:00Z",
                            "updated_at": "2026-04-06T20:30:00Z",
                            "primary_language": "Python",
                            "languages": [{"name": "Python", "size": 1000}],
                            "topics": ["api"],
                        }
                    ],
                    "contributions": {
                        "total_contributions": 10,
                        "total_pull_requests": 3,
                        "total_issue_contributions": 2,
                        "total_repositories_with_contributed_commits": 4,
                    },
                    "organizations": ["VentureScope"],
                }
            ),
        ):
            response = await client.get(
                "/api/users/me/github/sync",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "synced"
        assert payload["github_username"] == "syncpersist"

        snapshot_result = await db_session.get(GitHubSyncSnapshot, user.id)
        if not snapshot_result:
            from sqlalchemy import select

            selected = await db_session.execute(
                select(GitHubSyncSnapshot).where(GitHubSyncSnapshot.user_id == user.id)
            )
            snapshot_result = selected.scalar_one_or_none()

        assert snapshot_result is not None
        assert snapshot_result.github_username == "syncpersist"
        repositories = json.loads(snapshot_result.repositories_json)
        contributions = json.loads(snapshot_result.contributions_json)
        organizations = json.loads(snapshot_result.organizations_json)

        assert repositories[0]["name"] == "repo-a"
        assert contributions["total_contributions"] == 10
        assert organizations == ["VentureScope"]

    @pytest.mark.asyncio
    async def test_get_github_synced_data_not_found(
        self, client: AsyncClient, user_data
    ):
        """Test synced-data endpoint returns 404 if no snapshot exists."""
        register_response = await client.post("/api/auth/register", json=user_data)
        assert register_response.status_code == 200

        login_response = await client.post(
            "/api/auth/login",
            json={"email": user_data["email"], "password": user_data["password"]},
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        response = await client.get(
            "/api/users/me/github/synced-data",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404
        assert "No GitHub synced data found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_github_synced_data_success(self, client: AsyncClient, db_session):
        """Test synced-data endpoint returns persisted snapshot data."""
        user = User(
            id="4f7b64c5-6f4b-4f9d-9e6a-f5f6fd0d4de2",
            email="synced-data@example.com",
            password_hash="not-used",
            full_name="Synced Data",
            role="professional",
            is_active=True,
            is_admin=False,
        )
        db_session.add(user)
        await db_session.flush()

        snapshot = GitHubSyncSnapshot(
            user_id=user.id,
            github_username="octocat",
            repositories_json='[{"name":"repo1","languages":[{"name":"Python","size":1000}],"topics":["api"]}]',
            contributions_json='{"total_contributions":42,"total_pull_requests":7,"total_issue_contributions":3,"total_repositories_with_contributed_commits":2}',
            organizations_json='["GitHub"]',
        )
        db_session.add(snapshot)
        await db_session.commit()

        token = create_access_token(subject=user.id)
        response = await client.get(
            "/api/users/me/github/synced-data",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["github_username"] == "octocat"
        assert payload["repositories"][0]["name"] == "repo1"
        assert payload["repositories"][0]["languages"][0]["name"] == "Python"
        assert payload["contributions"]["total_contributions"] == 42
        assert payload["organizations"] == ["GitHub"]
        assert payload["synced_at"] is not None


@pytest.mark.integration
class TestUserEndpoints:
    """Test user-related endpoints."""

    @pytest.mark.asyncio
    async def test_get_current_user_success(self, client: AsyncClient, user_data):
        """Test getting current user profile with valid token."""
        # Register and login to get token
        register_response = await client.post("/api/auth/register", json=user_data)
        assert register_response.status_code == 200
        user_id = register_response.json()["id"]

        login_data = {"email": user_data["email"], "password": user_data["password"]}
        login_response = await client.post("/api/auth/login", json=login_data)
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        # Get current user profile
        headers = {"Authorization": f"Bearer {token}"}
        response = await client.get("/api/users/me", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == user_id
        assert data["email"] == user_data["email"]
        assert data["full_name"] == user_data["full_name"]
        assert data["career_interest"] == user_data["career_interest"]
        assert data["role"] == user_data["role"]

    @pytest.mark.asyncio
    async def test_get_current_user_no_token(self, client: AsyncClient):
        """Test getting current user profile without token."""
        response = await client.get("/api/users/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, client: AsyncClient):
        """Test getting current user profile with invalid token."""
        headers = {"Authorization": "Bearer invalid_token_here"}
        response = await client.get("/api/users/me", headers=headers)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_malformed_token(self, client: AsyncClient):
        """Test getting current user profile with malformed token."""
        headers = {"Authorization": "InvalidFormat token_here"}
        response = await client.get("/api/users/me", headers=headers)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_expired_token(self, client: AsyncClient, user_data):
        """Test getting current user profile with expired token."""
        # Register user first
        register_response = await client.post("/api/auth/register", json=user_data)
        assert register_response.status_code == 200
        user_id = register_response.json()["id"]

        # Create an expired token (negative expiration)
        from datetime import timedelta

        expired_token = create_access_token(
            subject=user_id,
            expires_delta=timedelta(minutes=-1),  # Expired 1 minute ago
        )

        headers = {"Authorization": f"Bearer {expired_token}"}
        response = await client.get("/api/users/me", headers=headers)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_missing_bearer_prefix(self, client: AsyncClient):
        """Test getting current user profile without 'Bearer' prefix."""
        headers = {"Authorization": "some_token_without_bearer_prefix"}
        response = await client.get("/api/users/me", headers=headers)
        assert response.status_code == 401


@pytest.mark.integration
class TestEndToEndUserFlow:
    """Test complete user registration and authentication flow."""

    @pytest.mark.asyncio
    async def test_complete_user_journey(self, client: AsyncClient, user_data):
        """Test complete user journey: register -> login -> access protected route."""
        # 1. Register user
        register_response = await client.post("/api/auth/register", json=user_data)
        assert register_response.status_code == 200
        user_profile = register_response.json()
        assert user_profile["email"] == user_data["email"]

        # 2. Login user
        login_data = {"email": user_data["email"], "password": user_data["password"]}
        login_response = await client.post("/api/auth/login", json=login_data)
        assert login_response.status_code == 200
        token_data = login_response.json()
        assert "access_token" in token_data

        # 3. Access protected route
        headers = {"Authorization": f"Bearer {token_data['access_token']}"}
        profile_response = await client.get("/api/users/me", headers=headers)
        assert profile_response.status_code == 200

        profile_data = profile_response.json()
        assert profile_data["id"] == user_profile["id"]
        assert profile_data["email"] == user_data["email"]

    @pytest.mark.asyncio
    async def test_multiple_users_isolation(self, client: AsyncClient):
        """Test that multiple users are properly isolated."""
        # Register two users
        user1_data = {
            "email": "user1@example.com",
            "password": "Test123!",
            "full_name": "User One",
        }
        user2_data = {
            "email": "user2@example.com",
            "password": "Test456!",
            "full_name": "User Two",
        }

        # Register both users
        response1 = await client.post("/api/auth/register", json=user1_data)
        response2 = await client.post("/api/auth/register", json=user2_data)
        assert response1.status_code == 200
        assert response2.status_code == 200

        # Login both users
        login1 = await client.post(
            "/api/auth/login",
            json={"email": user1_data["email"], "password": user1_data["password"]},
        )
        login2 = await client.post(
            "/api/auth/login",
            json={"email": user2_data["email"], "password": user2_data["password"]},
        )

        token1 = login1.json()["access_token"]
        token2 = login2.json()["access_token"]

        # Verify each user gets their own profile
        profile1 = await client.get(
            "/api/users/me", headers={"Authorization": f"Bearer {token1}"}
        )
        profile2 = await client.get(
            "/api/users/me", headers={"Authorization": f"Bearer {token2}"}
        )

        assert profile1.json()["email"] == user1_data["email"]
        assert profile2.json()["email"] == user2_data["email"]
        assert profile1.json()["id"] != profile2.json()["id"]

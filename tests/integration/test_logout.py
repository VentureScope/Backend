"""Integration tests for logout functionality."""

import pytest
from datetime import timedelta
from httpx import AsyncClient

from app.core.security import create_access_token


@pytest.mark.integration
class TestLogoutEndpoint:
    """Test logout endpoint."""

    @pytest.mark.asyncio
    async def test_logout_success(self, client: AsyncClient, authenticated_user: dict):
        """Test successful logout invalidates the token."""
        headers = authenticated_user["headers"]

        # Logout
        response = await client.post("/api/auth/logout", headers=headers)
        assert response.status_code == 200
        assert response.json()["message"] == "Successfully logged out"

        # Token should no longer work for protected endpoints
        profile_response = await client.get("/api/users/me", headers=headers)
        assert profile_response.status_code == 401
        assert "Token has been revoked" in profile_response.json()["detail"]

    @pytest.mark.asyncio
    async def test_logout_without_token(self, client: AsyncClient):
        """Test logout fails without authentication token."""
        response = await client.post("/api/auth/logout")
        assert (
            response.status_code == 403
        )  # HTTPBearer with auto_error=True returns 403

    @pytest.mark.asyncio
    async def test_logout_with_invalid_token(self, client: AsyncClient):
        """Test logout fails with invalid token."""
        headers = {"Authorization": "Bearer invalid_token_here"}
        response = await client.post("/api/auth/logout", headers=headers)
        assert response.status_code == 401
        assert "Invalid or expired token" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_logout_with_expired_token(
        self, client: AsyncClient, registered_user: dict
    ):
        """Test logout fails with expired token."""
        # Create an expired token
        expired_token = create_access_token(
            subject=registered_user["id"],
            expires_delta=timedelta(minutes=-1),  # Expired 1 minute ago
        )

        headers = {"Authorization": f"Bearer {expired_token}"}
        response = await client.post("/api/auth/logout", headers=headers)
        assert response.status_code == 401
        assert "Invalid or expired token" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_logout_twice_fails(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test logging out twice with the same token fails."""
        headers = authenticated_user["headers"]

        # First logout
        response1 = await client.post("/api/auth/logout", headers=headers)
        assert response1.status_code == 200

        # Second logout with same token
        response2 = await client.post("/api/auth/logout", headers=headers)
        assert response2.status_code == 400
        assert "Token already invalidated" in response2.json()["detail"]

    @pytest.mark.asyncio
    async def test_logout_only_invalidates_own_token(
        self, client: AsyncClient, user_data: dict
    ):
        """Test that logout only invalidates the specific token used."""
        # Register user
        response = await client.post("/api/auth/register", json=user_data)
        assert response.status_code == 200

        # Login twice to get two different tokens
        login_data = {"email": user_data["email"], "password": user_data["password"]}

        login1_response = await client.post("/api/auth/login", json=login_data)
        assert login1_response.status_code == 200
        token1 = login1_response.json()["access_token"]

        login2_response = await client.post("/api/auth/login", json=login_data)
        assert login2_response.status_code == 200
        token2 = login2_response.json()["access_token"]

        # Logout with token1
        response = await client.post(
            "/api/auth/logout", headers={"Authorization": f"Bearer {token1}"}
        )
        assert response.status_code == 200

        # Token1 should be invalidated
        profile1_response = await client.get(
            "/api/users/me", headers={"Authorization": f"Bearer {token1}"}
        )
        assert profile1_response.status_code == 401
        assert "Token has been revoked" in profile1_response.json()["detail"]

        # Token2 should still work
        profile2_response = await client.get(
            "/api/users/me", headers={"Authorization": f"Bearer {token2}"}
        )
        assert profile2_response.status_code == 200
        assert profile2_response.json()["email"] == user_data["email"]


@pytest.mark.integration
class TestLogoutUserFlow:
    """Test complete user flows involving logout."""

    @pytest.mark.asyncio
    async def test_login_logout_login_flow(self, client: AsyncClient, user_data: dict):
        """Test user can login again after logout."""
        # Register
        register_response = await client.post("/api/auth/register", json=user_data)
        assert register_response.status_code == 200

        login_data = {"email": user_data["email"], "password": user_data["password"]}

        # First login
        login1_response = await client.post("/api/auth/login", json=login_data)
        assert login1_response.status_code == 200
        token1 = login1_response.json()["access_token"]

        # Logout
        logout_response = await client.post(
            "/api/auth/logout", headers={"Authorization": f"Bearer {token1}"}
        )
        assert logout_response.status_code == 200

        # Second login (should work)
        login2_response = await client.post("/api/auth/login", json=login_data)
        assert login2_response.status_code == 200
        token2 = login2_response.json()["access_token"]

        # New token should work
        profile_response = await client.get(
            "/api/users/me", headers={"Authorization": f"Bearer {token2}"}
        )
        assert profile_response.status_code == 200

    @pytest.mark.asyncio
    async def test_logout_does_not_affect_other_users(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test that one user's logout does not affect another user."""
        # Create and authenticate a second user
        user2_data = {
            "email": "user2@example.com",
            "password": "SecurePass123!",
            "full_name": "User Two",
        }
        register_response = await client.post("/api/auth/register", json=user2_data)
        assert register_response.status_code == 200

        login2_response = await client.post(
            "/api/auth/login",
            json={"email": user2_data["email"], "password": user2_data["password"]},
        )
        assert login2_response.status_code == 200
        token2 = login2_response.json()["access_token"]

        # First user logs out
        logout_response = await client.post(
            "/api/auth/logout", headers=authenticated_user["headers"]
        )
        assert logout_response.status_code == 200

        # First user's token should be invalid
        profile1_response = await client.get(
            "/api/users/me", headers=authenticated_user["headers"]
        )
        assert profile1_response.status_code == 401

        # Second user's token should still work
        profile2_response = await client.get(
            "/api/users/me", headers={"Authorization": f"Bearer {token2}"}
        )
        assert profile2_response.status_code == 200
        assert profile2_response.json()["email"] == user2_data["email"]

"""
Integration tests for User Management CRUD endpoints.
Phase B Implementation.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestUserProfileEndpoints:
    """Test user profile self-service endpoints."""

    @pytest.mark.asyncio
    async def test_get_profile(self, client: AsyncClient, authenticated_user: dict):
        """Test getting current user profile."""
        response = await client.get(
            "/api/users/me", headers=authenticated_user["headers"]
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == authenticated_user["id"]
        assert data["email"] == authenticated_user["email"]
        assert data["is_active"] is True
        assert data["is_admin"] is False

    @pytest.mark.asyncio
    async def test_update_profile_full_name(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test updating user's full name."""
        update_data = {"full_name": "New Full Name"}

        response = await client.patch(
            "/api/users/me", json=update_data, headers=authenticated_user["headers"]
        )

        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == "New Full Name"
        assert data["email"] == authenticated_user["email"]  # Other fields unchanged

    @pytest.mark.asyncio
    async def test_update_profile_github_username(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test updating user's GitHub username."""
        update_data = {"github_username": "testuser123"}

        response = await client.patch(
            "/api/users/me", json=update_data, headers=authenticated_user["headers"]
        )

        assert response.status_code == 200
        data = response.json()
        assert data["github_username"] == "testuser123"

    @pytest.mark.asyncio
    async def test_update_profile_career_interest(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test updating user's career interest."""
        update_data = {"career_interest": "Machine Learning"}

        response = await client.patch(
            "/api/users/me", json=update_data, headers=authenticated_user["headers"]
        )

        assert response.status_code == 200
        data = response.json()
        assert data["career_interest"] == "Machine Learning"

    @pytest.mark.asyncio
    async def test_update_profile_multiple_fields(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test updating multiple profile fields at once."""
        update_data = {
            "full_name": "Updated Name",
            "github_username": "updated_user",
            "career_interest": "Data Science",
        }

        response = await client.patch(
            "/api/users/me", json=update_data, headers=authenticated_user["headers"]
        )

        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == "Updated Name"
        assert data["github_username"] == "updated_user"
        assert data["career_interest"] == "Data Science"

    @pytest.mark.asyncio
    async def test_update_profile_empty_data(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test updating profile with empty data (no changes)."""
        response = await client.patch(
            "/api/users/me", json={}, headers=authenticated_user["headers"]
        )

        assert response.status_code == 200
        data = response.json()
        # Profile should remain unchanged
        assert data["email"] == authenticated_user["email"]

    @pytest.mark.asyncio
    async def test_update_profile_without_auth(self, client: AsyncClient):
        """Test updating profile without authentication fails."""
        update_data = {"full_name": "New Name"}

        response = await client.patch("/api/users/me", json=update_data)

        assert response.status_code == 401


@pytest.mark.integration
class TestPasswordChangeEndpoint:
    """Test password change endpoint."""

    @pytest.mark.asyncio
    async def test_change_password_success(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test successful password change."""
        password_data = {
            "current_password": authenticated_user["password"],
            "new_password": "NewPassword123!",
        }

        response = await client.put(
            "/api/users/me/password",
            json=password_data,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == 200
        assert "successfully" in response.json()["message"].lower()

        # Verify can login with new password
        login_response = await client.post(
            "/api/auth/login",
            json={"email": authenticated_user["email"], "password": "NewPassword123!"},
        )
        assert login_response.status_code == 200

    @pytest.mark.asyncio
    async def test_change_password_wrong_current(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test password change fails with wrong current password."""
        password_data = {
            "current_password": "WrongPassword123!",
            "new_password": "NewPassword123!",
        }

        response = await client.put(
            "/api/users/me/password",
            json=password_data,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == 400
        assert "incorrect" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_change_password_same_as_current(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test password change fails when new password is same as current."""
        password_data = {
            "current_password": authenticated_user["password"],
            "new_password": authenticated_user["password"],
        }

        response = await client.put(
            "/api/users/me/password",
            json=password_data,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == 400
        assert "different" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_change_password_too_short(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test password change fails when new password is too short."""
        password_data = {
            "current_password": authenticated_user["password"],
            "new_password": "short",  # Less than 8 characters
        }

        response = await client.put(
            "/api/users/me/password",
            json=password_data,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_change_password_without_auth(self, client: AsyncClient):
        """Test password change without authentication fails."""
        password_data = {
            "current_password": "OldPassword123!",
            "new_password": "NewPassword123!",
        }

        response = await client.put("/api/users/me/password", json=password_data)

        assert response.status_code == 401


@pytest.mark.integration
class TestAccountDeletionEndpoint:
    """Test account deletion endpoint."""

    @pytest.mark.asyncio
    async def test_delete_account_success(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test successful account deletion (soft delete)."""
        delete_data = {"password": authenticated_user["password"]}

        response = await client.request(
            "DELETE",
            "/api/users/me",
            json=delete_data,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == 200
        assert "successfully" in response.json()["message"].lower()

        # Verify user can no longer login
        login_response = await client.post(
            "/api/auth/login",
            json={
                "email": authenticated_user["email"],
                "password": authenticated_user["password"],
            },
        )
        # Should fail because user is deactivated
        assert login_response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_account_wrong_password(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test account deletion fails with wrong password."""
        delete_data = {"password": "WrongPassword123!"}

        response = await client.request(
            "DELETE",
            "/api/users/me",
            json=delete_data,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == 400
        assert "incorrect" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_delete_account_without_auth(self, client: AsyncClient):
        """Test account deletion without authentication fails."""
        delete_data = {"password": "SomePassword123!"}

        response = await client.request("DELETE", "/api/users/me", json=delete_data)

        assert response.status_code == 401


@pytest.mark.integration
class TestAdminUserListEndpoint:
    """Test admin user listing endpoint."""

    @pytest.mark.asyncio
    async def test_list_users_as_admin(
        self, client: AsyncClient, authenticated_admin: dict, multiple_users
    ):
        """Test admin can list all users."""
        response = await client.get(
            "/api/admin/users", headers=authenticated_admin["headers"]
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert "pages" in data
        # 15 test users + 1 admin user
        assert data["total"] >= 15

    @pytest.mark.asyncio
    async def test_list_users_pagination(
        self, client: AsyncClient, authenticated_admin: dict, multiple_users
    ):
        """Test user listing pagination."""
        # Get first page with 5 items per page
        response = await client.get(
            "/api/admin/users?page=1&per_page=5", headers=authenticated_admin["headers"]
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
        assert data["page"] == 1
        assert data["per_page"] == 5
        assert data["pages"] >= 3  # At least 15 users / 5 per page = 3 pages

    @pytest.mark.asyncio
    async def test_list_users_second_page(
        self, client: AsyncClient, authenticated_admin: dict, multiple_users
    ):
        """Test getting second page of users."""
        response = await client.get(
            "/api/admin/users?page=2&per_page=5", headers=authenticated_admin["headers"]
        )

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 2
        assert len(data["items"]) <= 5

    @pytest.mark.asyncio
    async def test_list_users_as_non_admin(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test non-admin cannot list users."""
        response = await client.get(
            "/api/admin/users", headers=authenticated_user["headers"]
        )

        assert response.status_code == 403
        assert "admin" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_list_users_without_auth(self, client: AsyncClient):
        """Test user listing without authentication fails."""
        response = await client.get("/api/admin/users")

        assert response.status_code == 401


@pytest.mark.integration
class TestAdminGetUserEndpoint:
    """Test admin get specific user endpoint."""

    @pytest.mark.asyncio
    async def test_admin_get_user(
        self, client: AsyncClient, authenticated_admin: dict, registered_user: dict
    ):
        """Test admin can get any user by ID."""
        response = await client.get(
            f"/api/admin/users/{registered_user['id']}",
            headers=authenticated_admin["headers"],
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == registered_user["id"]
        assert data["email"] == registered_user["email"]

    @pytest.mark.asyncio
    async def test_admin_get_nonexistent_user(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        """Test getting non-existent user returns 404."""
        # Use a valid UUID format that doesn't exist
        nonexistent_uuid = "00000000-0000-4000-8000-000000000000"
        response = await client.get(
            f"/api/admin/users/{nonexistent_uuid}",
            headers=authenticated_admin["headers"],
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_non_admin_get_user(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test non-admin cannot get other users."""
        response = await client.get(
            f"/api/admin/users/{authenticated_user['id']}",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == 403


@pytest.mark.integration
class TestAdminUpdateUserEndpoint:
    """Test admin update user endpoint."""

    @pytest.mark.asyncio
    async def test_admin_update_user(
        self, client: AsyncClient, authenticated_admin: dict, registered_user: dict
    ):
        """Test admin can update any user."""
        update_data = {"full_name": "Admin Updated Name"}

        response = await client.patch(
            f"/api/admin/users/{registered_user['id']}",
            json=update_data,
            headers=authenticated_admin["headers"],
        )

        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == "Admin Updated Name"

    @pytest.mark.asyncio
    async def test_admin_update_user_role(
        self, client: AsyncClient, authenticated_admin: dict, registered_user: dict
    ):
        """Test admin can change user role."""
        update_data = {"role": "student"}

        response = await client.patch(
            f"/api/admin/users/{registered_user['id']}",
            json=update_data,
            headers=authenticated_admin["headers"],
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "student"

    @pytest.mark.asyncio
    async def test_admin_deactivate_user(
        self, client: AsyncClient, authenticated_admin: dict, registered_user: dict
    ):
        """Test admin can deactivate a user."""
        update_data = {"is_active": False}

        response = await client.patch(
            f"/api/admin/users/{registered_user['id']}",
            json=update_data,
            headers=authenticated_admin["headers"],
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False

    @pytest.mark.asyncio
    async def test_admin_grant_admin_privileges(
        self, client: AsyncClient, authenticated_admin: dict, registered_user: dict
    ):
        """Test admin can grant admin privileges to another user."""
        update_data = {"is_admin": True}

        response = await client.patch(
            f"/api/admin/users/{registered_user['id']}",
            json=update_data,
            headers=authenticated_admin["headers"],
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_admin"] is True

    @pytest.mark.asyncio
    async def test_admin_cannot_demote_self(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        """Test admin cannot remove their own admin privileges."""
        update_data = {"is_admin": False}

        response = await client.patch(
            f"/api/admin/users/{authenticated_admin['id']}",
            json=update_data,
            headers=authenticated_admin["headers"],
        )

        assert response.status_code == 400
        assert "own admin" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_non_admin_update_user(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test non-admin cannot update other users."""
        update_data = {"full_name": "Hacked Name"}

        response = await client.patch(
            f"/api/admin/users/{authenticated_user['id']}",
            json=update_data,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == 403


@pytest.mark.integration
class TestAdminDeleteUserEndpoint:
    """Test admin delete user endpoint."""

    @pytest.mark.asyncio
    async def test_admin_soft_delete_user(
        self, client: AsyncClient, authenticated_admin: dict, registered_user: dict
    ):
        """Test admin can soft delete (deactivate) a user."""
        response = await client.delete(
            f"/api/admin/users/{registered_user['id']}",
            headers=authenticated_admin["headers"],
        )

        assert response.status_code == 200
        assert "deactivated" in response.json()["message"].lower()

        # Verify user is deactivated but still exists
        get_response = await client.get(
            f"/api/admin/users/{registered_user['id']}",
            headers=authenticated_admin["headers"],
        )
        assert get_response.status_code == 200
        assert get_response.json()["is_active"] is False

    @pytest.mark.asyncio
    async def test_admin_hard_delete_user(
        self, client: AsyncClient, authenticated_admin: dict, registered_user: dict
    ):
        """Test admin can hard delete (permanently remove) a user."""
        response = await client.delete(
            f"/api/admin/users/{registered_user['id']}?hard_delete=true",
            headers=authenticated_admin["headers"],
        )

        assert response.status_code == 200
        assert "permanently" in response.json()["message"].lower()

        # Verify user no longer exists
        get_response = await client.get(
            f"/api/admin/users/{registered_user['id']}",
            headers=authenticated_admin["headers"],
        )
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_admin_cannot_delete_self(
        self, client: AsyncClient, authenticated_admin: dict
    ):
        """Test admin cannot delete their own account via admin endpoint."""
        response = await client.delete(
            f"/api/admin/users/{authenticated_admin['id']}",
            headers=authenticated_admin["headers"],
        )

        assert response.status_code == 400
        assert "own account" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_non_admin_delete_user(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test non-admin cannot delete users."""
        response = await client.delete(
            f"/api/admin/users/{authenticated_user['id']}",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == 403


@pytest.mark.integration
class TestAdminReactivateUserEndpoint:
    """Test admin reactivate user endpoint."""

    @pytest.mark.asyncio
    async def test_admin_reactivate_user(
        self, client: AsyncClient, authenticated_admin: dict, registered_user: dict
    ):
        """Test admin can reactivate a deactivated user."""
        # First deactivate the user
        await client.patch(
            f"/api/admin/users/{registered_user['id']}",
            json={"is_active": False},
            headers=authenticated_admin["headers"],
        )

        # Then reactivate
        response = await client.post(
            f"/api/admin/users/{registered_user['id']}/reactivate",
            headers=authenticated_admin["headers"],
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_admin_reactivate_already_active_user(
        self, client: AsyncClient, authenticated_admin: dict, registered_user: dict
    ):
        """Test reactivating an already active user fails."""
        response = await client.post(
            f"/api/admin/users/{registered_user['id']}/reactivate",
            headers=authenticated_admin["headers"],
        )

        assert response.status_code == 400
        assert "already active" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_non_admin_reactivate_user(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test non-admin cannot reactivate users."""
        response = await client.post(
            f"/api/admin/users/{authenticated_user['id']}/reactivate",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == 403


@pytest.mark.integration
class TestDeactivatedUserAccess:
    """Test that deactivated users cannot access the API."""

    @pytest.mark.asyncio
    async def test_deactivated_user_cannot_access_profile(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test deactivated user cannot access their profile."""
        # Delete the account (soft delete)
        delete_data = {"password": authenticated_user["password"]}
        await client.request(
            "DELETE",
            "/api/users/me",
            json=delete_data,
            headers=authenticated_user["headers"],
        )

        # Try to access profile with the same token
        response = await client.get(
            "/api/users/me", headers=authenticated_user["headers"]
        )

        assert response.status_code == 401
        assert "deactivated" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_deactivated_user_cannot_login(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test deactivated user cannot log in again."""
        # Delete the account
        delete_data = {"password": authenticated_user["password"]}
        await client.request(
            "DELETE",
            "/api/users/me",
            json=delete_data,
            headers=authenticated_user["headers"],
        )

        # Try to login
        login_data = {
            "email": authenticated_user["email"],
            "password": authenticated_user["password"],
        }
        response = await client.post("/api/auth/login", json=login_data)

        assert response.status_code == 401

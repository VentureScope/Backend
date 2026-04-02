"""End-to-end tests with real database operations."""

import pytest
import asyncio
from httpx import AsyncClient
from sqlalchemy import text

from app.models.user import User


@pytest.mark.e2e
class TestDatabaseIntegration:
    """Test real database operations end-to-end."""

    @pytest.mark.asyncio
    async def test_user_persistence_across_requests(
        self, client: AsyncClient, db_session, user_data
    ):
        """Test that user data persists correctly in database."""
        # Register user
        register_response = await client.post("/api/auth/register", json=user_data)
        assert register_response.status_code == 200
        user_id = register_response.json()["id"]

        # Verify user exists in database
        result = await db_session.execute(
            text("SELECT * FROM users WHERE id = :user_id"), {"user_id": user_id}
        )
        db_user = result.fetchone()
        assert db_user is not None
        assert db_user.email == user_data["email"]
        assert db_user.full_name == user_data["full_name"]

        # Login and verify token works
        login_response = await client.post(
            "/api/auth/login",
            json={"email": user_data["email"], "password": user_data["password"]},
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        # Access protected route
        headers = {"Authorization": f"Bearer {token}"}
        profile_response = await client.get("/api/users/me", headers=headers)
        assert profile_response.status_code == 200
        assert profile_response.json()["id"] == user_id

    @pytest.mark.asyncio
    async def test_email_uniqueness_constraint(self, client: AsyncClient, user_data):
        """Test that email uniqueness is enforced at database level."""
        # First registration
        response1 = await client.post("/api/auth/register", json=user_data)
        assert response1.status_code == 200

        # Second registration with same email should fail
        response2 = await client.post("/api/auth/register", json=user_data)
        assert response2.status_code == 400
        assert "Email already registered" in response2.json()["detail"]

    @pytest.mark.asyncio
    async def test_password_hashing_security(
        self, client: AsyncClient, db_session, user_data
    ):
        """Test that passwords are properly hashed in database."""
        # Register user
        register_response = await client.post("/api/auth/register", json=user_data)
        assert register_response.status_code == 200
        user_id = register_response.json()["id"]

        # Check that password is hashed in database
        result = await db_session.execute(
            text("SELECT password_hash FROM users WHERE id = :user_id"),
            {"user_id": user_id},
        )
        db_password_hash = result.fetchone().password_hash

        # Password should be hashed, not plain text
        assert db_password_hash != user_data["password"]
        assert len(db_password_hash) > 50  # Bcrypt hashes are longer
        assert db_password_hash.startswith("$2b$")  # Bcrypt prefix

    @pytest.mark.asyncio
    async def test_user_timestamps(self, client: AsyncClient, db_session, user_data):
        """Test that created_at and updated_at timestamps are set correctly."""
        import datetime

        # Record time before registration
        before_time = datetime.datetime.now(datetime.timezone.utc)

        # Small delay to ensure time difference
        await asyncio.sleep(0.1)

        # Register user
        register_response = await client.post("/api/auth/register", json=user_data)
        assert register_response.status_code == 200
        user_id = register_response.json()["id"]

        await asyncio.sleep(0.1)
        after_time = datetime.datetime.now(datetime.timezone.utc)

        # Check timestamps in database
        result = await db_session.execute(
            text("SELECT created_at, updated_at FROM users WHERE id = :user_id"),
            {"user_id": user_id},
        )
        row = result.fetchone()

        created_at = row.created_at
        updated_at = row.updated_at

        # Timestamps should be between before and after times
        assert before_time <= created_at <= after_time
        assert before_time <= updated_at <= after_time

        # For new records, created_at and updated_at should be very close
        time_diff = abs((updated_at - created_at).total_seconds())
        assert time_diff < 1  # Within 1 second

    @pytest.mark.asyncio
    async def test_concurrent_user_registration(self, client: AsyncClient):
        """Test concurrent user registrations don't cause conflicts."""

        async def register_user(email_suffix):
            user_data = {
                "email": f"concurrent_user_{email_suffix}@example.com",
                "password": "Test123!",
                "full_name": f"Concurrent User {email_suffix}",
            }
            return await client.post("/api/auth/register", json=user_data)

        # Register 5 users concurrently
        tasks = [register_user(i) for i in range(5)]
        responses = await asyncio.gather(*tasks)

        # All registrations should succeed
        for response in responses:
            assert response.status_code == 200

        # All users should have different IDs
        user_ids = [response.json()["id"] for response in responses]
        assert len(set(user_ids)) == 5  # All unique IDs


@pytest.mark.e2e
class TestAuthenticationFlow:
    """Test complete authentication flows end-to-end."""

    @pytest.mark.asyncio
    async def test_login_token_validation_cycle(self, client: AsyncClient, user_data):
        """Test complete login and token validation cycle."""
        # Register user
        register_response = await client.post("/api/auth/register", json=user_data)
        assert register_response.status_code == 200

        # Login multiple times - each should generate different tokens
        login_data = {"email": user_data["email"], "password": user_data["password"]}

        tokens = []
        for _ in range(3):
            login_response = await client.post("/api/auth/login", json=login_data)
            assert login_response.status_code == 200
            token = login_response.json()["access_token"]
            tokens.append(token)

            # Each token should work for accessing protected routes
            headers = {"Authorization": f"Bearer {token}"}
            profile_response = await client.get("/api/users/me", headers=headers)
            assert profile_response.status_code == 200

        # All tokens should be different (stateless JWT)
        assert len(set(tokens)) == 3

    @pytest.mark.asyncio
    async def test_invalid_credentials_attempts(self, client: AsyncClient, user_data):
        """Test multiple invalid login attempts."""
        # Register user first
        register_response = await client.post("/api/auth/register", json=user_data)
        assert register_response.status_code == 200

        # Try various invalid login attempts
        invalid_attempts = [
            {"email": user_data["email"], "password": "WrongPassword"},
            {"email": "wrong@email.com", "password": user_data["password"]},
            {"email": "wrong@email.com", "password": "WrongPassword"},
        ]

        for attempt in invalid_attempts:
            response = await client.post("/api/auth/login", json=attempt)
            assert response.status_code == 401
            assert "Invalid email or password" in response.json()["detail"]

        # Valid login should still work after failed attempts
        valid_login = {"email": user_data["email"], "password": user_data["password"]}
        response = await client.post("/api/auth/login", json=valid_login)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_token_isolation_between_users(self, client: AsyncClient):
        """Test that user tokens are properly isolated."""
        # Register two users
        user1_data = {
            "email": "isolation1@example.com",
            "password": "Test123!",
            "full_name": "Isolation User 1",
        }
        user2_data = {
            "email": "isolation2@example.com",
            "password": "Test456!",
            "full_name": "Isolation User 2",
        }

        # Register both users
        user1_response = await client.post("/api/auth/register", json=user1_data)
        user2_response = await client.post("/api/auth/register", json=user2_data)
        assert user1_response.status_code == 200
        assert user2_response.status_code == 200

        user1_id = user1_response.json()["id"]
        user2_id = user2_response.json()["id"]

        # Login both users
        token1_response = await client.post(
            "/api/auth/login",
            json={"email": user1_data["email"], "password": user1_data["password"]},
        )
        token2_response = await client.post(
            "/api/auth/login",
            json={"email": user2_data["email"], "password": user2_data["password"]},
        )

        token1 = token1_response.json()["access_token"]
        token2 = token2_response.json()["access_token"]

        # Each user should only access their own profile
        profile1 = await client.get(
            "/api/users/me", headers={"Authorization": f"Bearer {token1}"}
        )
        profile2 = await client.get(
            "/api/users/me", headers={"Authorization": f"Bearer {token2}"}
        )

        assert profile1.status_code == 200
        assert profile2.status_code == 200

        profile1_data = profile1.json()
        profile2_data = profile2.json()

        assert profile1_data["id"] == user1_id
        assert profile1_data["email"] == user1_data["email"]
        assert profile2_data["id"] == user2_id
        assert profile2_data["email"] == user2_data["email"]

        # Cross-token access should not work
        assert profile1_data["id"] != profile2_data["id"]
        assert profile1_data["email"] != profile2_data["email"]


@pytest.mark.e2e
@pytest.mark.slow
class TestDatabaseConstraints:
    """Test database constraints and edge cases."""

    @pytest.mark.asyncio
    async def test_long_text_fields(self, client: AsyncClient):
        """Test handling of maximum length text fields."""
        # Test with maximum allowed lengths
        long_user_data = {
            "email": "test@" + "a" * 240 + ".com",  # Close to 255 limit
            "password": "Test123!",
            "full_name": "A" * 255,  # Maximum length
            "career_interest": "B" * 500,  # Maximum length
            "role": "professional",
        }

        response = await client.post("/api/auth/register", json=long_user_data)
        assert response.status_code == 200

        # Verify data was stored correctly
        user_data = response.json()
        assert user_data["full_name"] == long_user_data["full_name"]
        assert user_data["career_interest"] == long_user_data["career_interest"]

    @pytest.mark.asyncio
    async def test_special_characters_in_data(self, client: AsyncClient):
        """Test handling of special characters in user data."""
        special_user_data = {
            "email": "special.chars+test@example.com",
            "password": "Test123!@#$%",
            "full_name": "José María O'Connor-Smith",
            "career_interest": "AI/ML & Data Science (Français) 中文",
            "role": "professional",
        }

        response = await client.post("/api/auth/register", json=special_user_data)
        assert response.status_code == 200

        # Login should work with special characters
        login_response = await client.post(
            "/api/auth/login",
            json={
                "email": special_user_data["email"],
                "password": special_user_data["password"],
            },
        )
        assert login_response.status_code == 200

        # Profile should preserve special characters
        token = login_response.json()["access_token"]
        profile_response = await client.get(
            "/api/users/me", headers={"Authorization": f"Bearer {token}"}
        )
        profile_data = profile_response.json()

        assert profile_data["full_name"] == special_user_data["full_name"]
        assert profile_data["career_interest"] == special_user_data["career_interest"]

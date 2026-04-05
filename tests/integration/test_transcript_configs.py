"""
Integration tests for Transcript Configuration API endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestTranscriptConfigEndpoints:
    """Test transcript configuration API endpoints."""

    @pytest.mark.asyncio
    async def test_get_config_auto_creates_default(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test getting config auto-creates default if none exists."""
        response = await client.get(
            "/api/transcript-configs/", headers=authenticated_user["headers"]
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == authenticated_user["id"]
        assert data["gpa_scale"] == 4.0  # Default US 4.0 scale
        assert "A+" in data["grading_schema"]
        assert isinstance(data["grade_display_order"], list)

    @pytest.mark.asyncio
    async def test_get_config_without_auth_fails(self, client: AsyncClient):
        """Test getting config without authentication fails."""
        response = await client.get("/api/transcript-configs/")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_config_success(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test updating config with valid data."""
        update_data = {
            "gpa_scale": 5.0,
            "grading_schema": {"A": 5.0, "B": 4.0, "C": 3.0, "D": 2.0, "F": 0.0},
            "grade_display_order": ["A", "B", "C", "D", "F"],
        }

        response = await client.put(
            "/api/transcript-configs/",
            json=update_data,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == 200
        data = response.json()
        assert data["gpa_scale"] == 5.0
        assert data["grading_schema"]["A"] == 5.0
        assert data["grade_display_order"] == ["A", "B", "C", "D", "F"]

    @pytest.mark.asyncio
    async def test_update_config_schema_display_mismatch(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test updating config fails when display order doesn't match schema."""
        update_data = {
            "gpa_scale": 4.0,
            "grading_schema": {"A": 4.0, "B": 3.0},
            "grade_display_order": ["A"],  # Missing "B"
        }

        response = await client.put(
            "/api/transcript-configs/",
            json=update_data,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == 422
        assert "Missing in display order" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_config_invalid_gpa_scale(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test updating config fails with invalid GPA scale."""
        update_data = {
            "gpa_scale": -1.0,  # Invalid negative
            "grading_schema": {"A": 4.0},
            "grade_display_order": ["A"],
        }

        response = await client.put(
            "/api/transcript-configs/",
            json=update_data,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_reset_config_to_default(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test resetting config to default."""
        # First update to non-default
        update_data = {
            "gpa_scale": 10.0,
            "grading_schema": {"10": 10.0},
            "grade_display_order": ["10"],
        }
        await client.put(
            "/api/transcript-configs/",
            json=update_data,
            headers=authenticated_user["headers"],
        )

        # Reset to default
        response = await client.delete(
            "/api/transcript-configs/", headers=authenticated_user["headers"]
        )

        assert response.status_code == 204

        # Verify it's back to default
        get_response = await client.get(
            "/api/transcript-configs/", headers=authenticated_user["headers"]
        )
        data = get_response.json()
        assert data["gpa_scale"] == 4.0  # Default

    @pytest.mark.asyncio
    async def test_get_presets(self, client: AsyncClient):
        """Test getting available grading presets."""
        response = await client.get("/api/transcript-configs/presets")

        assert response.status_code == 200
        data = response.json()
        assert "presets" in data
        assert len(data["presets"]) >= 5  # At least 5 presets

        preset_names = [p["name"] for p in data["presets"]]
        assert "US 4.0 Scale (Standard)" in preset_names
        assert "European 10-Point Scale" in preset_names

    @pytest.mark.asyncio
    async def test_use_preset_config(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test applying a preset configuration."""
        # Get presets
        presets_response = await client.get("/api/transcript-configs/presets")
        presets = presets_response.json()["presets"]

        # Use European 10-point preset
        european_preset = next(p for p in presets if "European" in p["name"])

        update_data = {
            "gpa_scale": european_preset["gpa_scale"],
            "grading_schema": european_preset["grading_schema"],
            "grade_display_order": european_preset["grade_display_order"],
        }

        response = await client.put(
            "/api/transcript-configs/",
            json=update_data,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == 200
        data = response.json()
        assert data["gpa_scale"] == 10.0

    @pytest.mark.asyncio
    async def test_config_isolation_between_users(
        self, client: AsyncClient, authenticated_user: dict, user_data: dict
    ):
        """Test that config changes for one user don't affect another."""
        # First user updates config
        update_data = {
            "gpa_scale": 5.0,
            "grading_schema": {"A": 5.0},
            "grade_display_order": ["A"],
        }
        await client.put(
            "/api/transcript-configs/",
            json=update_data,
            headers=authenticated_user["headers"],
        )

        # Register second user
        user_data["email"] = "second.user@test.com"
        await client.post("/api/auth/register", json=user_data)
        login_response = await client.post(
            "/api/auth/login",
            json={"email": user_data["email"], "password": user_data["password"]},
        )
        second_user_token = login_response.json()["access_token"]
        second_user_headers = {"Authorization": f"Bearer {second_user_token}"}

        # Second user gets default config
        response = await client.get(
            "/api/transcript-configs/", headers=second_user_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["gpa_scale"] == 4.0  # Default, not 5.0

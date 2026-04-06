"""
Integration tests for Academic Transcript API endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestTranscriptEndpoints:
    """Test academic transcript API endpoints."""

    def _create_transcript_payload(self, student_id="12345", sgpa=4.0, cgpa=4.0):
        """Helper to create valid transcript payload."""
        return {
            "transcript_data": {
                "student_id": student_id,
                "semesters": [
                    {
                        "academic_year": "2023/2024",
                        "semester": "First Semester",
                        "year_level": "First Year",
                        "courses": [
                            {
                                "code": "CS101",
                                "title": "Introduction to Programming",
                                "credit_hours": 3.0,
                                "grade": "A",
                                "points": 12.0,
                            },
                            {
                                "code": "MATH101",
                                "title": "Calculus I",
                                "credit_hours": 4.0,
                                "grade": "B+",
                                "points": 13.2,
                            },
                        ],
                        "semester_summary": {
                            "credit_hours": 7.0,
                            "points": 25.2,
                            "sgpa": sgpa,
                            "academic_status": "Good Standing",
                        },
                        "cumulative_summary": {
                            "credit_hours": 7.0,
                            "points": 25.2,
                            "cgpa": cgpa,
                        },
                    }
                ],
            }
        }

    @pytest.mark.asyncio
    async def test_upload_transcript_success(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test successful transcript upload."""
        payload = self._create_transcript_payload()

        response = await client.post(
            "/api/transcripts/", json=payload, headers=authenticated_user["headers"]
        )

        assert response.status_code == 201
        data = response.json()
        assert data["user_id"] == authenticated_user["id"]
        assert data["student_id"] == "12345"
        assert data["version"] == 1
        assert data["is_first_upload"] is True
        assert data["versions_deleted"] == 0
        assert "uploaded_at" in data

    @pytest.mark.asyncio
    async def test_upload_transcript_without_auth(self, client: AsyncClient):
        """Test upload fails without authentication."""
        payload = self._create_transcript_payload()

        response = await client.post("/api/transcripts/", json=payload)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_transcript_invalid_data(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test upload fails with invalid transcript data."""
        payload = {
            "transcript_data": {
                "semesters": []  # Empty semesters (invalid)
            }
        }

        response = await client.post(
            "/api/transcripts/", json=payload, headers=authenticated_user["headers"]
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_upload_transcript_gpa_exceeds_scale(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test upload fails when GPA exceeds configured scale."""
        # Set GPA scale to 3.0
        config_update = {
            "gpa_scale": 3.0,
            "grading_schema": {"A": 3.0, "B": 2.0},
            "grade_display_order": ["A", "B"],
        }
        await client.put(
            "/api/transcript-configs/",
            json=config_update,
            headers=authenticated_user["headers"],
        )

        # Try to upload transcript with GPA 4.0 (exceeds 3.0 scale)
        payload = self._create_transcript_payload(sgpa=4.0, cgpa=4.0)

        response = await client.post(
            "/api/transcripts/", json=payload, headers=authenticated_user["headers"]
        )

        assert response.status_code == 400
        assert "exceeds configured GPA scale" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_multiple_versions(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test uploading multiple transcript versions."""
        payload = self._create_transcript_payload()

        # Upload version 1
        response1 = await client.post(
            "/api/transcripts/", json=payload, headers=authenticated_user["headers"]
        )
        assert response1.status_code == 201
        assert response1.json()["version"] == 1

        # Upload version 2
        response2 = await client.post(
            "/api/transcripts/", json=payload, headers=authenticated_user["headers"]
        )
        assert response2.status_code == 201
        data2 = response2.json()
        assert data2["version"] == 2
        assert data2["is_first_upload"] is False

        # Upload version 3
        response3 = await client.post(
            "/api/transcripts/", json=payload, headers=authenticated_user["headers"]
        )
        assert response3.status_code == 201
        assert response3.json()["version"] == 3

    @pytest.mark.asyncio
    async def test_upload_version_cleanup(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test that old versions are cleaned up (keeps latest 3)."""
        payload = self._create_transcript_payload()

        # Upload 5 versions
        for _ in range(5):
            await client.post(
                "/api/transcripts/", json=payload, headers=authenticated_user["headers"]
            )

        # List all transcripts
        response = await client.get(
            "/api/transcripts/", headers=authenticated_user["headers"]
        )

        data = response.json()
        assert data["total_count"] == 3  # Only latest 3 kept
        assert len(data["transcripts"]) == 3

        # Verify versions are 5, 4, 3 (newest to oldest)
        versions = [t["version"] for t in data["transcripts"]]
        assert versions == [5, 4, 3]

    @pytest.mark.asyncio
    async def test_get_all_transcripts(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test getting all transcript versions."""
        payload = self._create_transcript_payload()

        # Upload 2 versions
        await client.post(
            "/api/transcripts/", json=payload, headers=authenticated_user["headers"]
        )
        await client.post(
            "/api/transcripts/", json=payload, headers=authenticated_user["headers"]
        )

        # Get all transcripts
        response = await client.get(
            "/api/transcripts/", headers=authenticated_user["headers"]
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 2
        assert len(data["transcripts"]) == 2
        assert data["transcripts"][0]["version"] == 2  # Newest first
        assert data["transcripts"][1]["version"] == 1

    @pytest.mark.asyncio
    async def test_get_latest_transcript(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test getting only the latest transcript."""
        payload = self._create_transcript_payload()

        # Upload 2 versions
        await client.post(
            "/api/transcripts/", json=payload, headers=authenticated_user["headers"]
        )
        await client.post(
            "/api/transcripts/", json=payload, headers=authenticated_user["headers"]
        )

        # Get latest
        response = await client.get(
            "/api/transcripts/latest", headers=authenticated_user["headers"]
        )

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == 2  # Latest version

    @pytest.mark.asyncio
    async def test_get_latest_transcript_none_exist(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test getting latest transcript when none exist."""
        response = await client.get(
            "/api/transcripts/latest", headers=authenticated_user["headers"]
        )

        assert response.status_code == 404
        assert "No transcripts found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_transcript_by_id(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test getting specific transcript by ID."""
        payload = self._create_transcript_payload()

        # Upload transcript
        upload_response = await client.post(
            "/api/transcripts/", json=payload, headers=authenticated_user["headers"]
        )
        transcript_id = upload_response.json()["id"]

        # Get by ID
        response = await client.get(
            f"/api/transcripts/{transcript_id}", headers=authenticated_user["headers"]
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == transcript_id
        assert data["student_id"] == "12345"

    @pytest.mark.asyncio
    async def test_get_transcript_by_id_not_found(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test getting non-existent transcript."""
        response = await client.get(
            "/api/transcripts/non-existent-id", headers=authenticated_user["headers"]
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_transcript(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test deleting a specific transcript."""
        payload = self._create_transcript_payload()

        # Upload transcript
        upload_response = await client.post(
            "/api/transcripts/", json=payload, headers=authenticated_user["headers"]
        )
        transcript_id = upload_response.json()["id"]

        # Delete
        response = await client.delete(
            f"/api/transcripts/{transcript_id}", headers=authenticated_user["headers"]
        )

        assert response.status_code == 204

        # Verify deleted
        get_response = await client.get(
            f"/api/transcripts/{transcript_id}", headers=authenticated_user["headers"]
        )
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_all_transcripts(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test deleting all transcripts for a user."""
        payload = self._create_transcript_payload()

        # Upload 3 transcripts
        for _ in range(3):
            await client.post(
                "/api/transcripts/", json=payload, headers=authenticated_user["headers"]
            )

        # Delete all
        response = await client.delete(
            "/api/transcripts/", headers=authenticated_user["headers"]
        )

        assert response.status_code == 204

        # Verify all deleted
        list_response = await client.get(
            "/api/transcripts/", headers=authenticated_user["headers"]
        )
        assert list_response.json()["total_count"] == 0

    @pytest.mark.asyncio
    async def test_student_id_consistency_enforcement(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test that student_id must be consistent across uploads."""
        # Upload first transcript with student_id "12345"
        payload1 = self._create_transcript_payload(student_id="12345")
        await client.post(
            "/api/transcripts/", json=payload1, headers=authenticated_user["headers"]
        )

        # Try to upload second transcript with different student_id
        payload2 = self._create_transcript_payload(student_id="99999")
        response = await client.post(
            "/api/transcripts/", json=payload2, headers=authenticated_user["headers"]
        )

        assert response.status_code == 400
        assert "Student ID mismatch" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_rate_limiting(self, client: AsyncClient, authenticated_user: dict):
        """Test rate limiting (10 uploads per hour)."""
        payload = self._create_transcript_payload()

        # Upload 11 transcripts rapidly
        responses = []
        for i in range(11):
            response = await client.post(
                "/api/transcripts/", json=payload, headers=authenticated_user["headers"]
            )
            responses.append(response)

        # First 10 should succeed
        for i in range(10):
            assert responses[i].status_code in [
                201,
                400,
            ]  # 400 if student_id check fails

        # 11th should be rate limited
        assert responses[10].status_code == 429
        assert "Rate limit exceeded" in responses[10].json()["detail"]

    @pytest.mark.asyncio
    async def test_recommend_grading_config(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test getting grading configuration recommendation."""
        payload = self._create_transcript_payload()

        response = await client.post(
            "/api/transcripts/recommend-config",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == 200
        data = response.json()
        assert "detected_grades" in data
        assert "recommended_preset" in data
        assert "confidence" in data
        assert "reason" in data
        assert "suggested_config" in data

        # Should detect A and B+ grades
        assert "A" in data["detected_grades"]
        assert "B+" in data["detected_grades"]

    @pytest.mark.asyncio
    async def test_transcript_isolation_between_users(
        self, client: AsyncClient, authenticated_user: dict, user_data: dict
    ):
        """Test that users can only access their own transcripts."""
        # First user uploads transcript
        payload = self._create_transcript_payload()
        upload_response = await client.post(
            "/api/transcripts/", json=payload, headers=authenticated_user["headers"]
        )
        first_user_transcript_id = upload_response.json()["id"]

        # Register and login second user
        user_data["email"] = "second.user@test.com"
        await client.post("/api/auth/register", json=user_data)
        login_response = await client.post(
            "/api/auth/login",
            json={"email": user_data["email"], "password": user_data["password"]},
        )
        second_user_token = login_response.json()["access_token"]
        second_user_headers = {"Authorization": f"Bearer {second_user_token}"}

        # Second user tries to access first user's transcript
        response = await client.get(
            f"/api/transcripts/{first_user_transcript_id}", headers=second_user_headers
        )

        assert response.status_code == 404  # Not found (ownership check)

        # Second user should see empty list
        list_response = await client.get(
            "/api/transcripts/", headers=second_user_headers
        )
        assert list_response.json()["total_count"] == 0

    @pytest.mark.asyncio
    async def test_upload_with_null_student_id(
        self, client: AsyncClient, authenticated_user: dict
    ):
        """Test uploading transcript with null student_id."""
        payload = {
            "transcript_data": {
                "student_id": None,
                "semesters": [
                    {
                        "academic_year": "2023/2024",
                        "semester": "First Semester",
                        "courses": [
                            {
                                "code": "CS101",
                                "title": "Programming",
                                "credit_hours": 3.0,
                                "grade": "A",
                                "points": 12.0,
                            }
                        ],
                        "semester_summary": {"credit_hours": 3.0, "sgpa": 4.0},
                        "cumulative_summary": {"credit_hours": 3.0, "cgpa": 4.0},
                    }
                ],
            }
        }

        response = await client.post(
            "/api/transcripts/", json=payload, headers=authenticated_user["headers"]
        )

        assert response.status_code == 201
        assert response.json()["student_id"] is None

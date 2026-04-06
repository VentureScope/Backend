"""Unit tests for TranscriptService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.transcript_service import TranscriptService
from app.models.academic_transcript import AcademicTranscript
from app.models.transcript_config import TranscriptConfig
from app.schemas.academic_transcript import (
    TranscriptCreate,
    TranscriptDataSchema,
    SemesterSchema,
    CourseSchema,
    SemesterSummarySchema,
    CumulativeSummarySchema,
)


@pytest.mark.unit
class TestTranscriptService:
    """Test TranscriptService business logic."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.mock_db = MagicMock(spec=AsyncSession)
        self.service = TranscriptService(self.mock_db)

    def _create_test_transcript_data(self):
        """Helper to create test transcript data."""
        return TranscriptCreate(
            transcript_data=TranscriptDataSchema(
                student_id="12345",
                semesters=[
                    SemesterSchema(
                        academic_year="2023/2024",
                        semester="First Semester",
                        year_level="First Year",
                        courses=[
                            CourseSchema(
                                code="CS101",
                                title="Programming",
                                credit_hours=3.0,
                                grade="A",
                                points=12.0,
                            )
                        ],
                        semester_summary=SemesterSummarySchema(
                            credit_hours=3.0,
                            points=12.0,
                            sgpa=4.0,
                            academic_status="Good Standing",
                        ),
                        cumulative_summary=CumulativeSummarySchema(
                            credit_hours=3.0, points=12.0, cgpa=4.0
                        ),
                    )
                ],
            )
        )

    @pytest.mark.asyncio
    async def test_create_transcript_success_first_upload(self):
        """Test successful transcript creation for first upload."""
        # Arrange
        user_id = "user-id"
        data = self._create_test_transcript_data()

        config = TranscriptConfig(
            id="config-id",
            user_id=user_id,
            gpa_scale=4.0,
            grading_schema={"A": 4.0},
            grade_display_order=["A"],
        )

        self.service.config_service.get_or_create_default = AsyncMock(
            return_value=config
        )
        self.service.repo.count_by_user = AsyncMock(return_value=0)  # First upload
        self.service.repo.get_next_version_number = AsyncMock(return_value=1)
        self.service.repo.create = AsyncMock(side_effect=lambda x: x)
        self.service.repo.delete_old_versions = AsyncMock(return_value=0)

        # Act
        with patch("uuid.uuid4", return_value="mocked-uuid"):
            (
                transcript,
                versions_deleted,
                is_first_upload,
            ) = await self.service.create_transcript(user_id, data)

        # Assert
        assert transcript.user_id == user_id
        assert transcript.student_id == "12345"
        assert transcript.version == 1
        assert is_first_upload is True
        assert versions_deleted == 0
        self.service.repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_transcript_gpa_exceeds_scale(self):
        """Test creation fails when GPA exceeds configured scale."""
        # Arrange
        user_id = "user-id"
        data = self._create_test_transcript_data()

        # Config with lower scale
        config = TranscriptConfig(
            id="config-id",
            user_id=user_id,
            gpa_scale=3.0,  # Lower than the 4.0 in transcript
            grading_schema={"A": 3.0},
            grade_display_order=["A"],
        )

        self.service.config_service.get_or_create_default = AsyncMock(
            return_value=config
        )

        # Act & Assert
        with pytest.raises(ValueError, match="exceeds configured GPA scale"):
            await self.service.create_transcript(user_id, data)

    @pytest.mark.asyncio
    async def test_create_transcript_student_id_mismatch(self):
        """Test creation fails when student_id doesn't match existing."""
        # Arrange
        user_id = "user-id"
        data = self._create_test_transcript_data()

        config = TranscriptConfig(
            id="config-id",
            user_id=user_id,
            gpa_scale=4.0,
            grading_schema={"A": 4.0},
            grade_display_order=["A"],
        )

        existing_transcript = AcademicTranscript(
            id="existing-id",
            user_id=user_id,
            student_id="99999",  # Different student ID
            transcript_data={},
            version=1,
        )

        self.service.config_service.get_or_create_default = AsyncMock(
            return_value=config
        )
        self.service.repo.count_by_user = AsyncMock(return_value=1)  # Not first upload
        self.service.repo.get_all_by_user = AsyncMock(
            return_value=[existing_transcript]
        )

        # Act & Assert
        with pytest.raises(ValueError, match="Student ID mismatch"):
            await self.service.create_transcript(user_id, data)

    @pytest.mark.asyncio
    async def test_create_transcript_cleans_old_versions(self):
        """Test that old versions are cleaned up after creation."""
        # Arrange
        user_id = "user-id"
        data = self._create_test_transcript_data()

        config = TranscriptConfig(
            id="config-id",
            user_id=user_id,
            gpa_scale=4.0,
            grading_schema={"A": 4.0},
            grade_display_order=["A"],
        )

        self.service.config_service.get_or_create_default = AsyncMock(
            return_value=config
        )
        self.service.repo.count_by_user = AsyncMock(return_value=3)
        self.service.repo.get_next_version_number = AsyncMock(return_value=4)
        self.service.repo.get_all_by_user = AsyncMock(return_value=[])
        self.service.repo.get_by_student_id = AsyncMock(return_value=None)
        self.service.repo.create = AsyncMock(side_effect=lambda x: x)
        self.service.repo.delete_old_versions = AsyncMock(
            return_value=1
        )  # Deleted 1 old version

        # Act
        with patch("uuid.uuid4", return_value="mocked-uuid"):
            (
                transcript,
                versions_deleted,
                is_first_upload,
            ) = await self.service.create_transcript(user_id, data)

        # Assert
        assert versions_deleted == 1
        assert is_first_upload is False
        self.service.repo.delete_old_versions.assert_called_once_with(user_id, 3)

    @pytest.mark.asyncio
    async def test_get_user_transcripts(self):
        """Test getting all user transcripts."""
        # Arrange
        user_id = "user-id"
        transcripts = [
            AcademicTranscript(
                id="t1",
                user_id=user_id,
                student_id="123",
                transcript_data={},
                version=1,
            )
        ]

        self.service.repo.get_all_by_user = AsyncMock(return_value=transcripts)

        # Act
        result = await self.service.get_user_transcripts(user_id)

        # Assert
        assert result == transcripts
        self.service.repo.get_all_by_user.assert_called_once_with(user_id)

    @pytest.mark.asyncio
    async def test_get_latest_transcript(self):
        """Test getting latest transcript."""
        # Arrange
        user_id = "user-id"
        latest = AcademicTranscript(
            id="latest",
            user_id=user_id,
            student_id="123",
            transcript_data={},
            version=3,
        )

        self.service.repo.get_latest_by_user = AsyncMock(return_value=latest)

        # Act
        result = await self.service.get_latest_transcript(user_id)

        # Assert
        assert result == latest
        self.service.repo.get_latest_by_user.assert_called_once_with(user_id)

    @pytest.mark.asyncio
    async def test_get_transcript_by_id_success(self):
        """Test getting transcript by ID successfully."""
        # Arrange
        transcript_id = "t-id"
        user_id = "user-id"
        transcript = AcademicTranscript(
            id=transcript_id,
            user_id=user_id,
            student_id="123",
            transcript_data={},
            version=1,
        )

        self.service.repo.get_by_id = AsyncMock(return_value=transcript)

        # Act
        result = await self.service.get_transcript_by_id(transcript_id, user_id)

        # Assert
        assert result == transcript
        self.service.repo.get_by_id.assert_called_once_with(transcript_id, user_id)

    @pytest.mark.asyncio
    async def test_get_transcript_by_id_not_found(self):
        """Test getting transcript by ID raises error when not found."""
        # Arrange
        transcript_id = "t-id"
        user_id = "user-id"

        self.service.repo.get_by_id = AsyncMock(return_value=None)

        # Act & Assert
        with pytest.raises(ValueError, match="Transcript not found"):
            await self.service.get_transcript_by_id(transcript_id, user_id)

    @pytest.mark.asyncio
    async def test_delete_transcript_success(self):
        """Test deleting transcript successfully."""
        # Arrange
        transcript_id = "t-id"
        user_id = "user-id"
        transcript = AcademicTranscript(
            id=transcript_id,
            user_id=user_id,
            student_id="123",
            transcript_data={},
            version=1,
        )

        self.service.repo.get_by_id = AsyncMock(return_value=transcript)
        self.service.repo.delete = AsyncMock()

        # Act
        await self.service.delete_transcript(transcript_id, user_id)

        # Assert
        self.service.repo.delete.assert_called_once_with(transcript)

    @pytest.mark.asyncio
    async def test_delete_all_transcripts(self):
        """Test deleting all transcripts for a user."""
        # Arrange
        user_id = "user-id"

        self.service.repo.delete_all_by_user = AsyncMock(return_value=3)

        # Act
        result = await self.service.delete_all_transcripts(user_id)

        # Assert
        assert result == 3
        self.service.repo.delete_all_by_user.assert_called_once_with(user_id)

    @pytest.mark.asyncio
    async def test_get_grade_recommendation(self):
        """Test getting grade recommendation based on transcript data."""
        # Arrange
        user_id = "user-id"
        data = self._create_test_transcript_data()

        # Act
        with patch.object(
            TranscriptService, "_extract_grades", return_value={"A", "B+"}
        ):
            result = await self.service.get_grade_recommendation(user_id, data)

        # Assert
        assert result.recommended_preset is not None
        assert result.confidence in ["high", "medium", "low"]

    def test_extract_grades(self):
        """Test extracting grades from transcript data."""
        # Arrange
        data = TranscriptCreate(
            transcript_data=TranscriptDataSchema(
                student_id="123",
                semesters=[
                    SemesterSchema(
                        academic_year="2023/2024",
                        semester="First",
                        courses=[
                            CourseSchema(
                                code="C1",
                                title="T1",
                                credit_hours=3,
                                grade="A",
                                points=12,
                            ),
                            CourseSchema(
                                code="C2",
                                title="T2",
                                credit_hours=3,
                                grade="B+",
                                points=10,
                            ),
                            CourseSchema(
                                code="C3",
                                title="T3",
                                credit_hours=3,
                                grade="A",
                                points=12,
                            ),
                        ],
                        semester_summary=SemesterSummarySchema(
                            credit_hours=9, sgpa=3.8
                        ),
                        cumulative_summary=CumulativeSummarySchema(
                            credit_hours=9, cgpa=3.8
                        ),
                    )
                ],
            )
        )

        # Act
        result = self.service._extract_grades(data)

        # Assert
        assert result == {"A", "B+"}
        assert len(result) == 2

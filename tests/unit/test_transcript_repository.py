"""Unit tests for TranscriptRepository."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.transcript_repository import TranscriptRepository
from app.models.academic_transcript import AcademicTranscript


@pytest.mark.unit
class TestTranscriptRepository:
    """Test TranscriptRepository database operations."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.mock_db = MagicMock(spec=AsyncSession)
        self.repo = TranscriptRepository(self.mock_db)

    @pytest.mark.asyncio
    async def test_create_transcript_success(self):
        """Test successful transcript creation."""
        # Arrange
        transcript = AcademicTranscript(
            id="transcript-id",
            user_id="user-id",
            student_id="12345",
            transcript_data={"semesters": []},
            version=1,
            uploaded_at=None,
        )

        self.mock_db.add = MagicMock()
        self.mock_db.commit = AsyncMock()
        self.mock_db.refresh = AsyncMock()

        # Act
        result = await self.repo.create(transcript)

        # Assert
        assert result == transcript
        self.mock_db.add.assert_called_once_with(transcript)
        self.mock_db.commit.assert_called_once()
        self.mock_db.refresh.assert_called_once_with(transcript)

    @pytest.mark.asyncio
    async def test_get_by_id_exists_and_owned(self):
        """Test getting transcript by ID when it exists and belongs to user."""
        # Arrange
        transcript_id = "transcript-id"
        user_id = "user-id"
        expected_transcript = AcademicTranscript(
            id=transcript_id,
            user_id=user_id,
            student_id="12345",
            transcript_data={"semesters": []},
            version=1,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_transcript
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.repo.get_by_id(transcript_id, user_id)

        # Assert
        assert result == expected_transcript
        self.mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_id_not_owned(self):
        """Test getting transcript by ID returns None for different user."""
        # Arrange
        transcript_id = "transcript-id"
        user_id = "different-user-id"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.repo.get_by_id(transcript_id, user_id)

        # Assert
        assert result is None
        self.mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_by_user_returns_ordered_list(self):
        """Test getting all transcripts for user returns ordered list."""
        # Arrange
        user_id = "user-id"
        transcripts = [
            AcademicTranscript(
                id="t3",
                user_id=user_id,
                student_id="123",
                transcript_data={},
                version=3,
            ),
            AcademicTranscript(
                id="t2",
                user_id=user_id,
                student_id="123",
                transcript_data={},
                version=2,
            ),
            AcademicTranscript(
                id="t1",
                user_id=user_id,
                student_id="123",
                transcript_data={},
                version=1,
            ),
        ]

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = transcripts
        mock_result.scalars.return_value = mock_scalars
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.repo.get_all_by_user(user_id)

        # Assert
        assert len(result) == 3
        assert result == transcripts
        self.mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_by_user_empty_list(self):
        """Test getting all transcripts returns empty list when none exist."""
        # Arrange
        user_id = "user-id"

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.repo.get_all_by_user(user_id)

        # Assert
        assert result == []
        self.mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_latest_by_user_exists(self):
        """Test getting latest transcript when it exists."""
        # Arrange
        user_id = "user-id"
        latest_transcript = AcademicTranscript(
            id="latest",
            user_id=user_id,
            student_id="123",
            transcript_data={},
            version=3,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = latest_transcript
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.repo.get_latest_by_user(user_id)

        # Assert
        assert result == latest_transcript
        self.mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_latest_by_user_none_exist(self):
        """Test getting latest transcript when none exist."""
        # Arrange
        user_id = "user-id"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.repo.get_latest_by_user(user_id)

        # Assert
        assert result is None
        self.mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_next_version_number_no_existing(self):
        """Test get_next_version_number returns 1 when no transcripts exist."""
        # Arrange
        user_id = "user-id"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.repo.get_next_version_number(user_id)

        # Assert
        assert result == 1
        self.mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_next_version_number_existing_versions(self):
        """Test get_next_version_number increments max version."""
        # Arrange
        user_id = "user-id"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = 3  # Max version is 3
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.repo.get_next_version_number(user_id)

        # Assert
        assert result == 4
        self.mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_count_by_user(self):
        """Test counting transcripts for a user."""
        # Arrange
        user_id = "user-id"

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.repo.count_by_user(user_id)

        # Assert
        assert result == 5
        self.mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_transcript(self):
        """Test deleting a transcript."""
        # Arrange
        transcript = AcademicTranscript(
            id="t-id", user_id="u-id", student_id="123", transcript_data={}, version=1
        )

        self.mock_db.delete = AsyncMock()
        self.mock_db.commit = AsyncMock()

        # Act
        await self.repo.delete(transcript)

        # Assert
        self.mock_db.delete.assert_called_once_with(transcript)
        self.mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_all_by_user(self):
        """Test deleting all transcripts for a user."""
        # Arrange
        user_id = "user-id"

        mock_result = MagicMock()
        mock_result.rowcount = 3
        self.mock_db.execute = AsyncMock(return_value=mock_result)
        self.mock_db.commit = AsyncMock()

        # Act
        result = await self.repo.delete_all_by_user(user_id)

        # Assert
        assert result == 3
        self.mock_db.execute.assert_called_once()
        self.mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_old_versions_keeps_latest_3(self):
        """Test delete_old_versions keeps only latest 3 versions."""
        # Arrange
        user_id = "user-id"
        transcripts = [
            AcademicTranscript(
                id="t5",
                user_id=user_id,
                student_id="123",
                transcript_data={},
                version=5,
            ),
            AcademicTranscript(
                id="t4",
                user_id=user_id,
                student_id="123",
                transcript_data={},
                version=4,
            ),
            AcademicTranscript(
                id="t3",
                user_id=user_id,
                student_id="123",
                transcript_data={},
                version=3,
            ),
            AcademicTranscript(
                id="t2",
                user_id=user_id,
                student_id="123",
                transcript_data={},
                version=2,
            ),
            AcademicTranscript(
                id="t1",
                user_id=user_id,
                student_id="123",
                transcript_data={},
                version=1,
            ),
        ]

        # Mock get_all_by_user
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = transcripts
        mock_result.scalars.return_value = mock_scalars
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        self.mock_db.delete = AsyncMock()
        self.mock_db.commit = AsyncMock()

        # Act
        result = await self.repo.delete_old_versions(user_id, keep_count=3)

        # Assert
        assert result == 2  # Deleted 2 oldest versions
        assert self.mock_db.delete.call_count == 2
        self.mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_old_versions_no_deletion_needed(self):
        """Test delete_old_versions when count is <= keep_count."""
        # Arrange
        user_id = "user-id"
        transcripts = [
            AcademicTranscript(
                id="t2",
                user_id=user_id,
                student_id="123",
                transcript_data={},
                version=2,
            ),
            AcademicTranscript(
                id="t1",
                user_id=user_id,
                student_id="123",
                transcript_data={},
                version=1,
            ),
        ]

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = transcripts
        mock_result.scalars.return_value = mock_scalars
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        self.mock_db.delete = AsyncMock()

        # Act
        result = await self.repo.delete_old_versions(user_id, keep_count=3)

        # Assert
        assert result == 0
        self.mock_db.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_by_student_id(self):
        """Test getting transcripts by student_id."""
        # Arrange
        student_id = "12345"
        transcripts = [
            AcademicTranscript(
                id="t1",
                user_id="u1",
                student_id=student_id,
                transcript_data={},
                version=1,
            ),
            AcademicTranscript(
                id="t2",
                user_id="u2",
                student_id=student_id,
                transcript_data={},
                version=1,
            ),
        ]

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = transcripts
        mock_result.scalars.return_value = mock_scalars
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.repo.get_by_student_id(student_id)

        # Assert
        assert len(result) == 2
        assert result == transcripts
        self.mock_db.execute.assert_called_once()

"""Unit tests for TranscriptConfigRepository."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.transcript_config_repository import TranscriptConfigRepository
from app.models.transcript_config import TranscriptConfig


@pytest.mark.unit
class TestTranscriptConfigRepository:
    """Test TranscriptConfigRepository database operations."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.mock_db = MagicMock(spec=AsyncSession)
        self.repo = TranscriptConfigRepository(self.mock_db)

    @pytest.mark.asyncio
    async def test_create_config_success(self):
        """Test successful config creation."""
        # Arrange
        config_to_create = TranscriptConfig(
            id="test-config-id",
            user_id="test-user-id",
            gpa_scale=4.0,
            grading_schema={"A": 4.0, "B": 3.0, "C": 2.0},
            grade_display_order=["A", "B", "C"],
        )

        self.mock_db.add = MagicMock()
        self.mock_db.commit = AsyncMock()
        self.mock_db.refresh = AsyncMock()

        # Act
        result = await self.repo.create(config_to_create)

        # Assert
        assert result == config_to_create
        self.mock_db.add.assert_called_once_with(config_to_create)
        self.mock_db.commit.assert_called_once()
        self.mock_db.refresh.assert_called_once_with(config_to_create)

    @pytest.mark.asyncio
    async def test_get_by_user_id_exists(self):
        """Test getting config by user_id when config exists."""
        # Arrange
        user_id = "test-user-id"
        expected_config = TranscriptConfig(
            id="test-config-id",
            user_id=user_id,
            gpa_scale=4.0,
            grading_schema={"A": 4.0},
            grade_display_order=["A"],
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_config
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.repo.get_by_user_id(user_id)

        # Assert
        assert result == expected_config
        self.mock_db.execute.assert_called_once()
        mock_result.scalar_one_or_none.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_user_id_not_exists(self):
        """Test getting config by user_id when config doesn't exist."""
        # Arrange
        user_id = "nonexistent-user-id"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.repo.get_by_user_id(user_id)

        # Assert
        assert result is None
        self.mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_id_exists(self):
        """Test getting config by ID when config exists."""
        # Arrange
        config_id = "test-config-id"
        expected_config = TranscriptConfig(
            id=config_id,
            user_id="user-id",
            gpa_scale=5.0,
            grading_schema={"A": 5.0},
            grade_display_order=["A"],
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_config
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.repo.get_by_id(config_id)

        # Assert
        assert result == expected_config
        self.mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_config_success(self):
        """Test successful config update."""
        # Arrange
        config = TranscriptConfig(
            id="test-id",
            user_id="user-id",
            gpa_scale=10.0,
            grading_schema={"10": 10.0, "9": 9.0},
            grade_display_order=["10", "9"],
        )

        self.mock_db.commit = AsyncMock()
        self.mock_db.refresh = AsyncMock()

        # Act
        result = await self.repo.update(config)

        # Assert
        assert result == config
        self.mock_db.commit.assert_called_once()
        self.mock_db.refresh.assert_called_once_with(config)

    @pytest.mark.asyncio
    async def test_delete_config_success(self):
        """Test successful config deletion."""
        # Arrange
        config = TranscriptConfig(
            id="test-id",
            user_id="user-id",
            gpa_scale=4.0,
            grading_schema={"A": 4.0},
            grade_display_order=["A"],
        )

        self.mock_db.delete = AsyncMock()
        self.mock_db.commit = AsyncMock()

        # Act
        await self.repo.delete(config)

        # Assert
        self.mock_db.delete.assert_called_once_with(config)
        self.mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_for_user_true(self):
        """Test exists_for_user returns True when config exists."""
        # Arrange
        user_id = "test-user-id"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "some-config-id"
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.repo.exists_for_user(user_id)

        # Assert
        assert result is True
        self.mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_for_user_false(self):
        """Test exists_for_user returns False when config doesn't exist."""
        # Arrange
        user_id = "nonexistent-user-id"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.repo.exists_for_user(user_id)

        # Assert
        assert result is False
        self.mock_db.execute.assert_called_once()

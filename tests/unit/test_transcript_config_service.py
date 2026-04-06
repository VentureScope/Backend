"""Unit tests for TranscriptConfigService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.transcript_config_service import TranscriptConfigService
from app.models.transcript_config import TranscriptConfig
from app.schemas.transcript_config import TranscriptConfigUpdate


@pytest.mark.unit
class TestTranscriptConfigService:
    """Test TranscriptConfigService business logic."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.mock_db = MagicMock(spec=AsyncSession)
        self.service = TranscriptConfigService(self.mock_db)

    @pytest.mark.asyncio
    async def test_get_or_create_default_existing_config(self):
        """Test get_or_create_default returns existing config when it exists."""
        # Arrange
        user_id = "test-user-id"
        existing_config = TranscriptConfig(
            id="config-id",
            user_id=user_id,
            gpa_scale=4.0,
            grading_schema={"A": 4.0},
            grade_display_order=["A"],
        )

        self.service.repo.get_by_user_id = AsyncMock(return_value=existing_config)
        self.service.repo.create = AsyncMock()

        # Act
        result = await self.service.get_or_create_default(user_id)

        # Assert
        assert result == existing_config
        self.service.repo.get_by_user_id.assert_called_once_with(user_id)
        self.service.repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_or_create_default_creates_new_config(self):
        """Test get_or_create_default creates new config when none exists."""
        # Arrange
        user_id = "test-user-id"

        self.service.repo.get_by_user_id = AsyncMock(return_value=None)
        self.service.repo.create = AsyncMock(side_effect=lambda x: x)

        # Act
        with patch("uuid.uuid4", return_value="mocked-uuid"):
            result = await self.service.get_or_create_default(user_id)

        # Assert
        assert result.user_id == user_id
        assert result.gpa_scale == 4.0  # Default US 4.0 scale
        assert "A+" in result.grading_schema
        self.service.repo.get_by_user_id.assert_called_once_with(user_id)
        self.service.repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_config_fails_if_exists(self):
        """Test create_config raises error if config already exists."""
        # Arrange
        user_id = "test-user-id"
        existing_config = TranscriptConfig(
            id="config-id",
            user_id=user_id,
            gpa_scale=4.0,
            grading_schema={"A": 4.0},
            grade_display_order=["A"],
        )
        data = TranscriptConfigUpdate(
            gpa_scale=5.0, grading_schema={"A": 5.0}, grade_display_order=["A"]
        )

        self.service.repo.get_by_user_id = AsyncMock(return_value=existing_config)

        # Act & Assert
        with pytest.raises(ValueError, match="Configuration already exists"):
            await self.service.create_config(user_id, data)

    @pytest.mark.asyncio
    async def test_update_config_creates_if_not_exists(self):
        """Test update_config creates new config if none exists."""
        # Arrange
        user_id = "test-user-id"
        data = TranscriptConfigUpdate(
            gpa_scale=10.0,
            grading_schema={"10": 10.0, "9": 9.0},
            grade_display_order=["10", "9"],
        )

        self.service.repo.get_by_user_id = AsyncMock(return_value=None)
        self.service.repo.create = AsyncMock(side_effect=lambda x: x)

        # Act
        with patch("uuid.uuid4", return_value="mocked-uuid"):
            result = await self.service.update_config(user_id, data)

        # Assert
        assert result.user_id == user_id
        assert result.gpa_scale == 10.0
        assert result.grading_schema == {"10": 10.0, "9": 9.0}
        self.service.repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_config_updates_existing(self):
        """Test update_config updates existing config."""
        # Arrange
        user_id = "test-user-id"
        existing_config = TranscriptConfig(
            id="config-id",
            user_id=user_id,
            gpa_scale=4.0,
            grading_schema={"A": 4.0},
            grade_display_order=["A"],
        )
        data = TranscriptConfigUpdate(
            gpa_scale=5.0,
            grading_schema={"A": 5.0, "B": 4.0},
            grade_display_order=["A", "B"],
        )

        self.service.repo.get_by_user_id = AsyncMock(return_value=existing_config)
        self.service.repo.update = AsyncMock(return_value=existing_config)

        # Act
        result = await self.service.update_config(user_id, data)

        # Assert
        assert result.gpa_scale == 5.0
        assert result.grading_schema == {"A": 5.0, "B": 4.0}
        assert result.grade_display_order == ["A", "B"]
        self.service.repo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_config_success(self):
        """Test delete_config deletes existing config."""
        # Arrange
        user_id = "test-user-id"
        existing_config = TranscriptConfig(
            id="config-id",
            user_id=user_id,
            gpa_scale=4.0,
            grading_schema={"A": 4.0},
            grade_display_order=["A"],
        )

        self.service.repo.get_by_user_id = AsyncMock(return_value=existing_config)
        self.service.repo.delete = AsyncMock()

        # Act
        await self.service.delete_config(user_id)

        # Assert
        self.service.repo.delete.assert_called_once_with(existing_config)

    @pytest.mark.asyncio
    async def test_delete_config_no_config_exists(self):
        """Test delete_config handles case when no config exists."""
        # Arrange
        user_id = "test-user-id"

        self.service.repo.get_by_user_id = AsyncMock(return_value=None)
        self.service.repo.delete = AsyncMock()

        # Act
        await self.service.delete_config(user_id)

        # Assert
        self.service.repo.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_reset_to_default(self):
        """Test reset_to_default deletes and recreates default config."""
        # Arrange
        user_id = "test-user-id"

        self.service.repo.get_by_user_id = AsyncMock(return_value=None)
        self.service.repo.create = AsyncMock(side_effect=lambda x: x)

        # Act
        with patch("uuid.uuid4", return_value="mocked-uuid"):
            result = await self.service.reset_to_default(user_id)

        # Assert
        assert result.user_id == user_id
        assert result.gpa_scale == 4.0  # Default US 4.0
        self.service.repo.create.assert_called_once()

    def test_get_presets(self):
        """Test get_presets returns all available presets."""
        # Act
        result = TranscriptConfigService.get_presets()

        # Assert
        assert len(result.presets) == 5
        preset_names = [p.name for p in result.presets]
        assert "US 4.0 Scale (Standard)" in preset_names
        assert "European 10-Point Scale" in preset_names

    def test_recommend_grading_system_us_letter_grades(self):
        """Test recommendation for US letter grades with modifiers."""
        # Arrange
        detected_grades = {"A+", "A", "B+", "B-", "C"}

        # Act
        result = TranscriptConfigService.recommend_grading_system(detected_grades)

        # Assert
        assert result.recommended_preset == "US 4.0 Scale (Standard)"
        assert result.confidence == "high"
        assert "A+" in result.reason or "plus/minus" in result.reason

    def test_recommend_grading_system_simple_letters(self):
        """Test recommendation for simple letter grades."""
        # Arrange
        detected_grades = {"A", "B", "C", "D", "F"}

        # Act
        result = TranscriptConfigService.recommend_grading_system(detected_grades)

        # Assert
        assert result.recommended_preset == "US 4.0 Scale (Standard)"
        assert (
            result.confidence == "high"
        )  # Simple grades are subset of us_letter_grades

    def test_recommend_grading_system_numeric_10_point(self):
        """Test recommendation for 10-point numeric grades."""
        # Arrange
        detected_grades = {"10", "9", "8", "7", "6"}

        # Act
        result = TranscriptConfigService.recommend_grading_system(detected_grades)

        # Assert
        assert result.recommended_preset == "European 10-Point Scale"
        assert result.confidence == "high"

    def test_recommend_grading_system_uk_classification(self):
        """Test recommendation for UK classification grades."""
        # Arrange
        detected_grades = {"First", "2:1", "2:2", "Third"}

        # Act
        result = TranscriptConfigService.recommend_grading_system(detected_grades)

        # Assert
        assert result.recommended_preset == "UK Classification System"
        assert result.confidence == "high"

    def test_recommend_grading_system_empty_grades(self):
        """Test recommendation with no gradable grades."""
        # Arrange
        detected_grades = {"-", "W", "IP"}

        # Act
        result = TranscriptConfigService.recommend_grading_system(detected_grades)

        # Assert
        assert result.recommended_preset == "US 4.0 Scale (Standard)"
        assert result.confidence == "low"

    def test_recommend_grading_system_unknown_pattern(self):
        """Test recommendation with unrecognized grading pattern."""
        # Arrange
        detected_grades = {"XYZ", "ABC", "DEF"}

        # Act
        result = TranscriptConfigService.recommend_grading_system(detected_grades)

        # Assert
        assert result.recommended_preset == "US 4.0 Scale (Standard)"
        assert result.confidence == "low"
        assert "Unrecognized" in result.reason

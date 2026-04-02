"""Unit tests for UserRepository."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user_repository import UserRepository
from app.models.user import User


@pytest.mark.unit
class TestUserRepository:
    """Test UserRepository database operations."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.mock_db = MagicMock(spec=AsyncSession)
        self.repo = UserRepository(self.mock_db)

    @pytest.mark.asyncio
    async def test_get_by_id_user_exists(self):
        """Test getting user by ID when user exists."""
        # Arrange
        user_id = "test-user-id"
        expected_user = User(
            id=user_id, email="test@example.com", password_hash="hashed_password"
        )

        # Mock the database query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = expected_user
        mock_result.scalars.return_value = mock_scalars
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.repo.get_by_id(user_id)

        # Assert
        assert result == expected_user
        self.mock_db.execute.assert_called_once()
        mock_result.scalars.assert_called_once()
        mock_scalars.one_or_none.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_id_user_not_exists(self):
        """Test getting user by ID when user doesn't exist."""
        # Arrange
        user_id = "nonexistent-user-id"

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = None
        mock_result.scalars.return_value = mock_scalars
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.repo.get_by_id(user_id)

        # Assert
        assert result is None
        self.mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_email_user_exists(self):
        """Test getting user by email when user exists."""
        # Arrange
        email = "test@example.com"
        expected_user = User(id="test-id", email=email, password_hash="hashed_password")

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = expected_user
        mock_result.scalars.return_value = mock_scalars
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.repo.get_by_email(email)

        # Assert
        assert result == expected_user
        self.mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_email_user_not_exists(self):
        """Test getting user by email when user doesn't exist."""
        # Arrange
        email = "nonexistent@example.com"

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = None
        mock_result.scalars.return_value = mock_scalars
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.repo.get_by_email(email)

        # Assert
        assert result is None
        self.mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_email_case_sensitivity(self):
        """Test that email lookup handles case correctly."""
        # Arrange
        email = "Test@Example.Com"  # Mixed case
        expected_user = User(
            id="test-id",
            email=email.lower(),  # Assuming emails are stored in lowercase
            password_hash="hashed_password",
        )

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = expected_user
        mock_result.scalars.return_value = mock_scalars
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.repo.get_by_email(email)

        # Assert
        assert result == expected_user
        self.mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_user_success(self):
        """Test successful user creation."""
        # Arrange
        user_to_create = User(
            email="new@example.com",
            password_hash="hashed_password",
            full_name="New User",
            role="professional",
        )

        # Mock database operations
        self.mock_db.add = MagicMock()
        self.mock_db.flush = AsyncMock()
        self.mock_db.refresh = AsyncMock()

        # Act
        result = await self.repo.create(user_to_create)

        # Assert
        assert result == user_to_create
        self.mock_db.add.assert_called_once_with(user_to_create)
        self.mock_db.flush.assert_called_once()
        self.mock_db.refresh.assert_called_once_with(user_to_create)

    @pytest.mark.asyncio
    async def test_create_user_with_minimal_data(self):
        """Test creating user with minimal required data."""
        # Arrange
        user_to_create = User(
            email="minimal@example.com",
            password_hash="hashed_password",
            # No full_name, career_interest, etc.
        )

        self.mock_db.add = MagicMock()
        self.mock_db.flush = AsyncMock()
        self.mock_db.refresh = AsyncMock()

        # Act
        result = await self.repo.create(user_to_create)

        # Assert
        assert result == user_to_create
        self.mock_db.add.assert_called_once_with(user_to_create)
        self.mock_db.flush.assert_called_once()
        self.mock_db.refresh.assert_called_once_with(user_to_create)

    @pytest.mark.asyncio
    async def test_create_user_database_error(self):
        """Test user creation when database operation fails."""
        # Arrange
        user_to_create = User(
            email="error@example.com", password_hash="hashed_password"
        )

        self.mock_db.add = MagicMock()
        self.mock_db.flush = AsyncMock(side_effect=Exception("Database error"))

        # Act & Assert
        with pytest.raises(Exception, match="Database error"):
            await self.repo.create(user_to_create)

        self.mock_db.add.assert_called_once_with(user_to_create)
        self.mock_db.flush.assert_called_once()
        self.mock_db.refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_by_id_with_none_parameter(self):
        """Test get_by_id with None parameter."""
        # Arrange
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = None
        mock_result.scalars.return_value = mock_scalars
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.repo.get_by_id(None)

        # Assert
        assert result is None
        self.mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_email_with_empty_string(self):
        """Test get_by_email with empty string."""
        # Arrange
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.one_or_none.return_value = None
        mock_result.scalars.return_value = mock_scalars
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await self.repo.get_by_email("")

        # Assert
        assert result is None
        self.mock_db.execute.assert_called_once()

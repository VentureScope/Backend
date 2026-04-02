"""Unit tests for AuthService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth_service import AuthService
from app.schemas.user import UserCreate, UserLogin
from app.models.user import User


@pytest.mark.unit
class TestAuthService:
    """Test AuthService registration and login logic."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.mock_db = MagicMock(spec=AsyncSession)
        self.auth_service = AuthService(self.mock_db)
        self.auth_service.repo = AsyncMock()

    @pytest.mark.asyncio
    async def test_register_success(self):
        """Test successful user registration."""
        # Arrange
        user_data = UserCreate(
            email="test@example.com",
            password="Test123!",
            full_name="Test User",
            career_interest="Software Development",
            role="professional",
        )

        # Mock repository methods
        self.auth_service.repo.get_by_email.return_value = None  # No existing user
        created_user = User(
            id="test-id",
            email=user_data.email,
            password_hash="hashed_password",
            full_name=user_data.full_name,
            career_interest=user_data.career_interest,
            role=user_data.role,
        )
        self.auth_service.repo.create.return_value = created_user

        # Act
        with patch(
            "app.services.auth_service.hash_password", return_value="hashed_password"
        ):
            result = await self.auth_service.register(user_data)

        # Assert
        assert result == created_user
        self.auth_service.repo.get_by_email.assert_called_once_with(user_data.email)
        self.auth_service.repo.create.assert_called_once()

        # Verify the user object passed to create has correct attributes
        created_user_arg = self.auth_service.repo.create.call_args[0][0]
        assert created_user_arg.email == user_data.email
        assert created_user_arg.password_hash == "hashed_password"
        assert created_user_arg.full_name == user_data.full_name
        assert created_user_arg.career_interest == user_data.career_interest
        assert created_user_arg.role == user_data.role

    @pytest.mark.asyncio
    async def test_register_email_already_exists(self):
        """Test registration fails when email already exists."""
        # Arrange
        user_data = UserCreate(
            email="existing@example.com", password="Test123!", full_name="Test User"
        )

        existing_user = User(
            id="existing-id", email=user_data.email, password_hash="existing_hash"
        )
        self.auth_service.repo.get_by_email.return_value = existing_user

        # Act & Assert
        with pytest.raises(ValueError, match="Email already registered"):
            await self.auth_service.register(user_data)

        self.auth_service.repo.get_by_email.assert_called_once_with(user_data.email)
        self.auth_service.repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_register_with_minimal_data(self):
        """Test registration with minimal required data."""
        # Arrange
        user_data = UserCreate(
            email="minimal@example.com",
            password="Test123!",
            # No full_name, career_interest - they should be None
        )

        self.auth_service.repo.get_by_email.return_value = None
        created_user = User(
            id="test-id",
            email=user_data.email,
            password_hash="hashed_password",
            full_name=None,
            career_interest=None,
            role="professional",  # Default role
        )
        self.auth_service.repo.create.return_value = created_user

        # Act
        with patch(
            "app.services.auth_service.hash_password", return_value="hashed_password"
        ):
            result = await self.auth_service.register(user_data)

        # Assert
        assert result == created_user
        created_user_arg = self.auth_service.repo.create.call_args[0][0]
        assert created_user_arg.full_name is None
        assert created_user_arg.career_interest is None
        assert created_user_arg.role == "professional"

    @pytest.mark.asyncio
    async def test_login_success(self):
        """Test successful user login."""
        # Arrange
        login_data = UserLogin(email="test@example.com", password="Test123!")

        user = User(
            id="user-id", email=login_data.email, password_hash="hashed_password"
        )
        self.auth_service.repo.get_by_email.return_value = user

        # Act
        with (
            patch("app.services.auth_service.verify_password", return_value=True),
            patch(
                "app.services.auth_service.create_access_token",
                return_value="access_token_123",
            ),
        ):
            result = await self.auth_service.login(login_data)

        # Assert
        assert result == "access_token_123"
        self.auth_service.repo.get_by_email.assert_called_once_with(login_data.email)

    @pytest.mark.asyncio
    async def test_login_user_not_found(self):
        """Test login fails when user doesn't exist."""
        # Arrange
        login_data = UserLogin(email="nonexistent@example.com", password="Test123!")

        self.auth_service.repo.get_by_email.return_value = None

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid email or password"):
            await self.auth_service.login(login_data)

        self.auth_service.repo.get_by_email.assert_called_once_with(login_data.email)

    @pytest.mark.asyncio
    async def test_login_wrong_password(self):
        """Test login fails with wrong password."""
        # Arrange
        login_data = UserLogin(email="test@example.com", password="WrongPassword")

        user = User(
            id="user-id", email=login_data.email, password_hash="hashed_password"
        )
        self.auth_service.repo.get_by_email.return_value = user

        # Act & Assert
        with patch("app.services.auth_service.verify_password", return_value=False):
            with pytest.raises(ValueError, match="Invalid email or password"):
                await self.auth_service.login(login_data)

        self.auth_service.repo.get_by_email.assert_called_once_with(login_data.email)

    @pytest.mark.asyncio
    async def test_login_creates_token_with_user_id(self):
        """Test that login creates token with correct user ID."""
        # Arrange
        login_data = UserLogin(email="test@example.com", password="Test123!")

        user_id = "specific-user-id-123"
        user = User(id=user_id, email=login_data.email, password_hash="hashed_password")
        self.auth_service.repo.get_by_email.return_value = user

        # Act
        with (
            patch("app.services.auth_service.verify_password", return_value=True),
            patch("app.services.auth_service.create_access_token") as mock_create_token,
        ):
            mock_create_token.return_value = "token_123"

            result = await self.auth_service.login(login_data)

        # Assert
        mock_create_token.assert_called_once_with(subject=user_id)
        assert result == "token_123"

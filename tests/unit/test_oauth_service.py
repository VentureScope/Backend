"""
Tests for OAuth service functionality.

Tests the complete OAuth flow including GitHub username handling.
"""

import pytest
import json
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timezone

from app.services.oauth_service import OAuthService, OAuthProviderError
from app.models.user import User
from app.models.oauth_account import OAuthAccount
from app.repositories.user_repository import UserRepository


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = Mock()

    # Mock the execute method to return a result mock
    result_mock = Mock()
    result_mock.scalar_one_or_none = Mock(return_value=None)
    db.execute = AsyncMock(return_value=result_mock)

    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def oauth_service(mock_db):
    """OAuth service with mocked dependencies."""
    return OAuthService(mock_db)


@pytest.fixture
def github_user_info():
    """Sample GitHub user info response."""
    return {
        "id": "12345",
        "email": "github-user@example.com",
        "name": "GitHub User",
        "picture": "https://avatar.url/user.jpg",
        "email_verified": True,
        "provider_login": "github-username",  # This is the GitHub username
    }


@pytest.fixture
def github_tokens():
    """Sample GitHub OAuth tokens."""
    return {
        "access_token": "github_access_token",
        "refresh_token": "github_refresh_token",
        "expires_in": 3600,
    }


class TestOAuthServiceGitHubUsername:
    """Test GitHub username handling in OAuth flow."""

    @pytest.mark.asyncio
    async def test_new_github_user_gets_username(
        self, oauth_service, mock_db, github_user_info, github_tokens
    ):
        """Test that new GitHub OAuth users get their github_username set."""

        # Mock no existing OAuth account - already done in mock_db fixture

        # Mock user repository
        mock_user_repo = Mock(spec=UserRepository)
        mock_user_repo.get_by_email = AsyncMock(return_value=None)  # No existing user

        # Mock user creation
        created_user = User(
            id="user-123",
            email="github-user@example.com",
            full_name="GitHub User",
            github_username="github-username",
            role="professional",
        )
        mock_user_repo.create_oauth_user = AsyncMock(return_value=created_user)
        mock_user_repo.create_oauth_account = AsyncMock()

        oauth_service.user_repo = mock_user_repo

        # Test user creation
        result_user = await oauth_service.find_or_create_user(
            provider="github",
            user_info=github_user_info,
            tokens=github_tokens,
        )

        # Verify create_oauth_user was called with github_username
        mock_user_repo.create_oauth_user.assert_called_once()
        call_args = mock_user_repo.create_oauth_user.call_args

        assert call_args[1]["github_username"] == "github-username"
        assert result_user.github_username == "github-username"

    @pytest.mark.asyncio
    async def test_existing_user_linking_sets_github_username(
        self, oauth_service, mock_db, github_user_info, github_tokens
    ):
        """Test that existing users get github_username when linking GitHub."""

        # Mock no existing OAuth account - already done in mock_db fixture

        # Mock existing user without github_username
        existing_user = User(
            id="user-123",
            email="github-user@example.com",
            full_name="Existing User",
            github_username=None,  # No GitHub username yet
            role="professional",
        )

        mock_user_repo = Mock(spec=UserRepository)
        mock_user_repo.get_by_email = AsyncMock(return_value=existing_user)
        mock_user_repo.create_oauth_account = AsyncMock()

        oauth_service.user_repo = mock_user_repo

        # Test user linking
        result_user = await oauth_service.find_or_create_user(
            provider="github",
            user_info=github_user_info,
            tokens=github_tokens,
        )

        # Verify github_username was set
        assert existing_user.github_username == "github-username"
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_existing_github_user_doesnt_override_username(
        self, oauth_service, mock_db, github_user_info, github_tokens
    ):
        """Test that existing users with github_username don't get it overridden during linking."""

        # Mock no existing OAuth account - already done in mock_db fixture

        # Mock existing user with different github_username
        existing_user = User(
            id="user-123",
            email="github-user@example.com",
            full_name="Existing User",
            github_username="existing-username",  # Already has a GitHub username
            role="professional",
        )

        mock_user_repo = Mock(spec=UserRepository)
        mock_user_repo.get_by_email = AsyncMock(return_value=existing_user)
        mock_user_repo.create_oauth_account = AsyncMock()

        oauth_service.user_repo = mock_user_repo

        # Test user linking
        result_user = await oauth_service.find_or_create_user(
            provider="github",
            user_info=github_user_info,
            tokens=github_tokens,
        )

        # Verify github_username was NOT changed (user already had one)
        assert existing_user.github_username == "existing-username"
        mock_db.flush.assert_not_called()

    @pytest.mark.asyncio
    async def test_returning_github_user_username_update(
        self, oauth_service, mock_db, github_user_info, github_tokens
    ):
        """Test that returning GitHub users get their username updated if changed."""

        # Mock existing user with old GitHub username
        existing_user = User(
            id="user-123",
            email="github-user@example.com",
            full_name="GitHub User",
            github_username="old-github-username",  # Old username
            role="professional",
        )

        # Mock existing OAuth account
        existing_oauth = OAuthAccount(
            id="oauth-123",
            user_id="user-123",
            provider="github",
            provider_account_id="12345",
            user=existing_user,
        )

        # Mock the database calls - we need to mock TWO separate execute calls:
        # 1. First call to find OAuth account
        # 2. Second call to find user by ID (for username update)
        # 3. Third call to return user (final return)
        oauth_result_mock = Mock()
        oauth_result_mock.scalar_one_or_none = Mock(return_value=existing_oauth)

        user_result_mock = Mock()
        user_result_mock.scalar_one = Mock(return_value=existing_user)

        # Configure execute to return different mocks based on call order
        mock_db.execute = AsyncMock(
            side_effect=[oauth_result_mock, user_result_mock, user_result_mock]
        )

        mock_user_repo = Mock(spec=UserRepository)
        oauth_service.user_repo = mock_user_repo

        # Test returning user with updated username in user_info
        result_user = await oauth_service.find_or_create_user(
            provider="github",
            user_info=github_user_info,  # Contains "github-username"
            tokens=github_tokens,
        )

        # Verify github_username was updated
        assert existing_user.github_username == "github-username"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_google_oauth_doesnt_set_github_username(
        self, oauth_service, mock_db, github_tokens
    ):
        """Test that Google OAuth doesn't set github_username."""

        google_user_info = {
            "id": "google-123",
            "email": "google-user@example.com",
            "name": "Google User",
            "picture": "https://avatar.url/google-user.jpg",
            "email_verified": True,
            # No provider_login field for Google
        }

        # Mock no existing OAuth account - already done in mock_db fixture

        mock_user_repo = Mock(spec=UserRepository)
        mock_user_repo.get_by_email = AsyncMock(return_value=None)

        created_user = User(
            id="user-123",
            email="google-user@example.com",
            full_name="Google User",
            role="professional",
        )
        mock_user_repo.create_oauth_user = AsyncMock(return_value=created_user)
        mock_user_repo.create_oauth_account = AsyncMock()

        oauth_service.user_repo = mock_user_repo

        # Test Google user creation
        result_user = await oauth_service.find_or_create_user(
            provider="google",
            user_info=google_user_info,
            tokens=github_tokens,
        )

        # Verify create_oauth_user was called WITHOUT github_username
        mock_user_repo.create_oauth_user.assert_called_once()
        call_args = mock_user_repo.create_oauth_user.call_args

        assert "github_username" not in call_args[1]

    @pytest.mark.asyncio
    async def test_github_user_without_login_field(
        self, oauth_service, mock_db, github_tokens
    ):
        """Test GitHub OAuth with missing provider_login field."""

        incomplete_user_info = {
            "id": "12345",
            "email": "github-user@example.com",
            "name": "GitHub User",
            "email_verified": True,
            # Missing provider_login field
        }

        # Mock no existing OAuth account - already done in mock_db fixture

        mock_user_repo = Mock(spec=UserRepository)
        mock_user_repo.get_by_email = AsyncMock(return_value=None)

        created_user = User(
            id="user-123",
            email="github-user@example.com",
            full_name="GitHub User",
            role="professional",
        )
        mock_user_repo.create_oauth_user = AsyncMock(return_value=created_user)
        mock_user_repo.create_oauth_account = AsyncMock()

        oauth_service.user_repo = mock_user_repo

        # Test user creation with missing login field
        result_user = await oauth_service.find_or_create_user(
            provider="github",
            user_info=incomplete_user_info,
            tokens=github_tokens,
        )

        # Verify create_oauth_user was called WITHOUT github_username
        mock_user_repo.create_oauth_user.assert_called_once()
        call_args = mock_user_repo.create_oauth_user.call_args

        assert "github_username" not in call_args[1]

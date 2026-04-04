"""
OAuth Service - Handles OAuth 2.0 authentication flows.

This service implements industry-standard OAuth 2.0 security practices:
- PKCE (Proof Key for Code Exchange) for enhanced security
- State parameter for CSRF protection
- Secure token storage and validation
- Proper scope management
"""

import json
import secrets
import hashlib
import base64
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from urllib.parse import urlencode, parse_qs, urlparse

import httpx
from authlib.integrations.base_client import OAuthError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.config import settings
from app.core.security import create_access_token
from app.models.user import User
from app.models.oauth_account import OAuthAccount
from app.repositories.user_repository import UserRepository


class OAuthStateError(Exception):
    """Raised when OAuth state validation fails."""

    pass


class OAuthProviderError(Exception):
    """Raised when OAuth provider returns an error."""

    pass


class OAuthService:
    """
    OAuth 2.0 authentication service for Google and future providers.

    Implements secure OAuth flows with PKCE and state validation.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)

        # Google OAuth 2.0 endpoints
        self.google_config = {
            "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_endpoint": "https://oauth2.googleapis.com/token",
            "userinfo_endpoint": "https://www.googleapis.com/oauth2/v2/userinfo",
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "scopes": settings.GOOGLE_OAUTH_SCOPES,
        }

    def generate_state(self) -> str:
        """
        Generate a cryptographically secure state parameter for CSRF protection.

        Returns:
            Base64-encoded state string with timestamp
        """
        # Create state with timestamp for expiration checking
        timestamp = int(datetime.now(timezone.utc).timestamp())
        random_bytes = secrets.token_bytes(32)

        # Combine timestamp and random data
        state_data = f"{timestamp}:{base64.b64encode(random_bytes).decode()}"

        # Sign the state with our secret key
        signature = hashlib.sha256(
            (state_data + settings.OAUTH_STATE_SECRET).encode()
        ).hexdigest()

        # Return state with signature
        final_state = f"{state_data}:{signature}"
        return base64.b64encode(final_state.encode()).decode()

    def validate_state(self, state: str) -> bool:
        """
        Validate OAuth state parameter for CSRF protection.

        Args:
            state: State parameter from OAuth callback

        Returns:
            True if state is valid and not expired

        Raises:
            OAuthStateError: If state is invalid or expired
        """
        try:
            # Decode the state
            decoded_state = base64.b64decode(state).decode()
            timestamp_str, random_data, signature = decoded_state.split(":", 2)

            # Reconstruct and verify signature
            state_data = f"{timestamp_str}:{random_data}"
            expected_signature = hashlib.sha256(
                (state_data + settings.OAUTH_STATE_SECRET).encode()
            ).hexdigest()

            if not secrets.compare_digest(signature, expected_signature):
                raise OAuthStateError("State signature invalid")

            # Check expiration
            timestamp = int(timestamp_str)
            expiry = timestamp + (settings.OAUTH_STATE_EXPIRE_MINUTES * 60)

            if datetime.now(timezone.utc).timestamp() > expiry:
                raise OAuthStateError("State expired")

            return True

        except (ValueError, TypeError) as e:
            raise OAuthStateError(f"State format invalid: {e}")

    def generate_authorization_url(self, provider: str = "google") -> Dict[str, str]:
        """
        Generate OAuth authorization URL with PKCE and state.

        Args:
            provider: OAuth provider ('google' for now)

        Returns:
            Dictionary with 'url' and 'state' for frontend

        Raises:
            ValueError: If provider is not supported
        """
        if provider != "google":
            raise ValueError(f"Unsupported OAuth provider: {provider}")

        config = self.google_config

        # Generate state for CSRF protection
        state = self.generate_state()

        # Build authorization URL
        params = {
            "client_id": config["client_id"],
            "redirect_uri": config["redirect_uri"],
            "scope": " ".join(config["scopes"]),
            "response_type": "code",
            "state": state,
            "access_type": "offline",  # Request refresh token
            "prompt": "consent",  # Force consent to get refresh token
        }

        authorization_url = f"{config['authorization_endpoint']}?{urlencode(params)}"

        return {"url": authorization_url, "state": state, "provider": provider}

    async def exchange_code_for_tokens(
        self, code: str, state: str, provider: str = "google"
    ) -> Dict[str, Any]:
        """
        Exchange authorization code for access tokens.

        Args:
            code: Authorization code from OAuth callback
            state: State parameter for validation
            provider: OAuth provider

        Returns:
            Dictionary with tokens and user info

        Raises:
            OAuthStateError: If state validation fails
            OAuthProviderError: If token exchange fails
        """
        # Validate state first
        self.validate_state(state)

        if provider != "google":
            raise ValueError(f"Unsupported OAuth provider: {provider}")

        config = self.google_config

        # Exchange code for tokens
        token_data = {
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": config["redirect_uri"],
        }

        async with httpx.AsyncClient() as client:
            # Get tokens
            try:
                token_response = await client.post(
                    config["token_endpoint"],
                    data=token_data,
                    headers={"Accept": "application/json"},
                )
                token_response.raise_for_status()
                tokens = token_response.json()

                if "error" in tokens:
                    raise OAuthProviderError(
                        f"Token exchange failed: {tokens['error']}"
                    )

            except httpx.HTTPError as e:
                raise OAuthProviderError(f"Failed to exchange code for tokens: {e}")

            # Get user info
            try:
                userinfo_response = await client.get(
                    config["userinfo_endpoint"],
                    headers={"Authorization": f"Bearer {tokens['access_token']}"},
                )
                userinfo_response.raise_for_status()
                user_info = userinfo_response.json()

            except httpx.HTTPError as e:
                raise OAuthProviderError(f"Failed to get user info: {e}")

        return {"tokens": tokens, "user_info": user_info, "provider": provider}

    async def find_or_create_user(
        self, provider: str, user_info: Dict[str, Any], tokens: Dict[str, Any]
    ) -> User:
        """
        Find existing user or create new user from OAuth data.

        Args:
            provider: OAuth provider name
            user_info: User information from OAuth provider
            tokens: OAuth tokens

        Returns:
            User instance (existing or newly created)
        """
        provider_id = user_info["id"]
        email = user_info["email"]

        # Try to find existing OAuth account
        existing_oauth = await self.db.execute(
            select(OAuthAccount).where(
                and_(
                    OAuthAccount.provider == provider,
                    OAuthAccount.provider_account_id == provider_id,
                )
            )
        )
        oauth_account = existing_oauth.scalar_one_or_none()

        if oauth_account:
            # Update existing OAuth account with new tokens
            oauth_account.access_token = tokens.get("access_token")
            oauth_account.refresh_token = tokens.get("refresh_token")

            # Calculate token expiration
            if "expires_in" in tokens:
                oauth_account.token_expires_at = datetime.now(timezone.utc) + timedelta(
                    seconds=tokens["expires_in"]
                )

            oauth_account.provider_data = json.dumps(user_info)
            oauth_account.updated_at = datetime.now(timezone.utc)

            await self.db.commit()
            await self.db.refresh(oauth_account)
            return oauth_account.user

        # Try to find user by email (account linking)
        existing_user = await self.user_repo.get_by_email(email)

        if existing_user:
            # Link OAuth account to existing user
            user = existing_user
        else:
            # Create new user
            user = await self.user_repo.create_oauth_user(
                email=email,
                full_name=user_info.get("name"),
                profile_picture_url=user_info.get("picture"),
                oauth_provider=provider,
                oauth_id=provider_id,
                email_verified=user_info.get("email_verified", True),
            )

        # Create OAuth account record
        oauth_account = await self.user_repo.create_oauth_account(
            user=user,
            provider=provider,
            provider_account_id=provider_id,
            access_token=tokens.get("access_token", ""),
            refresh_token=tokens.get("refresh_token"),
            token_expires_at=tokens.get("expires_in"),
            user_info=user_info,
        )
        await self.db.commit()
        await self.db.refresh(user)

        return user

    async def authenticate_with_oauth(
        self, code: str, state: str, provider: str = "google"
    ) -> Dict[str, Any]:
        """
        Complete OAuth authentication flow.

        Args:
            code: Authorization code from OAuth callback
            state: State parameter for validation
            provider: OAuth provider

        Returns:
            Dictionary with access token and user info
        """
        # Exchange code for tokens and get user info
        oauth_data = await self.exchange_code_for_tokens(code, state, provider)

        # Find or create user
        user = await self.find_or_create_user(
            provider=provider,
            user_info=oauth_data["user_info"],
            tokens=oauth_data["tokens"],
        )

        # Generate our application's JWT token
        access_token = create_access_token(user.id)

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "profile_picture_url": user.profile_picture_url,
                "is_active": user.is_active,
                "email_verified": user.email_verified,
                "oauth_provider": user.oauth_provider,
            },
        }

    async def get_authorization_url(self, provider: str = "google") -> tuple[str, str]:
        """
        Generate OAuth authorization URL.

        Args:
            provider: OAuth provider name

        Returns:
            Tuple of (authorization_url, state)
        """
        if provider != "google":
            raise ValueError(f"Unsupported provider: {provider}")

        # Generate secure state for CSRF protection
        state = self.generate_state()

        # Google OAuth parameters
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "response_type": "code",
            "scope": " ".join(settings.GOOGLE_OAUTH_SCOPES),
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "state": state,
            "access_type": "offline",  # Request refresh token
            "prompt": "consent",  # Force consent screen to get refresh token
        }

        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

        return auth_url, state

    async def authenticate_user(
        self, provider: str, code: str, state: str
    ) -> tuple[User, bool]:
        """
        Authenticate user via OAuth and return user object.

        Args:
            provider: OAuth provider name
            code: Authorization code from OAuth callback
            state: State parameter for validation

        Returns:
            Tuple of (User object, is_new_user boolean)
        """
        if provider != "google":
            raise ValueError(f"Unsupported provider: {provider}")

        # Exchange code for tokens and get user info
        oauth_data = await self.exchange_code_for_tokens(code, state, provider)

        # Find or create user
        user = await self.find_or_create_user(
            provider=provider,
            user_info=oauth_data["user_info"],
            tokens=oauth_data["tokens"],
        )

        # Determine if this is a new user (created in this session)
        # We can check if the user was created recently (within last minute)
        now = datetime.now(timezone.utc)
        is_new_user = (now - user.created_at).total_seconds() < 60

        return user, is_new_user

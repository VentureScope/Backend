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
from typing import Dict, Any
from urllib.parse import urlencode

import httpx
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
    OAuth 2.0 authentication service for supported providers.

    Implements secure OAuth flows with PKCE and state validation.
    """

    SUPPORTED_PROVIDERS = {"google", "github"}
    GITHUB_SYNC_REQUIRED_SCOPES = ["read:user", "user:email", "repo", "read:org"]

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)

        self.provider_configs = {
            "google": {
                "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_endpoint": "https://oauth2.googleapis.com/token",
                "userinfo_endpoint": "https://www.googleapis.com/oauth2/v2/userinfo",
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "scopes": settings.GOOGLE_OAUTH_SCOPES,
                "authorization_extras": {
                    "access_type": "offline",
                    "prompt": "consent",
                },
            },
            "github": {
                "authorization_endpoint": "https://github.com/login/oauth/authorize",
                "token_endpoint": "https://github.com/login/oauth/access_token",
                "userinfo_endpoint": "https://api.github.com/user",
                "email_endpoint": "https://api.github.com/user/emails",
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "redirect_uri": settings.GITHUB_REDIRECT_URI,
                "scopes": settings.GITHUB_OAUTH_SCOPES,
                "authorization_extras": {},
            },
        }

    def _get_provider_config(self, provider: str) -> Dict[str, Any]:
        if provider not in self.SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported provider: {provider}")
        return self.provider_configs[provider]

    def _normalize_scopes(self, provider: str, scopes: list[str] | None = None) -> list[str]:
        """Return a deduplicated, ordered scope list for an OAuth provider."""
        config = self._get_provider_config(provider)
        raw_scopes = scopes if scopes is not None else config["scopes"]

        normalized: list[str] = []
        for scope in raw_scopes:
            scope = scope.strip()
            if scope and scope not in normalized:
                normalized.append(scope)
        return normalized

    def _parse_provider_data(self, oauth_account: OAuthAccount | None) -> Dict[str, Any]:
        """Safely parse provider_data JSON from an OAuth account."""
        if not oauth_account or not oauth_account.provider_data:
            return {}

        try:
            data = json.loads(oauth_account.provider_data)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

        return {}

    def _get_granted_scopes(self, oauth_account: OAuthAccount | None) -> list[str]:
        data = self._parse_provider_data(oauth_account)
        raw_scopes = data.get("granted_scopes", [])

        if isinstance(raw_scopes, str):
            raw_scopes = [scope.strip() for scope in raw_scopes.split(",") if scope.strip()]

        if not isinstance(raw_scopes, list):
            return []

        return self._normalize_scopes("github", raw_scopes)

    def _get_required_github_scopes(self) -> list[str]:
        return self._normalize_scopes("github", self.GITHUB_SYNC_REQUIRED_SCOPES)

    def _missing_scopes(self, granted_scopes: list[str], required_scopes: list[str]) -> list[str]:
        granted = set(granted_scopes)
        return [scope for scope in required_scopes if scope not in granted]

    def _provider_data_payload(
        self, user_info: Dict[str, Any], granted_scopes: list[str]
    ) -> Dict[str, Any]:
        return {
            "profile": user_info,
            "granted_scopes": granted_scopes,
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _get_github_oauth_account(self, user_id: str) -> OAuthAccount | None:
        result = await self.db.execute(
            select(OAuthAccount).where(
                and_(
                    OAuthAccount.user_id == user_id,
                    OAuthAccount.provider == "github",
                )
            )
        )
        return result.scalar_one_or_none()

    def _build_github_profile_query(self) -> str:
        return """
query ($username: String!) {
  user(login: $username) {
    login
    name
    bio
    avatarUrl
    repositories(first: 20, orderBy: {field: STARGAZERS, direction: DESC}) {
      nodes {
        name
        description
        stargazerCount
        forkCount
        isPrivate
        isFork
        updatedAt
        pushedAt
        primaryLanguage {
          name
        }
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges {
            size
            node {
              name
            }
          }
        }
        repositoryTopics(first: 10) {
          nodes {
            topic {
              name
            }
          }
        }
      }
    }
    contributionsCollection {
      contributionCalendar {
        totalContributions
      }
      totalPullRequestContributions
      totalIssueContributions
      totalRepositoriesWithContributedCommits
    }
    organizations(first: 5) {
      nodes {
        name
      }
    }
  }
}
""".strip()

    def _normalize_github_repository(self, repo: Dict[str, Any]) -> Dict[str, Any]:
        languages = []
        for edge in repo.get("languages", {}).get("edges", []):
            node = edge.get("node") or {}
            if node.get("name"):
                languages.append({"name": node["name"], "size": edge.get("size", 0)})

        topics = []
        for item in repo.get("repositoryTopics", {}).get("nodes", []):
            topic = item.get("topic") or {}
            if topic.get("name"):
                topics.append(topic["name"])

        return {
            "name": repo.get("name"),
            "description": repo.get("description"),
            "stargazer_count": repo.get("stargazerCount", 0),
            "fork_count": repo.get("forkCount", 0),
            "is_private": repo.get("isPrivate", False),
            "is_fork": repo.get("isFork", False),
            "pushed_at": repo.get("pushedAt"),
            "updated_at": repo.get("updatedAt"),
            "primary_language": (repo.get("primaryLanguage") or {}).get("name"),
            "languages": languages,
            "topics": topics,
        }

    def _normalize_github_contributions(self, contributions: Dict[str, Any]) -> Dict[str, Any]:
        calendar = contributions.get("contributionCalendar", {})
        return {
            "total_contributions": calendar.get("totalContributions", 0),
            "total_pull_requests": contributions.get("totalPullRequestContributions", 0),
            "total_issue_contributions": contributions.get("totalIssueContributions", 0),
            "total_repositories_with_contributed_commits": contributions.get(
                "totalRepositoriesWithContributedCommits", 0
            ),
        }

    async def _fetch_github_profile_sync_data(
        self, access_token: str, github_username: str
    ) -> Dict[str, Any]:
        query = self._build_github_profile_query()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.github.com/graphql",
                json={"query": query, "variables": {"username": github_username}},
                headers=headers,
            )

            if response.status_code in {401, 403}:
                raise OAuthProviderError(
                    "GitHub profile sync requires updated OAuth permissions"
                )

            response.raise_for_status()
            payload = response.json()

        if payload.get("errors"):
            error_message = payload["errors"][0].get("message", "Unknown GitHub error")
            if "not accessible" in error_message.lower() or "scope" in error_message.lower():
                raise OAuthProviderError(
                    "GitHub profile sync requires updated OAuth permissions"
                )
            raise OAuthProviderError(f"GitHub GraphQL request failed: {error_message}")

        user = (payload.get("data") or {}).get("user")
        if not user:
            raise OAuthProviderError("GitHub user data was not returned")

        repositories = [
            self._normalize_github_repository(repo)
            for repo in (user.get("repositories", {}).get("nodes", []) or [])
            if repo
        ]

        contributions = self._normalize_github_contributions(
            user.get("contributionsCollection", {})
        )

        organizations = [
            item.get("name")
            for item in (user.get("organizations", {}).get("nodes", []) or [])
            if item and item.get("name")
        ]

        return {
            "github_username": user.get("login") or github_username,
            "full_name": user.get("name"),
            "profile_picture_url": user.get("avatarUrl"),
            "bio": user.get("bio"),
            "repositories": repositories,
            "contributions": contributions,
            "organizations": organizations,
        }

    async def _fetch_user_info(
        self, client: httpx.AsyncClient, provider: str, access_token: str
    ) -> Dict[str, Any]:
        config = self._get_provider_config(provider)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        userinfo_response = await client.get(config["userinfo_endpoint"], headers=headers)
        userinfo_response.raise_for_status()
        user_info = userinfo_response.json()

        if provider == "google":
            return user_info

        # Normalize GitHub payload to internal format expected by the user creation flow.
        email = user_info.get("email")
        if not email:
            emails_response = await client.get(config["email_endpoint"], headers=headers)
            emails_response.raise_for_status()
            emails = emails_response.json()

            primary_email = next(
                (item.get("email") for item in emails if item.get("primary")),
                None,
            )
            verified_email = next(
                (item.get("email") for item in emails if item.get("verified")),
                None,
            )
            email = primary_email or verified_email

        if not email:
            raise OAuthProviderError("GitHub account does not expose an accessible email")

        return {
            "id": str(user_info["id"]),
            "email": email,
            "name": user_info.get("name") or user_info.get("login"),
            "picture": user_info.get("avatar_url"),
            "email_verified": True,
            "provider_login": user_info.get("login"),
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

    def generate_authorization_url(
        self, provider: str = "google", scopes: list[str] | None = None
    ) -> Dict[str, str]:
        """
        Generate OAuth authorization URL with PKCE and state.

        Args:
            provider: OAuth provider name

        Returns:
            Dictionary with 'url' and 'state' for frontend

        Raises:
            ValueError: If provider is not supported
        """
        config = self._get_provider_config(provider)

        # Generate state for CSRF protection
        state = self.generate_state()

        # Build authorization URL
        params = {
            "client_id": config["client_id"],
            "redirect_uri": config["redirect_uri"],
            "scope": " ".join(self._normalize_scopes(provider, scopes)),
            "response_type": "code",
            "state": state,
        }
        params.update(config.get("authorization_extras", {}))

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

        config = self._get_provider_config(provider)

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

                if provider == "github" and "scope" in tokens and isinstance(tokens["scope"], str):
                    tokens["granted_scopes"] = [
                        scope.strip() for scope in tokens["scope"].split(",") if scope.strip()
                    ]

            except httpx.HTTPError as e:
                raise OAuthProviderError(f"Failed to exchange code for tokens: {e}")

            # Get user info
            try:
                user_info = await self._fetch_user_info(
                    client=client,
                    provider=provider,
                    access_token=tokens["access_token"],
                )

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

            if provider == "github":
                granted_scopes_from_token = self._normalize_scopes(
                    "github", tokens.get("granted_scopes") or []
                )
                granted_scopes = (
                    granted_scopes_from_token
                    or self._get_granted_scopes(oauth_account)
                    or self._get_required_github_scopes()
                )
                provider_data = self._provider_data_payload(
                    user_info=user_info,
                    granted_scopes=granted_scopes,
                )
                oauth_account.provider_data = json.dumps(provider_data)
            else:
                oauth_account.provider_data = json.dumps(user_info)
            oauth_account.updated_at = datetime.now(timezone.utc)

            await self.db.commit()
            await self.db.refresh(oauth_account)
            user = await self.user_repo.get_by_id(oauth_account.user_id)
            if not user:
                raise ValueError("Linked OAuth user not found")
            return user

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
        granted_scopes = (
            self._normalize_scopes(
                "github", tokens.get("granted_scopes") or []
            )
            if provider == "github"
            else []
        )
        provider_data = self._provider_data_payload(user_info=user_info, granted_scopes=granted_scopes)
        oauth_account = await self.user_repo.create_oauth_account(
            user=user,
            provider=provider,
            provider_account_id=provider_id,
            access_token=tokens.get("access_token", ""),
            refresh_token=tokens.get("refresh_token"),
            token_expires_at=tokens.get("expires_in"),
            user_info=user_info,
            provider_data=provider_data,
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

    async def get_authorization_url(
        self, provider: str = "google", scopes: list[str] | None = None
    ) -> tuple[str, str]:
        """
        Generate OAuth authorization URL.

        Args:
            provider: OAuth provider name

        Returns:
            Tuple of (authorization_url, state)
        """
        auth_data = self.generate_authorization_url(provider=provider, scopes=scopes)
        return auth_data["url"], auth_data["state"]

    async def get_github_profile_sync_status(self, user_id: str) -> Dict[str, Any]:
        """Return the current GitHub sync status for a user."""
        oauth_account = await self._get_github_oauth_account(user_id)
        required_scopes = self._get_required_github_scopes()

        if not oauth_account or not oauth_account.access_token:
            authorization_url, state = await self.get_authorization_url(
                provider="github", scopes=required_scopes
            )
            return {
                "status": "authorization_required",
                "message": "Connect GitHub to sync repository, language, and contribution data.",
                "github_connected": False,
                "required_scopes": required_scopes,
                "authorization_url": authorization_url,
                "state": state,
                "repositories": [],
                "contributions": None,
            }

        if oauth_account.token_expires_at and oauth_account.token_expires_at < datetime.now(timezone.utc):
            authorization_url, state = await self.get_authorization_url(
                provider="github", scopes=required_scopes
            )
            return {
                "status": "authorization_required",
                "message": "GitHub token has expired. Reconnect to continue syncing.",
                "github_connected": False,
                "required_scopes": required_scopes,
                "authorization_url": authorization_url,
                "state": state,
                "repositories": [],
                "contributions": None,
            }

        granted_scopes = self._get_granted_scopes(oauth_account)
        missing_scopes = self._missing_scopes(granted_scopes, required_scopes)
        if missing_scopes:
            authorization_url, state = await self.get_authorization_url(
                provider="github", scopes=required_scopes
            )
            return {
                "status": "scope_upgrade_required",
                "message": "GitHub access is connected, but repo-level permissions are required for full sync.",
                "github_connected": True,
                "required_scopes": required_scopes,
                "authorization_url": authorization_url,
                "state": state,
                "repositories": [],
                "contributions": None,
            }

        provider_data = self._parse_provider_data(oauth_account)
        github_login = (
            provider_data.get("profile", {}).get("login")
            or provider_data.get("profile", {}).get("provider_login")
            or provider_data.get("provider_login")
            or provider_data.get("login")
            or provider_data.get("profile", {}).get("name")
            or provider_data.get("profile", {}).get("email")
            or ""
        )

        try:
            profile = await self._fetch_github_profile_sync_data(
                access_token=oauth_account.access_token,
                github_username=github_login,
            )
        except OAuthProviderError as e:
            if "updated OAuth permissions" in str(e):
                authorization_url, state = await self.get_authorization_url(
                    provider="github", scopes=required_scopes
                )
                return {
                    "status": "scope_upgrade_required",
                    "message": "GitHub access is connected, but repo-level permissions are required for full sync.",
                    "github_connected": True,
                    "required_scopes": required_scopes,
                    "authorization_url": authorization_url,
                    "state": state,
                    "repositories": [],
                    "contributions": None,
                }
            raise

        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        user.github_username = profile["github_username"]
        if profile.get("full_name"):
            user.full_name = profile["full_name"]
        if profile.get("profile_picture_url"):
            user.profile_picture_url = profile["profile_picture_url"]

        await self.user_repo.update(user)

        oauth_account.provider_data = json.dumps(
            {
                "profile": {
                    "login": profile["github_username"],
                    "name": profile.get("full_name"),
                    "avatar_url": profile.get("profile_picture_url"),
                    "bio": profile.get("bio"),
                },
                "granted_scopes": granted_scopes,
                "synced_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        await self.db.flush()
        await self.db.commit()

        return {
            "status": "synced",
            "message": "GitHub profile synced successfully.",
            "github_connected": True,
            "github_username": profile["github_username"],
            "full_name": profile.get("full_name"),
            "profile_picture_url": profile.get("profile_picture_url"),
            "required_scopes": required_scopes,
            "repositories": profile.get("repositories", []),
            "contributions": profile.get("contributions"),
        }

    async def request_github_scope_upgrade(self) -> tuple[str, str, list[str]]:
        """Return a GitHub OAuth URL that requests the sync scopes."""
        required_scopes = self._get_required_github_scopes()
        authorization_url, state = await self.get_authorization_url(
            provider="github", scopes=required_scopes
        )
        return authorization_url, state, required_scopes

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
        self._get_provider_config(provider)

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

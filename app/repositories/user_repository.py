import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User
from app.models.oauth_account import OAuthAccount


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: str) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalars().one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalars().one_or_none()

    async def create(self, user: User) -> User:
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    # ==================== Phase B: User Management Methods ====================

    async def update(self, user: User) -> User:
        """Update an existing user."""
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def delete(self, user: User) -> bool:
        """Hard delete a user from the database."""
        await self.db.delete(user)
        await self.db.flush()
        return True

    async def list_all(
        self, skip: int = 0, limit: int = 10, include_inactive: bool = False
    ) -> list[User]:
        """List users with pagination. By default excludes inactive users."""
        query = select(User)
        if not include_inactive:
            query = query.where(User.is_active == True)  # noqa: E712
        query = query.offset(skip).limit(limit).order_by(User.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count(self, include_inactive: bool = False) -> int:
        """Count total users. By default excludes inactive users."""
        query = select(func.count(User.id))
        if not include_inactive:
            query = query.where(User.is_active == True)  # noqa: E712
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def get_active_by_id(self, user_id: str) -> User | None:
        """Get user by ID only if active."""
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.is_active == True)  # noqa: E712
        )
        return result.scalars().one_or_none()

    async def get_similar_users(self, user_embedding: list[float], limit: int = 5, exclude_user_id: str | None = None) -> list[User]:
        """
        Use pgvector cosine_distance to mathematically retrieve users who have similar
        career interests, github, and estudent profiles. 
        """
        query = select(User).where(User.embedding.is_not(None))
        if exclude_user_id:
            query = query.where(User.id != exclude_user_id)
            
        # Order by Cosine Distance
        query = query.order_by(User.embedding.cosine_distance(user_embedding)).limit(limit)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ==================== OAuth Methods ====================

    async def get_by_oauth_account(
        self, provider: str, provider_account_id: str
    ) -> User | None:
        """Get user by OAuth provider and provider account ID."""
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.oauth_accounts))
            .join(OAuthAccount)
            .where(
                OAuthAccount.provider == provider,
                OAuthAccount.provider_account_id == provider_account_id,
            )
        )
        return result.scalars().one_or_none()

    async def create_oauth_user(
        self, email: str, full_name: str | None = None, **kwargs
    ) -> User:
        """Create a new user for OAuth authentication."""
        # Set defaults for OAuth users
        oauth_defaults = {
            "email_verified": True,  # OAuth users are email verified by default
            "is_active": True,  # OAuth users are active by default
        }

        # Merge defaults with provided kwargs (kwargs take precedence)
        user_data = {**oauth_defaults, **kwargs}

        user = User(
            email=email,
            full_name=full_name,
            # OAuth users don't have password_hash (remains None)
            **user_data,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def create_oauth_account(
        self,
        user: User,
        provider: str,
        provider_account_id: str,
        access_token: str,
        refresh_token: str | None = None,
        token_expires_at: int | None = None,
        user_info: dict | None = None,
        provider_data: dict | None = None,
    ) -> OAuthAccount:
        """Create a new OAuth account for a user."""
        # Calculate token expiration datetime if expires_in seconds provided
        token_expires_datetime = None
        if token_expires_at:
            token_expires_datetime = datetime.now(timezone.utc) + timedelta(
                seconds=token_expires_at
            )

        oauth_account = OAuthAccount(
            user_id=user.id,
            provider=provider,
            provider_account_id=provider_account_id,
            provider_email=user_info.get("email") if user_info else None,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=token_expires_datetime,
            provider_data=json.dumps(provider_data or user_info or {}),
        )
        self.db.add(oauth_account)
        await self.db.flush()
        await self.db.refresh(oauth_account)
        return oauth_account

    async def update_oauth_account_tokens(
        self,
        oauth_account: OAuthAccount,
        access_token: str,
        refresh_token: str | None = None,
        token_expires_at: int | None = None,
    ) -> OAuthAccount:
        """Update OAuth account tokens."""
        oauth_account.access_token = access_token
        if refresh_token:
            oauth_account.refresh_token = refresh_token
        if token_expires_at:
            oauth_account.token_expires_at = token_expires_at

        await self.db.flush()
        await self.db.refresh(oauth_account)
        return oauth_account

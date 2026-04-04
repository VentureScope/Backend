"""
Token Repository - Database operations for token blocklist.
"""

from datetime import datetime, timezone
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.token_blocklist import TokenBlocklist


class TokenRepository:
    """Repository for token blocklist operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_to_blocklist(
        self, jti: str, user_id: str, expires_at: datetime
    ) -> TokenBlocklist:
        """
        Add a token to the blocklist.

        Args:
            jti: JWT ID (unique identifier for the token)
            user_id: ID of the user who owns the token
            expires_at: When the token expires (for cleanup)

        Returns:
            The created TokenBlocklist entry
        """
        entry = TokenBlocklist(
            jti=jti,
            user_id=user_id,
            expires_at=expires_at,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def is_blocklisted(self, jti: str) -> bool:
        """
        Check if a token is in the blocklist.

        Args:
            jti: JWT ID to check

        Returns:
            True if token is blocklisted, False otherwise
        """
        query = select(TokenBlocklist.id).where(TokenBlocklist.jti == jti).limit(1)
        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None

    async def cleanup_expired(self) -> int:
        """
        Remove expired tokens from the blocklist.

        Tokens are kept until their expiry time to prevent reuse.
        After expiry, the token would be rejected anyway, so we can
        safely remove it from the blocklist.

        Returns:
            Number of entries removed
        """
        now = datetime.now(timezone.utc)
        query = delete(TokenBlocklist).where(TokenBlocklist.expires_at < now)
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount

    async def get_blocklist_count(self) -> int:
        """
        Get the total number of blocklisted tokens.

        Useful for monitoring/debugging.

        Returns:
            Count of blocklisted tokens
        """
        query = select(func.count(TokenBlocklist.id))
        result = await self.db.execute(query)
        return result.scalar_one()

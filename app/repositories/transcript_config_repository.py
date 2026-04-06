"""
Repository for TranscriptConfig database operations.
"""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.transcript_config import TranscriptConfig


class TranscriptConfigRepository:
    """Repository for managing transcript configuration data access."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, config: TranscriptConfig) -> TranscriptConfig:
        """
        Create a new transcript configuration.

        Args:
            config: TranscriptConfig instance to create

        Returns:
            The created TranscriptConfig instance
        """
        self.db.add(config)
        await self.db.commit()
        await self.db.refresh(config)
        return config

    async def get_by_user_id(self, user_id: str) -> Optional[TranscriptConfig]:
        """
        Get transcript configuration for a specific user.

        Args:
            user_id: User ID to look up

        Returns:
            TranscriptConfig if found, None otherwise
        """
        stmt = select(TranscriptConfig).where(TranscriptConfig.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, config_id: str) -> Optional[TranscriptConfig]:
        """
        Get transcript configuration by ID.

        Args:
            config_id: Configuration ID

        Returns:
            TranscriptConfig if found, None otherwise
        """
        stmt = select(TranscriptConfig).where(TranscriptConfig.id == config_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, config: TranscriptConfig) -> TranscriptConfig:
        """
        Update an existing transcript configuration.

        Args:
            config: TranscriptConfig instance with updated values

        Returns:
            The updated TranscriptConfig instance
        """
        await self.db.commit()
        await self.db.refresh(config)
        return config

    async def delete(self, config: TranscriptConfig) -> None:
        """
        Delete a transcript configuration.

        Args:
            config: TranscriptConfig instance to delete
        """
        await self.db.delete(config)
        await self.db.commit()

    async def exists_for_user(self, user_id: str) -> bool:
        """
        Check if a configuration exists for a user.

        Args:
            user_id: User ID to check

        Returns:
            True if configuration exists, False otherwise
        """
        stmt = select(TranscriptConfig.id).where(TranscriptConfig.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

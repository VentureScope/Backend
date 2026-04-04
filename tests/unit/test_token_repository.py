"""Unit tests for token repository."""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.repositories.token_repository import TokenRepository
from app.models.token_blocklist import TokenBlocklist


@pytest.mark.unit
class TestTokenRepository:
    """Test token blocklist repository operations."""

    @pytest.mark.asyncio
    async def test_add_to_blocklist(self, db_session: AsyncSession):
        """Test adding a token to the blocklist."""
        repo = TokenRepository(db_session)

        jti = "test-jti-12345"
        user_id = "user-uuid-12345"
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        entry = await repo.add_to_blocklist(jti, user_id, expires_at)

        assert entry is not None
        assert entry.jti == jti
        assert entry.user_id == user_id
        assert entry.expires_at == expires_at
        assert entry.created_at is not None

    @pytest.mark.asyncio
    async def test_is_blocklisted_returns_true_for_blocklisted_token(
        self, db_session: AsyncSession
    ):
        """Test that is_blocklisted returns True for a blocklisted token."""
        repo = TokenRepository(db_session)

        jti = "blocklisted-jti-12345"
        user_id = "user-uuid-12345"
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        await repo.add_to_blocklist(jti, user_id, expires_at)
        await db_session.commit()

        result = await repo.is_blocklisted(jti)
        assert result is True

    @pytest.mark.asyncio
    async def test_is_blocklisted_returns_false_for_non_blocklisted_token(
        self, db_session: AsyncSession
    ):
        """Test that is_blocklisted returns False for a non-blocklisted token."""
        repo = TokenRepository(db_session)

        result = await repo.is_blocklisted("non-existent-jti")
        assert result is False

    @pytest.mark.asyncio
    async def test_cleanup_expired_removes_old_tokens(self, db_session: AsyncSession):
        """Test that cleanup_expired removes expired tokens."""
        repo = TokenRepository(db_session)

        # Add an expired token
        expired_jti = "expired-jti"
        expired_time = datetime.now(timezone.utc) - timedelta(hours=1)
        await repo.add_to_blocklist(expired_jti, "user-1", expired_time)

        # Add a valid (non-expired) token
        valid_jti = "valid-jti"
        valid_time = datetime.now(timezone.utc) + timedelta(hours=1)
        await repo.add_to_blocklist(valid_jti, "user-2", valid_time)

        await db_session.commit()

        # Run cleanup
        count = await repo.cleanup_expired()

        # Should have removed 1 token
        assert count == 1

        # Expired token should be gone
        assert await repo.is_blocklisted(expired_jti) is False

        # Valid token should still be there
        assert await repo.is_blocklisted(valid_jti) is True

    @pytest.mark.asyncio
    async def test_cleanup_expired_returns_zero_when_no_expired_tokens(
        self, db_session: AsyncSession
    ):
        """Test that cleanup_expired returns 0 when there are no expired tokens."""
        repo = TokenRepository(db_session)

        # Add only valid tokens
        valid_time = datetime.now(timezone.utc) + timedelta(hours=1)
        await repo.add_to_blocklist("valid-jti-1", "user-1", valid_time)
        await repo.add_to_blocklist("valid-jti-2", "user-2", valid_time)
        await db_session.commit()

        count = await repo.cleanup_expired()
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_blocklist_count(self, db_session: AsyncSession):
        """Test getting the count of blocklisted tokens."""
        repo = TokenRepository(db_session)

        # Initially should be 0
        count = await repo.get_blocklist_count()
        assert count == 0

        # Add tokens
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        await repo.add_to_blocklist("jti-1", "user-1", expires_at)
        await repo.add_to_blocklist("jti-2", "user-2", expires_at)
        await repo.add_to_blocklist("jti-3", "user-3", expires_at)
        await db_session.commit()

        count = await repo.get_blocklist_count()
        assert count == 3

    @pytest.mark.asyncio
    async def test_add_duplicate_jti_raises_error(self, db_session: AsyncSession):
        """Test that adding a duplicate JTI raises an error due to unique constraint."""
        repo = TokenRepository(db_session)

        jti = "duplicate-jti"
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        await repo.add_to_blocklist(jti, "user-1", expires_at)
        await db_session.commit()

        # Trying to add the same JTI should raise an error
        with pytest.raises(IntegrityError):
            await repo.add_to_blocklist(jti, "user-2", expires_at)
            await db_session.commit()

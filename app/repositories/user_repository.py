from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


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

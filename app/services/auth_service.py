from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password, create_access_token
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserLogin


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = UserRepository(db)

    async def register(self, data: UserCreate) -> User:
        existing = await self.repo.get_by_email(data.email)
        if existing:
            raise ValueError("Email already registered")
        user = User(
            email=data.email,
            password_hash=hash_password(data.password),
            full_name=data.full_name,
            career_interest=data.career_interest,
            role=data.role,
        )
        return await self.repo.create(user)

    async def login(self, data: UserLogin) -> str:
        user = await self.repo.get_by_email(data.email)
        if not user or not verify_password(data.password, user.password_hash):
            raise ValueError("Invalid email or password")
        return create_access_token(subject=user.id)

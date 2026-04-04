from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password, create_access_token
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserLogin
from app.services.embedding_service import get_embedding_service

# Dummy password hash for timing-attack prevention.
# Used when user doesn't exist to ensure consistent response time.
_DUMMY_HASH = hash_password("dummy-password-for-timing-consistency")


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = UserRepository(db)
        self.embedding_service = get_embedding_service()

    async def register(self, data: UserCreate) -> User:
        existing = await self.repo.get_by_email(data.email)
        if existing:
            raise ValueError("Email already registered")
            
        doc = self.embedding_service.construct_user_document(
            career_interest=data.career_interest,
            github_profile=None,
            estudent_profile=None
        )
        embedding = self.embedding_service.generate_embedding(doc)

        user = User(
            email=data.email,
            password_hash=hash_password(data.password),
            full_name=data.full_name,
            career_interest=data.career_interest,
            role=data.role,
            embedding=embedding
        )
        return await self.repo.create(user)

    async def login(self, data: UserLogin) -> str:
        user = await self.repo.get_by_email(data.email)

        # Always perform password verification to prevent timing attacks.
        # Use a dummy hash when user doesn't exist to maintain consistent timing.
        password_hash = user.password_hash if user else _DUMMY_HASH
        password_valid = verify_password(data.password, password_hash)

        if not user or not password_valid or not user.is_active:
            raise ValueError("Invalid email or password")

        return create_access_token(subject=user.id)

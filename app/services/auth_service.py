from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password, create_access_token
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserLogin
from app.services.embedding_service import get_embedding_service
from app.services.github_service import fetch_github_profile_description

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
            
        github_profile_desc = await fetch_github_profile_description(data.github_username) if data.github_username else None
            
        doc = self.embedding_service.construct_user_document(
            career_interest=data.career_interest,
            github_profile=github_profile_desc,
            estudent_profile=None
        )
        embedding = self.embedding_service.generate_embedding(doc)

        user = User(
            email=data.email,
            password_hash=hash_password(data.password),
            full_name=data.full_name,
            github_username=data.github_username,
            career_interest=data.career_interest,
            role=data.role,
            embedding=embedding
        )
        return await self.repo.create(user)

    async def login(self, data: UserLogin) -> str:
        user = await self.repo.get_by_email(data.email)

        # Check if user exists and is active
        if not user or not user.is_active:
            # Use dummy hash for timing consistency even when user doesn't exist
            verify_password(data.password, _DUMMY_HASH)
            raise ValueError("Invalid email or password")

        # Check if this is an OAuth user trying to login with password
        if user.password_hash is None or user.oauth_provider is not None:
            # Use dummy hash for timing consistency
            verify_password(data.password, _DUMMY_HASH)
            raise ValueError(
                "This account uses OAuth login. Please use the OAuth login option."
            )

        # Verify password for regular users
        password_valid = verify_password(data.password, user.password_hash)
        if not password_valid:
            raise ValueError("Invalid email or password")

        return create_access_token(subject=user.id)

    async def get_user_by_id(self, user_id: str) -> User | None:
        """Get user by ID, works for both regular and OAuth users."""
        return await self.repo.get_active_by_id(user_id)

    async def get_user_by_email(self, email: str) -> User | None:
        """Get user by email, works for both regular and OAuth users."""
        user = await self.repo.get_by_email(email)
        return user if user and user.is_active else None

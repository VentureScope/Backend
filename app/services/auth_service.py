import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password, create_access_token
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserLogin
from app.services.github_service import fetch_github_profile_description
from app.services.otp_service import OTPService
from app.tasks.user_embedding_task import generate_user_profile_embedding

logger = logging.getLogger(__name__)

# Dummy password hash for timing-attack prevention.
# Used when user doesn't exist to ensure consistent response time.
_DUMMY_HASH = hash_password("dummy-password-for-timing-consistency")


class AuthService:
    def __init__(self, db: AsyncSession, otp_service: OTPService | None = None):
        self.db = db
        self.repo = UserRepository(db)
        self._otp_service = otp_service

    async def register(self, data: UserCreate) -> User:
        existing = await self.repo.get_by_email(data.email)
        if existing:
            raise ValueError("Email already registered")

        user = User(
            email=data.email,
            password_hash=hash_password(data.password),
            full_name=data.full_name,
            github_username=data.github_username,
            career_interest=data.career_interest,
            skills=data.skills,
            role=data.role,
            embedding_status="pending",
            is_verified=False,  # Requires OTP verification before first login
        )
        user = await self.repo.create(user)
        await self.db.commit()
        await self.db.refresh(user)

        generate_user_profile_embedding.delay(user.id)

        # Send OTP verification email (non-fatal — user can resend via /auth/otp/resend)
        if self._otp_service is not None:
            try:
                await self._otp_service.send_otp(user)
            except Exception:
                logger.exception(
                    "Failed to send OTP email during registration for user %s", user.id
                )

        return user

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

        # Block login until email is verified via OTP
        if not user.is_verified:
            raise PermissionError(
                "Email not verified. Please check your inbox for the verification code."
            )

        return create_access_token(subject=user.id)

    async def get_user_by_id(self, user_id: str) -> User | None:
        """Get user by ID, works for both regular and OAuth users."""
        return await self.repo.get_active_by_id(user_id)

    async def get_user_by_email(self, email: str) -> User | None:
        """Get user by email, works for both regular and OAuth users."""
        user = await self.repo.get_by_email(email)
        return user if user and user.is_active else None

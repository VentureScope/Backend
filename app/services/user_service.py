"""
User Management Service - Business logic for user CRUD operations.
Phase B Implementation.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserUpdate, PasswordChange, UserAdminUpdate
from app.services.embedding_service import get_embedding_service


class UserService:
    """Service for user management operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = UserRepository(db)
        self.embedding_service = get_embedding_service()

    # ==================== Helper Operations ====================

    def _update_user_embedding(self, user: User) -> None:
        """Helper to compute and update the user's embedding based on their current text attributes."""
        doc = self.embedding_service.construct_user_document(
            career_interest=user.career_interest,
            github_profile=user.github_username, # In a real app you might fetch the actual github README/bio here
            estudent_profile=user.estudent_profile
        )
        user.embedding = self.embedding_service.generate_embedding(doc)

    # ==================== Self-Service Operations ====================

    async def get_profile(self, user_id: str) -> User | None:
        """Get user profile by ID."""
        return await self.repo.get_by_id(user_id)

    async def update_profile(self, user_id: str, data: UserUpdate) -> User:
        """
        Update user's own profile.
        Only allows updating: full_name, github_username, career_interest.
        """
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise ValueError("User profile not found")

        if not user.is_active:
            raise ValueError("User account is deactivated")

        # Update only provided fields (exclude unset)
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(user, field, value)

        # Vectorize new data
        if any(key in update_data for key in ['career_interest', 'github_username', 'estudent_profile']):
            self._update_user_embedding(user)

        return await self.repo.update(user)

    async def change_password(self, user_id: str, data: PasswordChange) -> bool:
        """
        Change user's password.
        Requires current password verification.
        """
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise ValueError("User not found for password change")

        if not user.is_active:
            raise ValueError("User account is deactivated")

        # Verify current password
        if not verify_password(data.current_password, user.password_hash):
            raise ValueError("Current password is incorrect")

        # Validate new password is different
        if data.current_password == data.new_password:
            raise ValueError("New password must be different from current password")

        # Update password
        user.password_hash = hash_password(data.new_password)
        await self.repo.update(user)
        return True

    async def delete_account(self, user_id: str, password: str) -> bool:
        """
        Delete user's own account.
        Requires password verification for security.
        Uses soft delete (sets is_active=False).
        """
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise ValueError("User not found for account deletion")

        # Verify password before deletion
        if not verify_password(password, user.password_hash):
            raise ValueError("Password is incorrect")

        # Soft delete - set is_active to False
        user.is_active = False
        await self.repo.update(user)
        return True

    # ==================== Admin Operations ====================

    async def list_users(
        self, page: int = 1, per_page: int = 10, include_inactive: bool = False
    ) -> tuple[list[User], int]:
        """
        List all users with pagination (admin only).
        Returns (users, total_count).
        """
        skip = (page - 1) * per_page
        users = await self.repo.list_all(
            skip=skip, limit=per_page, include_inactive=include_inactive
        )
        total = await self.repo.count(include_inactive=include_inactive)
        return users, total

    async def admin_get_user(self, user_id: str) -> User | None:
        """Get any user by ID (admin only)."""
        return await self.repo.get_by_id(user_id)

    async def admin_update_user(self, user_id: str, data: UserAdminUpdate) -> User:
        """
        Admin update any user.
        Can update: full_name, github_username, career_interest, role, is_active, is_admin.
        """
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise ValueError("User not found for admin update")

        # Update only provided fields
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(user, field, value)

        # Vectorize new data if needed
        if any(key in update_data for key in ['career_interest', 'github_username', 'estudent_profile']):
            self._update_user_embedding(user)

        return await self.repo.update(user)

    async def admin_delete_user(self, user_id: str, hard_delete: bool = False) -> bool:
        """
        Admin delete any user.
        By default uses soft delete (is_active=False).
        Set hard_delete=True to permanently remove user.
        """
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise ValueError("User not found for deletion")

        if hard_delete:
            return await self.repo.delete(user)
        else:
            # Soft delete
            user.is_active = False
            await self.repo.update(user)
            return True

    async def admin_reactivate_user(self, user_id: str) -> User:
        """Reactivate a soft-deleted user (admin only)."""
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise ValueError("User not found for reactivation")

        if user.is_active:
            raise ValueError("User is already active")

        user.is_active = True
        return await self.repo.update(user)

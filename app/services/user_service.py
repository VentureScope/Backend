"""
User Management Service - Business logic for user CRUD operations.
Phase B Implementation.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserUpdate, PasswordChange, UserAdminUpdate, SkillsUpdate
from app.services.embedding_service import get_embedding_service
from app.services.github_service import fetch_github_profile_description
from app.services.s3_service import get_s3_service, S3UploadError


class UserService:
    """Service for user management operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = UserRepository(db)
        self.embedding_service = get_embedding_service()
        
        from app.services.knowledge_service import KnowledgeService
        self.knowledge_service = KnowledgeService(db)
        self.s3_service = get_s3_service()

    # ==================== Helper Operations ====================

    async def _update_user_embedding(self, user: User) -> None:
        """Helper to compute and update the user's embedding based on their current text attributes."""
        github_profile_desc = await fetch_github_profile_description(user.github_username) if user.github_username else None
        
        doc = self.embedding_service.construct_user_document(
            career_interest=user.career_interest,
            github_profile=github_profile_desc,
            estudent_profile=user.estudent_profile,
            skills=user.skills,
            cv_url=user.cv_url,
        )
        user.embedding = self.embedding_service.generate_embedding(doc)

        # Update knowledge base with individual profile fields
        chunks = []
        if user.career_interest:
            chunks.append(f"Career Interest & Goals: {user.career_interest}")
        if user.skills:
            skills_text = ", ".join(user.skills)
            chunks.append(f"Skills: {skills_text}")
        if user.cv_url:
            chunks.append(f"CV uploaded at: {user.cv_url}")
        if github_profile_desc:
            chunks.append(f"GitHub Profile & Projects: {github_profile_desc}")
            
        await self.knowledge_service.replace_user_knowledge(
            user.id, chunks, source_type="profile"
        )

    # ==================== Self-Service Operations ====================

    async def get_profile(self, user_id: str) -> User | None:
        """Get user profile by ID."""
        return await self.repo.get_by_id(user_id)

    async def update_profile(self, user_id: str, data: UserUpdate) -> User:
        """
        Update user's own profile.
        Allows updating: full_name, github_username, career_interest, skills.
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
        if any(key in update_data for key in ['career_interest', 'github_username', 'estudent_profile', 'skills']):
            await self._update_user_embedding(user)

        return await self.repo.update(user)

    async def update_skills(self, user_id: str, data: SkillsUpdate) -> User:
        """
        Update user's skills.
        """
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise ValueError("User profile not found")

        if not user.is_active:
            raise ValueError("User account is deactivated")

        user.skills = data.skills
        await self._update_user_embedding(user)

        return await self.repo.update(user)

    async def upload_cv(
        self,
        user_id: str,
        file_content: bytes,
        filename: str,
        content_type: str,
    ) -> str:
        """
        Upload a CV file for the user.
        
        Args:
            user_id: The user's ID
            file_content: The CV file content as bytes
            filename: Original filename
            content_type: MIME type of the file
            
        Returns:
            The S3 URL of the uploaded CV
            
        Raises:
            ValueError: If user not found or deactivated
            S3UploadError: If upload fails
        """
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise ValueError("User profile not found")

        if not user.is_active:
            raise ValueError("User account is deactivated")

        # Delete old CV if exists
        if user.cv_url:
            await self.s3_service.delete_cv(user.cv_url)

        # Upload new CV
        cv_url = await self.s3_service.upload_cv(
            user_id=user_id,
            file_content=file_content,
            filename=filename,
            content_type=content_type,
        )

        # Update user with CV URL
        user.cv_url = cv_url
        await self._update_user_embedding(user)

        await self.repo.update(user)
        return cv_url

    async def delete_cv(self, user_id: str) -> bool:
        """
        Delete the user's CV.
        """
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise ValueError("User profile not found")

        if not user.is_active:
            raise ValueError("User account is deactivated")

        if user.cv_url:
            await self.s3_service.delete_cv(user.cv_url)
            user.cv_url = None
            await self._update_user_embedding(user)
            await self.repo.update(user)

        return True

    async def get_cv_presigned_url(self, user_id: str, expiration: int = 3600) -> str | None:
        """
        Get a presigned URL for downloading the user's CV.
        """
        user = await self.repo.get_by_id(user_id)
        if not user or not user.cv_url:
            return None

        return self.s3_service.get_presigned_url(user.cv_url, expiration)

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

        # Delete CV if exists
        if user.cv_url:
            await self.s3_service.delete_cv(user.cv_url)

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
        Can update: full_name, github_username, career_interest, skills, cv_url, role, is_active, is_admin.
        """
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise ValueError("User not found for admin update")

        # Update only provided fields
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(user, field, value)

        # Vectorize new data if needed
        if any(key in update_data for key in ['career_interest', 'github_username', 'estudent_profile', 'skills']):
            await self._update_user_embedding(user)

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
            # Delete CV if exists
            if user.cv_url:
                await self.s3_service.delete_cv(user.cv_url)
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

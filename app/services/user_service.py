"""
User Management Service - Business logic for user CRUD operations.
Phase B Implementation.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserUpdate, PasswordChange, UserAdminUpdate, SkillsUpdate
from app.services.github_service import fetch_github_profile_description
from app.services.s3_service import get_s3_service, S3UploadError
from app.tasks.user_embedding_task import generate_user_profile_embedding

logger = logging.getLogger(__name__)


class UserService:
    """Service for user management operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = UserRepository(db)
        
        from app.services.knowledge_service import KnowledgeService
        self.knowledge_service = KnowledgeService(db)
        self.s3_service = get_s3_service()

    # ==================== Helper Operations ====================

    async def _queue_user_embedding(self, user: User) -> None:
        """Queue embedding generation in background."""
        user.embedding_status = "pending"
        social_links = user.social_links

        # Get experiences for this user
        from app.services.experience_service import ExperienceService
        exp_service = ExperienceService(self.db)
        experiences = await exp_service.get_all_for_user(user.id)

        # Serialize ORM objects to plain dicts — Celery/Kombu cannot
        # JSON-serialize SQLAlchemy model instances directly
        experiences_data = [
            {
                "job_title": e.job_title,
                "company": e.company,
                "start_date": str(e.start_date.date()) if e.start_date else None,
                "end_date": str(e.end_date.date()) if e.end_date else None,
                "description": e.description,
                "skills_used": e.skills_used,
            }
            for e in experiences
        ]

        generate_user_profile_embedding.delay(
            user.id, social_links=social_links, experiences=experiences_data
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
        if any(key in update_data for key in ['career_interest', 'github_username', 'estudent_profile', 'skills', 'social_links']):
            await self._queue_user_embedding(user)

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
        await self._queue_user_embedding(user)

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
        await self._queue_user_embedding(user)

        # Extract CV text and create knowledge chunks
        try:
            from app.services.cv_extractor import get_cv_extractor
            extractor = get_cv_extractor()
            cv_text = extractor.extract_text(file_content, filename)
            
            if cv_text and len(cv_text) > 50:
                chunks = extractor.chunk_text(cv_text, chunk_size=1000, overlap=100)
                
                if chunks:
                    for chunk in chunks:
                        await self.knowledge_service.ingest_knowledge(
                            user_id=user_id,
                            content=chunk,
                            source_type="resume"
                        )
                    logger.info(f"Created {len(chunks)} knowledge chunks from CV for user {user_id}")
        except Exception as e:
            logger.warning(f"Failed to extract CV text: {e}")

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
            await self._queue_user_embedding(user)
            await self.repo.update(user)

        return True

    async def get_cv_presigned_url(self, user_id: str, expiration: int = 3600) -> str | None:
        """
        Get the public URL for downloading the user's CV.
        Since CVs are uploaded as public, return the direct URL.
        """
        user = await self.repo.get_by_id(user_id)
        if not user or not user.cv_url:
            return None

        return user.cv_url

    async def upload_profile_picture(
        self,
        user_id: str,
        file_content: bytes,
        filename: str,
        content_type: str,
    ) -> str:
        """
        Upload a profile picture for the user.

        Args:
            user_id: The user's ID
            file_content: The profile picture file content as bytes
            filename: Original filename
            content_type: MIME type of the file

        Returns:
            The URL of the uploaded profile picture

        Raises:
            ValueError: If user not found or deactivated
            S3UploadError: If upload fails
        """
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise ValueError("User profile not found")

        if not user.is_active:
            raise ValueError("User account is deactivated")

        # Delete old profile picture if exists
        if user.profile_picture_url:
            await self.s3_service.delete_profile_picture(user.profile_picture_url)

        # Upload new profile picture
        profile_picture_url = await self.s3_service.upload_profile_picture(
            user_id=user_id,
            file_content=file_content,
            filename=filename,
            content_type=content_type,
        )

        # Update user with profile picture URL
        user.profile_picture_url = profile_picture_url

        await self.repo.update(user)

        return profile_picture_url

    async def delete_profile_picture(self, user_id: str) -> bool:
        """
        Delete the user's profile picture.
        """
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise ValueError("User profile not found")

        if not user.is_active:
            raise ValueError("User account is deactivated")

        if user.profile_picture_url:
            await self.s3_service.delete_profile_picture(user.profile_picture_url)
            user.profile_picture_url = None
            await self.repo.update(user)

        return True

    async def get_profile_picture_url(self, user_id: str) -> str | None:
        """
        Get the profile picture URL for the user.
        """
        user = await self.repo.get_by_id(user_id)
        if not user or not user.profile_picture_url:
            return None

        return user.profile_picture_url

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

    async def delete_account(self, user_id: str, password: str | None) -> bool:
        """
        Delete user's own account (soft delete).

        - Email/password accounts: password required for verification.
        - OAuth-only accounts (password_hash is None): no password needed.
        """
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise ValueError("User not found for account deletion")

        if not user.is_active:
            raise ValueError("Account is already deactivated")

        if user.password_hash is not None:
            # Email/password account — require password confirmation
            if not password:
                raise ValueError(
                    "Password is required to delete an email/password account."
                )
            if not verify_password(password, user.password_hash):
                raise ValueError("Incorrect password.")

        # Delete S3 assets
        if user.cv_url:
            await self.s3_service.delete_cv(user.cv_url)

        # Soft delete — set is_active to False
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
            await self._queue_user_embedding(user)

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

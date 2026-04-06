"""
Repository for AcademicTranscript database operations.
"""

from typing import List, Optional
from sqlalchemy import select, delete, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.academic_transcript import AcademicTranscript


class TranscriptRepository:
    """Repository for managing academic transcript data access."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, transcript: AcademicTranscript) -> AcademicTranscript:
        """
        Create a new academic transcript.

        Args:
            transcript: AcademicTranscript instance to create

        Returns:
            The created AcademicTranscript instance
        """
        self.db.add(transcript)
        await self.db.commit()
        await self.db.refresh(transcript)
        return transcript

    async def get_by_id(
        self, transcript_id: str, user_id: str
    ) -> Optional[AcademicTranscript]:
        """
        Get a specific transcript by ID, ensuring it belongs to the user.

        Args:
            transcript_id: Transcript ID
            user_id: User ID (for ownership verification)

        Returns:
            AcademicTranscript if found and owned by user, None otherwise
        """
        stmt = select(AcademicTranscript).where(
            AcademicTranscript.id == transcript_id,
            AcademicTranscript.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_by_user(self, user_id: str) -> List[AcademicTranscript]:
        """
        Get all transcript versions for a user, ordered by version descending.

        Args:
            user_id: User ID

        Returns:
            List of AcademicTranscript instances (newest first)
        """
        stmt = (
            select(AcademicTranscript)
            .where(AcademicTranscript.user_id == user_id)
            .order_by(desc(AcademicTranscript.version))
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_by_user(self, user_id: str) -> Optional[AcademicTranscript]:
        """
        Get the latest transcript version for a user.

        Args:
            user_id: User ID

        Returns:
            Latest AcademicTranscript if any exist, None otherwise
        """
        stmt = (
            select(AcademicTranscript)
            .where(AcademicTranscript.user_id == user_id)
            .order_by(desc(AcademicTranscript.version))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_next_version_number(self, user_id: str) -> int:
        """
        Get the next version number for a user's transcript.

        Args:
            user_id: User ID

        Returns:
            Next version number (1 if no transcripts exist)
        """
        stmt = select(func.max(AcademicTranscript.version)).where(
            AcademicTranscript.user_id == user_id
        )
        result = await self.db.execute(stmt)
        max_version = result.scalar_one_or_none()
        return (max_version or 0) + 1

    async def count_by_user(self, user_id: str) -> int:
        """
        Count total number of transcript versions for a user.

        Args:
            user_id: User ID

        Returns:
            Count of transcript versions
        """
        stmt = select(func.count(AcademicTranscript.id)).where(
            AcademicTranscript.user_id == user_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def delete(self, transcript: AcademicTranscript) -> None:
        """
        Delete a specific transcript.

        Args:
            transcript: AcademicTranscript instance to delete
        """
        await self.db.delete(transcript)
        await self.db.commit()

    async def delete_all_by_user(self, user_id: str) -> int:
        """
        Delete all transcripts for a user.

        Args:
            user_id: User ID

        Returns:
            Number of transcripts deleted
        """
        stmt = delete(AcademicTranscript).where(AcademicTranscript.user_id == user_id)
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount

    async def delete_old_versions(self, user_id: str, keep_count: int = 3) -> int:
        """
        Delete old transcript versions, keeping only the most recent N versions.

        Args:
            user_id: User ID
            keep_count: Number of recent versions to keep (default: 3)

        Returns:
            Number of transcripts deleted
        """
        # Get all versions ordered by version descending
        all_transcripts = await self.get_all_by_user(user_id)

        # If we have more than keep_count, delete the oldest ones
        if len(all_transcripts) <= keep_count:
            return 0

        transcripts_to_delete = all_transcripts[keep_count:]
        delete_count = 0

        for transcript in transcripts_to_delete:
            await self.db.delete(transcript)
            delete_count += 1

        await self.db.commit()
        return delete_count

    async def get_by_student_id(self, student_id: str) -> List[AcademicTranscript]:
        """
        Get all transcripts with a specific student_id.
        Useful for cross-referencing or validation.

        Args:
            student_id: Student ID from e-student

        Returns:
            List of AcademicTranscript instances
        """
        stmt = (
            select(AcademicTranscript)
            .where(AcademicTranscript.student_id == student_id)
            .order_by(desc(AcademicTranscript.version))
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

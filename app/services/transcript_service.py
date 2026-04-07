"""
Service layer for AcademicTranscript business logic.
Includes dynamic GPA validation based on user config and grade recommendations.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Set
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academic_transcript import AcademicTranscript
from app.repositories.transcript_repository import TranscriptRepository
from app.services.transcript_config_service import TranscriptConfigService
from app.schemas.academic_transcript import TranscriptCreate, TranscriptUploadResponse
from app.schemas.transcript_config import GradeRecommendation


class TranscriptService:
    """Service for managing academic transcripts with validation and version control."""

    MAX_VERSIONS = 3  # Keep only the 3 most recent versions

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = TranscriptRepository(db)
        self.config_service = TranscriptConfigService(db)

    async def create_transcript(
        self, user_id: str, data: TranscriptCreate
    ) -> tuple[AcademicTranscript, int, bool]:
        """
        Create a new transcript version with validation.

        Performs the following:
        1. Gets or creates user's grading config
        2. Validates GPA values against user's configured scale
        3. Checks student_id consistency if this isn't the first upload
        4. Creates new version
        5. Cleans up old versions (keeps latest 3)

        Args:
            user_id: User ID
            data: Transcript data to upload

        Returns:
            Tuple of (created transcript, versions_deleted count, is_first_upload)

        Raises:
            ValueError: If validation fails (GPA out of bounds, student_id mismatch, etc.)
        """
        # 1. Get or create user's grading configuration
        config = await self.config_service.get_or_create_default(user_id)

        # 2. Validate GPA values against user's scale
        await self._validate_gpa_bounds(data, config.gpa_scale)

        # 3. Check student_id consistency
        is_first_upload = await self.repo.count_by_user(user_id) == 0

        if not is_first_upload and data.transcript_data.student_id:
            await self._validate_student_id_consistency(
                user_id, data.transcript_data.student_id
            )

        # 4. Get next version number
        next_version = await self.repo.get_next_version_number(user_id)

        # 5. Create new transcript
        transcript = AcademicTranscript(
            id=str(uuid.uuid4()),
            user_id=user_id,
            student_id=data.transcript_data.student_id,
            transcript_data=data.transcript_data.model_dump(),
            version=next_version,
            uploaded_at=datetime.now(timezone.utc),
        )

        transcript = await self.repo.create(transcript)

        # 6. Clean up old versions (keep only latest 3)
        versions_deleted = await self.repo.delete_old_versions(
            user_id, self.MAX_VERSIONS
        )

        # 7. Update user profile and regenerate embedding
        from app.services.user_service import UserService
        from app.services.knowledge_service import KnowledgeService
        
        user_service = UserService(self.db)
        user = await user_service.get_profile(user_id)
        if user:
            user.estudent_profile = self._generate_estudent_summary(data)
            await user_service._update_user_embedding(user)
            await self.db.commit()

        # 8. Update Knowledge Base chunks
        knowledge_service = KnowledgeService(self.db)
        chunks = self._generate_transcript_chunks(data)
        await knowledge_service.replace_user_knowledge(user_id, chunks, source_type="transcript_course")

        return transcript, versions_deleted, is_first_upload

    async def get_user_transcripts(self, user_id: str) -> List[AcademicTranscript]:
        """
        Get all transcript versions for a user.

        Args:
            user_id: User ID

        Returns:
            List of transcripts ordered by version descending (newest first)
        """
        return await self.repo.get_all_by_user(user_id)

    async def get_latest_transcript(self, user_id: str) -> AcademicTranscript | None:
        """
        Get the latest transcript version for a user.

        Args:
            user_id: User ID

        Returns:
            Latest transcript or None if no transcripts exist
        """
        return await self.repo.get_latest_by_user(user_id)

    async def get_transcript_by_id(
        self, transcript_id: str, user_id: str
    ) -> AcademicTranscript:
        """
        Get a specific transcript by ID.

        Args:
            transcript_id: Transcript ID
            user_id: User ID (for ownership verification)

        Returns:
            AcademicTranscript instance

        Raises:
            ValueError: If transcript not found or doesn't belong to user
        """
        transcript = await self.repo.get_by_id(transcript_id, user_id)

        if transcript is None:
            raise ValueError("Transcript not found or access denied")

        return transcript

    async def delete_transcript(self, transcript_id: str, user_id: str) -> None:
        """
        Delete a specific transcript version.

        Args:
            transcript_id: Transcript ID to delete
            user_id: User ID (for ownership verification)

        Raises:
            ValueError: If transcript not found or doesn't belong to user
        """
        transcript = await self.get_transcript_by_id(transcript_id, user_id)
        await self.repo.delete(transcript)

    async def delete_all_transcripts(self, user_id: str) -> int:
        """
        Delete all transcripts for a user.

        Args:
            user_id: User ID

        Returns:
            Number of transcripts deleted
        """
        return await self.repo.delete_all_by_user(user_id)

    async def get_grade_recommendation(
        self, user_id: str, data: TranscriptCreate
    ) -> GradeRecommendation:
        """
        Recommend a grading system based on detected grades in transcript data.

        Args:
            user_id: User ID
            data: Transcript data to analyze

        Returns:
            GradeRecommendation with suggested preset
        """
        # Extract all unique grades from the transcript
        detected_grades = self._extract_grades(data)

        # Use config service to get recommendation
        return TranscriptConfigService.recommend_grading_system(detected_grades)

    async def _validate_gpa_bounds(
        self, data: TranscriptCreate, gpa_scale: float
    ) -> None:
        """
        Validate that all GPA values are within the configured scale.

        Args:
            data: Transcript data to validate
            gpa_scale: Maximum GPA value from user's config

        Raises:
            ValueError: If any GPA value exceeds the scale
        """
        for semester in data.transcript_data.semesters:
            # Validate SGPA
            if semester.semester_summary.sgpa > gpa_scale:
                raise ValueError(
                    f"Semester GPA {semester.semester_summary.sgpa} exceeds "
                    f"configured GPA scale of {gpa_scale}. "
                    f"Please update your grading configuration at /api/transcript-configs."
                )

            # Validate CGPA
            if semester.cumulative_summary.cgpa > gpa_scale:
                raise ValueError(
                    f"Cumulative GPA {semester.cumulative_summary.cgpa} exceeds "
                    f"configured GPA scale of {gpa_scale}. "
                    f"Please update your grading configuration at /api/transcript-configs."
                )

    async def _validate_student_id_consistency(
        self, user_id: str, new_student_id: str
    ) -> None:
        """
        Validate that student_id matches across all versions for the same user.

        Args:
            user_id: User ID
            new_student_id: Student ID from new upload

        Raises:
            ValueError: If student_id doesn't match existing transcripts
        """
        existing_transcripts = await self.repo.get_all_by_user(user_id)

        for transcript in existing_transcripts:
            if transcript.student_id and transcript.student_id != new_student_id:
                raise ValueError(
                    f"Student ID mismatch: new upload has '{new_student_id}' but "
                    f"existing transcripts have '{transcript.student_id}'. "
                    f"Student ID must be consistent across all uploads for the same user."
                )

    def _extract_grades(self, data: TranscriptCreate) -> Set[str]:
        """
        Extract all unique grades from transcript data.

        Args:
            data: Transcript data

        Returns:
            Set of unique grade strings
        """
        grades = set()

        for semester in data.transcript_data.semesters:
            for course in semester.courses:
                if course.grade:
                    grades.add(course.grade)

        return grades

    def _generate_estudent_summary(self, data: TranscriptCreate) -> str:
        semesters = data.transcript_data.semesters
        if not semesters:
            return "No transcript data available."
        
        latest_semester = semesters[-1]
        cgpa = latest_semester.cumulative_summary.cgpa
        total_credits = latest_semester.cumulative_summary.credit_hours
        
        courses = [c.code for s in semesters for c in s.courses]
        unique_courses = list(dict.fromkeys(courses)) # preserve order, remove duplicates
        
        summary = f"Student ID: {data.transcript_data.student_id or 'Unknown'}. "
        summary += f"Cumulative GPA: {cgpa}. "
        summary += f"Total Credit Hours: {total_credits}. "
        summary += f"Courses Taken: {', '.join(unique_courses[:20])}"
        if len(unique_courses) > 20:
            summary += "..."
            
        return summary

    def _generate_transcript_chunks(self, data: TranscriptCreate) -> list[str]:
        semesters = data.transcript_data.semesters
        chunks = []
        for semester in semesters:
            sem_title = f"{semester.academic_year} {semester.semester}"
            for course in semester.courses:
                chunk = f"Course: {course.code} - {course.title} ({sem_title}). Credits: {course.credit_hours}. Grade: {course.grade}. Points: {course.points}."
                chunks.append(chunk)
            
            # Semester summary chunk
            summary = semester.semester_summary
            chunks.append(f"Semester Summary for {sem_title}: SGPA={summary.sgpa}, CrHrs={summary.credit_hours}, Pts={summary.points}.")
        return chunks

"""
Service layer for TranscriptConfig business logic.
Includes preset configurations and grade recommendations.
"""

import uuid
from typing import List, Set, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.transcript_config import TranscriptConfig
from app.repositories.transcript_config_repository import TranscriptConfigRepository
from app.schemas.transcript_config import (
    TranscriptConfigCreate,
    TranscriptConfigUpdate,
    GradingPreset,
    GradingPresetsResponse,
    GradeRecommendation,
)


class TranscriptConfigService:
    """Service for managing transcript configurations and grading presets."""

    # Predefined grading system presets
    PRESETS = [
        GradingPreset(
            name="US 4.0 Scale (Standard)",
            description="Standard US grading system with 4.0 maximum GPA. Most common in American universities.",
            gpa_scale=4.0,
            grading_schema={
                "A+": 4.0,
                "A": 4.0,
                "A-": 3.7,
                "B+": 3.3,
                "B": 3.0,
                "B-": 2.7,
                "C+": 2.3,
                "C": 2.0,
                "C-": 1.7,
                "D+": 1.3,
                "D": 1.0,
                "F": 0.0,
                "W": None,  # Withdrawn
                "IP": None,  # In Progress
                "-": None,  # Not yet graded
            },
            grade_display_order=[
                "A+",
                "A",
                "A-",
                "B+",
                "B",
                "B-",
                "C+",
                "C",
                "C-",
                "D+",
                "D",
                "F",
                "W",
                "IP",
                "-",
            ],
        ),
        GradingPreset(
            name="US 5.0 Scale (Weighted)",
            description="Weighted grading system with 5.0 maximum. Used for honors/AP courses.",
            gpa_scale=5.0,
            grading_schema={
                "A": 5.0,
                "B": 4.0,
                "C": 3.0,
                "D": 2.0,
                "F": 0.0,
                "W": None,
                "IP": None,
                "-": None,
            },
            grade_display_order=["A", "B", "C", "D", "F", "W", "IP", "-"],
        ),
        GradingPreset(
            name="European 10-Point Scale",
            description="European grading system with 10-point scale. Common in Netherlands, Belgium.",
            gpa_scale=10.0,
            grading_schema={
                "10": 10.0,
                "9": 9.0,
                "8": 8.0,
                "7": 7.0,
                "6": 6.0,
                "5": 5.0,
                "4": 4.0,
                "3": 3.0,
                "2": 2.0,
                "1": 1.0,
                "NAV": None,  # Not assessed/evaluated
            },
            grade_display_order=[
                "10",
                "9",
                "8",
                "7",
                "6",
                "5",
                "4",
                "3",
                "2",
                "1",
                "NAV",
            ],
        ),
        GradingPreset(
            name="UK Classification System",
            description="UK honors degree classification system.",
            gpa_scale=4.0,
            grading_schema={
                "First": 4.0,
                "2:1": 3.3,
                "2:2": 2.7,
                "Third": 2.0,
                "Pass": 1.0,
                "Fail": 0.0,
                "W": None,
                "IP": None,
            },
            grade_display_order=[
                "First",
                "2:1",
                "2:2",
                "Third",
                "Pass",
                "Fail",
                "W",
                "IP",
            ],
        ),
        GradingPreset(
            name="Percentage-Based (100-Point)",
            description="Percentage-based grading system. Common in high schools and some international systems.",
            gpa_scale=100.0,
            grading_schema={
                "A": 90.0,
                "B": 80.0,
                "C": 70.0,
                "D": 60.0,
                "F": 50.0,
                "W": None,
                "IP": None,
            },
            grade_display_order=["A", "B", "C", "D", "F", "W", "IP"],
        ),
    ]

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = TranscriptConfigRepository(db)

    async def get_or_create_default(self, user_id: str) -> TranscriptConfig:
        """
        Get user's config or create default (US 4.0 Scale) if it doesn't exist.

        Args:
            user_id: User ID

        Returns:
            User's TranscriptConfig
        """
        config = await self.repo.get_by_user_id(user_id)

        if config is None:
            # Create default config using US 4.0 Scale preset
            default_preset = self.PRESETS[0]  # US 4.0 Scale (Standard)
            config = TranscriptConfig(
                id=str(uuid.uuid4()),
                user_id=user_id,
                gpa_scale=default_preset.gpa_scale,
                grading_schema=default_preset.grading_schema,
                grade_display_order=default_preset.grade_display_order,
            )
            config = await self.repo.create(config)

        return config

    async def create_config(
        self, user_id: str, data: TranscriptConfigCreate
    ) -> TranscriptConfig:
        """
        Create or replace user's transcript configuration.

        Args:
            user_id: User ID
            data: Configuration data

        Returns:
            Created TranscriptConfig

        Raises:
            ValueError: If configuration already exists (use update instead)
        """
        # Check if config already exists
        existing = await self.repo.get_by_user_id(user_id)
        if existing:
            raise ValueError(
                "Configuration already exists for this user. Use update endpoint instead."
            )

        config = TranscriptConfig(
            id=str(uuid.uuid4()),
            user_id=user_id,
            gpa_scale=data.gpa_scale,
            grading_schema=data.grading_schema,
            grade_display_order=data.grade_display_order,
        )

        return await self.repo.create(config)

    async def update_config(
        self, user_id: str, data: TranscriptConfigUpdate
    ) -> TranscriptConfig:
        """
        Update user's transcript configuration.
        Creates new config if it doesn't exist.

        Args:
            user_id: User ID
            data: Updated configuration data

        Returns:
            Updated TranscriptConfig
        """
        config = await self.repo.get_by_user_id(user_id)

        if config is None:
            # Create new config if doesn't exist
            config = TranscriptConfig(
                id=str(uuid.uuid4()),
                user_id=user_id,
                gpa_scale=data.gpa_scale,
                grading_schema=data.grading_schema,
                grade_display_order=data.grade_display_order,
            )
            return await self.repo.create(config)
        else:
            # Update existing config
            config.gpa_scale = data.gpa_scale
            config.grading_schema = data.grading_schema
            config.grade_display_order = data.grade_display_order
            return await self.repo.update(config)

    async def delete_config(self, user_id: str) -> None:
        """
        Delete user's configuration and recreate with default.

        Args:
            user_id: User ID
        """
        config = await self.repo.get_by_user_id(user_id)
        if config:
            await self.repo.delete(config)

    async def reset_to_default(self, user_id: str) -> TranscriptConfig:
        """
        Reset user's configuration to default (US 4.0 Scale).

        Args:
            user_id: User ID

        Returns:
            Reset TranscriptConfig with default values
        """
        # Delete existing config
        await self.delete_config(user_id)

        # Create new default config
        return await self.get_or_create_default(user_id)

    @classmethod
    def get_presets(cls) -> GradingPresetsResponse:
        """
        Get all available grading system presets.

        Returns:
            GradingPresetsResponse with list of presets
        """
        return GradingPresetsResponse(presets=cls.PRESETS)

    @classmethod
    def recommend_grading_system(cls, detected_grades: Set[str]) -> GradeRecommendation:
        """
        Recommend a grading system based on detected grades in transcript.

        Args:
            detected_grades: Set of unique grade strings found in transcript

        Returns:
            GradeRecommendation with suggested preset and confidence level
        """
        # Remove null-value grades from detection
        grade_set = {
            g for g in detected_grades if g not in ["-", "W", "IP", "NAV", None, ""]
        }

        if not grade_set:
            # No grades to analyze, return default
            return GradeRecommendation(
                detected_grades=list(detected_grades),
                recommended_preset="US 4.0 Scale (Standard)",
                confidence="low",
                reason="No gradable grades detected. Using default US 4.0 scale.",
                suggested_config=cls.PRESETS[0],
            )

        # Check for US letter grades with +/-
        us_letter_grades = {
            "A+",
            "A",
            "A-",
            "B+",
            "B",
            "B-",
            "C+",
            "C",
            "C-",
            "D+",
            "D",
            "F",
        }
        if grade_set.issubset(us_letter_grades):
            return GradeRecommendation(
                detected_grades=list(detected_grades),
                recommended_preset="US 4.0 Scale (Standard)",
                confidence="high",
                reason="Detected US letter grades with plus/minus modifiers (A+, B-, etc.).",
                suggested_config=cls.PRESETS[0],
            )

        # Check for simple letter grades (A, B, C, D, F)
        simple_letter_grades = {"A", "B", "C", "D", "F"}
        if grade_set.issubset(simple_letter_grades):
            return GradeRecommendation(
                detected_grades=list(detected_grades),
                recommended_preset="US 5.0 Scale (Weighted)",
                confidence="medium",
                reason="Detected simple letter grades without modifiers. Could be standard or weighted scale.",
                suggested_config=cls.PRESETS[1],
            )

        # Check for numeric grades (1-10)
        numeric_grades = {str(i) for i in range(1, 11)}
        if grade_set.issubset(numeric_grades):
            return GradeRecommendation(
                detected_grades=list(detected_grades),
                recommended_preset="European 10-Point Scale",
                confidence="high",
                reason="Detected numeric grades from 1-10, typical of European grading systems.",
                suggested_config=cls.PRESETS[2],
            )

        # Check for UK classification
        uk_classifications = {"First", "2:1", "2:2", "Third", "Pass", "Fail"}
        if grade_set.issubset(uk_classifications):
            return GradeRecommendation(
                detected_grades=list(detected_grades),
                recommended_preset="UK Classification System",
                confidence="high",
                reason="Detected UK degree classifications (First, 2:1, 2:2, Third).",
                suggested_config=cls.PRESETS[3],
            )

        # Check for percentage-based grades
        try:
            # Try to parse all grades as numbers
            numeric_values = {
                float(g) for g in grade_set if g.replace(".", "").isdigit()
            }
            if numeric_values and all(0 <= v <= 100 for v in numeric_values):
                return GradeRecommendation(
                    detected_grades=list(detected_grades),
                    recommended_preset="Percentage-Based (100-Point)",
                    confidence="medium",
                    reason="Detected numeric values that appear to be percentages (0-100).",
                    suggested_config=cls.PRESETS[4],
                )
        except (ValueError, TypeError):
            pass

        # Default fallback
        return GradeRecommendation(
            detected_grades=list(detected_grades),
            recommended_preset="US 4.0 Scale (Standard)",
            confidence="low",
            reason=f"Unrecognized grading pattern with grades: {', '.join(list(grade_set)[:5])}. Using default US 4.0 scale.",
            suggested_config=cls.PRESETS[0],
        )

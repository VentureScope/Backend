"""add_jobs_and_roadmap_tables

Revision ID: auto_20260514
Revises: auto_20260507
Create Date: 2026-05-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers
revision = "auto_20260514"
down_revision = "auto_20260507"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension if not already enabled
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create jobs table
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(255), nullable=True),
        sa.Column("company_name", sa.String(500), nullable=True),
        sa.Column("job_title", sa.String(500), nullable=True),
        sa.Column("normalized_title", sa.String(500), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column("city", sa.String(255), nullable=True),
        sa.Column("region", sa.String(255), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("is_remote", sa.Boolean, nullable=True),
        sa.Column("job_type", sa.String(100), nullable=True),
        sa.Column("education_level", sa.String(255), nullable=True),
        sa.Column("skills", sa.JSON, nullable=True),
        sa.Column("source", sa.String(50), nullable=False, server_default="manual_csv"),
        sa.Column("posted_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Index("ix_jobs_normalized_title", "normalized_title"),
        sa.Index("ix_jobs_company_name", "company_name"),
        sa.Index("ix_jobs_source", "source"),
        sa.UniqueConstraint("job_id", name="uq_jobs_job_id"),
    )

    # Create learning_roadmaps table
    op.create_table(
        "learning_roadmaps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("trend_name", sa.String(255), nullable=True),
        sa.Column("goal", sa.Text, nullable=True),
        sa.Column("total_weeks", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Index("ix_learning_roadmaps_user_id", "user_id"),
    )

    # Create learning_roadmap_steps table
    op.create_table(
        "learning_roadmap_steps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("roadmap_id", sa.String(36), sa.ForeignKey("learning_roadmaps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("week_number", sa.Integer, nullable=False),
        sa.Column("topic", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Index("ix_learning_roadmap_steps_roadmap_id", "roadmap_id"),
    )

    # Create learning_roadmap_step_resources table
    op.create_table(
        "learning_roadmap_step_resources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("step_id", sa.String(36), sa.ForeignKey("learning_roadmap_steps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("url", sa.String(2000), nullable=True),
        sa.Column("resource_type", sa.String(50), nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Index("ix_learning_roadmap_step_resources_step_id", "step_id"),
    )

    # Create learning_roadmap_progress table
    op.create_table(
        "learning_roadmap_progress",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_id", sa.String(36), sa.ForeignKey("learning_roadmap_steps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="not_started"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Index("ix_learning_roadmap_progress_user_id", "user_id"),
        sa.Index("ix_learning_roadmap_progress_step_id", "step_id"),
        sa.UniqueConstraint("user_id", "step_id", name="uq_user_step_progress"),
    )

    # Create resumes table
    op.create_table(
        "resumes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_role", sa.String(255), nullable=False),
        sa.Column("professional_summary", sa.Text, nullable=True),
        sa.Column("skills", sa.JSON, nullable=True),
        sa.Column("experience", sa.JSON, nullable=True),
        sa.Column("education", sa.JSON, nullable=True),
        sa.Column("projects", sa.JSON, nullable=True),
        sa.Column("certifications", sa.JSON, nullable=True),
        sa.Column("trending_skills_highlighted", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Index("ix_resumes_user_id", "user_id"),
    )


def downgrade() -> None:
    op.drop_table("resumes")
    op.drop_table("learning_roadmap_progress")
    op.drop_table("learning_roadmap_step_resources")
    op.drop_table("learning_roadmap_steps")
    op.drop_table("learning_roadmaps")
    op.drop_table("jobs")

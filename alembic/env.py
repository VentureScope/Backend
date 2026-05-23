import asyncio
import os
from logging.config import fileConfig
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import your models here for autogenerate support
from app.models.user import User
from app.models.oauth_account import OAuthAccount
from app.models.token_blocklist import TokenBlocklist
from app.models.chat import ChatSession, ChatMessage
from app.models.notification import Notification
from app.models.user_knowledge import UserKnowledge
from app.models.academic_transcript import AcademicTranscript
from app.models.transcript_config import TranscriptConfig
from app.models.github_sync_snapshot import GitHubSyncSnapshot
from app.models.experience import Experience
from app.models.job import Job
from app.models.roadmap import LearningRoadmap, LearningRoadmapStep, LearningRoadmapStepResource, LearningRoadmapProgress, LearningRoadmapResourceProgress
from app.models.resume import Resume
from app.models.organization import Organization, OrganizationMember, OrganizationInvite, OrganizationRoadmap
from app.models.org_chat import OrgChatSession, OrgChatMessage

# Set target metadata for autogenerate
from app.core.database import Base
target_metadata = Base.metadata

# Get database URL from environment variable
# This allows different URLs for different environments (dev, test, prod)
database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Helper function to run migrations with connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in async mode."""
    url = config.get_main_option("sqlalchemy.url")

    connectable = create_async_engine(url, poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

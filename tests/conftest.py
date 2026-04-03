import os
import pytest
import pytest_asyncio
import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from httpx import AsyncClient, ASGITransport
from faker import Faker

from app.core.database import Base, get_db
from app.main import app
from app.core.config import settings

fake = Faker()

# Test database URL
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://venturescope:venturescope@localhost:5432/venturescope_test",
)


@pytest_asyncio.fixture(scope="function")
async def engine():
    """Create test database engine for each test."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test with proper transaction isolation."""
    # Create tables before each test
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session factory
    async_session_factory = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Create and yield session
    async with async_session_factory() as session:
        yield session

    # Drop tables after each test to ensure clean state
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create test client with database session override."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def user_data():
    """Generate fake user data for tests."""
    return {
        "email": fake.email(),
        "password": "Test123!",
        "full_name": fake.name(),
        "career_interest": "Software Development",
        "role": "professional",
    }


@pytest.fixture
def mock_user():
    """Generate mock user data without password."""
    return {
        "id": fake.uuid4(),
        "email": fake.email(),
        "full_name": fake.name(),
        "career_interest": "Software Development",
        "role": "professional",
        "github_username": None,
    }

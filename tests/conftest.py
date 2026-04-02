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


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Create test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

        async_session = sessionmaker(
            bind=connection, class_=AsyncSession, expire_on_commit=False
        )

        async with async_session() as session:
            yield session
            await session.rollback()

        await connection.run_sync(Base.metadata.drop_all)


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

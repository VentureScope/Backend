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
from app.core.security import create_access_token, hash_password
from app.models.user import User

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
        "password": "Test123!@#",
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
        "is_active": True,
        "is_admin": False,
    }


# ==================== Phase B: User Management Test Fixtures ====================


@pytest_asyncio.fixture
async def registered_user(client: AsyncClient, user_data: dict) -> dict:
    """Register a user and return user data with id."""
    response = await client.post("/api/auth/register", json=user_data)
    assert response.status_code == 200
    user_info = response.json()
    user_info["password"] = user_data["password"]  # Include password for login tests
    return user_info


@pytest_asyncio.fixture
async def authenticated_user(client: AsyncClient, registered_user: dict) -> dict:
    """Register and login a user, return user data with token."""
    login_data = {
        "email": registered_user["email"],
        "password": registered_user["password"],
    }
    response = await client.post("/api/auth/login", json=login_data)
    assert response.status_code == 200
    token_data = response.json()

    return {
        **registered_user,
        "access_token": token_data["access_token"],
        "headers": {"Authorization": f"Bearer {token_data['access_token']}"},
    }


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """Create an admin user directly in the database."""
    admin = User(
        email="admin@venturescope.example.com",
        password_hash=hash_password("AdminPass123!"),
        full_name="Admin User",
        role="professional",
        is_active=True,
        is_admin=True,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest_asyncio.fixture
async def authenticated_admin(
    client: AsyncClient, admin_user: User, db_session: AsyncSession
) -> dict:
    """Create and authenticate an admin user, return with token."""
    # Ensure the admin user is committed and visible to the app
    await db_session.commit()

    # Login the admin user
    login_data = {
        "email": admin_user.email,
        "password": "AdminPass123!",
    }
    response = await client.post("/api/auth/login", json=login_data)
    assert response.status_code == 200, f"Admin login failed: {response.json()}"
    token_data = response.json()

    return {
        "id": admin_user.id,
        "email": admin_user.email,
        "full_name": admin_user.full_name,
        "is_admin": admin_user.is_admin,
        "access_token": token_data["access_token"],
        "headers": {"Authorization": f"Bearer {token_data['access_token']}"},
    }


@pytest_asyncio.fixture
async def multiple_users(db_session: AsyncSession) -> list[User]:
    """Create multiple test users for pagination testing."""
    users = []
    for i in range(15):  # Create 15 users for pagination testing
        user = User(
            email=f"user{i}@test.com",
            password_hash=hash_password("Test123!"),
            full_name=f"Test User {i}",
            role="professional",
            is_active=True,
            is_admin=False,
        )
        db_session.add(user)
        users.append(user)

    await db_session.commit()
    for user in users:
        await db_session.refresh(user)

    return users

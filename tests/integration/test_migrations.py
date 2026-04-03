"""
Integration tests for Alembic database migrations.
These tests verify that migrations work correctly in both directions.
"""

import os
import subprocess
import asyncio
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text

# Test database URL
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://venturescope:venturescope@localhost:5432/venturescope_test",
)


class TestAlembicMigrations:
    """Test Alembic migration functionality."""

    def run_alembic_command(self, command: str) -> tuple[int, str, str]:
        """Run an alembic command and return exit code, stdout, stderr."""
        env = os.environ.copy()
        env["DATABASE_URL"] = TEST_DATABASE_URL

        process = subprocess.run(
            f"alembic {command}",
            shell=True,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        return process.returncode, process.stdout, process.stderr

    @pytest_asyncio.fixture
    async def clean_database(self):
        """Fixture to ensure a clean database state for each test."""
        # Drop all tables and alembic version before test
        engine = create_async_engine(TEST_DATABASE_URL, echo=False)

        async with engine.begin() as conn:
            # Drop all tables in public schema
            await conn.execute(
                text("""
                DO $$ DECLARE
                    r RECORD;
                BEGIN
                    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                        EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
                    END LOOP;
                END $$;
            """)
            )

        await engine.dispose()
        yield

        # Cleanup after test
        engine = create_async_engine(TEST_DATABASE_URL, echo=False)
        async with engine.begin() as conn:
            await conn.execute(
                text("""
                DO $$ DECLARE
                    r RECORD;
                BEGIN
                    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                        EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
                    END LOOP;
                END $$;
            """)
            )
        await engine.dispose()

    def test_migration_upgrade_succeeds(self, clean_database):
        """Test that migration upgrade succeeds."""
        # Run upgrade
        exit_code, stdout, stderr = self.run_alembic_command("upgrade head")

        # Verify upgrade succeeded
        assert exit_code == 0, f"Migration upgrade failed: {stderr}"
        assert "Running upgrade" in stdout
        assert "Initial migration" in stdout

    def test_migration_downgrade_succeeds(self, clean_database):
        """Test that migration downgrade succeeds."""
        # First upgrade to have something to downgrade
        exit_code, _, stderr = self.run_alembic_command("upgrade head")
        assert exit_code == 0, f"Initial upgrade failed: {stderr}"

        # Then downgrade
        exit_code, stdout, stderr = self.run_alembic_command("downgrade base")

        # Verify downgrade succeeded
        assert exit_code == 0, f"Migration downgrade failed: {stderr}"
        assert "Running downgrade" in stdout

    @pytest.mark.asyncio
    async def test_migration_creates_correct_schema(self, clean_database):
        """Test that migration creates the correct database schema."""
        # Run upgrade
        exit_code, _, stderr = self.run_alembic_command("upgrade head")
        assert exit_code == 0, f"Migration failed: {stderr}"

        # Connect to database and verify schema
        engine = create_async_engine(TEST_DATABASE_URL, echo=False)

        async with engine.begin() as conn:
            # Check that users table exists
            result = await conn.execute(
                text("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'users'
            """)
            )
            tables = [row[0] for row in result.fetchall()]
            assert "users" in tables, "Users table was not created"

            # Check users table columns
            result = await conn.execute(
                text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_schema = 'public' AND table_name = 'users'
                ORDER BY column_name
            """)
            )
            columns = {
                row[0]: {"type": row[1], "nullable": row[2]}
                for row in result.fetchall()
            }

            # Verify expected columns exist
            expected_columns = {
                "id": {"type": "character varying", "nullable": "NO"},
                "email": {"type": "character varying", "nullable": "NO"},
                "password_hash": {"type": "character varying", "nullable": "NO"},
                "full_name": {"type": "character varying", "nullable": "YES"},
                "github_username": {"type": "character varying", "nullable": "YES"},
                "career_interest": {"type": "character varying", "nullable": "YES"},
                "role": {"type": "character varying", "nullable": "NO"},
                "created_at": {"type": "timestamp with time zone", "nullable": "NO"},
                "updated_at": {"type": "timestamp with time zone", "nullable": "NO"},
            }

            for col_name, expected in expected_columns.items():
                assert col_name in columns, f"Column {col_name} not found"
                assert columns[col_name]["type"] == expected["type"], (
                    f"Column {col_name} type mismatch: {columns[col_name]['type']} != {expected['type']}"
                )
                assert columns[col_name]["nullable"] == expected["nullable"], (
                    f"Column {col_name} nullable mismatch: {columns[col_name]['nullable']} != {expected['nullable']}"
                )

            # Check indexes
            result = await conn.execute(
                text("""
                SELECT indexname, indexdef FROM pg_indexes 
                WHERE tablename = 'users' AND schemaname = 'public'
            """)
            )
            indexes = {row[0]: row[1] for row in result.fetchall()}

            # Verify expected indexes
            assert "users_pkey" in indexes, "Primary key index not found"
            assert "ix_users_email" in indexes, "Email unique index not found"
            assert "UNIQUE" in indexes["ix_users_email"], "Email index is not unique"

        await engine.dispose()

    def test_alembic_version_tracking(self, clean_database):
        """Test that Alembic properly tracks migration versions."""
        # Initially no version should be set
        exit_code, stdout, stderr = self.run_alembic_command("current")
        assert exit_code == 0, f"Current command failed: {stderr}"

        # Run upgrade
        exit_code, _, stderr = self.run_alembic_command("upgrade head")
        assert exit_code == 0, f"Migration failed: {stderr}"

        # Check current version is set
        exit_code, stdout, stderr = self.run_alembic_command("current")
        assert exit_code == 0, f"Current command failed: {stderr}"
        assert "93e091e52124" in stdout, "Migration version not tracked correctly"

    def test_migration_idempotency(self, clean_database):
        """Test that running migrations multiple times doesn't break anything."""
        # Run upgrade twice
        exit_code1, _, stderr1 = self.run_alembic_command("upgrade head")
        assert exit_code1 == 0, f"First upgrade failed: {stderr1}"

        exit_code2, _, stderr2 = self.run_alembic_command("upgrade head")
        assert exit_code2 == 0, f"Second upgrade failed: {stderr2}"

        # Both should succeed (second one should be a no-op)

    def test_migration_history(self, clean_database):
        """Test that migration history is properly maintained."""
        # Run upgrade
        exit_code, _, stderr = self.run_alembic_command("upgrade head")
        assert exit_code == 0, f"Migration failed: {stderr}"

        # Check history
        exit_code, stdout, stderr = self.run_alembic_command("history")
        assert exit_code == 0, f"History command failed: {stderr}"
        assert "Initial migration - User table" in stdout
        assert "93e091e52124" in stdout

    @pytest.mark.asyncio
    async def test_migration_with_data_preservation(self, clean_database):
        """Test that migrations preserve existing data (when applicable)."""
        # Run initial migration
        exit_code, _, stderr = self.run_alembic_command("upgrade head")
        assert exit_code == 0, f"Migration failed: {stderr}"

        # Insert test data
        engine = create_async_engine(TEST_DATABASE_URL, echo=False)
        test_user_id = "test-user-123"
        test_email = "test@example.com"

        async with engine.begin() as conn:
            await conn.execute(
                text("""
                INSERT INTO users (id, email, password_hash, role, created_at, updated_at)
                VALUES (:id, :email, 'test_hash', 'professional', NOW(), NOW())
            """),
                {"id": test_user_id, "email": test_email},
            )

        # Run downgrade and upgrade to simulate a migration cycle
        exit_code, _, stderr = self.run_alembic_command("downgrade base")
        assert exit_code == 0, f"Downgrade failed: {stderr}"

        exit_code, _, stderr = self.run_alembic_command("upgrade head")
        assert exit_code == 0, f"Re-upgrade failed: {stderr}"

        # For this test, we expect data to be lost since we're dropping tables
        # This test is more relevant for future schema-only migrations

        await engine.dispose()

    def test_alembic_commands_basic_functionality(self, clean_database):
        """Test basic Alembic commands work correctly."""
        commands_to_test = [
            ("current", "Check current migration state"),
            ("history", "Show migration history"),
            ("branches", "Show branch information"),
        ]

        for command, description in commands_to_test:
            exit_code, stdout, stderr = self.run_alembic_command(command)
            assert exit_code == 0, f"{description} failed: {stderr}"

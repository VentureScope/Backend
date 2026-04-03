# Testing Strategy

## Overview
This document outlines the testing approach for the VentureScope Backend API.

## Test Structure

### Unit Tests (`tests/unit/`)
- **Purpose**: Test individual components in isolation
- **Coverage**: Services, repositories, utilities, security functions
- **Database**: Uses in-memory SQLite for fast, isolated testing
- **Current Status**: 32 tests covering authentication, security, and user management

### Integration Tests (`tests/integration/`)
- **Purpose**: Test API endpoints and component interactions
- **Coverage**: HTTP endpoints, database operations, authentication flows
- **Database**: Uses test database with proper setup/teardown

### End-to-End Tests (`tests/e2e/`)
- **Purpose**: Test complete user workflows
- **Coverage**: User registration → login → protected operations
- **Database**: Full database interactions with realistic scenarios

## Test Execution

### Local Development
```bash
# Run all tests
./run_tests.sh

# Run specific test types
./run_tests.sh --unit-only
./run_tests.sh --integration-only

# Run with coverage
./run_tests.sh --coverage
```

### Docker Environment
```bash
# Run tests in Docker container (recommended)
docker run --rm --network backend_default \
  -v "$(pwd)":/app \
  -e TEST_DATABASE_URL=postgresql+asyncpg://venturescope:venturescope@postgres:5432/venturescope_test \
  backend-test:latest \
  pytest tests/unit/ tests/integration/ -v
```

See [docs/testing/commands.md](./commands.md) for complete Docker test commands and setup instructions.

## Test Configuration

- **pytest.ini**: Configures pytest behavior, markers, and asyncio settings (updated to modern `[pytest]` format)
- **conftest.py**: Shared fixtures for database sessions, test client, and authentication
- **Dockerfile.test**: Dedicated test container with all testing dependencies

### Test Infrastructure Improvements (April 3, 2026)

**Event Loop Management:**
- Removed deprecated custom `event_loop` fixture to fix `RuntimeError: Task got Future attached to a different loop`
- Now using pytest-asyncio's automatic event loop management (0.21.0+)
- Each test function gets its own isolated event loop

**Database Session Handling:**
- Simplified `db_session` fixture to use `sessionmaker` directly
- Removed complex nested transaction management that caused "Can't operate on closed transaction" errors
- Let SQLAlchemy 2.0 handle transaction management automatically
- Removed deprecated `autocommit` and `autoflush` parameters from sessionmaker

**Dependency Compatibility:**
- Pinned bcrypt to 4.0.1 to fix passlib compatibility issue
- Updated datetime handling to use `datetime.now(timezone.utc)` instead of deprecated `datetime.utcnow()`
- All deprecation warnings resolved for Python 3.12+ compatibility

## Testing Guidelines

### Writing Tests
1. **Arrange-Act-Assert**: Structure tests clearly
2. **Isolation**: Each test should be independent
3. **Descriptive Names**: Test names should explain what is being tested
4. **Edge Cases**: Include both happy path and error scenarios

### Test Data
- Use factories or fixtures for consistent test data
- Clean up data between tests
- Use realistic but non-sensitive data

### Mocking Strategy
- Mock external dependencies (external APIs, file system)
- Use real database for database-related tests
- Mock time-dependent operations for consistency

## Continuous Integration

Tests should run automatically on:
- Pull requests
- Commits to main branch
- Scheduled nightly runs

## Coverage Goals

- **Minimum**: 80% overall coverage
- **Critical Paths**: 95% coverage for authentication and user management
- **New Features**: 90% coverage required

## Performance Testing

- Monitor test execution time
- Keep unit tests under 100ms each
- Integration tests should complete within 5 seconds

## Last Updated
April 3, 2026 - Added test infrastructure improvements and Docker command updates
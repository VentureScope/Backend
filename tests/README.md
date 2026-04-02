# Testing Guide for VentureScope Backend

This guide covers the comprehensive testing setup for the VentureScope backend, including unit tests, integration tests, and end-to-end tests.

## Test Structure

```
tests/
├── conftest.py              # Shared test fixtures and configuration
├── unit/                    # Unit tests (fast, isolated)
│   ├── test_security.py     # Security functions (hashing, JWT)
│   ├── test_auth_service.py # AuthService business logic
│   └── test_user_repository.py # UserRepository database logic
├── integration/             # Integration tests (API endpoints)
│   └── test_api_endpoints.py # API route testing
└── e2e/                     # End-to-end tests (full flows)
    └── test_user_flows.py   # Complete user journeys
```

## Test Categories

### 🔹 Unit Tests (`pytest -m unit`)
- **Fast**: Run in milliseconds
- **Isolated**: No database, no external dependencies
- **Mocked**: All dependencies are mocked
- **Coverage**: Core business logic, security functions

**Examples:**
- Password hashing and verification
- JWT token creation and validation
- Service layer business rules
- Repository query logic

### 🔹 Integration Tests (`pytest -m integration`)
- **API-focused**: Test HTTP endpoints
- **Database**: Uses test database
- **Real interactions**: Actual FastAPI app with test DB
- **Coverage**: API contracts, request/response validation

**Examples:**
- User registration endpoint
- Authentication endpoints
- Protected route access
- Request validation

### 🔹 End-to-End Tests (`pytest -m e2e`)
- **Complete flows**: Full user journeys
- **Real database**: Persistent data across requests
- **Slower**: More comprehensive testing
- **Coverage**: User workflows, database constraints

**Examples:**
- Register → Login → Access profile flow
- Concurrent user operations
- Database constraint validation
- Cross-user data isolation

## Running Tests

### Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run unit and integration tests (default)
./run_tests.sh

# Or use pytest directly
pytest
```

### Test Runner Options

```bash
# Unit tests only (fastest)
./run_tests.sh --unit-only

# Integration tests only
./run_tests.sh --integration-only

# All tests including E2E (slowest but most comprehensive)
./run_tests.sh --all

# Skip coverage reporting
./run_tests.sh --no-coverage

# Verbose output
./run_tests.sh --verbose
```

### Docker Testing

```bash
# Start test infrastructure
docker compose --profile testing up -d postgres redis

# Run tests in Docker container
docker compose --profile testing run --rm test

# Run specific test types
docker compose --profile testing run --rm test ./run_tests.sh --unit-only
```

## Test Database Setup

### Local Development

The test runner automatically handles database setup:

1. **Starts Docker containers** for PostgreSQL and Redis
2. **Creates test database** (`venturescope_test`)
3. **Manages schema** creation/cleanup per test
4. **Isolates tests** with transactions

### Environment Variables

```bash
# Override test database URL
export TEST_DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/test_db"

# Test configuration
export SECRET_KEY="test-secret-key"
export DEBUG="true"
```

### CI/CD Integration

For GitHub Actions or other CI systems:

```yaml
# Example GitHub Actions configuration
services:
  postgres:
    image: postgres:16
    env:
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: test_db
    ports:
      - 5432:5432

steps:
  - uses: actions/checkout@v4
  - name: Run tests
    env:
      TEST_DATABASE_URL: postgresql+asyncpg://postgres:postgres@localhost:5432/test_db
    run: |
      pip install -r requirements.txt
      ./run_tests.sh --all
```

## Test Configuration

### pytest.ini

Key settings:
- **Coverage**: 80% minimum threshold
- **Markers**: Organized by test type
- **Async**: Automatic async test handling
- **Output**: Detailed reporting

### conftest.py

Provides shared fixtures:
- `client`: Test HTTP client
- `db_session`: Isolated database session
- `user_data`: Fake user data
- `engine`: Database engine

## Writing Tests

### Unit Test Example

```python
@pytest.mark.unit
class TestPasswordHashing:
    def test_hash_password_returns_different_hash_each_time(self):
        password = "test_password"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2
```

### Integration Test Example

```python
@pytest.mark.integration
class TestAuthEndpoints:
    @pytest.mark.asyncio
    async def test_register_success(self, client: AsyncClient, user_data):
        response = await client.post("/api/auth/register", json=user_data)
        assert response.status_code == 200
```

### E2E Test Example

```python
@pytest.mark.e2e
class TestUserFlow:
    @pytest.mark.asyncio
    async def test_complete_user_journey(self, client: AsyncClient, user_data):
        # Register
        register_response = await client.post("/api/auth/register", json=user_data)
        # Login
        login_response = await client.post("/api/auth/login", json=login_data)
        # Access protected route
        profile_response = await client.get("/api/users/me", headers=headers)
```

## Coverage Reports

### Viewing Coverage

After running tests with coverage:

```bash
# Terminal report
pytest --cov=app --cov-report=term-missing

# HTML report (opens in browser)
open htmlcov/index.html
```

### Coverage Goals

- **Minimum**: 80% overall coverage
- **Target**: 90%+ for business logic
- **Focus**: Critical paths (auth, user management)

### Coverage Exclusions

Some files are excluded from coverage requirements:
- Test files themselves
- Database migrations
- Configuration files

## Debugging Tests

### Running Single Tests

```bash
# Run specific test file
pytest tests/unit/test_security.py

# Run specific test method
pytest tests/unit/test_security.py::TestPasswordHashing::test_hash_password

# Run with debugging
pytest tests/unit/test_security.py -vvv --tb=short
```

### Database Debugging

```bash
# Check test database
docker compose exec postgres psql -U venturescope -d venturescope_test

# View test logs
docker compose --profile testing logs test
```

### Common Issues

1. **Database connection errors**
   - Ensure PostgreSQL is running
   - Check TEST_DATABASE_URL

2. **Import errors**
   - Verify PYTHONPATH includes `/app`
   - Check dependency installation

3. **Async test issues**
   - Use `@pytest.mark.asyncio`
   - Ensure proper await usage

## Performance

### Test Execution Times

- **Unit tests**: < 5 seconds
- **Integration tests**: 30-60 seconds
- **E2E tests**: 2-5 minutes
- **Full suite**: 3-6 minutes

### Optimization Tips

- Run unit tests frequently during development
- Use integration tests for API validation
- Reserve E2E tests for critical user flows
- Use `--unit-only` for fast feedback

## Best Practices

### Test Organization

- **Group related tests** in classes
- **Use descriptive names** that explain the scenario
- **Follow AAA pattern**: Arrange, Act, Assert
- **Keep tests independent** and isolated

### Test Data

- **Use Faker** for realistic test data
- **Create focused fixtures** for specific scenarios
- **Avoid hard-coded values** where possible
- **Clean up after tests** (handled automatically)

### Assertions

- **Be specific** in assertions
- **Test both success and failure cases**
- **Verify side effects** (database changes, logs)
- **Use meaningful error messages**

## Continuous Integration

The testing setup is designed to work seamlessly in CI/CD pipelines:

- **Docker-based**: Consistent environments
- **Fast feedback**: Quick unit test results
- **Comprehensive**: Full test coverage
- **Reliable**: Isolated test execution

For local development, the test runner provides quick feedback while maintaining the same quality standards as the CI environment.
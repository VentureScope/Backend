# Testing Guide

## Quick Test Command (Recommended)

```bash
docker run --rm --network backend_default \
  -v "$(pwd)":/app \
  -e TEST_DATABASE_URL=postgresql+asyncpg://venturescope:venturescope@postgres:5432/venturescope_test \
  backend-test:latest \
  pytest tests/unit/ tests/integration/ -v
```

## Prerequisites

1. Start database services:
```bash
docker compose up -d postgres redis
```

2. Create test database (first time only):
```bash
docker compose exec -T postgres psql -U venturescope -d postgres -c "CREATE DATABASE venturescope_test;"
```

## Test Commands

### Run all tests with coverage
```bash
docker run --rm --network backend_default \
  -v "$(pwd)":/app \
  -e TEST_DATABASE_URL=postgresql+asyncpg://venturescope:venturescope@postgres:5432/venturescope_test \
  backend-test:latest \
  pytest tests/unit/ tests/integration/ --cov=app --cov-report=term-missing
```

### Run only unit tests
```bash
docker run --rm --network backend_default \
  -v "$(pwd)":/app \
  backend-test:latest \
  pytest tests/unit/ -v
```

### Run only integration tests
```bash
docker run --rm --network backend_default \
  -v "$(pwd)":/app \
  -e TEST_DATABASE_URL=postgresql+asyncpg://venturescope:venturescope@postgres:5432/venturescope_test \
  backend-test:latest \
  pytest tests/integration/ -v
```

### Run tests using test script
```bash
docker run --rm --network backend_default \
  -v "$(pwd)":/app \
  -e TEST_DATABASE_URL=postgresql+asyncpg://venturescope:venturescope@postgres:5432/venturescope_test \
  backend-test:latest \
  ./run_tests.sh
```

## Expected Results

- **51 tests** should pass (32 unit + 19 integration)
- **91%+ code coverage**
- **0 failures, 0 errors**

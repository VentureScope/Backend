# Testing Guide

## Easiest Method: Using run_tests.sh (Recommended)

The `run_tests.sh` script automatically detects your environment and runs tests appropriately:

```bash
./run_tests.sh
```

**What it does:**
- Automatically detects if Python dependencies are installed locally
- If dependencies are missing, automatically uses Docker to run tests
- Starts database services (postgres, redis)
- Creates test database if needed
- Runs all tests with coverage reporting

### Options

```bash
# Run only unit tests
./run_tests.sh --unit-only

# Run only integration tests
./run_tests.sh --integration-only

# Run all tests including e2e
./run_tests.sh --all

# Skip coverage reporting
./run_tests.sh --no-coverage

# Verbose output
./run_tests.sh --verbose

# Force Docker execution
./run_tests.sh --docker

# Force local execution (requires dependencies)
./run_tests.sh --local
```

## Manual Docker Commands

If you prefer to run Docker commands manually:

### Prerequisites

1. Build the test image (first time only):
```bash
docker build -t backend-test:latest -f Dockerfile.test .
```

2. Start database services:
```bash
docker compose up -d postgres redis
```

3. Create test database (first time only):
```bash
docker compose exec -T postgres psql -U venturescope -d postgres -c "CREATE DATABASE venturescope_test;"
```

### Quick Test Command

```bash
docker run --rm --network backend_default \
  -v "$(pwd)":/app \
  -e TEST_DATABASE_URL=postgresql+asyncpg://venturescope:venturescope@postgres:5432/venturescope_test \
  backend-test:latest \
  pytest tests/unit/ tests/integration/ -v
```

### Run all tests with coverage
```bash
docker run --rm --network backend_default \
  -v "$(pwd)":/app \
  -e TEST_DATABASE_URL=postgresql+asyncpg://venturescope:venturescope@postgres:5432/venturescope_test \
  backend-test:latest \
  pytest tests/unit/ tests/integration/ --cov=app --cov-report=term-missing --cov-report=html
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

## Local Testing (Advanced)

For developers who want to run tests locally without Docker:

### Setup

1. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Start database services:
```bash
docker compose up -d postgres redis
```

4. Create test database:
```bash
docker compose exec -T postgres psql -U venturescope -d postgres -c "CREATE DATABASE venturescope_test;"
```

5. Set environment variable:
```bash
export TEST_DATABASE_URL=postgresql+asyncpg://venturescope:venturescope@localhost:5432/venturescope_test
```

### Run Tests

```bash
# Run all tests with coverage
pytest tests/unit/ tests/integration/ --cov=app --cov-report=term-missing --cov-report=html

# Run only unit tests
pytest tests/unit/ -v

# Run only integration tests  
pytest tests/integration/ -v

# Or use the test script with --local flag
./run_tests.sh --local
```

## Expected Results

- **51 tests** should pass (32 unit + 19 integration)
- **91%+ code coverage**
- **0 failures, 0 errors**

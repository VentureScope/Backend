#!/usr/bin/env bash
# Test runner script for VentureScope Backend

set -e

echo "🧪 VentureScope Backend Test Suite"
echo "=================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
RUN_UNIT=true
RUN_INTEGRATION=true
RUN_E2E=false
COVERAGE=true
VERBOSE=false
USE_DOCKER=false
FORCE_LOCAL=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --unit-only)
            RUN_UNIT=true
            RUN_INTEGRATION=false
            RUN_E2E=false
            shift
            ;;
        --integration-only)
            RUN_UNIT=false
            RUN_INTEGRATION=true
            RUN_E2E=false
            shift
            ;;
        --e2e-only)
            RUN_UNIT=false
            RUN_INTEGRATION=false
            RUN_E2E=true
            shift
            ;;
        --all)
            RUN_UNIT=true
            RUN_INTEGRATION=true
            RUN_E2E=true
            shift
            ;;
        --no-coverage)
            COVERAGE=false
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --docker)
            USE_DOCKER=true
            shift
            ;;
        --local)
            FORCE_LOCAL=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --unit-only       Run only unit tests"
            echo "  --integration-only Run only integration tests"
            echo "  --e2e-only        Run only e2e tests"
            echo "  --all             Run all test types including e2e"
            echo "  --no-coverage     Skip coverage reporting"
            echo "  --verbose         Verbose output"
            echo "  --docker          Force use of Docker for tests"
            echo "  --local           Force local execution (requires pytest installed)"
            echo "  -h, --help        Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option $1"
            exit 1
            ;;
    esac
done

# Detect if we should use Docker for tests
if [ "$FORCE_LOCAL" = false ]; then
    # Check if pytest and required dependencies are available locally
    if ! python3 -c "import pytest_asyncio, sqlalchemy, httpx" &> /dev/null; then
        echo "⚠️  Required test dependencies not found locally, will use Docker for testing"
        USE_DOCKER=true
    fi
fi

# Check if we're in a Docker environment or need to set up test database
if [ -n "$CI" ] || [ -n "$GITHUB_ACTIONS" ]; then
    echo "🐳 Running in CI environment"
    export TEST_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/test_db"
elif [ "$USE_DOCKER" = true ]; then
    echo "🐳 Running tests in Docker container"
    echo ""
    
    # Start database services
    echo "Starting database services..."
    docker compose up -d postgres redis
    
    # Wait for database to be ready
    echo "⏳ Waiting for database..."
    sleep 5
    
    # Create test database if it doesn't exist
    docker compose exec -T postgres psql -U venturescope -d postgres -c "CREATE DATABASE venturescope_test;" 2>/dev/null || echo "Test database already exists"
    
    # Build test paths based on what we're running
    TEST_PATHS=""
    if [ "$RUN_UNIT" = true ]; then
        TEST_PATHS="$TEST_PATHS tests/unit/"
    fi
    if [ "$RUN_INTEGRATION" = true ]; then
        TEST_PATHS="$TEST_PATHS tests/integration/"
    fi
    if [ "$RUN_E2E" = true ]; then
        TEST_PATHS="$TEST_PATHS tests/e2e/"
    fi
    
    # Build pytest arguments
    PYTEST_ARGS=""
    if [ "$COVERAGE" = true ]; then
        PYTEST_ARGS="--cov=app --cov-report=term-missing --cov-report=html"
    fi
    if [ "$VERBOSE" = true ]; then
        PYTEST_ARGS="$PYTEST_ARGS -v"
    fi
    
    # Run tests in Docker
    echo ""
    echo "Running tests..."
    docker run --rm --network backend_default \
        -v "$(pwd)":/app \
        -e TEST_DATABASE_URL=postgresql+asyncpg://venturescope:venturescope@postgres:5432/venturescope_test \
        backend-test:latest \
        pytest $TEST_PATHS $PYTEST_ARGS
    
    EXIT_CODE=$?
    
    # Final summary
    echo ""
    echo "============================================"
    if [ $EXIT_CODE -eq 0 ]; then
        echo -e "${GREEN}🎉 All tests passed successfully!${NC}"
        
        if [ "$COVERAGE" = true ]; then
            echo ""
            echo "📊 Coverage report generated in htmlcov/"
            echo "   Open htmlcov/index.html in your browser"
        fi
    else
        echo -e "${RED}💥 Some tests failed (exit code: $EXIT_CODE)${NC}"
    fi
    echo "============================================"
    exit $EXIT_CODE
else
    echo "🏠 Running locally"
    # Check if Docker is available and start test database
    if command -v docker-compose &> /dev/null || command -v docker &> /dev/null; then
        echo "🐳 Starting test database..."
        docker compose up -d postgres redis
        export TEST_DATABASE_URL="postgresql+asyncpg://venturescope:venturescope@localhost:5432/venturescope_test"
        
        # Wait for database to be ready
        echo "⏳ Waiting for database..."
        sleep 5
        
        # Create test database if it doesn't exist
        docker compose exec -T postgres psql -U venturescope -d postgres -c "CREATE DATABASE venturescope_test;" 2>/dev/null || echo "Test database already exists"
    else
        echo "⚠️  Docker not available. Make sure test database is running."
        echo "   Set TEST_DATABASE_URL environment variable if using external database."
    fi
fi

# Build test command
PYTEST_CMD="python3 -m pytest"

# Add coverage if enabled
if [ "$COVERAGE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD --cov=app --cov-report=term-missing --cov-report=html"
fi

# Add verbosity if requested
if [ "$VERBOSE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -v"
fi

# Function to run tests with proper error handling
run_tests() {
    local test_type=$1
    local test_path=$2
    local marker=$3
    
    echo ""
    echo -e "${YELLOW}Running $test_type tests...${NC}"
    echo "----------------------------------------"
    
    if [ -n "$marker" ]; then
        eval "$PYTEST_CMD -m $marker $test_path"
    else
        eval "$PYTEST_CMD $test_path"
    fi
    
    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}✅ $test_type tests passed!${NC}"
    else
        echo -e "${RED}❌ $test_type tests failed!${NC}"
        return $exit_code
    fi
}

# Main test execution
EXIT_CODE=0

if [ "$RUN_UNIT" = true ]; then
    run_tests "Unit" "tests/unit/" "unit" || EXIT_CODE=$?
fi

if [ "$RUN_INTEGRATION" = true ]; then
    run_tests "Integration" "tests/integration/" "integration" || EXIT_CODE=$?
fi

if [ "$RUN_E2E" = true ]; then
    echo ""
    echo -e "${YELLOW}⚠️  Running E2E tests (this may take a while)...${NC}"
    run_tests "End-to-End" "tests/e2e/" "e2e" || EXIT_CODE=$?
fi

# Final summary
echo ""
echo "============================================"
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}🎉 All tests passed successfully!${NC}"
    
    if [ "$COVERAGE" = true ]; then
        echo ""
        echo "📊 Coverage report generated in htmlcov/"
        echo "   Open htmlcov/index.html in your browser"
    fi
else
    echo -e "${RED}💥 Some tests failed (exit code: $EXIT_CODE)${NC}"
fi

echo "============================================"
exit $EXIT_CODE
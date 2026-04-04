#!/usr/bin/env bash
# Test runner wrapper for VentureScope Backend
# Handles Windows/WSL environment differences

set -e

echo "🧪 VentureScope Test Runner"
echo "=========================="

# Set test database URL for Docker container
export TEST_DATABASE_URL="postgresql+asyncpg://venturescope:venturescope@localhost:5432/venturescope_test"

echo "Database: $TEST_DATABASE_URL"
echo ""

# Detect if we're in WSL and need to run Windows pytest
if [[ -f ".venv/Scripts/python.exe" ]]; then
    echo "💡 Detected Windows virtual environment, switching to PowerShell..."
    echo "Please run this command in PowerShell instead:"
    echo ""
    echo "cd Backend"
    echo ".venv\\Scripts\\Activate.ps1"
    echo "\$env:TEST_DATABASE_URL = \"postgresql+asyncpg://venturescope:venturescope@localhost:5432/venturescope_test\""
    echo "pytest tests/unit/test_token_repository.py tests/unit/test_security.py tests/integration/test_logout.py -v"
    echo ""
    exit 1
elif [[ -f ".venv/bin/python" ]]; then
    echo "✓ Using Unix virtual environment"
    source .venv/bin/activate
    python -m pytest "$@"
else
    echo "❌ No virtual environment found"
    echo "Please ensure you have activated your virtual environment"
    exit 1
fi
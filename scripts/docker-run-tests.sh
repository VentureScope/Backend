#!/usr/bin/env bash
# Test runner for Docker environment
# Runs tests inside Docker container with proper database setup

set -e

echo "🧪 VentureScope Docker Test Runner"
echo "==================================="
echo ""

# Wait for database to be ready
echo "Waiting for database to be ready..."
sleep 5

# Run migrations on test database
echo "Running database migrations..."
alembic upgrade head

echo ""
echo "Running tests..."
echo ""

# Run pytest with coverage
pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=html

echo ""
echo "✅ Tests completed!"

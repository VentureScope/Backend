#!/usr/bin/env bash
# Database initialization script for VentureScope Backend
# This script creates database tables and optionally seeds test data

set -e

echo "🗄️  VentureScope Database Initialization"
echo "========================================"

# Check if we're running in Docker
if [ -n "$DOCKER_CONTAINER" ]; then
    echo "🐳 Running in Docker container"
    python scripts/create_tables.py
else
    echo "🏠 Running locally"
    
    # Check if we should use Docker for database
    if command -v docker &> /dev/null && (docker compose ps postgres | grep -q "Up" || true); then
        echo "✓ Using Docker PostgreSQL"
        docker compose exec backend python scripts/create_tables.py
    else
        # Try local Python environment
        if [ -f .venv/bin/python ]; then
            echo "✓ Using local virtual environment"
            .venv/bin/python scripts/create_tables.py
        elif command -v python3 &> /dev/null; then
            echo "✓ Using system Python"
            python3 scripts/create_tables.py
        else
            echo "❌ Error: No Python interpreter found"
            exit 1
        fi
    fi
fi

echo ""
echo "✅ Database tables created successfully!"
echo ""
echo "Next steps:"
echo "  - Start the API: docker compose up backend"
echo "  - Or locally: uvicorn app.main:app --reload"
echo "  - Visit docs: http://localhost:8000/docs"

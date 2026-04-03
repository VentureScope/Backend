#!/usr/bin/env bash
# Database migration runner for VentureScope Backend
# This script runs Alembic migrations and handles errors gracefully

set -e

echo "🔄 VentureScope Backend - Database Migrations"
echo "=============================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo -e "${RED}❌ ERROR: DATABASE_URL environment variable not set${NC}"
    echo "Please set DATABASE_URL before running migrations."
    echo "Example: export DATABASE_URL=postgresql+asyncpg://user:pass@host:port/db"
    exit 1
fi

echo "📍 Database URL: ${DATABASE_URL}"
echo ""

# Function to run alembic command with error handling
run_alembic() {
    local command=$1
    local description=$2
    
    echo -e "${YELLOW}▶ ${description}...${NC}"
    
    if alembic $command; then
        echo -e "${GREEN}✅ ${description} completed successfully${NC}"
        return 0
    else
        echo -e "${RED}❌ ${description} failed${NC}"
        return 1
    fi
}

# Show current migration status
echo -e "${YELLOW}📊 Current Migration Status:${NC}"
run_alembic "current" "Checking current migration version"
echo ""

# Show migration history (last 5)
echo -e "${YELLOW}📜 Recent Migration History:${NC}"
run_alembic "history --rev-range=-5:" "Showing migration history"
echo ""

# Run migrations
echo -e "${YELLOW}🚀 Running Migrations:${NC}"
if run_alembic "upgrade head" "Applying all pending migrations"; then
    echo ""
    echo -e "${GREEN}🎉 All migrations completed successfully!${NC}"
    
    # Show final status
    echo ""
    echo -e "${YELLOW}📊 Final Migration Status:${NC}"
    run_alembic "current" "Final migration version check"
else
    echo ""
    echo -e "${RED}💥 Migration failed!${NC}"
    echo ""
    echo "Troubleshooting steps:"
    echo "1. Check database connection: ${DATABASE_URL}"
    echo "2. Verify database exists and is accessible"
    echo "3. Check migration files for syntax errors"
    echo "4. Review Alembic logs above for specific error details"
    echo ""
    echo "For rollback, run: alembic downgrade -1"
    exit 1
fi

echo ""
echo "=============================================="
echo -e "${GREEN}✅ Migration script completed${NC}"
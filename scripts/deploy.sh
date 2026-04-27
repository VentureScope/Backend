#!/bin/bash
set -e

echo "=================================================="
echo "  VentureScope Backend - Deployment Script"
echo "=================================================="

PROJECT_NAME="venturescope"
COMPOSE_FILE="docker-compose.prod.yml"

echo ""
echo "[1/4] Checking environment..."
if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found!"
    exit 1
fi

echo "[2/4] Building Docker images..."
docker compose -f $COMPOSE_FILE build

echo ""
echo "[3/4] Stopping existing containers..."
docker compose -f $COMPOSE_FILE down --remove-orphans 2>/dev/null || true

echo ""
echo "[4/4] Starting services..."
docker compose -f $COMPOSE_FILE up -d

echo ""
echo "=================================================="
echo "  Deployment Complete!"
echo "=================================================="
echo ""
echo "Services running:"
docker compose -f $COMPOSE_FILE ps

echo ""
echo "View logs with: ./scripts/logs.sh"
echo "stop services with: ./scripts/stop.sh"
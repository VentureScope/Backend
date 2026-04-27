#!/bin/bash
set -e

COMPOSE_FILE="docker-compose.prod.yml"

echo "Stopping VentureScope services..."

docker compose -f $COMPOSE_FILE down

echo "Services stopped."
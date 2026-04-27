#!/bin/bash
set -e

COMPOSE_FILE="docker-compose.prod.yml"
SERVICE="${1:-}"

if [ -n "$SERVICE" ]; then
    echo "Showing logs for: $SERVICE"
    docker compose -f $COMPOSE_FILE logs -f --tail=100 "$SERVICE"
else
    echo "Showing all logs (showing last 100 lines, use Ctrl+C to exit)"
    docker compose -f $COMPOSE_FILE logs -f --tail=100
fi
#!/usr/bin/env bash
# Build and (re)start API + worker + Caddy on AWS EC2 (or any Ubuntu VM).
# Run from anywhere:  bash /path/to/Backend/deploy/aws/deploy.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/deploy/aws/docker-compose.yml"
cd "$REPO_ROOT"

if [[ ! -f .env ]]; then
  echo "Missing $REPO_ROOT/.env — aborting."
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker not found. Run deploy/aws/setup.sh first."
  exit 1
fi

echo "==> Building and starting stack"
docker compose -f "$COMPOSE_FILE" --env-file .env up -d --build --remove-orphans

echo "==> Running database migrations"
docker compose -f "$COMPOSE_FILE" exec -T backend \
  alembic upgrade head || {
    echo "Migration failed — check DATABASE_URL / Supabase connectivity."
    exit 1
  }

echo "==> Container status"
docker compose -f "$COMPOSE_FILE" ps

echo ""
echo "Done. After DNS + TLS settle, check:"
echo "  curl -fsS https://api.venturescope.tech/health"
echo "Logs:"
echo "  docker compose -f deploy/aws/docker-compose.yml logs -f --tail=100"

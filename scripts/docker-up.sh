#!/bin/sh
# Run full stack with Docker Compose
# Usage: ./scripts/docker-up.sh
# Or for dev: ./scripts/docker-up.sh --dev

set -e
cd "$(dirname "$0")/.."

if [ "$1" = "--dev" ]; then
  echo "Starting dev stack (frontend + api + worker + infra)..."
  docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis opensearch qdrant minio
  sleep 5
  docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
else
  echo "Starting full stack..."
  docker compose up -d
fi

echo ""
echo "Services:"
echo "  API:      http://localhost:8000"
echo "  Frontend: http://localhost:5174 (prod) or http://localhost:5173 (dev)"
echo "  Docs:     http://localhost:8000/docs"
echo ""

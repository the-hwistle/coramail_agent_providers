#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="${CORAMAIL_PROD_ENV_FILE:-config/production.env}"
export CORAMAIL_PROD_COMPOSE_ENV_FILE="$ENV_FILE"

exec docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml \
  --profile edge --profile tunnel --profile tools \
  down --remove-orphans

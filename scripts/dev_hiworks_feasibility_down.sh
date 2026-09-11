#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="${CORAMAIL_HIWORKS_FEASIBILITY_ENV_FILE:-config/hiworks-feasibility.env}"

exec docker compose \
  --env-file "$ENV_FILE" \
  -f docker-compose.yml \
  -f docker-compose.hiworks-feasibility.yml \
  down --remove-orphans

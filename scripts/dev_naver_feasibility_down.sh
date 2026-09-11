#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="${CORAMAIL_NAVER_FEASIBILITY_ENV_FILE:-config/naver-feasibility.env}"

exec docker compose \
  --env-file "$ENV_FILE" \
  -f docker-compose.yml \
  -f docker-compose.naver-feasibility.yml \
  down --remove-orphans

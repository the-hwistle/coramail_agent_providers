#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="${CORAMAIL_HIWORKS_FEASIBILITY_ENV_FILE:-config/hiworks-feasibility.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  cp config/hiworks-feasibility.env.example "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  printf '[INFO] Created %s from template. Edit it before adding real Hiworks credentials.\n' "$ENV_FILE"
fi

exec docker compose \
  --env-file "$ENV_FILE" \
  -f docker-compose.yml \
  -f docker-compose.hiworks-feasibility.yml \
  up --build

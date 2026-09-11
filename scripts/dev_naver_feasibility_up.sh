#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="${CORAMAIL_NAVER_FEASIBILITY_ENV_FILE:-config/naver-feasibility.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  cp config/naver-feasibility.env.example "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  printf '[INFO] Created %s from template. Edit it before adding real Naver credentials.\n' "$ENV_FILE"
fi

exec docker compose \
  --env-file "$ENV_FILE" \
  -f docker-compose.yml \
  -f docker-compose.naver-feasibility.yml \
  up --build

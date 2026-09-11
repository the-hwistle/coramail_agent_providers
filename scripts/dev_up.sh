#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

fail() {
  printf '\n[ERROR] %s\n' "$*" >&2
  exit 1
}

command -v docker >/dev/null 2>&1 || fail "docker is required."
docker compose version >/dev/null 2>&1 || fail "docker compose is required."

log "Starting the full Docker development stack."

if [[ "${CORAMAIL_DEV_WITH_OLLAMA:-false}" == "true" ]]; then
  exec docker compose --profile ollama up --build
fi

exec docker compose up --build

#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="${CORAMAIL_PROD_ENV_FILE:-config/production.env}"
export CORAMAIL_PROD_COMPOSE_ENV_FILE="$ENV_FILE"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'missing_command=%s\n' "$1" >&2
    exit 1
  fi
}

require_command uv
require_command docker

if [[ ! -f "$ENV_FILE" ]]; then
  printf 'production_env_missing=%s\n' "$ENV_FILE" >&2
  exit 1
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  MODE="$(stat -c '%a' "$ENV_FILE")"
  case "$MODE" in
    600|640)
      ;;
    *)
      printf 'production_env_insecure_mode=%s mode=%s expected=600-or-640\n' "$ENV_FILE" "$MODE" >&2
      exit 1
      ;;
  esac
fi

docker compose version >/dev/null
uv run python -m app.tools.check_deployment_readiness --env-file "$ENV_FILE" --warnings-as-errors
docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml config >/dev/null

printf 'production_preflight=ok\n'

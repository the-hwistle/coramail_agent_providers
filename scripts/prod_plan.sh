#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="${CORAMAIL_PROD_ENV_FILE:-config/production.env}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

exec uv run python -m app.tools.render_deployment_plan --env-file "$ENV_FILE" "$@"

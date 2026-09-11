#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# shellcheck source=scripts/dev_env.sh
source "$REPO_ROOT/scripts/dev_env.sh"

args=(app.server:app --host "$CORAMAIL_DEV_HOST" --port "$CORAMAIL_DEV_PORT")
if [[ "$CORAMAIL_DEV_RELOAD" == "true" ]]; then
  args+=(--reload)
fi

exec uv run uvicorn "${args[@]}"

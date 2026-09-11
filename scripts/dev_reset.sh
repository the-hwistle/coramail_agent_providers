#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ "${CORAMAIL_DEV_RESET_CONFIRM:-}" != "delete-dev-volumes" ]]; then
  cat >&2 <<'EOF'
This deletes local Docker volumes for CoRA Mail Agent development data.
Set CORAMAIL_DEV_RESET_CONFIRM=delete-dev-volumes to confirm.
EOF
  exit 2
fi

docker compose down --volumes --remove-orphans

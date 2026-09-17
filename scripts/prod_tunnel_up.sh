#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="${CORAMAIL_PROD_ENV_FILE:-config/production.env}"
export CORAMAIL_PROD_COMPOSE_ENV_FILE="$ENV_FILE"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

uv run python -m app.tools.check_deployment_readiness --env-file "$ENV_FILE" --warnings-as-errors
uv run python - "$ENV_FILE" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

from app.tools.check_deployment_readiness import _read_env_file

values = _read_env_file(Path(sys.argv[1]))
if not values.get("CORAMAIL_CLOUDFLARE_TUNNEL_TOKEN", "").strip():
    print("CORAMAIL_CLOUDFLARE_TUNNEL_TOKEN is required for Cloudflare Named Tunnel startup.", file=sys.stderr)
    raise SystemExit(1)
PY
exec docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml --profile tunnel up -d web tunnel

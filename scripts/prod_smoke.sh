#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="${CORAMAIL_PROD_ENV_FILE:-config/production.env}"
export CORAMAIL_PROD_COMPOSE_ENV_FILE="$ENV_FILE"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

uv run python -m app.tools.check_deployment_readiness --env-file "$ENV_FILE" --warnings-as-errors

docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml ps

docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml exec -T web python - <<'PY'
import json
import os
import sys
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=10) as response:
    payload = json.loads(response.read().decode("utf-8"))

print(json.dumps(payload, ensure_ascii=False, sort_keys=True))

status = str(payload.get("status") or "")
allow_degraded = os.getenv("CORAMAIL_PROD_SMOKE_ALLOW_DEGRADED", "").strip().casefold() in {
    "1",
    "true",
    "yes",
    "on",
}
if status == "ok" or (allow_degraded and status == "degraded"):
    raise SystemExit(0)

print(f"production smoke failed: health status={status!r}", file=sys.stderr)
raise SystemExit(1)
PY

printf 'production_smoke=ok\n'

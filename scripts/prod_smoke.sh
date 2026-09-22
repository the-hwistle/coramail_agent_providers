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
import time
import urllib.error
import urllib.request

health_url = "http://127.0.0.1:8000/api/health"
deadline = time.monotonic() + 60
last_error: Exception | None = None
while time.monotonic() < deadline:
    try:
        with urllib.request.urlopen(health_url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        break
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        last_error = exc
        time.sleep(1)
else:
    print(f"production smoke failed: {health_url} was not ready within 60s: {last_error}", file=sys.stderr)
    raise SystemExit(1)

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

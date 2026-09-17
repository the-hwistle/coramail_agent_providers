#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="${CORAMAIL_PROD_ENV_FILE:-config/production.env}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

uv run python -m app.tools.check_deployment_readiness --env-file "$ENV_FILE" --warnings-as-errors

uv run python - "$ENV_FILE" <<'PY'
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

from app.tools.check_deployment_readiness import _read_env_file

env_file = Path(sys.argv[1])
values = _read_env_file(env_file)
base_url = values.get("CORAMAIL_BETA_BASE_URL", "").strip().rstrip("/") + "/"
health_url = urljoin(base_url, "api/health")

try:
    with urllib.request.urlopen(health_url, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
except urllib.error.URLError as exc:
    print(f"external smoke failed: {health_url} unreachable: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc

print(json.dumps({"url": health_url, "health": payload}, ensure_ascii=False, sort_keys=True))
status = str(payload.get("status") or "")
if status != "ok":
    print(f"external smoke failed: health status={status!r}", file=sys.stderr)
    raise SystemExit(1)
PY

printf 'production_external_smoke=ok\n'

#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BACKUP_DIR="${1:-}"
if [[ -z "$BACKUP_DIR" ]]; then
  if [[ -d backups/production ]]; then
    BACKUP_DIR="$(find backups/production -mindepth 1 -maxdepth 1 -type d -print | sort | tail -n 1)"
  fi
fi
if [[ -z "$BACKUP_DIR" ]]; then
  printf 'restore_drill=error reason=no-backup-directory\n' >&2
  exit 1
fi
BACKUP_DIR_ABS="$(cd "$BACKUP_DIR" && pwd)"

ENV_FILE="${CORAMAIL_PROD_ENV_FILE:-config/production.env}"
WEB_IMAGE="${CORAMAIL_RESTORE_DRILL_WEB_IMAGE:-$(sed -n 's/^CORAMAIL_WEB_IMAGE=//p' "$ENV_FILE" | tail -n 1)}"
POSTGRES_IMAGE="${CORAMAIL_RESTORE_DRILL_POSTGRES_IMAGE:-$(sed -n 's/^CORAMAIL_POSTGRES_IMAGE=//p' "$ENV_FILE" | tail -n 1)}"
QDRANT_IMAGE="${CORAMAIL_RESTORE_DRILL_QDRANT_IMAGE:-$(sed -n 's/^CORAMAIL_QDRANT_IMAGE=//p' "$ENV_FILE" | tail -n 1)}"
for image in "$WEB_IMAGE" "$POSTGRES_IMAGE" "$QDRANT_IMAGE"; do
  if [[ -z "$image" || ! "$image" =~ ^[A-Za-z0-9._/@:-]+$ ]]; then
    printf 'restore_drill=error reason=invalid-image-reference\n' >&2
    exit 1
  fi
done

export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"
VERIFY_JSON="$(uv run python -m app.tools.verify_production_backup "$BACKUP_DIR_ABS" --format json)"
POSTGRES_DUMP="$(sed -n 's/^postgres_dump=//p' "$BACKUP_DIR_ABS/manifest.txt" | tail -n 1)"
RUNTIME_ARCHIVE="$(sed -n 's/^runtime_archive=//p' "$BACKUP_DIR_ABS/manifest.txt" | tail -n 1)"
QDRANT_COLLECTION="$(sed -n 's/^qdrant_collection=//p' "$BACKUP_DIR_ABS/manifest.txt" | tail -n 1)"
QDRANT_SNAPSHOT="$(find "$BACKUP_DIR_ABS" -maxdepth 1 -type f -name '*.snapshot' -printf '%f\n')"

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
PREFIX="coramail-restore-drill-$RUN_ID"
NETWORK="$PREFIX-network"
POSTGRES_VOLUME="$PREFIX-postgres"
QDRANT_VOLUME="$PREFIX-qdrant"
RUNTIME_VOLUME="$PREFIX-runtime"
POSTGRES_CONTAINER="$PREFIX-postgres"
QDRANT_CONTAINER="$PREFIX-qdrant"
KEEP="${CORAMAIL_RESTORE_DRILL_KEEP:-false}"

cleanup() {
  if [[ "$KEEP" =~ ^(1|true|yes|on)$ ]]; then
    printf 'restore_drill_resources=%s\n' "$PREFIX"
    return
  fi
  docker rm -f "$POSTGRES_CONTAINER" "$QDRANT_CONTAINER" >/dev/null 2>&1 || true
  docker volume rm "$POSTGRES_VOLUME" "$QDRANT_VOLUME" "$RUNTIME_VOLUME" >/dev/null 2>&1 || true
  docker network rm "$NETWORK" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker network create "$NETWORK" >/dev/null
docker volume create "$POSTGRES_VOLUME" >/dev/null
docker volume create "$QDRANT_VOLUME" >/dev/null
docker volume create "$RUNTIME_VOLUME" >/dev/null

docker run -d --name "$POSTGRES_CONTAINER" --network "$NETWORK" --network-alias postgres \
  -e POSTGRES_DB=coramail_restore \
  -e POSTGRES_USER=coramail_restore \
  -e POSTGRES_PASSWORD=restore-drill-only \
  -v "$POSTGRES_VOLUME:/var/lib/postgresql/data" \
  "$POSTGRES_IMAGE" >/dev/null

docker run -d --name "$QDRANT_CONTAINER" --network "$NETWORK" --network-alias qdrant \
  -v "$QDRANT_VOLUME:/qdrant/storage" \
  "$QDRANT_IMAGE" >/dev/null

for _ in $(seq 1 60); do
  if docker exec "$POSTGRES_CONTAINER" pg_isready -U coramail_restore -d coramail_restore >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker exec "$POSTGRES_CONTAINER" pg_isready -U coramail_restore -d coramail_restore >/dev/null

docker run --rm -i --network "$NETWORK" "$WEB_IMAGE" python - <<'PY'
import time
import urllib.request

for attempt in range(60):
    try:
        with urllib.request.urlopen("http://qdrant:6333/readyz", timeout=2) as response:
            if response.status == 200:
                raise SystemExit(0)
    except Exception:
        if attempt == 59:
            raise
        time.sleep(1)
raise SystemExit(1)
PY

docker exec -i "$POSTGRES_CONTAINER" pg_restore \
  -U coramail_restore \
  -d coramail_restore \
  --no-owner \
  --no-acl \
  --exit-on-error \
  <"$BACKUP_DIR_ABS/$POSTGRES_DUMP"

docker run --rm \
  -v "$RUNTIME_VOLUME:/restore" \
  -v "$BACKUP_DIR_ABS:/backup:ro" \
  "$WEB_IMAGE" \
  tar -xzf "/backup/$RUNTIME_ARCHIVE" -C /restore --strip-components=1

docker run --rm \
  --network "$NETWORK" \
  -v "$REPO_ROOT:/workspace:ro" \
  -v "$BACKUP_DIR_ABS:/backup:ro" \
  -w /workspace \
  "$WEB_IMAGE" \
  python -m app.tools.restore_qdrant_snapshot "/backup/$QDRANT_SNAPSHOT" \
  --qdrant-url http://qdrant:6333 \
  --collection "$QDRANT_COLLECTION"

RUNTIME_REPORT="$(docker run --rm -i \
  --network "$NETWORK" \
  -v "$RUNTIME_VOLUME:/app/data/runtime:ro" \
  "$WEB_IMAGE" \
  python - <<'PY'
import hashlib
import json
from pathlib import Path

import psycopg

database_url = "postgresql://coramail_restore:restore-drill-only@postgres:5432/coramail_restore"
with psycopg.connect(database_url) as connection:
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM email_messages")
        email_count = int(cursor.fetchone()[0])
        cursor.execute(
            """
            SELECT storage_uri, file_size, checksum
            FROM email_attachments
            WHERE deleted_at IS NULL
            ORDER BY storage_uri
            """
        )
        attachments = cursor.fetchall()

errors = []
digests = {}
verified = 0
for storage_uri, expected_size, expected_checksum in attachments:
    path = Path(str(storage_uri))
    if not path.is_absolute():
        path = Path("/app") / path
    if not path.is_file():
        errors.append(f"missing:{storage_uri}")
        continue
    if expected_size is not None and path.stat().st_size != int(expected_size):
        errors.append(f"size:{storage_uri}")
        continue
    if expected_checksum:
        digest = digests.get(path)
        if digest is None:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            digests[path] = digest
        if digest.casefold() != str(expected_checksum).casefold():
            errors.append(f"checksum:{storage_uri}")
            continue
    verified += 1

report = {
    "status": "ok" if not errors and email_count > 0 and attachments else "error",
    "email_count": email_count,
    "attachment_count": len(attachments),
    "verified_attachment_count": verified,
    "unique_hashed_files": len(digests),
    "errors": errors[:10],
}
print(json.dumps(report, ensure_ascii=False, sort_keys=True))
if report["status"] != "ok":
    raise SystemExit(1)
PY
)"
if [[ -z "$RUNTIME_REPORT" ]]; then
  printf 'restore_drill=error reason=empty-runtime-verification\n' >&2
  exit 1
fi

printf '%s\n' "$VERIFY_JSON"
printf '%s\n' "$RUNTIME_REPORT"
printf 'restore_drill=ok backup=%s isolated_prefix=%s\n' "$BACKUP_DIR_ABS" "$PREFIX"

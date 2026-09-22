#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="${CORAMAIL_PROD_ENV_FILE:-config/production.env}"
export CORAMAIL_PROD_COMPOSE_ENV_FILE="$ENV_FILE"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_ROOT="${CORAMAIL_PROD_BACKUP_DIR:-backups/production}"
BACKUP_DIR="${BACKUP_ROOT%/}/${TIMESTAMP}"
if [[ "$BACKUP_DIR" = /* ]]; then
  BACKUP_DIR_ABS="$BACKUP_DIR"
else
  BACKUP_DIR_ABS="$(pwd)/$BACKUP_DIR"
fi
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
QDRANT_COLLECTION="$(sed -n 's/^CORAMAIL_QDRANT_CASE_COLLECTION=//p' "$ENV_FILE" | tail -n 1)"

uv run python -m app.tools.check_deployment_readiness --env-file "$ENV_FILE" --warnings-as-errors

docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-acl' \
  >"$BACKUP_DIR/postgres.dump"

docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml exec -T web python - \
  >"$BACKUP_DIR/runtime.tar.gz" <<'PY'
import sys
import tarfile

with tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz") as archive:
    archive.add("/app/data/runtime", arcname="runtime")
PY

docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml --profile tools run --rm \
  -v "$BACKUP_DIR_ABS:/backup" \
  migrate \
  python -m app.tools.create_qdrant_snapshot --output-dir /backup

cat >"$BACKUP_DIR/manifest.txt" <<EOF
created_at=$TIMESTAMP
env_file=$ENV_FILE
postgres_dump=postgres.dump
runtime_archive=runtime.tar.gz
qdrant_collection=$QDRANT_COLLECTION
EOF

uv run python -m app.tools.verify_production_backup "$BACKUP_DIR"

printf 'production_backup=%s\n' "$BACKUP_DIR"

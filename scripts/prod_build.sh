#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ -z "${CORAMAIL_WEB_IMAGE:-}" ]]; then
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    CORAMAIL_WEB_IMAGE="coramail-agent:$(git rev-parse --short HEAD)"
  else
    CORAMAIL_WEB_IMAGE="coramail-agent:local"
  fi
fi

docker build -t "$CORAMAIL_WEB_IMAGE" .
printf 'CORAMAIL_WEB_IMAGE=%s\n' "$CORAMAIL_WEB_IMAGE"

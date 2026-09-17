#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TRACK="${1:-}"
TARGET="${CORAMAIL_PROD_ENV_FILE:-config/production.env}"
FORCE="${CORAMAIL_PROD_INIT_FORCE:-false}"

usage() {
  cat <<'EOF'
usage: scripts/prod_init_env.sh setup|saas|private|hybrid

Creates the production env file from the matching beta template.
Set CORAMAIL_PROD_ENV_FILE=/path/to/production.env to write outside the repo.
Set CORAMAIL_PROD_INIT_FORCE=true to replace an existing target.
EOF
}

case "$TRACK" in
  setup)
    SOURCE="config/production.env.example"
    ;;
  saas)
    SOURCE="config/production.saas.env.example"
    ;;
  private)
    SOURCE="config/production.private.env.example"
    ;;
  hybrid)
    SOURCE="config/production.hybrid.env.example"
    ;;
  -h|--help|help|"")
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

if [[ -e "$TARGET" && "$FORCE" != "true" ]]; then
  printf 'production_env_exists=%s\n' "$TARGET" >&2
  printf 'Set CORAMAIL_PROD_INIT_FORCE=true to replace it.\n' >&2
  exit 1
fi

mkdir -p "$(dirname "$TARGET")"
install -m 600 "$SOURCE" "$TARGET"
printf 'production_env_initialized=%s\n' "$TARGET"
printf 'production_env_source=%s\n' "$SOURCE"
printf 'Next: edit placeholders in %s, then run scripts/prod_check.sh\n' "$TARGET"

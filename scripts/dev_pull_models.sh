#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# shellcheck source=scripts/dev_env.sh
source "$REPO_ROOT/scripts/dev_env.sh"

models=(
  "$CORAMAIL_TEXT_MODEL"
  "$CORAMAIL_VISION_MODEL"
  "$CORAMAIL_EMBEDDING_MODEL"
)

docker compose up -d ollama

for model in "${models[@]}"; do
  if [[ -z "$model" ]]; then
    continue
  fi
  docker compose exec ollama ollama pull "$model"
done

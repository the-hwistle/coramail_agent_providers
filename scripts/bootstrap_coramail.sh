#!/usr/bin/env bash
set -Eeuo pipefail

EXPECTED_REPO="${EXPECTED_REPO:-the-hwistle/coramail_agent}"
TARGET_BRANCH="${TARGET_BRANCH:-feat/e2e-evaluation-runner}"

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

fail() {
  printf '\n[ERROR] %s\n' "$*" >&2
  exit 1
}

command -v git >/dev/null 2>&1 || fail "git이 설치되어 있지 않습니다."
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail "현재 경로가 Git 저장소가 아닙니다. VS Code의 coramail_agent 저장소 루트에서 실행하세요."

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

ORIGIN_URL="$(git remote get-url origin 2>/dev/null || true)"
[[ -n "$ORIGIN_URL" ]] || fail "origin remote가 없습니다."

case "$ORIGIN_URL" in
  *"$EXPECTED_REPO"* ) ;;
  * ) fail "현재 origin이 예상 저장소가 아닙니다: $ORIGIN_URL" ;;
esac

if [[ -n "$(git status --porcelain)" ]]; then
  printf '\n현재 로컬 변경 사항:\n' >&2
  git status --short >&2
  fail "pull 전에 변경 사항을 commit 또는 stash하세요. 자동으로 삭제하거나 stash하지 않습니다."
fi

log "원격 변경사항을 가져옵니다."
git fetch origin --prune

if ! git show-ref --verify --quiet "refs/remotes/origin/$TARGET_BRANCH"; then
  fail "원격 브랜치를 찾을 수 없습니다: origin/$TARGET_BRANCH"
fi

CURRENT_BRANCH="$(git branch --show-current)"
if [[ "$CURRENT_BRANCH" == "$TARGET_BRANCH" ]]; then
  log "현재 작업 브랜치를 유지합니다: $TARGET_BRANCH"
elif git show-ref --verify --quiet "refs/heads/$TARGET_BRANCH"; then
  log "기존 로컬 브랜치로 전환합니다: $TARGET_BRANCH"
  git switch "$TARGET_BRANCH"
else
  log "원격 브랜치를 추적하는 로컬 브랜치를 생성합니다: $TARGET_BRANCH"
  git switch --track -c "$TARGET_BRANCH" "origin/$TARGET_BRANCH"
fi

log "최신 코드를 fast-forward 방식으로 pull합니다."
git pull --ff-only origin "$TARGET_BRANCH"

log "현재 상태"
printf 'repository: %s\n' "$REPO_ROOT"
printf 'branch:     %s\n' "$(git branch --show-current)"
printf 'commit:     %s\n' "$(git rev-parse --short HEAD)"
printf 'remote:     %s\n' "$(git remote get-url origin)"

cat <<'EOF'

업데이트가 완료되었습니다.
VS Code에서 CODEX_PROMPT.md를 열고 전체 내용을 Codex에 전달하세요.

EOF

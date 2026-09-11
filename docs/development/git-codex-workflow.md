# Git과 Codex 공동 개발 워크플로우

## 목적

이 문서는 사람과 Codex가 함께 개발할 때 코드 수정 권한과 Git 게시 권한을 분리하고, 검증 가능한 변경 이력을 유지하는 기준을 정의한다.

## 기본 원칙

- 코드나 문서 수정 요청은 자동으로 commit 또는 push 권한을 뜻하지 않는다.
- Codex는 사용자가 명시적으로 요청한 경우에만 commit, push, PR 생성·수정, merge 같은 GitHub 상태 변경을 수행한다.
- `main`은 설명 가능한 안정 상태로 유지하고, 공유할 변경은 기능·수정·정리 브랜치와 pull request를 우선한다.
- 서로 관계없는 변경은 같은 commit에 섞지 않는다.
- 민감 정보, 실제 고객 개인정보, 인증 정보, 런타임 데이터, 생성된 대형 평가 산출물은 commit하지 않는다.
- 확정된 기술 선택은 대화 기록에만 남기지 않고 `docs/decisions/`에 기록한다.

## 권장 작업 흐름

1. 현재 브랜치와 작업 트리 상태를 확인한다.
2. 관련 `AGENTS.md`와 필요한 제품·기능·아키텍처 문서를 읽는다.
3. 변경을 구현한다.
4. 가장 작은 관련 검증부터 실행한다.
5. 완료 전에 `git status --short`와 관련 diff를 검토한다.
6. 사용자가 commit을 요청한 경우에만 논리적으로 응집된 commit을 만든다.
7. 사용자가 원격 게시를 요청한 경우에만 feature/fix/chore 브랜치에 push하고 PR을 우선한다.

기본 검증 명령:

```bash
uv sync --frozen
uv run python -m compileall app tests
uv run ruff check .
uv run pytest -q
```

UI 변경은 필요한 Playwright 테스트를 추가로 실행한다.

## 브랜치 규칙

- `main`: 안정 기준선
- `feat/*`: 기능
- `fix/*`: 버그 수정
- `refactor/*`: 동작 변경 없는 구조 개선
- `chore/*`: 저장소, CI, 개발환경 정리
- `docs/*`: 문서 중심 변경
- `spike/*`: 폐기 가능한 실험

Codex는 사용자 요청 없이 `main`에 직접 push하지 않는다.

## Commit 규칙

사용자가 commit을 요청한 경우 다음 형식을 권장한다.

```text
type: short summary
```

`docs`, `feat`, `fix`, `test`, `refactor`, `chore`, `data`를 사용한다.

## Pull Request

원격 공유가 필요한 작업은 PR을 기본 단위로 삼는다. PR 본문에는 다음을 간결히 기록한다.

- 변경 목적
- 주요 변경 사항
- 실행한 검증
- 실행하지 못한 검증과 이유
- 남은 위험과 후속 작업

## 개발 기록

Git diff와 commit이 변경 내용의 원본 기록이다. 장기적으로 가치가 있는 개발 맥락만 `docs/development/codex-history/YYYY/MM/` 아래에 작은 날짜별 문서로 기록한다.

기록 대상 예:

- 반복해서 참조할 설계 제약
- 어려웠던 장애의 근본 원인과 재발 방지책
- 사용자가 명시적으로 수락·거부한 중요한 방향
- 아직 남은 위험과 다음 검증 지점

단순 명령 출력, 전체 traceback, diff 복사본, 매 대화의 진행 상황은 장기 기록으로 남기지 않는다.

## 복구

커밋된 변경을 되돌릴 때는 `git revert`를 우선한다.

`git reset --hard`, force push, 추적 중인 사용자 작업 삭제처럼 이력을 지우거나 작업물을 잃을 수 있는 방법은 사용자가 명시적으로 요청하고 승인한 경우에만 사용한다.

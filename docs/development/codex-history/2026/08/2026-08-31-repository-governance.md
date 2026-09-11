# Repository governance and Codex maintainability

## 요청

저장소를 검토한 뒤 Codex가 안전하고 효율적으로 작업할 수 있도록 운영 규칙, CI, 문서 정확성, 계층형 지침, 대형 파일·평가 데이터 관리 기준을 순서대로 개선한다.

## 확인한 사실

- 루트 `AGENTS.md`가 의미 있는 변경마다 commit과 push를 사실상 기본 동작으로 요구했다.
- `docs/development/codex-history/session-log.md`가 약 884KB의 단일 누적 로그가 되었다.
- 루트 `CODEX_PROMPT.md`는 특정 과거 브랜치와 PR을 전제로 한 일회성 로컬 E2E 검증 지시였다.
- README의 `초기 설계 단계` 설명은 현재 Gmail, PostgreSQL, Qdrant, Agent, workflow, UI, 평가, 테스트 구현 상태와 맞지 않았다.
- `app/server.py`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py`가 대형 파일로 성장했다.

## 결정

- 코드 수정 권한과 commit/push 권한을 분리한다.
- 루트 지침은 영속적인 불변조건만 유지하고 `app/`, `tests/`, `data/`에 세부 `AGENTS.md`를 둔다.
- 단일 Codex 로그는 legacy archive로 보존하고 신규 기록은 날짜별 파일로 나눈다.
- 특정 과거 세션의 `CODEX_PROMPT.md`는 개발 runbook으로 이동한다.
- 생성 평가 산출물과 source dataset/ground truth/curated baseline을 구분한다.
- 대형 애플리케이션·UI 파일은 기능 변경과 분리된 작은 refactor로 단계적으로 분해한다.

## 검증

이번 변경은 GitHub 연결을 통한 저장소 수정이므로 로컬 `uv`, pytest, Playwright, Docker 기반 검증을 직접 실행하지 못했다. CI가 이 브랜치/PR에서 기본 정적 검증과 테스트를 실행하도록 추가한다.

## 남은 위험

- 기존 대형 파일의 실제 분해는 각 기능 경계의 회귀 테스트를 확보하면서 별도 refactor로 진행해야 한다.
- 기존 tracked evaluation 산출물은 이 변경에서 삭제하지 않는다. 새 정책을 적용한 뒤 실제로 재현 가능한 파일인지 확인해 후속 정리한다.

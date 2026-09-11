# Repository maintainability roadmap

이 문서는 현재 기능 동작을 유지하면서 대형 파일과 테스트 구조를 단계적으로 분리하는 실행 기준이다.

## 1. `app/server.py`

새 책임을 추가하지 않는다. 다음 순서로 얇게 만든다.

1. 인증·쿠키·환경 보조 함수를 독립 모듈로 이동한다.
2. `/api/*` route group을 `app/api/` router로 이동한다.
3. `/ui/*` view route를 기능별 web router로 이동한다.
4. service/repository 전역 생성 코드를 application wiring 모듈로 이동한다.
5. 마지막 `server.py`는 app 생성, middleware, static/template 설정, router 등록만 담당한다.

각 추출은 동작 변경 없는 별도 refactor로 하고 기존 UI/API 회귀 테스트를 먼저 고정한다.

## 2. UI 템플릿과 CSS

- `shell.html`은 layout, navigation, reusable component, page-specific block으로 나눈다.
- `app.css`는 tokens/base/layout/components/pages 단위로 나눈다.
- 기존 selector와 DOM 계약을 보존하면서 Playwright smoke를 통과시킨 뒤 불필요한 legacy selector를 제거한다.

## 3. 테스트 구조

새 테스트는 `unit`, `contract`, `integration`, `e2e` 경계를 따른다. 기존 대형 `test_mail_decision_ui.py`는 변경하는 기능부터 별도 파일로 추출하고, 한 번에 전체를 이동하지 않는다.

## 4. 평가 데이터

- source dataset, ground truth, deterministic fixture는 추적 가능하다.
- generated run output은 기본적으로 ignored 경로에 둔다.
- curated baseline은 metadata와 함께 명시적으로 승격한다.
- 기존 대형 tracked 결과물은 재현 가능성을 확인한 뒤 작은 후속 PR에서 제거하거나 artifact 저장소로 옮긴다.

## 완료 조건

- `server.py`에 신규 기능 로직이 추가되지 않는다.
- 새 route가 적절한 router/service 경계를 따른다.
- 대형 UI 파일은 기능 단위 수정 범위가 작아진다.
- contract/architecture test가 계층 역전을 조기에 감지한다.
- 평가 실행으로 생기는 임시 산출물이 Git diff를 오염시키지 않는다.

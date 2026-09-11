# Codex 세션 로그

이 문서는 CoRA Mail Agent를 Codex와 함께 개발하면서 생긴 요청, 판단, 오류, 해결, 리스크를 날짜순으로 누적한다.

---

# 2026-08-31 - 견적의뢰서 12-13번 품목 누락 원인 수정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Attachment analysis, RFQ vertical table parsing |
| 관련 파일 | `app/document_processing/parsers.py`, `tests/test_attachment_parsers.py` |

## 요청 또는 배경

- 사용자는 `35f326b5-28b9-5a6b-8a0b-4de14d82904b` 메일의 0번 첨부파일에서 실제 `No`가 13까지 있는데 UI에는 11까지만 나온다고 보고했다.
- 근본 원인 파악 후 해결을 요청했다.

## 확인한 사실

- 해당 PDF의 pypdf 텍스트 추출 결과에서 `No` 12와 13은 실제로 존재했다.
- 12번 품목은 `Code`가 `98516704-80B-`와 `2`로 줄바꿈 분리되고 그 뒤 `Qty=1`, `Unit=EA`가 이어졌다.
- 13번 품목은 Description이 여러 줄로 감긴 뒤 `Code=VA-FR-05`, `Qty=3`, `Unit=EA`가 이어졌다.
- 기존 RFQ 세로 표 파서는 `No, Description, Code, Qty, Unit`이 항상 5개 토큰으로 붙어 있다고 가정해, 줄바꿈으로 감긴 품목을 유효 행으로 인식하지 못했다.

## 해결 방법

- RFQ 세로 표에서 단순 5토큰 파싱 전에 `No` anchor 사이의 segment를 기준으로 품목을 복구하는 경로를 추가했다.
- 각 segment는 뒤에서부터 `Unit`, `Qty`, `Code`를 찾고, 앞쪽 나머지를 Description으로 병합한다.
- 하이픈 등으로 끊긴 Code 토큰은 이어 붙이도록 처리했다.
- 12번 split code와 13번 multiline Description 형태를 회귀 테스트로 고정했다.

## 검증

- `uv run pytest tests/test_attachment_parsers.py`: 22 passed.
- `uv run pytest tests/test_attachment_analysis_presentation.py tests/test_quote_attachment_field_labels.py tests/test_mail_decision_ui.py -k "attachment_line_item or attachment_details_for_business or attachment_reanalysis_skips_llm"`: 4 passed.
- `python -m py_compile app/document_processing/parsers.py app/document_processing/text_analyzer.py app/document_processing/vision_analyzer.py app/presentation/attachment_analysis.py`: passed.
- Docker Compose `web` 재시작 후 `/api/health` 정상 확인.
- `POST /api/emails/35f326b5-28b9-5a6b-8a0b-4de14d82904b/attachments/reanalyze` 실행 결과, 0번 RFQ 첨부의 품목이 `No` 1부터 13까지 표시되는 것을 확인했다.

---

# 2026-08-31 - Monitoring 전달 대기 주황 상태 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring UI, pipeline status |
| 관련 파일 | `app/server.py`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Monitoring 탭의 상태 표시가 초록/빨강 2색으로만 구분되어 있어, 모든 처리가 완료됐지만 담당자 전달만 아직 안 된 상태를 주황색으로 별도 표시해 달라고 요청했다.
- 빨간색 표시는 기존 빨간색 대상에서 이 주황 상태를 제외한 나머지 미완료 상태를 의미해야 한다.

## 해결 방법

- `ops_pipeline_status()`에서 첨부, 요약, 분류, Mail Decision, 라우팅 단계가 완료 계열이고 전달 단계만 미완료인 경우 `delivery_pending` 상태와 `is-delivery-pending` 클래스를 반환하도록 분리했다.
- 전달 실패는 명시적인 실패 상태이므로 기존처럼 빨간색 `is-blocked`로 남겼다.
- Monitoring 상태 원에 주황색 CSS를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "ops_pipeline_status or ops_row_view_requires_decision"`: 5 passed.

---

# 2026-08-31 - 견적의뢰서 품목 수 검증과 컬럼 폭 조정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Attachment analysis, RFQ line items, email detail UI |
| 관련 파일 | `app/document_processing/parsers.py`, `app/document_processing/text_analyzer.py`, `app/document_processing/vision_analyzer.py`, `app/static/app.css`, `app/templates/partials/email_detail.html`, `docs/features/attachment-analysis.md`, `tests/test_attachment_parsers.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 견적의뢰서도 견적서와 마찬가지로 `No` 컬럼의 최대값을 품목 총 개수로 보고, 추출 품목 수와 일치하는지 확인해 부족하면 재추출하도록 요청했다.
- 또한 견적의뢰서 품목 표에서 `No` 컬럼은 많이 줄이고, `Description`은 많이 넓히며, `Code`는 조금 넓히고, `Qty`는 조금 줄여달라고 요청했다.

## 확인한 사실

- 기존 RFQ 파서는 품목 행을 추출하더라도 `No` 최대값 기반 count 검증과 부족 행 복구/경고를 수행하지 않았다.
- 이메일 상세 UI의 품목 grid는 문서 유형 modifier가 없어 견적서와 견적의뢰서에 서로 다른 컬럼 비율을 줄 수 없었다.
- Playwright Chromium은 기본 샌드박스 실행에서 `sandbox_host_linux.cc` 오류로 실패해 승인된 unsandboxed 실행으로 실제 브라우저 검증을 수행했다.

## 해결 방법

- RFQ 가로/세로 표에서 `No` 숫자를 확인해 최대값을 기대 품목 수로 계산하도록 했다.
- 저장/LLM 결과의 `line_items` 수가 기대 품목 수보다 적으면 파싱 텍스트에서 RFQ 품목 행을 다시 복구하고, 그래도 부족하면 `fixed_rfq_line_items_missing:expected=<n>,actual=<m>` warning을 남기도록 했다.
- 텍스트/비전 분석 프롬프트와 기능 문서에 RFQ `No` 최대값 기준을 반영했다.
- 이메일 상세 템플릿에 `attachment-line-item-grid--rfq` modifier를 추가하고, RFQ 품목 grid에서 `No`, `Qty`는 좁게, `Description`, `Code`는 넓게 표시되도록 CSS를 추가했다.

## 검증

- `uv run pytest tests/test_attachment_parsers.py tests/test_attachment_analysis_presentation.py tests/test_quote_attachment_field_labels.py`: 42 passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "attachment_line_item or attachment_details_for_business or attachment_reanalysis_skips_llm"`: 4 passed.
- `python -m py_compile app/document_processing/parsers.py app/document_processing/text_analyzer.py app/document_processing/vision_analyzer.py app/presentation/attachment_analysis.py`: passed.
- Docker Compose `web` 재시작 후 `/api/health` 정상 확인.
- `POST /api/emails/35f326b5-28b9-5a6b-8a0b-4de14d82904b/attachments/reanalyze` 실행 결과, RFQ 첨부 품목이 `No` 1부터 11까지 표시되는 것을 확인했다.
- Playwright 실제 브라우저 검증에서 RFQ grid class와 계산 폭 `No 24px`, `Description 220px`, `Code 112px`, `Qty 36px`, `Unit 48px`를 확인했다.

---

# 2026-08-31 - 견적의뢰서 PDF 파싱 및 필드 추출 적용

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Attachment analysis, RFQ PDF parsing, document type classification |
| 관련 파일 | `app/document_processing/attachment_classifier.py`, `app/document_processing/parsers.py`, `app/document_processing/text_analyzer.py`, `app/document_processing/vision_analyzer.py`, `app/presentation/attachment_analysis.py`, `docs/features/attachment-analysis.md`, `tests/test_attachment_parsers.py`, `tests/test_attachment_analysis_presentation.py` |

## 요청 또는 배경

- 사용자는 기존 견적서 첨부파일 분석과 같은 방식으로 PDF 문서 유형 `견적의뢰서`에 대한 파싱 및 정보 추출을 적용해 달라고 요청했다.
- 견적서는 문서 내 `견적서` 또는 `QUOTATION`, 견적의뢰서는 `견적의뢰서` 또는 `INQUIRY` 문구로 구분한다고 명시했다.
- UI와 데이터 구조는 우선 기존 견적서 구조를 따르되, 표시 필드는 `To`, `Attn`, `Email`, `Tel`, `Fax`, `Vessel`, `Date`, `Our Ref No`, `In Charge`, 품목 행의 `No`, `Description`, `Code`, `Qty`, `Unit`으로 정했다.

## 확인한 사실

- 기존 코드에는 `rfq` 문서 유형과 `견적의뢰서` 라벨은 있었지만, 표 행 정규화와 UI 표시 컬럼이 견적서 가격 컬럼 중심으로 고정되어 있었다.
- 실제 샘플 PDF 3건은 모두 `INQUIRY / 견적의뢰서` 텍스트를 포함했으나, 기존 분류 우선순위 때문에 `quote`로 잘못 분류될 수 있었다.
- 샘플 PDF의 품목 표는 pypdf 추출 시 `No`, `Description`, `Code`, `Qty`, `Unit` 헤더와 행 값이 세로 토큰 형태로 풀려 나와 RFQ 전용 행 복구가 필요했다.

## 해결 방법

- 문서 텍스트 분류에서 `INQUIRY`/`견적의뢰서`를 `QUOTATION`/`견적서`보다 먼저 판정하도록 변경했다.
- RFQ 고정 필드는 헤더 필드와 `line_items`로 제한하고, `line_items`에는 `No`, `Description`, `Code`, `Qty`, `Unit`만 보존하도록 분리했다.
- RFQ 가로 표와 세로 토큰 표를 복구하는 deterministic parser를 추가하고, 오래된 품목 10개 제한을 제거했다.
- 화면 표시 계층에서 문서 유형별 품목 컬럼을 사용하도록 변경해 `quote`는 가격 컬럼, `rfq`는 `No/Code` 컬럼을 표시하게 했다.
- 텍스트/비전 분석 프롬프트와 기능 문서의 RFQ 필드 계약을 갱신했다.

## 검증

- `uv run pytest tests/test_attachment_parsers.py tests/test_attachment_analysis_presentation.py tests/test_quote_attachment_field_labels.py`: 40 passed.
- 사용자가 제공한 세 샘플 첨부 URL을 8000번 서버에서 다운로드해 로컬 파서로 확인했다. 결과는 모두 `document_type=rfq`이며 품목 행은 각각 1개, 2개, 11개로 추출됐다.
- Docker Compose `web` 서비스를 재시작하고 `/api/health` 정상 상태를 확인했다.
- `POST /api/emails/{email_uid}/attachments/reanalyze`를 세 샘플 이메일에 순차 실행해 실제 저장/표시 결과가 `견적의뢰서`와 RFQ 품목 행으로 갱신되는 것을 확인했다.

---

# 2026-08-31 - Settings 담당자 우선순위 드래그 복원

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Settings, assignee routing priority, drag reorder |
| 관련 파일 | `app/repositories/postgres_assignee_admin_repository.py`, `app/server.py`, `app/templates/shell.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Settings 탭의 `담당자 우선순위 배정` 영역에서 담당자 이름을 누르거나 왼쪽 drag handle을 끌어 담당자 간 우선순위를 바꾸는 기능이 동작하지 않는다고 보고했다.

## 확인한 사실

- Settings summary chip에는 `draggable="true"`와 drag handle 마크업이 남아 있었다.
- 클라이언트 dragstart 핸들러는 handle이 아니면 long-press 상태가 먼저 활성화되어야만 드래그를 허용했는데, 브라우저 native dragstart가 timer보다 먼저 발생하면 이름 영역 드래그가 차단될 수 있었다.
- `/ui/settings/routing-summary/reorder` endpoint는 POST body를 저장하지 않고 summary partial만 다시 렌더링해, 화면에서 순서를 바꿔도 persisted priority가 바뀌지 않았다.

## 해결 방법

- 이름 영역과 drag handle 모두 chip drag를 허용하되, 활성 상태 toggle 버튼만 드래그 대상에서 제외했다.
- reorder POST에 카테고리 label을 포함하고, endpoint가 다중 `assignee_ids`와 category를 읽어 저장하도록 했다.
- 카테고리별 담당자 우선순위를 `assignee_capabilities.priority`에 저장하고, Settings summary 렌더링도 category priority 기준으로 정렬하게 했다.
- 회귀 테스트로 category priority 정렬, reorder endpoint 저장 호출, shell drag payload를 고정했다.

## 검증

- `python -m py_compile app/server.py app/repositories/postgres_assignee_admin_repository.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "settings_route_assignments_follow_category_priority or assignee_view_derives_category_priority_from_capabilities or settings_routing_reorder_persists_category_order or shell_allows_drag_from_routing_assignee_name_and_sends_category or settings_renders_synthetic_assignees" -q`: 5 passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "settings or routing_summary or routing_table or manual_assignment_options" -q`: 7 passed.
- Docker Compose web 재시작 후 8000번 서버 `/api/health` 정상 확인.
- Playwright 실제 브라우저 검증: Settings 서비스 담당자 이름 영역 드래그로 `최유진, 이준호`가 `이준호, 최유진`으로 변경되고, drag handle 드래그로 원래 순서로 복구되는 reorder POST 2건을 확인했다.

---

# 2026-08-31 - 견적서 품목 Amount 원 단위 제거

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Attachment analysis, quotation line items, presentation |
| 관련 파일 | `app/document_processing/parsers.py`, `app/document_processing/text_analyzer.py`, `app/document_processing/vision_analyzer.py`, `app/presentation/attachment_analysis.py`, `tests/test_attachment_parsers.py`, `tests/test_attachment_analysis_presentation.py` |

## 요청 또는 배경

- 사용자는 견적서 첨부파일 분석에서 품목의 `Amount` 값에 `원` 단위가 붙는 오류를 해결해 달라고 요청했다.

## 확인한 사실

- 한국어 견적서 행의 `420,000원 2,100,000원` 같은 값은 텍스트 파서가 품목 `U/Price`, `Amount`에 원문 단위를 그대로 저장할 수 있었다.
- 화면 표시 계층은 `Total Price`, `U/Price`, `Amount` 라벨을 모두 통화 포맷 대상으로 처리해 품목 `Amount`에도 `원`을 다시 붙였다.
- 총액(`Total Price`) 표시는 기존처럼 원화 표시가 필요하지만, 품목 `Amount`는 사용자가 지적한 오류 범위이므로 line item 전용 표시 계약으로 분리해야 했다.

## 해결 방법

- 견적서 line item 정규화에서 `U/Price`, `Amount` 값의 한국어 `원` 단위를 제거해 저장값이 숫자 중심으로 유지되게 했다.
- 화면 행 생성 시 품목 `Amount`는 자동 원화 포맷을 적용하지 않고, 품목 `U/Price`와 문서 총액만 기존 원화 표시를 유지했다.
- 텍스트/비전 LLM 프롬프트에도 quote line item `Amount`에는 한국어 `원` 단위를 붙이지 말라는 제약을 추가했다.
- 파서와 프레젠테이션 회귀 테스트를 추가/수정했다.

## 검증

- `uv run pytest tests/test_attachment_parsers.py tests/test_attachment_analysis_presentation.py`: 34 passed.
- `uv run pytest tests/test_mail_decision_ui.py::test_email_detail_renders_attachment_line_items_as_field_grid`: 1 passed.

---

# 2026-08-31 - Monitoring 단계 셀 아이콘 전용 표시

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring, pipeline stage cells, duration labels |
| 관련 파일 | `app/templates/partials/ops_rows.html`, `app/templates/views/ops.html`, `app/static/app.css`, `app/server.py`, `app/services/postgres_mail_service.py`, `app/services/demo_mail_service.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Monitoring 탭의 Attach, Summary, Classify, Decision, Routing, Forward 단계 컬럼 값에서 `1개 완료`, `첨부 없음`, `완료` 같은 텍스트를 제거하고 아이콘만 남기기를 요청했다.
- Decision, Routing, Forward 단계 값의 아이콘은 Summary와 동일한 상태 아이콘 체계로 맞추기를 요청했다.
- Monitoring 소요시간은 표시될 때 소수 둘째 자리까지 보이도록 요청했다.
- 단계 컬럼명은 `첨부파일`, `요약`, `업무유형 분류`, `담당자 배정`, `전달`로 바꾸기를 요청했다.

## 확인한 사실

- 단계 셀 텍스트는 `ops_stage_cell()` 매크로에서 모든 단계 공통으로 렌더링되고 있었다.
- Routing과 Forwarding 단계는 완료/미시작 상태에서 Summary와 다른 커스텀 아이콘을 직접 지정하고 있었다.
- PostgreSQL 기반 duration은 `PostgresMailboxService._duration_label()`에서 정수 초로 잘라 표시했고, Demo row에는 `0초`가 고정값으로 들어 있었다.
- 작업 시작 전부터 첨부 분석 관련 파일에 별도 dirty 변경이 있었으므로 이번 커밋 범위에서 제외했다.

## 해결 방법

- `ops_stage_cell()`에서 단계 라벨 span을 제거하고, CSS를 아이콘 전용 24px pill에 맞춰 정리했다.
- Routing과 Forwarding 단계 아이콘은 `ops_stage_icon()` 상태 매핑을 사용하도록 바꿔 Summary와 동일한 상태 아이콘 체계를 따르게 했다.
- Monitoring 컬럼 선택 메뉴와 테이블 헤더의 단계 컬럼명을 한국어 라벨로 변경했다.
- duration formatter는 초를 버리지 않고 `12.34초`, `2분 0.50초`, `1시간 0분 0.00초`처럼 소수 둘째 자리까지 표시하도록 변경했다.

## 검증

- `python -m py_compile app/server.py app/services/postgres_mail_service.py app/services/demo_mail_service.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "monitoring or ops_pipeline_status or ops_row_view or typography" -q`: 23 passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 190 passed.
- Docker Compose web 재시작 후 8000번 서버에서 `/ui/monitoring` 응답 200 확인.
- Playwright 실제 브라우저 DOM 검사: 헤더는 `첨부파일`, `요약`, `업무유형 분류`, `담당자 배정`, `라우팅`, `전달`; 첫 행 6개 단계 pill은 모두 `24x24`, stage text/nested label은 0개, 아이콘은 `remove_done`, `task_alt` 상태 아이콘으로 렌더링됨.

---

# 2026-08-27 - 데모모드 탭 전환 즉시 반영

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode, shell navigation, HTMX, UI responsiveness |
| 관련 파일 | `app/templates/shell.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 데모모드에서 탭별 전환이 지연 없이 즉시 반영되도록 근본 원인을 파악해 해결하기를 요청했다.
- 이후 포트는 항상 8000번을 사용하라고 지시했다.

## 확인한 사실

- fixture-only 로컬 실행에서는 탭 fragment 응답이 대체로 0.1~0.2초였지만, 실제 8000 Docker Compose PostgreSQL 데모 환경에서는 `/ui/inbox`가 약 1초 이상 걸릴 수 있었다.
- 기존 구조는 데모 화면도 매 탭 클릭마다 서버 fragment 응답을 기다린 뒤 `#main-panel`을 교체했다.
- 전체 탭을 동시에 프리페치하면 PostgreSQL 기반 데모에서 오히려 요청이 몰려 응답 시간이 늘어났다.
- 캐시 HTML을 클릭 시점에 문자열로 다시 파싱하면 Dashboard와 Inbox 같은 큰 화면에서 200~400ms의 DOM/레이아웃 비용이 남았다.

## 해결 방법

- 메인 내비게이션 버튼의 `hx-sync="#main-panel:replace"`를 렌더된 HTML에 직접 포함해 오래 걸리는 이전 탭 요청이 최신 탭 전환을 덮지 않게 했다.
- 데모모드 전용 탭 fragment 캐시를 추가하고, 프리페치 시 HTML뿐 아니라 DOM 노드까지 미리 구성하도록 했다.
- 캐시가 있는 탭 클릭은 capture 단계에서 HTMX 요청을 기다리지 않고 즉시 `#main-panel`에 캐시 노드를 붙인다.
- 차트 초기화, iframe 높이 계산, HTMX `load` 후처리 같은 무거운 작업은 탭 본문 교체 후 다음 프레임으로 미뤘다.
- 메일 삭제, 재분석, 수동 배정, 업무 확인 등 화면 데이터가 바뀌는 이벤트에서는 데모 탭 캐시를 무효화해 오래된 화면이 즉시 재사용되지 않게 했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py`: 188 passed.
- `npm run test:e2e:ui-smoke`: 4 passed.
- 8000 Docker Compose web 재시작 후 Playwright native click 측정: Inbox 52ms, Monitoring 78ms, Dashboard 24ms, Inbox 재진입 60ms, Search 52ms, Chats 1ms. 모든 측정에서 active 상태는 클릭 즉시 반영됨.

---

# 2026-08-27 - Inbox 삭제 확인 팝업 디자인 통일

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox, mail detail delete, HTMX confirm modal |
| 관련 파일 | `app/templates/partials/email_detail.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Inbox 탭에서 메일 삭제 시 뜨는 확인 팝업을 다른 서비스 팝업 디자인과 일관되게 맞추기를 요청했다.

## 확인한 사실

- 삭제 버튼은 `hx-confirm`만 사용해 브라우저 기본 확인 팝업으로 표시될 수 있었다.
- shell에는 수동 라우팅과 업무 완료에 쓰는 커스텀 확인 모달이 이미 구현되어 있었다.

## 해결 방법

- 삭제 버튼에 `data-mail-delete-button` 식별자를 추가해 기존 HTMX confirm 인터셉터가 같은 커스텀 모달을 열도록 했다.
- 삭제 액션 전용 문구, `delete` 아이콘, 위험 강조 색상 variant를 추가했다.
- 후속 보정으로 삭제 모달 상단의 `메일 정리` eyebrow를 숨기고, 빨간색 강조는 삭제 확인 버튼에만 남겼다.
- 기존 수동 라우팅/업무 완료 확인 모달 동작은 유지했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "manual_route_confirm_dialog or email_detail"`: 14 passed.
- 실제 브라우저 검증은 로컬 `uv` 캐시 쓰기 권한 오류로 서버 기동이 막혀 생략했다.

---

# 2026-08-27 - 담당자 메일 확인 상태 즉시 반영

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox, My Work, work item acknowledgement, HTMX refresh |
| 관련 파일 | `app/server.py`, `app/templates/shell.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 담당자 계정으로 Inbox 탭 또는 메일 상세를 열어 본문을 확인하면 `미확인` 상태가 즉시 확인/진행 상태로 전환되고 화면에 바로 표시되기를 요청했다.

## 확인한 사실

- `work_items.acknowledged_at`와 `assigned -> in_progress` 전이는 repository에 이미 구현되어 있었다.
- 상세 조회 경로는 확인 처리를 호출했지만 결과를 버렸고, Inbox 전체 렌더링은 확인 처리 전 목록을 그대로 반환할 수 있었다.
- 메일 행에서 상세만 HTMX 교체하는 경우에는 상세 패널만 갱신되어 목록 배지와 카운트가 즉시 바뀌지 않았다.

## 해결 방법

- 담당자 확인 처리 함수가 갱신된 work item을 반환하게 하고, 최초 확인으로 상태가 바뀐 경우 `work-item-acknowledged` HTMX 이벤트를 응답 헤더에 싣도록 했다.
- Inbox 전체 컨텍스트는 확인 처리 후 목록을 재조회해 같은 렌더링 안에서 상태 배지와 필터 결과가 최신 상태를 반영하게 했다.
- shell은 `work-item-acknowledged` 이벤트를 받으면 Inbox 행, My Work/담당자 화면, Monitoring 행, Dashboard 관련 조각과 통계를 현재 필터 기준으로 즉시 새로고침한다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "acknowledge or acknowledged or shell_refreshes_current_inbox_after_manual_assignment_completed"`: 4 passed.
- `uv run pytest tests/test_mail_decision_ui.py`: 187 passed.

---

# 2026-08-27 - 업무 진행 상태 색상 구분

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox, Dashboard, My Work, work status visual state |
| 관련 파일 | `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 진행 상태 색깔이 모두 초록색으로 보여 상태별 구분이 어렵다고 지적했다.

## 확인한 사실

- 메일 목록과 My Work는 `row-status {{ state }}`로 상태 class를 렌더링하고 있었다.
- CSS에는 업무 실행 상태인 `in_progress`, `responded`의 색상 규칙이 없고, 기본 `.row-status` 색이 초록색이라 완료처럼 보였다.

## 해결 방법

- `assigned`/`auto_assigned`, `in_progress`, `responded`, `completed`/`forwarded`에 서로 다른 색상 규칙을 명시했다.
- 색상 규칙이 빠지지 않도록 CSS 회귀 테스트를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "work_status_rows_define_distinct_visual_tones or mail_rows_template_renders_work_status_before_classification_state"`: 2 passed.

---

# 2026-08-27 - 자동 배정 후 미전달 보정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Mail Decision auto assignment, routing delivery, Dashboard delivery state |
| 관련 파일 | `app/repositories/postgres_routing_repository.py`, `app/services/mail_decision_routing_service.py`, `app/services/postgres_mail_service.py`, `tests/test_mail_decision_routing_service.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 배정 완료 상태인데 전달 상태가 `미전달`로 남는 이유를 지적했다.
- 의도는 UI 변경이 아니라, 수동으로 누르던 전달 작업이 배정 완료 후 자동으로 실행되도록 하는 것이다.

## 확인한 사실

- 자동 전달 생성이 `provider == synthetic` 조건에 묶여 일반 자동 배정에는 적용되지 않았다.
- 이미 이전 상태로 저장된 `auto_assign + assigned + 미전달` row는 새 persist 경로를 다시 타지 않아 계속 미전달로 남을 수 있었다.

## 해결 방법

- `auto_assign`이면 provider와 무관하게 수동 전달과 같은 `manual_route_forward` sent notification을 생성하고 routing assignment를 `forwarded`로 전이하도록 했다.
- 메일 목록 조회 전에 기존 `auto_assign + assigned + no sent notification` row를 찾아 같은 자동 전달 보정을 수행하도록 했다.

## 검증

- `uv run pytest tests/test_demo_seed_service.py tests/test_mail_decision_routing_service.py tests/test_mail_decision_ui.py`: 201 passed.

---

# 2026-08-27 - Inbox 진행 상태 라벨 제거

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox, work status filter |
| 관련 파일 | `app/templates/views/inbox.html` |

## 요청 또는 배경

- 사용자는 Inbox 탭 상단의 `진행상태` 텍스트 영역 제거를 요청했고, 빠르게 마무리해 달라고 했다.

## 해결 방법

- Inbox 진행 상태 필터의 보이는 라벨만 제거했다.
- hidden label과 `aria-label`은 유지해 필터 접근성과 동작 계약은 바꾸지 않았다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k inbox_context`: 3 passed.

---

# 2026-08-27 - 데모 자동 전달 의미 정정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode, Mail Decision auto assignment, routing delivery |
| 관련 파일 | `app/repositories/postgres_routing_repository.py`, `app/services/mail_decision_routing_service.py`, `app/services/postgres_mail_service.py`, `app/services/demo_mail_service.py`, `app/templates/views/dashboard.html`, `app/templates/partials/mail_rows.html`, `tests/test_mail_decision_routing_service.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 UI를 바꾸라는 뜻이 아니라, 수동 버튼을 눌러야만 라우팅되는 흐름을 요청 없이 자동 전달되도록 바꾸라는 의미였다고 정정했다.

## 해결 방법

- 직전 UI 표시 변경과 Dashboard 강제 1초 refresh 변경을 원래 구조로 되돌렸다.
- synthetic/demo Mail Decision 자동 배정 완료 시 수동 버튼이 만들던 `manual_route_forward` notification을 backend에서 자동 생성하고 즉시 `sent`로 기록하도록 보완했다.
- 자동 전달 notification에는 메일 제목과 본문 preview를 함께 저장하고, routing assignment는 `forwarded`로 전이한다.

## 검증

- `uv run pytest tests/test_demo_seed_service.py tests/test_mail_decision_routing_service.py tests/test_mail_decision_ui.py`: 200 passed.

---

# 2026-08-27 - 데모 자동 전달 및 Dashboard 즉시 갱신 보완

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode, automatic routing delivery, Dashboard Mail Streams refresh |
| 관련 파일 | `app/repositories/postgres_routing_repository.py`, `app/services/mail_decision_routing_service.py`, `app/services/postgres_mail_service.py`, `app/services/demo_mail_service.py`, `app/services/demo_seed_service.py`, `app/templates/views/dashboard.html`, `app/templates/partials/mail_rows.html`, `tests/test_demo_seed_service.py`, `tests/test_mail_decision_routing_service.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 데모모드에서 자동 전달이 실제로 되지 않고, Dashboard의 상태·업무 유형·담당자·자동 라우팅 상태 변경이 즉시 반영되지 않는다고 지적했다.
- 빠르게 마무리해 달라고 요청했다.

## 해결 방법

- synthetic/demo Mail Decision 자동 배정이 완료되면 `routing_assignments`를 `forwarded`까지 자동 전이하는 repository 경로를 추가했다.
- 데모 fixture와 PostgreSQL 데모 seed도 자동 라우팅 완료 상태가 실제 전달 완료(`forwarded_at`)까지 포함하도록 정렬했다.
- 자동 배정 후 전달된 row는 수동 전달이 아니라 `자동 라우팅`으로 표시되도록 label/status를 분리했다.
- Dashboard Mail Streams row 영역에 1초 HTMX 갱신을 추가해 상태·업무 유형·담당자·자동 라우팅 컬럼 변경이 바로 반영되도록 했다.

## 검증

- `uv run pytest tests/test_demo_seed_service.py tests/test_mail_decision_routing_service.py tests/test_mail_decision_ui.py`: 200 passed.

---

# 2026-08-27 - 데모모드 자동 라우팅 상태 전환

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode, Dashboard Mail Streams, Mail Decision Run, routing assignments |
| 관련 파일 | `app/services/demo_mail_service.py`, `app/services/demo_seed_service.py`, `app/templates/views/dashboard.html`, `app/templates/partials/mail_rows.html`, `tests/test_demo_seed_service.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 데모모드에서 수동 라우팅을 요구하지 않고, 라우팅에 필요한 처리가 완료되면 자동으로 라우팅되도록 변경해 달라고 요청했다.
- 토큰 낭비 없이 최적 범위로 진행해 달라고 요청했다.

## 확인한 사실

- 데모 fixture와 PostgreSQL 데모 시드는 Mail Decision Run 내부 `routing_decision`에는 `auto_assign`을 저장하고 있었지만, 외부 라우팅 상태는 `forwarded`와 수동 전달 `sent`로 고정되어 있었다.
- 이 때문에 데모 화면은 자동 배정 결과가 있음에도 수동 전달이 완료된 것처럼 표시했다.

## 해결 방법

- 파일 기반 데모 서비스의 row와 Mail Decision Run 상태를 `auto_assigned`로 바꾸고, routing assignment 상태는 `assigned`로 정렬했다.
- PostgreSQL 데모 시드도 `mail_decision_runs.status/state_json.status = auto_assigned`, `routing_assignments.status = assigned`, `forwarded_at = NULL` 계약으로 변경했다.
- 데모 Dashboard Mail Streams에서는 수동 `/route-manual` POST 버튼 대신 비활성 자동 라우팅 상태 버튼을 표시하고, 컬럼 제목도 데모모드에서 `자동 라우팅`으로 바꿨다.
- 운영/Gmail 모드의 기존 수동 라우팅 버튼과 pending/failed/sent 상태 처리는 유지했다.

## 검증

- `uv run pytest tests/test_demo_seed_service.py tests/test_mail_decision_ui.py`: 193 passed.
- `uv run pytest tests/test_demo_seed_service.py tests/test_mail_decision_ui.py -k "demo or manual_route or manual_assignment or auto_assigned or dashboard_mail_rows"`: 39 passed.

## 남은 리스크와 후속 작업

- 실제 실행 중인 데모 DB가 이미 시드되어 있으면 `load_demo_seed_postgres` 또는 개발 환경 재시작 시 새 상태가 반영된다.

---

# 2026-08-27 - 필터 하이라이트 슬라이드 애니메이션 및 Mail Streams 유형 필터 UI 통일

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard, Inbox, Mail Streams, status/category filters |
| 관련 파일 | `app/templates/views/dashboard.html`, `app/templates/views/inbox.html`, `app/templates/partials/category_filter_chips.html`, `app/templates/partials/dashboard_distribution.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Inbox와 Dashboard의 진행 상태 필터에서 선택된 상태가 하이라이트되어야 하고, 하이라이트 전환이 슬라이드 애니메이션으로 보여야 한다고 요청했다.
- Dashboard Mail Streams의 메일 유형별 필터 UI도 같은 디자인으로 통일해 달라고 요청했다.

## 확인한 사실

- 진행 상태 버튼은 활성 상태 텍스트만 바뀌고 이동하는 하이라이트 레이어가 없었다.
- Dashboard Mail Streams의 유형 필터는 별도 chip 스타일과 인라인 스타일 스크립트를 사용해 진행 상태 필터와 시각적으로 달랐다.
- 모바일 Dashboard에서는 고정 viewport overflow 때문에 하단 필터 영역 접근성이 떨어질 수 있었다.

## 해결 방법

- Inbox와 Dashboard 진행 상태 필터에 공통 `.mail-status-filter-highlight` 레이어를 추가하고, 활성 버튼 위치와 폭을 CSS 변수로 계산해 슬라이드 전환되도록 했다.
- Dashboard Mail Streams 유형 필터를 동일한 segmented filter 구조로 바꾸고, 유형 필터 상태 갱신도 shell 전역 스크립트로 통합했다.
- 기존 Dashboard distribution partial의 중복 유형 필터 스크립트와 chip 전용 인라인 색상 구조를 제거했다.
- 모바일 Dashboard에서 필터 컨트롤이 viewport 밖으로 밀리지 않도록 헤더/컨트롤 래핑과 overflow 규칙을 조정했다.

## 검증

- Playwright로 `http://127.0.0.1:8000/`에서 Dashboard 진행 상태, Dashboard 유형 필터, Inbox 진행 상태 클릭 후 활성 텍스트와 하이라이트 위치 변경을 확인했다.
- 모바일 390px 폭에서 Dashboard 진행 상태 필터 클릭과 하이라이트 표시를 확인했다.
- `git diff --check`: 통과.
- 호스트 pytest는 PostgreSQL `127.0.0.1:5432` 연결 실패로 전체 관련 묶음 실행이 중단되었고, 컨테이너에는 `pytest`가 없어 컨테이너 테스트는 실행할 수 없었다.

## 남은 리스크와 후속 작업

- 실제 DB 의존 UI 렌더 테스트는 PostgreSQL 테스트 환경이 준비된 상태에서 재실행이 필요하다.

---

# 2026-08-27 - 진행 상태 필터 가로 영역 재배치

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard, Inbox, work status filter, layout |
| 관련 파일 | `app/templates/views/dashboard.html`, `app/templates/views/inbox.html`, `app/static/app.css` |

## 요청 또는 배경

- 사용자는 Inbox 탭과 Dashboard 탭의 새 업무 진행 상태 영역이 기존 가로 단 영역에서 벗어나지 않도록 다른 영역 크기를 조정해 달라고 요청했다.

## 확인한 사실

- 직전 수정은 상태 버튼 노출을 보장하려고 진행 상태 필터를 별도 줄로 분리했다.
- 사용자가 원하는 배치는 별도 줄이 아니라 기존 검색/카테고리 또는 Mail Streams 헤더의 가로 컨트롤 영역 안에 유지하는 것이다.

## 해결 방법

- Inbox는 검색창, 카테고리 select, 진행 상태 버튼 그룹이 같은 `.inbox-filter-row` 안에 들어가도록 되돌렸다.
- Dashboard는 진행 상태 버튼 그룹을 Mail Streams `panel-head`의 `.dashboard-mail-controls` 안으로 다시 넣었다.
- 검색창과 카테고리 영역 폭, Dashboard 카테고리 칩 영역의 flex 폭을 줄여 진행 상태 버튼이 같은 가로 단 안에서 보이도록 조정했다.
- 템플릿에는 상태 옵션 fallback을 둬 컨텍스트 누락 시에도 `전체` 외 상태 버튼이 렌더링되도록 했다.

## 검증

- `UV_CACHE_DIR=/tmp/uv-cache uv run python ...`: Inbox와 Dashboard 렌더 결과에서 각각 `data-mail-status-target` 버튼 5개 확인.
- `git diff --check`: 통과.
- 컨테이너에는 `pytest`가 설치되어 있지 않아 `docker compose exec web python -m pytest ...`는 실행 불가했다.

## 남은 리스크와 후속 작업

- 실제 브라우저 픽셀 검증은 수행하지 않았다. 렌더 구조와 CSS diff 기준으로 같은 가로 컨트롤 영역 내 배치를 확인했다.

---

# 2026-08-27 - 진행 상태 필터 버튼 UI 수정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard, Inbox, work status filter, UI consistency |
| 관련 파일 | `app/templates/views/dashboard.html`, `app/templates/views/inbox.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Dashboard와 Inbox에 추가한 진행 상태 필터가 `전체 상태`만 보이고 다른 상태를 선택할 수 없다고 보고했다.
- 또한 필터 디자인을 서비스 디자인과 일관되게 만들어 달라고 요청했다.

## 확인한 사실

- 새 필터는 일반 select로 추가되어 기존 My Work/Monitoring의 버튼형 상태 필터와 시각 패턴이 달랐다.
- 템플릿에서 dict 값을 `option.value`로 접근하면 `value` 이름 충돌 가능성이 있어 상태 옵션 렌더링에 취약하다.

## 해결 방법

- Dashboard와 Inbox의 상태 select를 제거하고, 기존 업무 큐/상태 버튼 톤에 가까운 segmented 상태 버튼 그룹으로 바꿨다.
- 상태 값은 hidden `status` input에 저장하고 버튼 클릭 시 JS가 값을 갱신한 뒤 Dashboard Mail Streams 또는 Inbox 패널을 다시 로드하도록 했다.
- 템플릿 상태 옵션 접근은 `option['value']`로 명시해 dict key 접근이 안전하게 동작하도록 했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "inbox_context or dashboard_mail_rows_route_filters_by_work_status or dashboard_stats_cards_filter_mail_stream_rows or shell_refreshes_current_inbox_after_manual_assignment_completed or dashboard_manual_route_poll"`: 6 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 시각 검증은 수행하지 않았다. 렌더링/상태 파라미터/HTMX URL 연결은 테스트로 확인했다.

---

# 2026-08-27 - Dashboard와 Inbox 진행 상태 필터 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard, Inbox, Mail Streams, work status filter |
| 관련 파일 | `app/server.py`, `app/templates/views/dashboard.html`, `app/templates/views/inbox.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Dashboard 탭과 Inbox 탭의 메일 목록에서 완료, 진행중 같은 진행 상태 기준 필터링을 추가해 달라고 요청했다.

## 확인한 사실

- 업무 수행 상태는 기존 `work_status`와 `status_matches_work_filter()`에서 이미 `assigned`, `in_progress`, `responded`, `completed` 등으로 다뤄지고 있었다.
- My Work/Monitoring은 같은 상태 기준 필터를 이미 사용하고 있었으므로 Dashboard와 Inbox 목록에도 같은 상태 키와 한국어 라벨을 재사용하는 것이 일관적이다.
- Inbox는 필터 후 목록 밖으로 밀려난 선택 메일을 계속 상세에 보여주지 않도록 선택 UID를 필터 결과 안에서 다시 계산해야 한다.

## 해결 방법

- 공통 진행 상태 필터 옵션을 추가하고 Dashboard Mail Streams와 Inbox 검색/업무유형 필터 옆에 상태 select를 배치했다.
- `/ui/mail-rows`, `/ui/inbox`, `/`, `/api/ui-state`가 `status` 파라미터를 받아 목록 갱신과 polling 상태 비교에 같은 필터를 적용하도록 했다.
- Dashboard는 통계와 차트는 전체 기준을 유지하고 Mail Streams 행만 상태 필터로 제한했다.
- Inbox는 상태 필터 변경 시 선택 메일이 현재 목록에 없으면 첫 번째 필터 결과로 선택을 재설정하도록 했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "inbox_context or dashboard_mail_rows_route_filters_by_work_status or dashboard_stats_cards_filter_mail_stream_rows or shell_refreshes_current_inbox_after_manual_assignment_completed or dashboard_manual_route_poll"`: 6 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 클릭/시각 검증은 이번 범위에서 수행하지 않았다. HTMX 파라미터 유지와 서버 필터링은 테스트로 확인했다.

---

# 2026-08-27 - 데모 담당자 Dashboard 업무 상태 분포 조정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode, assignee Dashboard, work_items, seed writer |
| 관련 파일 | `app/services/demo_seed_service.py`, `app/repositories/postgres_seed_writer.py`, `tests/test_demo_seed_service.py`, `docs/development/demo-data-standard.md` |

## 요청 또는 배경

- 사용자는 데모모드 담당자 계정 기준 Dashboard 탭에서 기한 초과 데이터 비중이 과도하므로, 가짜 데이터인 만큼 데모용 비중을 조정해 달라고 요청했다.

## 확인한 사실

- 담당자 Dashboard의 기한 초과는 `work_items.due_at`과 현재 시각으로 계산된다.
- 기존 demo seed는 `routing_assignments`만 만들고 `work_items`는 schema backfill 또는 과거 런타임 상태에 맡겨, 재적재 후에도 오래된 due 값이 남을 수 있었다.
- 실제 로컬 DB에는 과거 synthetic `mail_decision_policy` 배정이 남아 있어 처음 추가한 `work_items` seed가 FK 제약에서 실패했다.

## 해결 방법

- `DemoSeedService`가 `work_items`를 함께 생성하도록 추가했다.
- 업무 상태는 고정 UUIDv5 hash로 `assigned`, `in_progress`, `responded`, `completed`가 섞이게 하고, active 업무 중 일부만 overdue가 되도록 했다.
- `PostgresSeedWriter`가 `work_items`를 `email_message_id` 기준으로 갱신하게 했다.
- Gmail 또는 사용자 편집 배정은 보존하되, provider가 `synthetic`인 fake 메일의 라우팅 배정은 demo seed가 다시 소유하도록 허용했다.
- 데모 데이터 기준 문서에 `work_items` 분포가 시연용 합성 상태이며 SLA/업무량 성과 지표가 아니라고 명시했다.

## 검증

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_demo_seed_service.py`: 9 passed.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.tools.export_demo_seed --check`: `work_items=1213` 포함 통과.
- `docker compose exec web python -m app.tools.load_demo_seed_postgres`: `work_items=1213` written 확인.
- PostgreSQL 쿼리로 synthetic 김민수 기준 `assigned=255`, `in_progress=140`, `responded=79`, `completed=71`, overdue `26/545` 확인.

## 남은 리스크와 후속 작업

- `tests/test_mail_decision_ui.py -k assignee_login_dashboard_context_uses_only_assigned_work`는 현재 host test 환경에서 PostgreSQL 접속 단계가 실패해 assertion까지 가지 못했다. 이번 변경 대상인 seed 생성/적재 경로는 별도 검증했다.

---

# 2026-08-27 - 메일 상태 변경 즉시 화면 반영

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | UI sync, Inbox, Dashboard, Monitoring, Mail Decision status |
| 관련 파일 | `app/server.py`, `app/templates/shell.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 상태, 업무 유형, 담당자, 전달 상태 등의 변경이 있을 때 화면에 즉시 반영되도록 요청했다.

## 확인한 사실

- 기존 `/api/ui-state` digest는 메일 개수와 서비스 버전만 반영했다.
- 따라서 Mail Decision 완료, 업무 유형 변경, 담당자 배정, forwarding 상태 변경처럼 row 수가 변하지 않는 업데이트는 polling에서 변경 없음으로 판단됐다.
- Inbox detail 갱신 비교 키도 서버는 `email_detail`, 클라이언트는 `detail`을 보고 있어 상세 패널 변경 감지가 빠질 수 있었다.
- Monitoring view는 `currentUiView()` polling 대상에 포함되지 않아 자동 처리 상태 변경을 주기적으로 감지하지 않았다.

## 해결 방법

- `/api/ui-state`를 상태 관련 row 필드 기반 digest로 변경했다.
- `processing_status`, `classification`, `summary`, `routing_display`, `routing_status`, `routing_forwarded_at`, `work_status`, `mail_decision_status`, 시작/완료 시각을 digest에 포함했다.
- 선택된 메일 상세는 별도 `detail`/`email_detail` digest를 만들도록 했다.
- Monitoring도 `ui-state` polling 대상에 포함하고, 검색/카테고리/status 필터를 유지한 채 `#opsRows`를 갱신하도록 연결했다.
- 메일 상태 화면의 polling 간격을 1.5초로 줄였다. 문서 탭은 기존처럼 10초 간격을 유지한다.

## 검증

- `python -m py_compile app/server.py`: 통과.
- `uv run pytest tests/test_mail_decision_ui.py`: 180 passed.
- 컨테이너 재시작 후 `ui_state()` 런타임 호출로 `mail_rows`, `detail`, `monitoring_rows` digest 생성 확인.
- `uv run pytest tests/test_mail_decision_ui.py tests/test_document_type_navigation.py` 실행 시 문서 탭 기존 기대값 불일치 2건이 함께 실패했다. 이번 변경 파일의 테스트는 통과했다.

## 남은 리스크와 후속 작업

- 1.5초 polling은 즉시성 확보를 위한 균형점이다. 운영 부하가 커지면 상태 digest endpoint 비용을 더 줄이거나 서버 push/SSE로 전환할 수 있다.
- 문서 탭 테스트 2건은 현재 템플릿과 기대값이 맞지 않는 별도 이슈로 남아 있다.

---

# 2026-08-26 - 데모 신규 수신 실제 처리 경로 복원

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode, Settings, processing jobs, Mail Decision worker |
| 관련 파일 | `app/server.py`, `app/services/postgres_email_analysis_worker.py`, `tests/test_mail_decision_ui.py`, `tests/test_postgres_email_analysis_worker.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 데모모드 확인은 실제 동작 검증이어야 하며, 데이터만 가짜일 뿐 처리 방식이 실제와 달라지면 안 된다고 지적했다.
- 직전 구현은 새 메일에 기존 데모 결과를 즉시 복제하는 fast path였기 때문에 신규 수신 검증 목적에 맞지 않았다.

## 확인한 사실

- `demo_fast_receive` 방식은 새 `email_messages` row를 만들지만 분석 결과, Mail Decision run, routing 결과를 기존 메일에서 복제했다.
- 사용자가 원하는 검증 기준은 결과 복제가 아니라 신규 메일 row에 대해 실제 Mail Decision worker가 실행되는 것이다.

## 해결 방법

- 결과 복제 fast path를 제거했다.
- 신규 데모 메일 생성 시 `processing_jobs`에 `analysis_type='mail_decision'`, `pipeline_version='actual-mail-decision-v1'`인 실제 처리 job을 등록하도록 변경했다.
- 버튼 POST는 즉시 리다이렉트하되, 방금 만든 메일의 job ID만 찾아 백그라운드 스레드에서 `PostgresEmailAnalysisWorker.run_one(job_id)`로 실제 Mail Decision 경로를 실행하게 했다.
- `PostgresEmailAnalysisWorker`가 `mail_decision` job을 claim하고 `_run_mail_decision()`으로 전체 분석, facts, retrieval, decision, routing 저장 경로를 타도록 확장했다.

## 검증

- `python -m py_compile app/server.py app/services/postgres_email_analysis_worker.py`: 통과.
- `uv run pytest tests/test_mail_decision_ui.py tests/test_postgres_email_analysis_worker.py`: 179 passed.
- 웹 컨테이너 재시작 후 assignee 세션과 demo display mode 쿠키로 실제 POST 호출: 303, 약 0.02초.
- 생성된 신규 메일 `19b0c683-9dad-44b2-86a6-8f62102dd895`는 `processing_jobs.status='success'`, `mail_decision_runs.status='completed'`, routing `assigned`, 담당자 `김민수`로 확인됐다.
- 같은 assignee 세션으로 리다이렉트된 Inbox URL 접근: 200.

## 남은 리스크와 후속 작업

- 실제 처리 경로를 사용하므로 LLM/runtime 상태에 따라 완료 시간은 달라질 수 있다. 버튼 응답은 즉시 반환되지만 결과 완료는 백그라운드 worker 실행 완료 시점에 반영된다.
- 임시 데모 수신 버튼 제거 시 이 demo-only job 등록 및 접근 예외도 함께 제거해야 한다.

---

# 2026-08-26 - 데모 신규 수신 즉시 결과 표시

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode, Settings, Inbox, Mail Decision, routing |
| 관련 파일 | `app/server.py`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 `최신 메일 다시 수신` 버튼으로 신규 메일을 받은 뒤 대기 상태가 너무 길며, 신규 수신 시 즉시 병렬 처리된 것처럼 빠르게 결과가 표시되어야 한다고 요청했다.

## 확인한 사실

- 실제 Mail Decision 실행을 버튼 요청 안에서 동기 처리하면 결과는 생성되지만 응답에 약 58초가 걸려 데모 확인 흐름에 맞지 않았다.
- 기존 pending job 등록 방식은 새 메일을 바로 볼 수 있게 하지만, `미분류`/대기 상태가 먼저 노출되어 사용자가 원하는 “신규 수신 직후 완료 결과 확인”과 맞지 않았다.

## 해결 방법

- 임시 데모 수신 기능에서 pending job을 만들지 않고, 새 메일 생성 직후 최신 원본 데모 메일의 현재 분석 결과, 카테고리, Mail Decision run, facts, routing, work item을 새 메일 ID로 즉시 복제하도록 변경했다.
- 새 처리 이력은 `processing_jobs.status='success'`, `pipeline_version='demo-fast-receive-v1'`로 남겨 데모 fast path임을 구분했다.
- 버튼 라우트 테스트는 신규 메일 생성 후 즉시 처리 함수가 호출되는지 검증하도록 보강했다.

## 검증

- `python -m py_compile app/server.py`: 통과.
- `uv run pytest tests/test_mail_decision_ui.py`: 178 passed.
- 웹 컨테이너 재시작 후 assignee 세션과 demo display mode 쿠키로 실제 POST 호출: 303, 약 0.03초.
- 리다이렉트된 Inbox URL 접근: 200.
- 생성된 신규 메일 `971957e7-876a-4e53-9466-0b274f695e3a`는 `문의`, Mail Decision `completed`, routing `assigned`, 담당자 `김민수`로 즉시 표시됐다.

## 남은 리스크와 후속 작업

- 이 경로는 데모 검증을 위한 fast path이며 실제 운영 LLM/worker 병렬 처리 최적화가 아니다. 임시 수신 버튼 제거 시 함께 제거해야 한다.

---

# 2026-08-26 - 데모 신규 수신 메일 assignee 접근 403 수정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode, assignee access, Inbox, PostgreSQL mail row |
| 관련 파일 | `app/server.py`, `app/services/postgres_mail_service.py`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 `최신 메일 다시 수신` 버튼 후 `{"detail":"본인에게 배정된 업무만 확인할 수 있습니다."}`가 표시된다고 보고했다.

## 확인한 사실

- 로그상 버튼 POST 자체는 303으로 성공했고, 새 메일 생성 후 `/?view=inbox&email_uid=...` 리다이렉트에서 403이 발생했다.
- 신규 수신건은 의도적으로 미배정 상태라 assignee 계정의 `ensure_can_view_work_email()` 가드에서 차단됐다.
- Monitoring도 assignee 계정에서는 본인 배정 row만 보이도록 필터링하므로, 미배정 신규 수신건을 직접 검토하려면 이 임시 데모 수신건에 대한 좁은 접근 예외가 필요했다.

## 해결 방법

- PostgreSQL-backed mail row에 `provider_message_id`를 포함시켰다.
- `provider_message_id`가 `demo-duplicate-latest-`로 시작하는 임시 데모 신규 수신건은 assignee 권한 필터와 상세 접근 가드에서 허용했다.
- 담당자 배정 데이터는 만들지 않고, 실제 미배정 신규 메일 상태는 유지했다.

## 검증

- `python -m py_compile app/server.py app/services/postgres_mail_service.py`: 통과.
- `uv run pytest tests/test_mail_decision_ui.py`: 178 passed.
- assignee 사용자 세션으로 실제 POST 호출: 303.
- 같은 assignee 세션으로 리다이렉트된 Inbox URL 접근: 200.
- 생성된 신규 메일 `1b7fd7f6-5955-4380-8cf9-d9ae4463a8bf`는 `미분류`, Mail Decision 없음, routing 없음이며 `classification`/`executive_summary` pending job만 등록됐다.

## 남은 리스크와 후속 작업

- 접근 예외는 `demo-duplicate-latest-` provider id를 가진 임시 데모 검증 메일에만 적용된다. 임시 기능 제거 시 함께 제거해야 한다.

---

# 2026-08-26 - 데모 신규 수신 버튼 500 오류 수정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode, Settings, PostgreSQL JSONB insert |
| 관련 파일 | `app/server.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Settings의 `최신 메일 다시 수신` 버튼 클릭 시 Internal Server Error가 발생한다고 보고했다.

## 확인한 사실

- 웹 로그에서 `/ui/settings/demo/receive-latest-duplicate` 처리 중 PostgreSQL `jsonb_build_object(...)` 파라미터 타입 추론 오류가 발생했다.
- 첫 오류는 `could not determine data type of parameter`, 두 번째 오류는 같은 파라미터가 `text`와 `varchar`로 동시에 추론된 `inconsistent types deduced`였다.

## 해결 방법

- `processing_jobs.metadata`와 `email_analysis_results.result_json`에 넣는 파라미터를 `::text`로 명시 캐스팅했다.
- `email_analysis_results.analysis_type`과 `prompt_version` 컬럼 위치의 파라미터는 각각 `::varchar(50)`, `::varchar(100)`로 명시 캐스팅했다.

## 검증

- `python -m py_compile app/server.py`: 통과.
- `uv run pytest tests/test_mail_decision_ui.py -k "demo_duplicate_receive_button or receive_latest_duplicate_demo_mail"`: 2 passed.
- 웹 컨테이너 재시작 후 로그인 쿠키와 `coramail_display_mode=demo` 쿠키로 실제 POST 호출: 303.
- 생성된 신규 메일 `8f919b6a-555e-45a6-abff-4b74523b0fce`는 `미분류`, Mail Decision 없음, routing 없음 상태이며 `classification`/`executive_summary` pending job만 2건 등록됐다.

## 남은 리스크와 후속 작업

- 실제 확인용으로 생성된 `demo-duplicate-latest-%` 메일은 사용자가 직접 검토할 대상이므로 유지했다. 데모 seed reload 시 제거될 수 있다.

---

# 2026-08-26 - 데모 최신 메일 신규 수신 임시 기능

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode, Settings, Inbox, Monitoring, PostgreSQL demo seed |
| 관련 파일 | `app/server.py`, `app/templates/views/settings.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 데모 모드에서 가장 최신 메일 1건과 같은 메일이 다시 신규 메일로 수신됐다고 가정하고 직접 검토할 수 있는 임시 기능을 요청했다.
- 사용자는 Codex가 결과를 검토하는 것이 아니라, 신규 메일 수신 부분을 위한 임시 기능만 구현하라고 정정했다.
- 사용자는 업무유형과 담당자가 이미 정해진 상태로 들어오면 안 되며, 실제 신규 메일처럼 다시 돌릴 수 있어야 한다고 정정했다.
- 신규 메일이더라도 데모의 최근 7일 기준은 2026-08-12로 유지돼야 한다고 요청했다.

## 확인한 사실

- 데모 Compose는 PostgreSQL-backed demo source를 사용한다.
- `email_messages`는 같은 계정에서 `provider_message_id`가 같으면 기존 메일을 갱신하므로, 같은 본문을 신규 수신으로 보려면 새 provider id와 UUID가 필요하다.
- Dashboard 데모 기준일은 데모 row 날짜의 최댓값을 사용하므로, 새 수신건을 실제 현재 시각으로 넣으면 최근 7일 범위가 2026-08-12에서 밀릴 수 있다.

## 해결 방법

- Settings 화면에 `데모 메일 수신` 임시 패널과 `최신 메일 다시 수신` 버튼을 추가했다.
- 버튼은 `/ui/settings/demo/receive-latest-duplicate`로 POST하고, 성공 시 새 메일이 선택된 Inbox로 이동한다.
- 복제 기준 메일은 `demo-duplicate-latest-%` provider id를 제외한 최신 synthetic demo mail로 제한해 복제본의 복제본을 만들지 않는다.
- 새 수신건은 제목, 본문, 수신자, 첨부 참조, content hash만 복제하고 업무유형, 요약 성공 결과, Mail Decision Run, 담당자, work item은 복제하지 않는다.
- 새 수신건의 `sent_at`/`received_at`은 원본 최신 메일보다 1분 뒤로 설정해 2026-08-12 데모 날짜 범위 안에 남긴다.
- `classification`과 `executive_summary`는 pending job과 pending analysis result만 생성해 사용자가 직접 실행 흐름을 확인할 수 있게 했다.
- 구현 중 잘못 넣었던 완료 상태 수동 복제 row는 `provider_message_id='demo-duplicate-latest-20260826-verify'` 기준으로 삭제했다.

## 검증

- `python -m py_compile app/server.py`: 통과.
- `uv run pytest tests/test_mail_decision_ui.py -k "demo_duplicate_receive_button or receive_latest_duplicate_demo_mail"`: 2 passed.
- 웹 컨테이너를 재시작했고 `/api/health`가 200을 반환하는 것을 확인했다.

## 남은 리스크와 후속 작업

- 이 기능은 데모 검증용 임시 도구이므로 운영 Gmail 수신 경로와 혼동하지 않도록 제거 시점을 별도로 정해야 한다.
- 사용자가 직접 버튼을 눌러 생성된 `demo-duplicate-latest-%` 메일은 데모 seed reload 시 제거될 수 있다.

---

# 2026-08-26 - Inbox 업무번호 복사와 Mail Decision 중복 제거

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox, Mail Overview, Mail Decision, clipboard toast |
| 관련 파일 | `app/templates/partials/email_detail.html`, `app/templates/partials/mail_decision_panel.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Inbox 탭에서 업무번호가 Mail Overview와 Mail Decision에 중복 표시되므로 Mail Decision에서는 숨기고, Mail Overview의 업무번호를 클릭하면 클립보드에 복사되며 화면 중간 하단에 짧은 복사 알림이 뜨게 해 달라고 요청했다.

## 확인한 사실

- Mail Overview는 `email_detail.html`에서 `classification.business_refs`를 표시하고 있었다.
- Mail Decision 요약 표도 `mail_decision_panel.html`에서 같은 업무번호 첫 값을 표시해 중복이 발생했다.
- 상세 패널은 HTMX로 교체되므로 클릭 동작은 개별 버튼 바인딩보다 document-level 위임 방식이 안전하다.

## 해결 방법

- Mail Decision 요약 표에서 업무번호 행을 제거했다.
- Mail Overview 업무번호 pill을 `button`으로 바꾸고 `data-copy-business-ref` 값을 부여했다.
- shell 공통 JS에 클립보드 복사, fallback copy, 하단 중앙 toast 표시/자동 숨김 동작을 추가했다.
- 업무번호 버튼 hover/focus와 toast 스타일을 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py::test_email_detail_polishes_demo_summary_key_request_for_screenshots tests/test_mail_decision_ui.py::test_mail_decision_panel_deduplicates_business_refs_for_display tests/test_mail_decision_ui.py::test_shell_installs_search_fallback_when_htmx_cdn_is_unavailable`: 3 passed.
- `uv run pytest tests/test_mail_decision_ui.py`: 175 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 clipboard permission 동작은 환경별 차이가 있을 수 있으나, 보안 컨텍스트에서는 `navigator.clipboard.writeText`, 그 외에는 `document.execCommand("copy")` fallback을 사용한다.

---

# 2026-08-26 - My Work 헤더 담당자 이름 표시

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | My Work, assignee work header |
| 관련 파일 | `app/templates/views/assignee_work.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 My Work 탭 헤더에서 이메일 주소 위에 보이는 `My Work` 문구 대신 해당 담당자 이름이 보이게 해 달라고 요청했다.

## 확인한 사실

- My Work 진입 경로는 `assignee_work_context()`에 `work_title="My Work"`를 넘기고 있었다.
- `views/assignee_work.html`의 헤더는 `assignee_work_title`을 `selected.name`보다 먼저 사용해, 담당자 이름이 있어도 `My Work`가 표시됐다.

## 해결 방법

- My Work view에서는 선택된 담당자 이름이 있으면 헤더 제목으로 우선 사용하도록 템플릿의 제목 계산만 좁게 변경했다.
- 담당자 이메일, My Work 네비게이션 라벨, Assignments 기본 헤더 동작은 유지했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "my_work_email_drawer_renders_detail_side_tab or assignee_work_template_renders_selected_workload or shell_replaces_assignments_with_my_work_for_assignee_login"`: 3 passed.

## 남은 리스크와 후속 작업

- 별도 리스크 없음.

---

# 2026-08-26 - My Work/Monitoring 브라우저 클릭 검증 보강

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Playwright e2e, My Work drawer, Monitoring inspector, mobile click targets |
| 관련 파일 | `package.json`, `package-lock.json`, `playwright.config.ts`, `tests/e2e/my-work-monitoring.spec.ts`, `app/static/app.css`, `.gitignore` |

## 요청 또는 배경

- 사용자는 이전에 브라우저 실행 파일이 없어 수행하지 못한 실제 클릭 기반 open/close/Escape/outside-click 및 스크린샷 검증 공백을 해결하고 싶다고 요청했다.
- Browser plugin은 현재 환경에서 사용할 수 없어 Playwright Chromium을 설치해 실제 브라우저 검증 경로를 구성했다.

## 확인한 사실

- 초기 환경에는 Chromium/Playwright 실행 파일이 없었고, workspace sandbox 안에서 Chromium을 실행하면 `sandbox_host_linux.cc` 오류로 브라우저가 시작되지 않았다.
- Playwright Chromium을 설치한 뒤 unsandboxed 실행에서는 데스크톱/모바일 브라우저 테스트가 가능했다.
- 모바일 viewport에서 My Work drawer의 제목 flex 영역과 shell 폭이 콘텐츠 최소 폭을 따라 늘어나 닫기 버튼 hit target이 패널 밖으로 밀리는 문제가 있었다.
- 이메일 본문 iframe의 sandbox 정책 때문에 브라우저가 script 차단 콘솔 메시지를 출력하지만, 이는 의도된 보안 동작이며 앱 오류와 구분해야 한다.

## 해결 방법

- `@playwright/test` 기반 e2e 설정과 My Work/Monitoring smoke 테스트를 추가했다.
- 담당자 세션은 서버 인증 쿠키 서명 방식과 동일하게 생성해 데모 담당자 김민수 화면을 직접 열도록 했다.
- My Work drawer와 Monitoring inspector에 대해 실제 click open, close button click, Escape close, outside-click close, 스크린샷 저장을 데스크톱과 모바일 프로젝트에서 검증한다.
- drawer/inspector shell 폭과 헤더 flex, 닫기 버튼 hit target을 패널 내부로 고정하고 모바일에서는 작업 영역 내부 absolute overlay로 동작하게 조정했다.
- Playwright 산출물인 `test-results/`와 `playwright-report/`를 ignore 처리했다.

## 검증

- `npm run test:e2e:ui-smoke`: 4 passed. Desktop Chromium 및 mobile Chromium에서 My Work drawer와 Monitoring inspector open/close/Escape/outside-click, 스크린샷 저장 확인.
- `uv run pytest tests/test_mail_decision_ui.py -k "monitoring or assignee or work_reply or work_complete"`: 33 passed.
- `git diff --check`: passed.

## 남은 리스크와 후속 작업

- 현재 Codex workspace sandbox에서는 Chromium sandbox 오류가 발생하므로 Playwright 브라우저 검증은 unsandboxed 로컬 실행 또는 승인된 실행 환경이 필요하다.
- Browser plugin 자체는 여전히 환경에 없으며, 이번 변경은 Playwright Chromium fallback을 프로젝트에 추가한 것이다.

---

# 2026-08-26 - 전역 UI 클릭 반응성 개선

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | shell navigation, HTMX request sync, tab/button active state |
| 관련 파일 | `app/templates/shell.html`, `app/static/app.css` |

## 요청 또는 배경

- 사용자는 `coramail_agent` 전반에서 탭 전환과 버튼 클릭이 딜레이 없이 실행되도록 검토 및 개선해 달라고 요청했다.
- 이전 메모리상 전역 애니메이션 확대는 사용자가 원하지 않았고, 탭 지연은 stale runtime 또는 HTMX 중복 요청과 연결된 적이 있어 원인 분리를 우선했다.

## 확인한 사실

- shell의 HTMX와 Chart.js CDN script가 `<head>`에서 동기 로드되어 네트워크가 느리면 초기 렌더와 클릭 핸들러 설치가 늦어질 수 있었다.
- 탭과 주요 필터 버튼은 클릭 직후 일부 상태를 바꾸지만, 같은 target으로 들어가는 이전 HTMX 요청이 늦게 완료될 경우 최신 클릭 화면을 덮을 여지가 있었다.
- Monitoring, Inbox, Search, Chats fragment는 재시작 후 authenticated HTTP 기준 200으로 응답했다.

## 해결 방법

- HTMX script는 `defer`, Chart.js는 `async`로 바꿔 초기 화면 렌더링과 기본 클릭 fallback 설치를 외부 CDN 로드에 덜 묶이게 했다.
- 주요 HTMX target(`#main-panel`, `#email-detail`, `#mailRows`, `#opsRows`, drawer target 등)에 `hx-sync="...:replace"`를 자동 부여해 최신 클릭 요청이 이전 요청을 대체하도록 했다.
- `htmx:beforeRequest`에서 nav, Monitoring/My Work 상태 버튼, 담당자 roster, 업무 row 선택 상태를 즉시 반영하게 했다.
- 탭/row/상태 버튼의 짧은 CSS transition duration을 0ms로 override해 클릭 반응이 애니메이션 때문에 늦어 보이지 않도록 했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `CORAMAIL_DATABASE_URL= CORAMAIL_LOCAL_DEV_DEFAULTS=false .venv/bin/python -m pytest tests/test_mail_decision_ui.py`: 173 passed.
- 최초 UI 테스트 묶음은 DB 기본값이 켜진 현재 shell에서 PostgreSQL 접속 실패로 실패했으며, DB fallback을 끄고 재실행해 관련 UI 테스트를 통과시켰다.
- `docker compose restart web` 후 `/api/health`: 200.
- 로그인 세션의 HTMX fragment 응답: `/ui/monitoring` 200 0.066s, `/ui/inbox` 200 0.247s.
- Playwright Chromium smoke: Monitoring 335ms, Inbox 637ms, Search 408ms, Chats 139ms 안에 화면 전환 완료.
- 빠른 연속 클릭 smoke에서 Monitoring 직후 Search 클릭 시 최종 active 탭과 `data-view`가 모두 `search`로 유지됐다.

## 남은 리스크와 후속 작업

- `app/static/app.css`와 `.gitignore`에 이번 작업 전후로 별도 변경이 함께 존재하므로 커밋 시 반응성 변경과 분리해 staging해야 한다.
- 실제 사용자가 체감하는 지연은 서버 쿼리/LLM 실행 상태에 따라 달라질 수 있으며, 이번 변경은 브라우저 상호작용과 HTMX 요청 경쟁을 줄이는 범위다.

---

# 2026-08-26 - Inbox 업무 액션을 Mail Overview 박스 위로 이동

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox detail, Mail Overview action placement |
| 관련 파일 | `app/templates/partials/email_detail.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 이전 수정에서 `답장`, `업무 완료` 버튼이 Mail Overview 헤더/내부에 들어간 것이 아니라 Mail Overview 박스 바깥의 바로 위에 있어야 한다고 정정했다.

## 해결 방법

- 업무 액션 바를 `mail-overview-panel` 내부에서 제거하고, `analysis-stack` 안에서 Mail Overview 패널 바로 앞의 형제 요소로 이동했다.
- 액션 바는 오른쪽 정렬을 유지하되 별도 박스 스타일 없이 패널 위에 놓이도록 padding을 정리했다.
- 회귀 테스트를 헤더/내부 위치 검증에서 Mail Overview 박스 바깥 위쪽 위치 검증으로 수정했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "work_reply_initiate or inbox_email_detail_places_work_actions or inbox_detail_overview"`: 4 passed.
- `uv run pytest tests/test_mail_decision_ui.py`: 175 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저에서 패널 상단 간격이 기대와 다르면 CSS gap만 추가 조정하면 된다.

---

# 2026-08-26 - Inbox Gmail 회신 버튼과 상세 액션 배치 수정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox detail, Gmail reply initiation, work actions, selected mail header |
| 관련 파일 | `app/server.py`, `app/templates/partials/email_detail.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Inbox 탭에서 `답장` 버튼을 눌러도 아무 일도 일어나지 않는 문제를 해결해 달라고 요청했다.
- Inbox 탭의 Selected Mail 영역에서 휴지통 아이콘은 항상 가장 오른쪽에 있어야 했다.
- `답장`, `업무 완료` 같은 업무 액션은 Mail Overview 상단 영역에 배치해야 했다.

## 확인한 사실

- 기존 회신 버튼은 `hx-post`와 `hx-swap="none"`으로 `/ui/emails/{email_uid}/work/reply-initiate`를 호출하고, 서버는 `204`와 `HX-Redirect`만 반환했다.
- 이 방식은 HTMX 응답 헤더 처리에 의존하므로 사용자가 클릭 후 Gmail 이동을 확인하지 못하면 무반응처럼 보일 수 있었다.
- 기존 상세 헤더에는 휴지통, Gmail 회신, 업무 완료 버튼이 같은 액션 행에 함께 배치되어 있었다.

## 해결 방법

- `/ui/emails/{email_uid}/work/reply-initiate`가 HTMX 요청에는 기존 `HX-Redirect`를 유지하고, 일반 POST에는 Gmail thread URL로 `303` redirect를 반환하게 했다.
- Inbox 상세의 `답장`은 새 탭 form POST로 바꿔 서버에 회신 시작을 기록한 뒤 Gmail thread를 안정적으로 열도록 했다.
- `답장`과 `업무 완료` 버튼을 Mail Overview 패널 헤더 오른쪽으로 이동했다.
- Selected Mail 헤더에는 휴지통 버튼만 남기고 액션 행 폭을 보강해 아이콘이 오른쪽 끝에 유지되게 했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "work_reply_initiate or inbox_email_detail_places_work_actions"`: 3 passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "email_detail or inbox_detail_overview or work_reply_initiate"`: 15 passed.
- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py`: 175 passed.

## 남은 리스크와 후속 작업

- 실제 Gmail 계정과 브라우저 팝업 정책은 유효한 로그인/토큰이 있는 런타임에서 추가로 확인해야 한다.
- 현재 구현은 Gmail 새 탭을 열고 CoRA에는 회신 시작 상태를 기록한다. 실제 SENT 감지는 기존 후속 Gmail sync 계약을 따른다.

---

# 2026-08-26 - My Work와 Monitoring 최종 점검 및 stale 요약 tooltip 정리

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | My Work, Monitoring, assignee scope, ops summary stage tooltip |
| 관련 파일 | `app/server.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 전날 예정 업무 중 `담당자 업무 화면 및 monitoring 화면 최종 점검`을 진행하고 싶다고 요청했다.
- 담당자 계정 화면은 담당자 본인 데이터만 보여야 하고, My Work 상세 drawer와 Monitoring inspector가 실제 HTMX fragment 기준으로 정상 동작해야 했다.

## 확인한 사실

- Docker Compose web, PostgreSQL, Qdrant, Ollama가 실행 중이었고 `/api/health`는 정상 응답했다.
- `admin` 세션의 `/`, `/ui/assignees`, `/ui/monitoring`, Monitoring HTMX fragment는 200으로 렌더링됐다.
- 김민수 담당자 세션의 My Work fragment는 김민수 업무와 상세 열기, Gmail 회신, 업무 완료 액션을 렌더링했고 다른 담당자 roster 이름은 노출하지 않았다.
- 김민수 담당자 세션에서 다른 담당자의 My Work 상세 endpoint는 403을 반환했다.
- Monitoring row scope 자체는 김민수 row로 제한됐지만, 일부 오래된 요약문 문장이 `최서연에게 전달`처럼 현재 담당자와 다른 라우팅 문구를 stage tooltip에 그대로 노출했다.

## 해결 방법

- Monitoring summary stage tooltip/detail은 자유형 요약문 본문이 아니라 `요약문 생성 완료`, `요약문 생성 대기`, `요약문 생성 중`, `요약문 생성 실패` 같은 상태 문구만 표시하게 변경했다.
- 실제 메일/요약 본문은 기존처럼 상세 drawer에서 확인하도록 유지했다.
- stale 요약문에 다른 담당자 이름이 들어 있어도 Monitoring stage tooltip에 노출되지 않는 회귀 테스트를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "monitoring or assignee or work_reply or work_complete"`: 32 passed.
- `python -m py_compile app/server.py`: passed.
- `docker compose restart web` 후 `/api/health`: ok.
- 김민수 세션 `/ui/assignees`, `/ui/monitoring`, `/ui/my-work/emails/83085804-57f9-5ead-af71-a200fdae85db`, `/ui/monitoring/emails/83085804-57f9-5ead-af71-a200fdae85db`: 모두 200.
- 수정 후 김민수 Monitoring fragment에서 다른 담당자 이름 검색 결과가 없고, 문제 row의 summary tooltip은 `요약문 생성 완료`로 표시됨을 확인했다.

## 남은 리스크와 후속 작업

- Browser plugin과 로컬 Playwright/Chromium 실행 파일이 없어 실제 브라우저 스크린샷과 클릭 기반 open/close/Escape/outside-click 검증은 수행하지 못했다.
- 해당 상호작용 계약은 기존 템플릿 테스트와 실제 HTMX fragment 응답으로 보완 확인했다.

---

# 2026-08-26 - Text vLLM 전환을 위한 role별 provider 분리

| 항목 | 내용 |
|---|---|
| 상태 | 부분 해결, 런타임 blocker |
| 관련 영역 | LLM provider routing, vLLM runtime activation, Docker/WSL2 GPU |
| 관련 파일 | `app/config.py`, `app/llm/gateway.py`, `app/server.py`, `app/services/mail_decision_runtime_service.py`, `app/tools/qdrant_similar_case_index.py`, `docker-compose.yml`, `.env.example`, `scripts/benchmark_llm_inference.py`, `docs/development/llm-vllm-inference-architecture.md`, `tests/test_vision_fact_extraction.py` |

## 요청 또는 배경

- 사용자는 이전 benchmark에서 더 낫다고 판단했던 vLLM 방향으로 실제 구현을 진행하라고 요청했다.
- 의도한 운영 구성은 text generation, Chats, FactExtraction, DecisionAgent는 vLLM으로 옮기고 vision/embedding은 Ollama에 남기는 것이다.

## 확인한 사실

- 기존 구현은 role별 endpoint는 있었지만 provider는 전역 `CORAMAIL_LLM_PROVIDER`만 사용했다.
- 이 상태에서 `CORAMAIL_LLM_PROVIDER=vllm`을 켜면 text뿐 아니라 vision/embedding provider semantics도 함께 흔들릴 수 있었다.
- 실행 중인 서비스는 아직 Ollama였고, 실제 vLLM 전환은 적용되지 않은 상태였다.

## 해결 방법

- `CORAMAIL_TEXT_LLM_PROVIDER`, `CORAMAIL_VISION_LLM_PROVIDER`, `CORAMAIL_EMBEDDING_PROVIDER`를 추가하고 기존 `CORAMAIL_LLM_PROVIDER`를 fallback으로 유지했다.
- `LocalLLMGateway`가 role별 provider를 기준으로 Ollama native `/api/chat`, vLLM/OpenAI-compatible `/chat/completions`, Gemini 경로를 선택하게 했다.
- server, runtime service, Qdrant indexing tool, benchmark script가 새 role별 provider 설정을 전달하게 했다.
- `.env.example`과 Docker Compose web env에 role별 provider 설정을 추가했다.
- role별 provider 테스트를 추가해 text는 vLLM JSON schema path, vision은 Ollama native schema path, embedding은 Ollama-compatible embedding path로 분리되는 것을 검증했다.

## 검증

- `python -m py_compile app/config.py app/llm/gateway.py app/server.py app/services/mail_decision_runtime_service.py app/tools/qdrant_similar_case_index.py scripts/benchmark_llm_inference.py`: passed.
- `env GEMINI_API_KEY= GOOGLE_API_KEY= CORAMAIL_TEXT_LLM_PROVIDER=vllm CORAMAIL_VISION_LLM_PROVIDER=ollama CORAMAIL_EMBEDDING_PROVIDER=ollama docker compose --profile vllm config --services`: parsed.
- `uv run pytest tests/test_vision_fact_extraction.py tests/test_decision_agent.py tests/test_mail_search_service.py tests/test_mail_decision_runtime.py tests/test_mail_decision_runtime_client.py`: 73 passed.
- web container accepted the desired config: global provider `ollama`, text provider `vllm`, vision provider `ollama`, embedding provider `ollama`, text model `qwen2.5-7b-awq`, text concurrency 16.

## 런타임 blocker

- vLLM 0.27.1 server failed to start in the current WSL2 Docker environment before CoRA Mail could send real traffic.
- Host and container both showed the RTX 5060 Ti via `nvidia-smi`, and Ollama models were unloaded so VRAM pressure was not the cause.
- vLLM `EngineCore` still failed with `RuntimeError: No CUDA GPUs are available`.
- Tried workarounds: Compose `gpus: all`, manual `docker run --gpus all`, `VLLM_WSL2_ENABLE_PIN_MEMORY=1`, `VLLM_WORKER_MULTIPROC_METHOD=spawn`, `VLLM_USE_V2_MODEL_RUNNER=0`, `VLLM_ENABLE_V1_MULTIPROCESSING=0`.
- Because text=vLLM would make the live service unusable while vLLM is down, the running dev service was restored to Ollama defaults after the failed activation attempts.

## 남은 리스크와 후속 작업

- The application-side role provider split is complete, but actual text=vLLM runtime activation is blocked on WSL2/Docker/vLLM CUDA worker initialization.
- Next action requires resolving the host/runtime issue or testing the same code path on Native Linux / a different vLLM image known to work with the RTX 5060 Ti stack.

---

# 2026-08-26 - vLLM 후보 모델 실측 검증과 운영 후보 정리

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | vLLM, Hugging Face gated access, WSL2 runner, model benchmark, structured output, CoRA Mail agent workload |
| 관련 파일 | `docker-compose.yml`, `.env.example`, `app/config.py`, `app/llm/gateway.py`, `app/server.py`, `app/services/mail_decision_runtime_service.py`, `scripts/benchmark_llm_inference.py`, `docs/development/llm-vllm-inference-architecture.md`, `docs/development/reports/coramail_vllm_session_report_2026-08-26.docx` |

## 요청 또는 배경

- 사용자는 이전 vLLM 검증을 계속 진행하되, 동일한 Ollama 모델 재현에만 묶이지 말고 CoRA Mail 온프레미스 workload에 적합한 `model + inference engine` 조합을 찾으라고 요청했다.
- Hugging Face gated access는 사용자가 로컬 인증과 권한 승인을 완료했으며, Codex는 이후 blocked 상태를 풀고 실제 vLLM 서버 기동과 후보 모델 평가를 이어갔다.
- 사용자는 vLLM이 더 빠른 방향으로 보인다고 판단했고, 양자화 모델 후보도 평가하라고 했다.

## 확인한 사실

- `hf auth whoami` 기준 로컬 Hugging Face 인증은 완료되어 있었고, `meta-llama/Llama-3.2-3B-Instruct` gated 모델 다운로드와 기동을 확인했다. 토큰 값은 출력하거나 저장하지 않았다.
- WSL2, NVIDIA GeForce RTX 5060 Ti 16GB, NVIDIA driver 596.36, vLLM 0.27.1 환경에서 `VLLM_WSL2_ENABLE_PIN_MEMORY=1`을 사용하면 vLLM V2 runner가 기동했다.
- `Llama 3.2 3B BF16 + vLLM`은 기동과 benchmark는 가능했지만 일부 CoRA Mail structured schema에서 malformed JSON 또는 필수 facts 누락이 발생했다.
- `Qwen/Qwen2.5-7B-Instruct-AWQ + vLLM`은 구조화 출력 80/80, 실제 agent 경로 5/5를 통과했고, background Mail Decision과 interactive Search/Chats 혼합 workload에서 Ollama baseline보다 낮은 latency를 보였다.

## 해결 방법

- vLLM Llama 경로에서 출력이 과도하게 길어져 JSON이 깨지는 문제를 막기 위해 `CORAMAIL_LLM_MAX_OUTPUT_TOKENS`와 `LocalLLMConfig.max_output_tokens`를 추가하고 Ollama/OpenAI-compatible/Gemini 호출에 반영했다.
- Docker Compose web 환경에 `CORAMAIL_LLM_MAX_OUTPUT_TOKENS` 전달을 추가했다.
- optional `vllm-text` profile 기본 모델을 실측 추천 후보인 `Qwen/Qwen2.5-7B-Instruct-AWQ`, served model `qwen2.5-7b-awq`, max model length 4096으로 조정했다. 기본 provider는 Ollama로 유지했다.
- `.env.example`에는 vLLM text 전환 예시와 WSL2 pinned memory workaround, text concurrency 16 추천값을 주석으로 남겼다.
- vLLM architecture 문서에 후보별 실측 결과와 개발 머신 권장 배치 전략을 추가했다.
- 요청 단위별 진행 내용을 Word 리포트로 작성했다.

## 검증

- `Qwen/Qwen2.5-7B-Instruct-AWQ + vLLM`: structured output 80/80, 실제 CoRA Mail FactExtraction/Decision path 5/5.
- Ollama baseline `llama3.2:latest` Q4_K_M: 실제 agent path 5/5이나 동시성 증가 시 p95와 throughput이 크게 악화됐다.
- `Qwen2.5-7B-Instruct-AWQ + vLLM` synthetic fact extraction c8 p95 약 3.6s, throughput 약 1.94 rps; decision burst 20 throughput 약 9.2 rps; mixed workload interactive 평균 약 0.99s.
- `uv run pytest tests/test_vision_fact_extraction.py tests/test_decision_agent.py tests/test_mail_search_service.py tests/test_mail_decision_runtime.py tests/test_mail_decision_runtime_client.py`: 72 passed.

## 남은 리스크와 후속 작업

- 이번 단계에서는 `CORAMAIL_LLM_PROVIDER` 기본값을 vLLM으로 전환하지 않았다. 실제 기본 전환은 사용자의 승인 후 별도 변경으로 진행한다.
- 16GB 단일 GPU 개발 머신에서는 text만 vLLM으로 두고 vision/embedding은 Ollama 유지가 현실적이다.
- 고객사 Native Linux 또는 더 큰 GPU 환경에서는 WSL2 workaround 없이 기본 vLLM runner, 별도 embedding/vision backend, 더 큰 모델 후보를 다시 benchmark해야 한다.
- 사용자가 이후 commit/push 금지를 철회해 이번 변경은 세션 로그와 함께 커밋/푸시 대상으로 정리했다.

---

# 2026-08-25 - Chats 원본 메일 요약 후속 질문 복구

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Chats, follow-up query resolution, mailbox RAG search |
| 관련 파일 | `app/services/mail_chat_service.py`, `app/services/mail_search_service.py`, `tests/test_mail_decision_ui.py`, `tests/test_mail_search_service.py` |

## 요청 또는 배경

- 사용자는 Chats 탭에서 예시 질문 후 같은 채팅 세션에서 `원본 메일 요약해줘`를 요청하면 `질문과 관련된 메일 본문이나 첨부 분석 근거를 찾지 못했습니다.`라고 답하는 문제를 보고했다.
- 해당 문구 하나만 예외 처리하지 말고, 유사한 후속 지시형 질문도 의도대로 동작하게 해 달라고 요청했다.

## 확인한 사실

- Chats 후속 질의 보정은 이전 결과의 `business_refs`, `email_uid`, 제목, source를 모두 `관련 업무 식별자`로 붙였다.
- Search는 `required_identifiers`가 있으면 모든 식별자가 같은 document search text에 존재해야만 후보로 인정한다.
- 첨부 근거에는 참조번호가 있지만 원본 메일 본문 document에는 같은 참조번호가 없고 같은 `email_uid`만 있는 경우가 가능하다.
- 이 조합 때문에 `원본 메일 요약해줘`처럼 원본 메일을 요구하는 후속 질문이 같은 메일의 본문을 보지 못하고 후보 없음으로 끝날 수 있었다.

## 해결 방법

- Chats 후속 질의 보정에서 이전 결과의 `email_uid`를 안정적인 타깃 식별자로 우선 사용하고, 결과에 UID가 없을 때만 업무 참조번호와 제목/source 식별자를 fallback으로 사용하게 했다.
- Search query signal에 `prefer_mail_body`를 추가해 `원본 메일`, `메일 본문`, `본문`, `메일 요약` 요청은 같은 UID의 첨부보다 mail body document를 우선 후보로 사용하게 했다.
- Planner가 `mailbox_lookup`으로 잘못 분류해도 식별자가 있는 원본/요약 질문은 기존 content-question 보정으로 `document_qa` 경로를 유지한다.
- Chats와 Search 각각에 회귀 테스트를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "chat" tests/test_mail_search_service.py -k "follow_up or original_mail or latest_mail or identifier_field"`: 12 passed.
- `uv run pytest tests/test_mail_search_service.py tests/test_mail_decision_ui.py -k "chat or search"`: 49 passed.
- `python -m py_compile app/services/mail_chat_service.py app/services/mail_search_service.py`: passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 세션에서 예시 버튼 클릭 후 질의 제출까지의 시각 검증은 수행하지 않았다.
- 이번 변경 전부터 작업트리에 있던 vLLM/LLM 설정 관련 미커밋 변경은 이번 요청 범위에서 제외했다.

---

# 2026-08-25 - Chats 답변과 근거 UI 밀도 조정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Chats, answer bubble, evidence cards |
| 관련 파일 | `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Chats 탭에서 답변 메시지 박스가 텍스트 내용에 비해 가로가 짧고 높이가 과하게 길다고 보고했다.
- 근거 박스는 `원본 메일 보기` 버튼의 가로가 과하게 길어 근거 박스 높이와 버튼 폭을 줄이고, 버튼 위치를 최우측으로 재배치해 달라고 요청했다.

## 확인한 사실

- Chats 답변 버블은 최대 폭이 `760px`로 제한되어 긴 답변이 빨리 줄바꿈될 수 있었다.
- Chats 근거 카드 본문은 CSS grid item 기본 stretch 동작 때문에 `result-detail-button`이 본문 폭을 채우기 쉬운 구조였다.
- 검색 화면도 같은 `result-detail-button`을 사용하므로 공용 스타일을 바꾸지 않고 Chats 범위에서만 override해야 했다.

## 해결 방법

- Chats 답변 버블의 최대 폭을 넓히고 내부 padding과 검색 답변 상태 gap을 줄여 긴 답변의 세로 높이를 낮췄다.
- Chats 근거 패널과 카드의 gap, padding, rank column 폭을 줄여 카드 높이를 낮췄다.
- Chats 근거 카드 안의 `원본 메일 보기` 버튼에만 `justify-self: end`, `width: fit-content`, 더 작은 높이와 padding을 적용했다.
- 관련 CSS 계약 테스트를 보강했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "chats"`: 7 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다.
- 이번 변경 전부터 작업트리에 있던 vLLM/LLM 설정 및 Gmail 회신 관련 미커밋 변경은 이번 요청 범위에서 제외했다.

---

# 2026-08-25 - Gmail 회신 버튼 HTMX redirect 무반응 수정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | My Work, Gmail reply initiation, HTMX redirect |
| 관련 파일 | `app/server.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 담당자 계정에서 `답장` 버튼을 클릭해도 아무 일도 일어나지 않는다고 보고했다.

## 확인한 사실

- `/ui/emails/{email_ref}/work/reply-initiate`는 회신 시작 이벤트를 기록한 뒤 외부 Gmail thread URL로 `303 RedirectResponse`와 `HX-Redirect`를 함께 반환하고 있었다.
- HTMX/XHR 요청에서 3xx redirect는 브라우저가 먼저 따라가므로, 앱 JavaScript가 원래 응답의 `HX-Redirect`를 안정적으로 처리하지 못한다.
- 외부 Gmail URL을 XHR로 따라가면 CORS/응답 처리 때문에 사용자 화면에서는 이동이 일어나지 않은 것처럼 보일 수 있다.

## 해결 방법

- 회신 시작 기록 후 HTTP 상태를 `204`로 반환하고 `HX-Redirect` 헤더만 실어 HTMX가 정상적으로 브라우저 위치 이동을 처리하게 했다.
- 관련 테스트 기대값을 `303`에서 `204`로 갱신했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "work_reply_initiate_redirects_to_gmail_after_recording"`: 1 passed.
- `uv run pytest tests/test_mail_decision_ui.py`: 171 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 못했다.
- 이번 변경 전부터 작업트리에 있던 vLLM/LLM 설정 관련 미커밋 변경은 이번 요청 범위에서 제외했다.

---

# 2026-08-25 - Gmail 회신 의도 정리와 업무 완료 확인 모달 정렬

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | My Work, Gmail reply initiation, work completion confirm modal, Dashboard route modal |
| 관련 파일 | `app/templates/partials/email_detail.html`, `app/templates/views/assignee_work.html`, `app/templates/shell.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 담당자 계정으로 로그인했을 때 `답장` 버튼의 의도된 동작을 정리한 뒤 의도대로 구현해 달라고 요청했다.
- `업무 완료` 버튼 클릭 시 뜨는 확인 팝업을 Dashboard 탭의 전달 버튼 팝업처럼 전체 서비스 디자인과 일관되게 바꿔 달라고 요청했다.

## 확인한 사실

- `답장`은 CoRA가 메일을 작성·발송하는 버튼이 아니라, 담당자 본인 여부를 검증한 뒤 `reply_initiated_at`과 `work_events.reply_initiated`를 기록하고 Gmail thread로 이동시키는 흐름이다.
- 실제 회신 발송 여부는 이후 Gmail SENT 동기화가 같은 `provider_thread_id`와 `reply_initiated_at` 이후 발신 metadata를 연결해 `responded`로 갱신한다.
- `업무 완료`는 `responded`와 분리된 담당자의 명시 액션이며, 기존 서버 구현은 이 계약에 맞게 담당자 검증 후 `work_items.status = completed`를 기록한다.
- 업무 완료 확인창만 브라우저 기본 `hx-confirm`을 사용하고 있어 Dashboard 수동 전달 모달과 시각적으로 불일치했다.

## 해결 방법

- 기존 Dashboard 수동 전달 확인 모달을 범용 확인 모달로 확장해 `data-work-complete-button`도 같은 모달을 사용하게 했다.
- 업무 완료 확인 시 eyebrow, 제목, 아이콘, 제출 라벨을 `업무 처리`, `업무를 완료할까요?`, `task_alt`, `업무 완료`로 바꿔 표시한다.
- 메일 상세와 담당자 업무 선택 패널의 업무 완료 버튼에 새 데이터 속성을 추가했다.
- 회신 시작 서버 흐름은 의도와 이미 일치하므로 변경하지 않고, 관련 UI 계약 테스트를 보강했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "assignee_work_template_keeps_actions_in_selected_work_panel or shell_includes_manual_route_confirm_modal or work_reply_initiate_redirects_to_gmail_after_recording or work_complete_requires_authenticated_assignee"`: 3 passed.
- `uv run pytest tests/test_mail_decision_ui.py`: 171 passed.

## 남은 리스크와 후속 작업

- 이번 변경 전부터 작업트리에 있던 vLLM/LLM 설정 관련 미커밋 변경은 이번 요청 범위에서 제외했다.
- 별도 브라우저 스크린샷 검증은 수행하지 않았고, 공통 모달 구조와 템플릿 테스트로 회귀를 확인했다.

---

# 2026-08-25 - Chats 입력 대기 상태 UI 오류 수정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Chats, HTMX pending state, chat composer, CSS spacing |
| 관련 파일 | `app/templates/views/chats.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Chats 탭에서 질문 입력 후 답변이 나오기 전까지 이전 답변의 근거 박스와 새 입력 메시지 박스가 겹치는 UI 오류를 보고했다.
- 같은 대기 상태에서 입력창에 방금 보낸 쿼리가 계속 남아 있는 오류도 함께 보고했다.
- 추가로 Chats 입력창의 연한 예시 placeholder 텍스트 제거를 요청했다.

## 확인한 사실

- Chats composer는 `htmx:beforeRequest`에서 pending 말풍선을 렌더링하지만, 입력창은 `htmx:afterRequest` 성공 시점에만 비워졌다.
- 실패 표시 로직은 입력창 값을 다시 읽어 사용자 질문을 표시했으므로, 입력창을 즉시 비우려면 pending query를 별도 보존해야 했다.
- pending 대화는 기존 대화 뒤에 별도 `.chat-conversation` sibling으로 붙어, 이전 근거 패널 뒤 간격을 명시적으로 보강할 필요가 있었다.

## 해결 방법

- pending 렌더링 시 `form.dataset.chatPendingQuery`에 질문을 저장하고, pending 말풍선을 붙인 직후 입력창을 즉시 비우게 했다.
- 오류 응답은 비워진 입력창 대신 저장된 pending query를 사용해 사용자 질문 말풍선을 복원하게 했다.
- 성공 응답 후에는 저장한 pending query를 삭제한다.
- Chats 입력창의 placeholder를 제거하고, pending 대화가 기존 대화 뒤에 붙을 때 18px 상단 여백을 갖도록 CSS를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "chats"`: 7 passed.
- `uv run pytest tests/test_mail_decision_ui.py`: 171 passed.
- `python -m py_compile app/server.py`: passed.
- Docker Compose `web` 서비스를 재시작한 뒤 실제 `/` Chats 화면, `/ui/chats-results`, `/static/app.css` 응답이 200으로 내려오는 것을 확인했다.
- 실제 Chats HTML에서 `chatQueryInput`에 placeholder가 없고, inline script에 pending query 저장/입력 초기화/성공 후 삭제 로직이 포함되며, CSS 응답에 `.chat-conversation + .chat-conversation-pending` 여백 규칙이 포함되는 것을 확인했다.

## 남은 리스크와 후속 작업

- Browser plugin과 로컬 Playwright/브라우저 실행 파일이 없어 스크린샷 기반 시각 검증은 수행하지 못했다.
- 기존 작업트리의 vLLM 관련 미커밋 변경은 이번 요청 범위에서 제외했다.

---

# 2026-08-25 - 사이드 패널 지연 중 빈 패널 노출 제거

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | UI motion, Assignments drawer, Monitoring inspector, HTMX timing |
| 관련 파일 | `app/templates/shell.html` |

## 요청 또는 배경

- 사용자는 사이드 패널 표시 딜레이 때문에 뒷배경이 먼저 가려지고 패널이 나중에 열리는 오류가 돋보인다고 지적했다.
- 근본적으로 이 문제가 발생하지 않도록 UI 구조를 바꿔 달라고 요청했다.

## 확인한 사실

- Assignments 상세 열기와 Monitoring 메일 클릭 핸들러가 HTMX 응답을 받기 전에 즉시 `openAssigneeDetailDrawer()` 또는 `openOpsInspector()`를 호출했다.
- 이 때문에 네트워크/렌더 딜레이 동안 비어 있거나 이전 상태의 사이드 패널 영역이 먼저 화면을 덮을 수 있었다.
- 이후 HTMX `afterSwap`에서 다시 open과 애니메이션을 실행하므로, 딜레이가 길수록 배경 가림과 패널 열림 사이의 간극이 더 눈에 띄었다.

## 해결 방법

- 클릭 핸들러에서는 선택 row 표시만 처리하고 사이드 패널을 즉시 열지 않게 했다.
- HTMX 응답이 `#opsInspector` 또는 `#assigneeEmailDetailDrawer`에 실제 swap된 뒤에만 패널을 열게 했다.
- 닫혀 있던 패널이 처음 열리는 경우에만 오른쪽에서 왼쪽으로 들어오는 애니메이션을 실행하고, 이미 열린 패널에서 다른 메일을 선택할 때는 패널 전체 slide를 반복하지 않게 했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "assignee or monitoring or chats or chat"`: 42 passed.

## 남은 리스크와 후속 작업

- Browser plugin과 로컬 Playwright 패키지가 없어 실제 스크린샷 기반 시각 검증은 수행하지 못했다.
- 기존 작업트리의 vLLM 및 별도 Chats 관련 미커밋 변경은 이번 요청 범위에서 제외했다.

---

# 2026-08-25 - 사이드 패널 배경/열림 애니메이션 동기화

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | UI motion, Assignments drawer, Monitoring inspector |
| 관련 파일 | `app/static/app.css`, `app/templates/shell.html` |

## 요청 또는 배경

- 사용자는 Assignments/Monitoring 사이드 패널이 열릴 때 뒷배경이 먼저 가려지고 그 뒤 패널이 움직이는 간극이 있다고 보고했다.
- 뒷배경 가림 영역과 사이드 패널 열림 애니메이션이 같은 속도와 시점으로 나오게 해 달라고 요청했다.

## 확인한 사실

- HTMX swap 후 `openOpsInspector()` 또는 `openAssigneeDetailDrawer()`가 먼저 `hidden=false`로 패널을 최종 위치에 노출했다.
- 이후 `playSideDrawerEnter()`가 `requestAnimationFrame` 안에서 `side-drawer-enter` 클래스를 붙여, 한 프레임 동안 패널 배경이 먼저 보이고 다음 프레임부터 이동 애니메이션이 시작될 수 있었다.
- 사이드 패널 keyframe에도 opacity 변화가 있어 배경 덮임과 이동이 분리되어 보일 여지가 있었다.

## 해결 방법

- `playSideDrawerEnter()`에서 `requestAnimationFrame` 지연을 제거하고, 클래스 제거 후 reflow를 강제한 다음 같은 프레임에서 `side-drawer-enter`를 즉시 재부여하게 했다.
- 사이드 패널 keyframe은 opacity 없이 `translateX(28px) -> 0`만 사용하게 해 패널 배경과 본문이 같은 이동 애니메이션으로 들어오도록 조정했다.
- Chats 메시지 애니메이션과 다른 화면 갱신 범위는 변경하지 않았다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "assignee or monitoring or chats or chat"`: 42 passed.
- 실행 중인 앱에서 `/api/health`, `/static/app.css`, `/` 렌더 HTML을 확인했고, 렌더된 inline script는 Node `vm.Script`로 2개 모두 parse 됐다.
- CSS 응답에서 `side-drawer-enter`는 유지되고 opacity 기반 drawer keyframe은 제거된 것을 확인했다.

## 남은 리스크와 후속 작업

- Browser plugin과 로컬 Playwright 패키지가 없어 실제 스크린샷 기반 시각 검증은 수행하지 못했다.
- 기존 작업트리의 vLLM 관련 미커밋 변경은 이번 요청 범위에서 제외했다.

---

# 2026-08-25 - Chats 외 화면 애니메이션 롤백과 사이드 패널 전환 한정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | UI motion, Chats, Assignments drawer, Monitoring inspector |
| 관련 파일 | `app/static/app.css`, `app/templates/shell.html` |

## 요청 또는 배경

- 사용자는 이전 화면 갱신 애니메이션 중 Chats 수정사항 외의 변경을 모두 롤백해 달라고 요청했다.
- 추가로 Assignments 탭의 상세 열기 버튼과 Monitoring 탭의 메일 클릭에서 뜨는 사이드 패널에만 오른쪽에서 왼쪽으로 밀려 나오는 애니메이션을 적용해 달라고 요청했다.

## 해결 방법

- 이전 커밋에서 추가한 사이드 내비게이션 active transition, `#main-panel`, `#email-detail`, `#mailRows` enter 애니메이션과 JS 호출을 제거했다.
- Chats 메시지 pending/응답 enter 애니메이션은 유지했다.
- `#assigneeEmailDetailDrawer`와 `#opsInspector` HTMX swap 이후에만 `side-drawer-enter` 클래스를 부여해 오른쪽에서 왼쪽으로 짧게 들어오는 애니메이션을 적용했다.
- `prefers-reduced-motion: reduce`에서는 Chats와 사이드 패널 신규 애니메이션이 모두 꺼지도록 유지했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "chats or chat or inbox_initial_queue or email_detail or assignee or monitoring"`: 53 passed.
- CSS/JS diff에서 `main-panel`, `email-detail`, `mailRows`, nav active 대상의 이전 motion hook이 제거되고 `side-drawer-enter`가 Assignments/Monitoring drawer에만 적용되는 것을 확인했다.

## 남은 리스크와 후속 작업

- Browser plugin과 로컬 Playwright 패키지가 없어 실제 스크린샷 기반 시각 검증은 수행하지 못했다.
- 기존 작업트리의 vLLM 관련 미커밋 변경은 이번 요청 범위에서 제외했다.

---

# 2026-08-25 - 화면 갱신 애니메이션 polish

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | UI motion, HTMX tab swap, Inbox detail, Chats |
| 관련 파일 | `app/static/app.css`, `app/templates/shell.html` |

## 요청 또는 배경

- 사용자는 이메일이 사이드 패널에서 열리는 동작, Chats 탭에서 입력/답변 메시지가 올라가는 동작, 탭 전환과 갱신 흐름에 자연스럽고 과하지 않은 애니메이션을 추가해 달라고 요청했다.
- 비즈니스 서비스인 만큼 장식적이거나 큰 움직임이 아니라 서비스 품질을 높이는 수준의 미묘한 전환이 필요했다.

## 해결 방법

- 공통 motion duration/easing CSS 변수를 추가하고 사이드 내비게이션 활성 상태에 짧은 색/배경 전환을 부여했다.
- HTMX로 교체되는 `#main-panel`, `#email-detail`, `#mailRows`에 swap 직후 한 번만 실행되는 fade/slide enter 애니메이션을 추가했다.
- Chats는 pending 메시지와 서버 응답 후 마지막 사용자/AI 메시지 묶음만 부드럽게 들어오도록 `shell.html` helper를 추가했다.
- `prefers-reduced-motion: reduce`에서는 신규 애니메이션이 실행되지 않도록 CSS/JS 양쪽에서 방어했다.
- 기존 HTMX 데이터 흐름, 채팅 `session_id` 동기화, Inbox 선택 hidden input 계약은 유지했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "chats or chat or inbox_initial_queue or email_detail"`: 24 passed.
- Docker Compose web service restart 후 `/api/health`: 200 ok.
- 로그인 쿠키로 `/`, `/ui/chats`, `/ui/inbox`, `/ui/chats-results?q=가장 최신 메일이 뭐야`를 호출해 CSS/inline JS hook, Chats fragment, Inbox row/detail target, chat session OOB input이 응답에 포함되는 것을 확인했다.
- Browser plugin과 로컬 Playwright 패키지가 없어 실제 스크린샷 기반 시각 검증은 수행하지 못했다.

## 남은 리스크와 후속 작업

- 시각적 타이밍과 체감 품질은 실제 브라우저에서 최종 확인하는 것이 좋다.
- 기존 작업트리에는 vLLM 전환 준비 관련 미커밋 변경이 있었으므로 이번 커밋 범위에서 제외한다.

---

# 2026-08-25 - vLLM 전환 준비와 LLM inference 계측

| 항목 | 내용 |
|---|---|
| 상태 | 진행 |
| 관련 영역 | LLM Gateway, vLLM provider, latency instrumentation, Docker Compose, benchmark |
| 관련 파일 | `app/llm/gateway.py`, `app/config.py`, `app/server.py`, `app/services/mail_decision_runtime_service.py`, `docker-compose.yml`, `.env.example`, `scripts/benchmark_llm_inference.py`, `docs/development/llm-vllm-inference-architecture.md`, `tests/test_vision_fact_extraction.py` |

## 요청 또는 배경

- 사용자는 현재 `main` 브랜치 전체 코드를 기준으로 Ollama 중심 LLM inference 구조를 분석하고, 운영형 온프레미스 환경에서 vLLM 중심 전환이 타당한지 코드와 benchmark로 검증해 달라고 요청했다.
- 단순 문자열 치환이 아니라 text, vision, embedding 역할별 inference architecture, structured output 호환성, concurrency, throughput, rollback 가능성을 함께 검토하라고 했다.
- 마지막에는 commit/push하지 말고 변경 내용과 benchmark 결과를 먼저 보고하라고 명시했다.

## 확인한 사실

- Mail Decision path는 attachment parsing 이후 vision/document understanding, fact extraction, retrieval embedding, decision generation을 순차적으로 수행한다.
- Search/Chats path는 query planning, embedding retrieval, answer synthesis를 `LocalLLMGateway`로 호출한다.
- 기존 gateway는 Ollama provider에서 native `/api/chat` JSON schema path를 사용하고, embedding은 `/embeddings`를 호출했다.
- 기존 transport는 `urllib.request` 기반 동기 HTTP 호출이어서 connection pooling과 role별 backpressure가 없었다.
- 현재 로컬 환경에서 Ollama는 응답하지만 vLLM endpoint `127.0.0.1:8001`은 기동되어 있지 않았다.

## 해결 방법

- `LocalLLMGateway`에 metadata-only `llm_call` 로그를 추가했다. operation, role, provider, model, UTC start/end, latency, usage token 또는 근사 input token, error, timeout, status code만 기록하고 prompt/body/output은 기록하지 않는다.
- HTTP transport를 `requests.Session` 기반으로 바꿔 connection pooling을 사용하게 하고, text/vision/embedding role별 semaphore concurrency guard를 추가했다.
- `CORAMAIL_TEXT_LLM_BASE_URL`, `CORAMAIL_VISION_LLM_BASE_URL`, `CORAMAIL_EMBEDDING_BASE_URL`과 role별 concurrency env를 추가하되 기존 `CORAMAIL_LLM_BASE_URL` fallback을 유지했다.
- `CORAMAIL_LLM_PROVIDER=vllm`에서는 OpenAI-compatible `/chat/completions`에 `response_format={"type":"json_schema"}`를 사용해 Pydantic structured output 계약을 유지하게 했다.
- Docker Compose에 optional `vllm-text`와 `vllm-embedding` profile, Hugging Face cache volume, GPU passthrough, readiness healthcheck를 추가했다. Ollama는 rollback과 A/B benchmark를 위해 유지했다.
- 합성 CoRA Mail prompt 기반 benchmark 스크립트를 추가해 fact extraction, decision, mixed chat workload를 concurrency 1/2/4/8 등으로 측정할 수 있게 했다.
- 코드 기준 호출 체인, 병목, vLLM role 분리 권고, benchmark 절차를 `docs/development/llm-vllm-inference-architecture.md`에 문서화했다.

## 검증

- `python -m py_compile app/config.py app/llm/gateway.py app/server.py app/services/mail_decision_runtime_service.py scripts/benchmark_llm_inference.py`: passed.
- `uv run pytest tests/test_vision_fact_extraction.py tests/test_hosting_defaults.py tests/test_mail_search_service.py tests/test_decision_agent.py tests/test_dev_environment.py`: 75 passed.
- `env GEMINI_API_KEY= GOOGLE_API_KEY= docker compose --profile vllm --profile vllm-embedding config --services`: vLLM profile services parsed.
- Ollama fact extraction benchmark on RTX 5060 Ti 16GB: concurrency 1 p95 3481.65ms throughput 0.3116 rps; concurrency 2 p95 6503.34ms throughput 0.3244 rps; concurrency 4 p95 12165.12ms throughput 0.3297 rps; concurrency 8 p95 23481.4ms throughput 0.326 rps; errors 0.
- `uv run pytest`: 408 passed, 2 failed. Failures were existing document type navigation expectations in `tests/test_document_type_navigation.py` and no modified file touched the templates under assertion.

## 남은 리스크와 후속 작업

- vLLM server was not running in the local environment, so Ollama vs vLLM 실측 비교표는 아직 완성되지 않았다.
- 실제 vLLM 전환 결론은 동일 GPU, 동일 또는 등가 모델/quantization, structured schema validation, mixed background/interactive workload benchmark 후 내려야 한다.
- 현재 변경은 app layer 전체 async 전환이 아니라 gateway transport pooling과 role별 concurrency guard에 한정된다. background worker queue priority, cancellation, per-route interactive quota는 다음 단계다.
- 사용자가 commit/push 금지를 명시했으므로 이번 변경은 로컬 작업트리에만 남겼다.

---

# 2026-08-24 - Chats 후속 질문 최신 메일 회귀 수정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Chats, mail search planner, conversation session, routing metadata |
| 관련 파일 | `app/services/mail_chat_service.py`, `app/services/mail_search_service.py`, `app/repositories/postgres_mail_repository.py`, `app/services/demo_mail_service.py`, `app/templates/shell.html`, `tests/test_mail_search_service.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Chats 탭에서 첫 번째 질문 뒤 같은 세션으로 두 번째 질문을 했는데, 후속 질문에 답하지 않고 생뚱맞게 최신 메일이 무엇인지 다시 답하는 근본 원인을 파악해 해결해 달라고 요청했다.

## 확인한 사실

- `MailChatService`는 세션 히스토리를 유지하고 있었지만, 후속 질문을 좁힐 때 이전 답변 문장의 업무번호만 주로 사용하고 이전 결과 카드의 `email_uid`는 쓰지 않았다.
- 검색 플래너 후처리가 `최신/최근 메일` 표현 또는 이전 최신 메일 맥락에 끌려 후속 필드 질문을 `mailbox_lookup`으로 유지할 수 있었다.
- 실제 웹 런타임에서 `가장 최신 메일이 뭐야` 다음 `위 메일의 담당자`를 호출하니, 세션은 유지됐지만 검색/선택 단계가 전체 최신 메일 답변 또는 근거 부족으로 회귀하는 경로가 재현됐다.
- 담당자 값은 PostgreSQL `routing_assignments`와 `users`에 있었지만 검색 문서 근거에는 명시적으로 포함되지 않았고, 검색 후보 excerpt가 길어질 때 preview 끝의 라우팅 메타데이터가 잘릴 수 있었다.

## 해결 방법

- 후속 질문 제약을 만들 때 이전 턴의 `result.results`에서 `email_uid`, 업무 참조, 제목, source를 우선 추출하게 했다.
- 날짜처럼 보이는 `2026-07-02`류 토큰은 업무 식별자에서 제외해 검색 조건을 과도하게 좁히지 않게 했다.
- `최신/최근/오래된 메일` 표현이 있어도 발신자, 담당자, 분류, 상태, 제목, 납기 등 필드 질문이면 `document_qa`로 고정했다.
- HTMX 응답 후 hidden `session_id`를 명시적으로 동기화해 OOB 처리에만 의존하지 않게 했다.
- PostgreSQL/demo 검색 문서에 현재 라우팅 담당자/상태를 포함하고, 결정적 필드 답변 경로에서 담당자와 발신자를 LLM citation 선택 없이 답하게 했다.
- 검색 후보에는 원문 preview를 `raw_preview`로 보존해 excerpt로 잘린 메타데이터도 결정적 추출에 사용할 수 있게 했다.

## 검증

- `uv run pytest tests/test_mail_search_service.py`: 23 passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "chat or chats"`: 12 passed.
- `python -m py_compile app/services/mail_chat_service.py app/services/mail_search_service.py app/repositories/postgres_mail_repository.py app/services/demo_mail_service.py`: passed.
- `docker compose restart web`: web restarted.
- 라이브 웹 프로세스에서 `가장 최신 메일이 뭐야` 다음 `위 메일의 담당자`를 같은 세션으로 실행해 effective query가 `email_uid + FB24291770`로 좁혀지고, 후보 1개/선택 1개로 `현재 담당자는 최서연`을 답하는 것을 확인했다.

## 남은 리스크와 후속 작업

- 실제 브라우저 클릭 대신 HTMX 엔드포인트와 서버 프로세스에서 검증했다. 브라우저 DOM OOB 처리는 shell 동기화 보강과 테스트로 방어했다.
- 기존 미추적 `docs/development/reports/` 디렉터리는 이번 요청 범위가 아니므로 커밋에서 제외한다.

---

# 2026-08-24 - My Work 행 선택 패널 갱신과 영역 높이 고정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | My Work, selected work panel, fixed layout |
| 관련 파일 | `app/server.py`, `app/templates/views/assignee_work.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 My Work 탭에서 메일 클릭 시 사이드탭이 열리거나 Inbox 탭으로 이동하는 대신 `선택된 업무` 영역이 갱신되게 해 달라고 요청했다.
- 선택된 업무 영역의 너비는 조금만 줄여 달라고 요청했다.
- 업무 큐, 현재 할당 업무, 선택된 업무의 큰 영역 높이가 메일 개수에 따라 유동적으로 바뀌지 않고 항상 고정되게 해 달라고 요청했다.

## 확인한 사실

- 이전 구현은 My Work 행 클릭을 상세 drawer로 연결하거나, 과거에는 Inbox 이동 경로로 연결했다.
- 선택된 업무 패널은 첫 번째 행을 기본으로 사용했으며, 사용자가 클릭한 행을 서버 컨텍스트에서 명시 선택하는 파라미터가 없었다.
- 3개 큰 패널의 외곽 높이는 컨텐츠에 의해 결정되어 메일 개수나 담당자 목록 길이에 따라 전체 틀이 달라질 수 있었다.

## 해결 방법

- `selected_email_uid` 파라미터를 My Work/Assignments 컨텍스트에 추가해 클릭한 메일을 `selected_assignee_work`로 지정하게 했다.
- My Work 행 클릭은 `/ui/my-work/emails/...` drawer가 아니라 `/ui/my-work?...&selected_email_uid=...`로 `#main-panel`을 갱신하게 했다.
- 선택된 메일이 담당자 본인 업무이면 기존 확인 처리 경로를 호출하고, `assigned` 상태는 화면 컨텍스트에서 즉시 `in_progress`로 반영되게 했다.
- 선택된 업무 영역 너비는 이전 확대폭에서 소폭 줄이고, `업무 큐 / 현재 할당 업무 / 선택된 업무` 3개 영역은 viewport 기반 고정 높이를 갖게 했다.
- 메일이나 담당자 수가 많을 때는 각 패널 내부에서만 스크롤되도록 overflow를 조정했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 170 passed.
- `git diff --check`: passed.
- `docker compose restart web`: web restarted.
- 담당자 계정으로 `/ui/my-work` 실제 HTML 확인: 55개 행 모두 `selected_email_uid`와 `#main-panel` 갱신을 사용하고, 행 자체에는 drawer URL/타깃이 없음을 확인했다.

## 남은 리스크와 후속 작업

- 전체 테스트의 Documents 탭 관련 기존 불일치는 이번 변경 범위가 아니므로 수정하지 않았다.
- 계정/비밀번호가 포함된 Word 리포트 디렉터리는 로컬 산출물로 유지하고 커밋에서 제외한다.

---

# 2026-08-24 - My Work 열람 처리 경로와 작업 컬럼 정리

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | My Work, Inbox detail acknowledge, assignee detail drawer |
| 관련 파일 | `app/server.py`, `app/templates/views/assignee_work.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 상세열기 버튼 외에도 My Work 탭에서 메일을 클릭하거나 Inbox에서 메일을 조회했을 때도 담당자가 확인한 것으로 처리되게 해 달라고 요청했다.
- 이어서 My Work 탭의 작업 컬럼은 선택된 업무 패널에 이미 버튼이 있으므로 제거해 달라고 요청했다.
- 작업 컬럼 제거 후 생긴 여유 공간만큼 선택된 업무 영역을 늘려 달라고 추가 요청했다.

## 확인한 사실

- My Work의 상세열기 버튼과 `/ui/emails/{email_ref}` 상세 엔드포인트는 이미 담당자 확인 처리 경로를 타고 있었다.
- My Work 테이블 행 클릭은 Inbox 전체 화면으로 이동하고 있어, 사용자가 기대하는 사이드탭 상세 경험과 달랐다.
- `/ui/inbox?email_uid=...`처럼 Inbox 화면 자체가 선택 메일을 포함해 렌더링하는 경로는 `inbox_context`에서 직접 상세를 구성하므로 확인 처리 호출이 빠져 있었다.

## 해결 방법

- My Work 테이블 행 클릭을 `/ui/my-work/emails/{email_uid}` drawer 엔드포인트로 바꾸고 `#assigneeEmailDetailDrawer`에 렌더링되게 했다.
- `inbox_context`가 request를 받아 선택된 메일에 대해 권한 확인과 담당자 확인 처리를 수행하도록 했다.
- My Work 테이블의 `작업` 컬럼, 행 내부 상세/회신/완료 버튼, 관련 CSS를 제거했다.
- 상세/회신/완료 버튼은 기존처럼 선택된 업무 패널에 유지했다.
- 작업 컬럼 제거에 맞춰 메일 테이블 최소폭을 줄이고, 데스크톱 3열 레이아웃에서 선택된 업무 패널의 최소 폭과 비율을 키웠다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 168 passed.
- `git diff --check`: passed.
- `docker compose restart web`: web restarted.
- 담당자 계정으로 `/ui/my-work` 실제 HTML 확인: `작업` 컬럼과 `assignee-action-cell` 없음, 행 클릭은 `#assigneeEmailDetailDrawer`와 `/ui/my-work/emails/`를 사용.
- CSS 보호 테스트를 새 테이블 최소폭 기준으로 갱신해 My Work dense layout 회귀를 확인했다.

## 남은 리스크와 후속 작업

- 전체 테스트의 Documents 탭 관련 기존 불일치는 이번 변경 범위가 아니므로 수정하지 않았다.
- 계정/비밀번호가 포함된 Word 리포트 디렉터리는 로컬 산출물로 유지하고 커밋에서 제외한다.

---

# 2026-08-24 - Admin Assignments 전체 담당자 기본 보기 복구

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Assignments, My Work, 관리자 권한 |
| 관련 파일 | `app/server.py`, `app/templates/views/assignee_work.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 admin 계정으로 로그인한 경우 Assignments 탭에서 모든 담당자 업무 현황을 확인할 수 있어야 하며, 담당자용 My Work 탭과 같으면 안 된다고 지적했다.

## 확인한 사실

- 담당자 업무 컨텍스트에서 `assignee` 파라미터가 없으면 첫 담당자를 자동 선택하는 로직이 있었다.
- 이 로직 때문에 관리자도 Assignments 기본 진입 시 전체 담당자 범위가 아니라 특정 담당자 범위처럼 보일 수 있었다.
- 선택 담당자 계산 fallback도 빈 선택값에서 첫 행의 담당자를 선택하는 문제가 있었다.

## 해결 방법

- 관리자처럼 전체 담당자 권한이 있는 경우에는 `assignee`가 명시되지 않은 Assignments 기본 화면에서 담당자를 자동 선택하지 않도록 수정했다.
- 전체 보기에서는 `selected_assignee`를 비워 두고 전체 담당자 업무 요약과 전체 행 목록을 유지하게 했다.
- 담당자 목록에 `전체 담당자` 복귀 버튼을 추가해, 관리자가 특정 담당자를 클릭한 뒤 다시 전체 현황으로 돌아갈 수 있게 했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 166 passed.
- `git diff --check`: passed.
- `docker compose restart web`: web restarted.
- admin 로그인 후 `/ui/assignees`에서 `data-view="assignees"`, `전체 담당자 업무 현황`, `전체 담당자` 버튼이 렌더링됨을 확인했다.
- admin Assignments와 담당자 `m.kim@dawonict.co.kr`의 `/ui/my-work` HTML이 서로 다르고, 표시 건수도 다름을 확인했다.

## 남은 리스크와 후속 작업

- 전체 테스트의 Documents 탭 관련 기존 불일치는 이번 변경 범위가 아니므로 수정하지 않았다.
- 계정/비밀번호가 포함된 Word 리포트 디렉터리는 로컬 산출물로 유지하고 커밋에서 제외한다.

---

# 2026-08-24 - Search/Chats 전용 답변 모델 분리

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search/Chats RAG, Local LLM latency control, health readiness |
| 관련 파일 | `app/config.py`, `app/server.py`, `app/services/mail_search_service.py`, `.env.example`, `docs/development/docker-dev-environment.md`, 관련 테스트 |

## 요청 또는 배경

- 사용자는 답변 생성 시간을 줄이는 3가지 제안 중 `로컬 LLM은 계속 쓰되 응답 생성 전용 경량 경로 분리`를 구현해 달라고 요청했다.
- Mail Decision 본 분석 모델은 유지하면서 Search/Chats 답변 생성만 더 작은 로컬 모델로 바꿀 수 있어야 한다.

## 확인한 사실

- `MailSearchService`가 질문 planner와 답변 synthesis를 모두 `LocalLLMGateway.generate_structured()`로 호출하고, 기존에는 gateway의 `text_model`만 trace에 기록했다.
- Search/Chats는 `mail_search_service()`를 통해 생성되므로 여기서 별도 answer model을 주입하면 Mail Decision Runtime의 `CORAMAIL_TEXT_MODEL` 사용과 분리할 수 있다.

## 해결 방법

- `CORAMAIL_CHAT_TEXT_MODEL` 설정을 추가했다. 값이 비어 있으면 기존 `CORAMAIL_TEXT_MODEL`을 그대로 사용한다.
- `MailSearchService`가 planner와 answer synthesis 호출에 전용 `answer_model`을 전달하고 trace의 `answer_model`에도 이 값을 기록하게 했다.
- 서버의 `mail_search_service()` wiring과 `/api/health` LLM readiness required 모델 목록에 `chat_text_model`을 추가했다.
- `.env.example`과 Docker 개발 문서에 전용 chat 모델 설정과 Gemini API 전환 시 함께 바꿀 값을 기록했다.

## 검증

- `uv run pytest tests/test_mail_search_service.py -k "dedicated_chat_answer_model or embedding_retrieval"`: 2 passed.
- `uv run pytest tests/test_hosting_defaults.py -k "llm_readiness"`: 3 passed.
- `python -m py_compile app/config.py app/server.py app/services/mail_search_service.py`: passed.

## 남은 리스크와 후속 작업

- 현재 설치된 Ollama 모델 목록 기준으로 실제 더 빠른 chat 전용 모델은 아직 선택/설치하지 않았다. 모델 후보 선정과 pull, 실제 응답 시간 측정은 별도 작업이다.
- 작업 중 감지된 My Work/assignee 관련 변경은 이번 요청과 무관해 그대로 두고 커밋 대상에서 제외한다.

---

# 2026-08-24 - 로컬 LLM 기본 실행 복구

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Local LLM provider, Docker dev environment, Gemini demo switch |
| 관련 파일 | `.env`, `.env.example`, `docs/development/docker-dev-environment.md` |

## 요청 또는 배경

- 사용자는 Gemini API quota 문제 이후 지연 개선은 나중에 다루고, 우선 로컬 LLM으로 돌아가게 해 달라고 요청했다.
- 단, 나중에 API 방식으로 다시 바꾸고 싶을 때 바로 전환할 수 있는 여지는 남겨 달라고 요청했다.

## 확인한 사실

- 로컬 `.env`는 `CORAMAIL_LLM_PROVIDER=gemini`, Gemini text/vision/embedding 모델로 설정되어 있었다.
- `.env.example`과 Docker Compose 기본값은 이미 Ollama를 기본 provider로 두고 있었다.
- `LocalLLMGateway`는 provider 환경 변수로 Ollama와 Gemini를 전환할 수 있어 코드 변경 없이 실행 설정만 되돌릴 수 있었다.

## 해결 방법

- 로컬 `.env`의 LLM provider와 모델 값을 Ollama 기본값으로 되돌렸다.
- `.env.example`과 Docker 개발 문서에 Gemini API 방식으로 되돌릴 때 변경할 provider/model 값과 API key 보관 기준을 명시했다.
- `docker compose up -d web`으로 web 컨테이너를 새 `.env` 기준으로 재생성했다.

## 검증

- `curl -s http://127.0.0.1:8000/api/health`: `local_ai.llm.provider=ollama`, `base_url=http://ollama:11434/v1`, `missing={}`, `ready=true` 확인.
- `docker compose ps`: web, postgres, qdrant, ollama 컨테이너 실행 확인.

## 남은 리스크와 후속 작업

- 로컬 LLM 지연 문제는 이번 요청 범위에서 다루지 않았다. 모델/프롬프트/검색 호출 최적화는 별도 작업으로 남긴다.
- `docker compose exec web env`는 Docker socket 권한 문제로 실패했지만, `/api/health`가 컨테이너 내부 LLM 설정과 model readiness를 확인했다.
- 작업 전부터 존재하던 `docs/development/reports/` untracked 폴더는 이번 요청과 무관해 그대로 두었다.

---

# 2026-08-24 - Chats 근거 간격과 Gemini quota 오류 정리

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Chats tab, RAG answer evidence, LLM provider error handling |
| 관련 파일 | `app/static/app.css`, `app/services/mail_chat_service.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Chats 탭에서 첫 번째 답변의 근거 박스가 다음 사용자 입력 쿼리 박스와 붙어서 보이는 UI 문제를 수정해 달라고 요청했다.
- 지연을 줄이려고 로컬 LLM 대신 Gemini API를 쓰고 있었으나 `LLM HTTP 429`와 `RESOURCE_EXHAUSTED` quota 오류가 화면에 그대로 표시되어, 로컬 LLM으로 되돌릴지 API 문제를 해결할지 더 나은 방향을 요청했다.

## 확인한 사실

- Chats 결과 partial은 각 턴을 사용자 질문, AI 답변 그룹, 근거 패널 순서로 반복 렌더링한다.
- CSS는 전체 대화 grid gap만 갖고 있어 AI 답변 그룹 내부의 근거 패널 뒤에 다음 사용자 질문이 바로 이어져 보일 수 있었다.
- `MailChatService.ask()`는 검색/LLM 예외를 그대로 문자열화해 사용자 화면에 노출했다. Gemini 429의 긴 JSON 원문은 사용자가 조치하기 어렵고 UI도 깨끗하지 않다.
- `.env.example` 기준 기본 LLM provider는 `ollama`이고, Gemini 설정은 임시 데모 모드로 표시되어 있으며 메일/첨부 내용이 Google로 전송된다는 주석이 있다.

## 해결 방법

- `.chat-message-group-assistant + .chat-message-user`에 상단 여백을 추가해 근거 패널이 포함된 AI 응답 그룹과 다음 사용자 질문을 시각적으로 분리했다.
- Chats 서비스의 예외 메시지 정규화를 추가해 Gemini quota/429 오류는 긴 원본 JSON 대신 짧은 사용자용 안내로 표시되게 했다.
- CSS 간격과 quota 오류 정규화 회귀 테스트를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "chats_css_separates_evidence_from_next_user_query or mail_chat_service_summarizes_gemini_quota_error or chats_results_render_thread_messages_and_evidence or mail_chat_service_resolves_follow_up_without_exposing_history_payload"`: 4 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. CSS selector와 서버 렌더링 단위 테스트로 확인했다.
- Gemini quota 자체는 코드 수정으로 해결할 수 없다. 데모 안정성은 로컬 LLM 기본값으로 되돌리고, API는 billing/quota가 확인된 보조 가속 경로 또는 fallback 구조가 생긴 뒤 사용하는 편이 안전하다.
- 작업 전부터 존재하던 `docs/development/reports/` untracked 폴더는 이번 요청과 무관해 그대로 두었다.

---

# 2026-08-24 - 담당자 Dashboard My Work Aging 그래프

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard, assignee scoped data, Routing Overview replacement |
| 관련 파일 | `app/server.py`, `app/templates/views/dashboard.html`, `app/templates/partials/dashboard_my_work_aging.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 담당자 계정으로 로그인했을 때 Dashboard 탭의 `Routing Overview` 영역은 필요 없으므로 더 적절한 그래프를 구현해 달라고 요청했다.
- 담당자 계정에서는 반드시 해당 담당자에게 배정된 데이터만 표시되어야 한다고 강조했다.

## 확인한 사실

- 기존 Dashboard context는 먼저 `dashboard_rows_for_request()`로 로그인 사용자의 권한에 맞게 row를 좁힌 뒤 summary, distribution, routing overview를 계산한다.
- 담당자 계정에서는 `dashboard_work_scope`가 true이고 오늘/전체 scope toggle은 비활성화된다.
- 기존 `Routing Overview`는 운영자에게는 담당자별 업무 편중을 보여주는 의미가 있지만, 담당자 계정에서는 다른 담당자와 비교하는 정보라 직접적인 업무 우선순위 판단에 덜 적합하다.

## 해결 방법

- 담당자 scope가 적용된 Dashboard rows만 입력으로 받는 `my_work_aging()` 집계를 추가했다.
- 담당자 Dashboard에서는 `Routing Overview` 대신 `My Work Aging` partial을 렌더링하도록 분기했다.
- `My Work Aging`은 미완료 업무를 `기한 초과`, `오늘 수신`, `1일 경과`, `2-3일 경과`, `4일 이상` 구간으로 표시하고, 하단에 미완료 수와 오늘 완료 수를 함께 보여준다.
- `/ui/dashboard-routing-overview` fragment refresh도 담당자 계정에서는 새 partial을 반환하도록 맞췄다.
- 기존 운영자 Dashboard의 `Routing Overview` 렌더링과 테스트는 유지했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "assignee_login_dashboard_context_uses_only_assigned_work or routing_overview or dashboard_summary"`: 6 passed.
- `uv run pytest tests/test_mail_decision_ui.py`: 161 passed.
- `git diff --check`: passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 픽셀/스크린샷 검증은 수행하지 않았다. 서버 렌더링과 UI 테스트로 담당자 scope와 partial 전환을 검증했다.
- 작업 전부터 존재하던 `docs/development/reports/` untracked 폴더는 이번 요청과 무관해 그대로 두었다.

---

# 2026-08-24 - My Work 이메일 상세 사이드탭

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | My Work tab, email detail drawer, assignee workload UI |
| 관련 파일 | `app/server.py`, `app/templates/views/assignee_work.html`, `app/templates/partials/assignee_email_drawer.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 My Work 화면에서 `상세 열기`를 클릭하면 이메일 상세가 사이드탭으로 뜨게 해 달라고 요청했다.

## 확인한 사실

- 기존 My Work `상세 열기`는 우측 선택 업무 패널 내부 `#assigneeDetailPreview`를 메일 상세 partial로 교체하고 있었다.
- Monitoring 화면에는 `opsInspector` 기반의 오른쪽 side peek 패턴과 명시적 닫기, Escape 닫기, 외부 클릭 닫기 로직이 이미 있었다.
- 이전 사용자 선호상 메일 클릭/상세 확인은 화면 내부 오른쪽 side peek로 여닫히는 방식이 적합하다.

## 해결 방법

- My Work 전용 drawer endpoint `/ui/my-work/emails/{email_ref}`를 추가하고, 기존 이메일 상세 partial을 `assignee_email_drawer.html` wrapper 안에 렌더링하도록 했다.
- My Work 상세 버튼과 우측 패널의 `상세 열기` 버튼을 `#assigneeEmailDetailDrawer` 대상으로 연결했다.
- shell JS에 My Work drawer 열기, 닫기, Escape 닫기, 외부 클릭 닫기, HTMX afterSwap 초기화를 추가했다.
- CSS에 My Work 오른쪽 drawer 레이아웃과 drawer 내부 상세 카드 평탄화 스타일을 추가했다.
- 관련 템플릿/route/shell 동작 테스트를 추가하고 기존 기대 경로를 새 drawer 경로로 갱신했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "my_work_email_drawer or assignee_work_template_renders_selected_workload or my_work_detail_drawer_closes or shell_resizes_email_body_frames"`: 4 passed.
- `uv run pytest tests/test_mail_decision_ui.py`: 163 passed.
- `git diff --check`: passed.
- `docker compose restart web`: completed.
- 담당자 쿠키로 `http://127.0.0.1:8000/?view=my-work` 요청: 200, `assigneeEmailDetailDrawer`, `/ui/my-work/emails/...`, `data-assignee-detail-open` HTML 확인.
- 첫 번째 drawer URL `/ui/my-work/emails/83085804-57f9-5ead-af71-a200fdae85db` 요청: 200, `assignee-detail-drawer-shell`, `data-assignee-detail-close`, `detail-card`, `message-panel` HTML 확인.
- `http://127.0.0.1:8000/api/health`: 200.

## 남은 리스크와 후속 작업

- Browser 플러그인은 사용 가능 목록에 없고, Node/Python Playwright 및 Chromium 계열 브라우저도 설치되어 있지 않아 실제 클릭/스크린샷 검증은 수행하지 못했다. 서버 HTML, route, 템플릿, JS 문자열 테스트는 통과했다.
- 작업 전부터 존재하던 `docs/development/reports/` untracked 폴더는 이번 요청과 무관해 그대로 두었다.

---

# 2026-08-24 - My Work 업무 화면 UI 재구성

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | My Work tab, assignee dashboard drilldown, assignment workload UI |
| 관련 파일 | `app/templates/views/assignee_work.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 담당자 계정에서 Dashboard의 `My Work`를 눌러 이동하는 현재 할당 업무 현황 탭의 UI 구성을 처음부터 다시 재구성해 달라고 요청했다.

## 확인한 사실

- `My Work` 탭은 이전 변경으로 `/ui/my-work`와 기존 담당자 업무 context/template을 재사용하고 있었다.
- 화면은 담당자별 할당 업무, 상태 필터, 상세/회신/완료 액션을 이미 갖고 있었지만, 정보 구조가 단일 리스트 중심이라 대시보드에서 진입한 업무 집중 화면으로는 우선순위와 다음 액션이 충분히 드러나지 않았다.
- 렌더링 도구 확인 결과 현재 환경에는 Playwright와 Chromium 계열 브라우저가 없어 실제 브라우저 스크린샷 검증은 수행할 수 없었다.

## 해결 방법

- 이미지 생성으로 새 엔터프라이즈 업무 대시보드 콘셉트를 만들고, 이를 기준으로 My Work 화면을 명령 헤더, 핵심 상태 카드, 업무 큐 레일, 중앙 업무 테이블, 선택 업무 패널 구조로 재구성했다.
- 기존 HTMX 상태 필터와 상세/회신/완료 액션 경로는 유지하면서, 현재 선택된 첫 업무의 요약, 근거 참조, 담당자/업무 유형/수신일시 정보를 우측 패널에 배치했다.
- 반응형 CSS를 새로 정리해 데스크톱에서는 3열 업무 워크벤치로, 중간 화면에서는 선택 패널을 아래로, 모바일에서는 단일 컬럼과 가로 스크롤 큐로 전환되게 했다.
- 기존 테스트가 기대하던 업무 상태 라벨 접근성 텍스트를 유지하고, 새 구조의 핵심 영역 렌더링을 테스트에 추가했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "assignee_work or my_work or non_dashboard_typography"`: 9 passed.
- `uv run pytest tests/test_mail_decision_ui.py`: 161 passed.
- `git diff --check`: passed.
- `docker compose restart web`: completed.
- 담당자 쿠키로 `http://127.0.0.1:8000/?view=my-work` 요청: 200, `data-view="my-work"`, `work-queue-rail`, `현재 할당 업무`, `assignee-next-panel`, `선택된 업무` HTML 확인.
- `http://127.0.0.1:8000/api/health`: 200.

## 남은 리스크와 후속 작업

- 실제 브라우저 픽셀/스크린샷 검증은 Playwright 및 로컬 브라우저 부재로 수행하지 못했다. 서버 HTML 구조와 테스트는 통과했다.
- 작업 전부터 존재하던 `docs/development/reports/` untracked 폴더는 이번 요청과 무관해 그대로 두었다.
- UI 콘셉트 이미지는 `/home/ysh/.codex/generated_images/01a03175-13fd-7120-a5ba-3a23f137ed9b/call_SJ0DbpOHYYWMTvTnug4JONP4.png`에서 확인했다.

---

# 2026-08-24 - 담당자 계정 My Work 탭 진입 구조

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard, My Work tab, assignee navigation, assignments replacement |
| 관련 파일 | `app/server.py`, `app/templates/shell.html`, `app/templates/partials/stats.html`, `app/templates/views/assignee_work.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 담당자 계정 로그인 시 `Assignments` 탭 대신 Dashboard의 `My Work` 부분을 클릭해 현재 할당 업무 현황을 확인할 수 있는 탭으로 이동하게 해 달라고 요청했다.

## 확인한 사실

- 기존 담당자 업무 현황 화면은 `/ui/assignees`와 `views/assignee_work.html`에 있었고, 관리자에게는 전체 담당자 업무 현황으로 의미가 맞지만 담당자 계정에는 `Assignments` 라벨이 관리 화면처럼 보일 수 있었다.
- 이전 대시보드 변경으로 담당자 스코프에서는 stats 첫 카드가 `My Work`로 표시되지만, 해당 카드는 이동 동작이 없는 정적 카드였다.
- 업무 현황 화면 내부 상태 필터는 route를 고정 `/ui/assignees`로 사용하고 있어, 새 탭 경로를 만들면 내부 필터도 같은 경로를 유지해야 했다.

## 해결 방법

- `/ui/my-work` GET/POST route와 `view=my-work` 초기 진입을 추가하고 기존 담당자 업무 context/template을 재사용했다.
- 담당자 계정 사이드바에서는 `Assignments` 대신 `My Work` 탭을 표시하고, 관리자 계정은 기존 `Assignments` 탭을 유지한다.
- Dashboard 담당자용 `My Work` stats 카드를 HTMX 버튼으로 바꿔 `/ui/my-work`로 이동하게 했다.
- `assignee_work.html`이 `assignee_work_endpoint`와 `assignee_work_view_name`을 받아 `/ui/assignees`와 `/ui/my-work` 양쪽에서 내부 검색, 담당자 선택, 상태 필터 경로를 유지하도록 했다.
- shell history/title mapping에 `my-work`와 `status` query 보존을 추가했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "my_work or assignee_login_dashboard_context or shell_uses_single_htmx_path"`: 3 passed.
- `uv run pytest tests/test_mail_decision_ui.py`: 161 passed.
- `git diff --check`: passed.

## 남은 리스크와 후속 작업

- 브라우저 스크린샷 검증은 실행하지 않았다. 변경은 route, Jinja 렌더링, HTMX 경로 연결이며 관련 UI 테스트는 통과했다.
- 작업 시작 전에 이미 존재하던 `app/templates/views/ops.html`, `db/postgresql/006_work_reply_tracking.sql`, `docs/development/reports/` 변경은 이번 요청 커밋에서 제외한다.

---

# 2026-08-24 - 담당자 계정용 대시보드 업무 stats 구성

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard, assignee login, work status stats, access scoped rows |
| 관련 파일 | `app/server.py`, `app/templates/partials/stats.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 담당자 계정으로 로그인했을 때 대시보드가 해당 담당자의 업무와 관련된 stats로 구성되도록 구현해 달라고 요청했다.

## 확인한 사실

- 기존 담당자 업무 화면은 로그인 사용자와 담당자 이메일/이름/user_id를 비교해 볼 수 있는 업무 rows를 제한하는 흐름을 갖고 있었다.
- 대시보드는 `dashboard_context()`가 요청 객체를 받지 않아 stats, category distribution, routing overview, mail rows refresh가 전체 메일 기준으로 계산될 수 있었다.
- `/ui/mail-rows`는 대시보드 폴링과 수동 라우팅 후 부분 갱신에 사용되므로, 초기 렌더링만 제한하면 갱신 시 전체 rows가 다시 노출될 수 있었다.

## 해결 방법

- `dashboard_context(request)`와 `dashboard_rows_for_request()`를 추가해 비관리자 로그인에서는 대시보드 summary, charts, routing overview, mail rows를 본인 담당 업무 rows로 제한했다.
- 담당자 스코프에서는 stats 카드를 `My Work`, `Unacknowledged`, `In Progress`, `Responded`, `Completed`, `Overdue` 중심으로 렌더링하고 조직 전체용 Today/Urgent/Classified/Routed/Forwarded 카드는 숨겼다.
- `dashboard_summary()`에 업무 상태, 기한 초과, 오늘 완료 카운트를 추가했다.
- `/ui/dashboard`, `/ui/stats`, dashboard chart partials, dashboard mail rows, 수동 라우팅 후 refresh가 모두 request-scoped dashboard context를 사용하도록 연결했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "assignee_login_dashboard_context or demo_dashboard_context_exposes_today_and_all_chart_scopes or dashboard_summary_excludes_unclassified"`: 3 passed.
- `uv run pytest tests/test_mail_decision_ui.py`: 160 passed.
- `git diff --check`: passed.

## 남은 리스크와 후속 작업

- 브라우저 스크린샷 검증은 실행하지 않았다. 변경은 request-scoped 서버 컨텍스트와 Jinja 조건 렌더링이며 관련 UI 테스트는 통과했다.
- 작업 시작 전에 이미 존재하던 `app/static/app.css`, `app/templates/views/assignee_work.html`, `app/templates/views/ops.html`, `db/postgresql/006_work_reply_tracking.sql`, `docs/development/reports/` 변경은 이번 요청 커밋에서 제외한다.

---

# 2026-08-24 - 담당자 계정 업무 범위 제한과 업무 액션 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Assignee Work, Monitoring, work_items, 담당자 권한 |
| 관련 파일 | `app/server.py`, `app/templates/shell.html`, `app/templates/partials/stats.html`, `app/templates/views/assignee_work.html`, `app/templates/views/ops.html`, `app/static/app.css`, `db/postgresql/006_work_reply_tracking.sql`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 담당자 계정 로그인 시 기본 권한이 Monitoring, Assignments 등에서 본인이 맡은 업무만 확인 가능해야 한다고 요청했다.
- 기존 담당자 화면은 미확인, 진행중, 회신함, 완료 통계만 표시하고 해당 상태와 연계된 실질적인 담당자 액션이 부족했다.

## 확인한 사실

- 담당자 화면의 assignee 필터는 URL 파라미터 중심이라 일반 담당자가 다른 담당자 값을 넣으면 타인 업무를 볼 수 있는 여지가 있었다.
- Monitoring 컨텍스트도 담당자 로그인 기준 업무 범위 제한을 적용하지 않았다.
- 이전 작업에서 `work_items` 테이블은 추가됐지만 기존 `routing_assignments` 운영 데이터에 대한 work item 백필이 없어 상태별 업무 액션 대상 데이터가 부족했다.

## 해결 방법

- 요청 사용자 기준으로 업무 행을 필터링하는 서버 공통 함수를 추가하고 Assignments, Monitoring, 메일 상세/검사 엔드포인트에 적용했다.
- 담당자 권한이 아닌 계정은 본인의 이름, 이메일, 사용자 ID와 매칭되는 업무만 볼 수 있게 하고, 관리자 계정은 전체 담당자 업무를 유지했다.
- 일반 담당자 로그인에서는 상단 내비게이션의 Assignments를 My Work로 대체하고, 대시보드의 My Work 카드가 담당자 전용 업무 화면으로 이동하게 했다.
- Assignments와 Monitoring의 통계 카드를 클릭 가능한 상태 필터로 바꿔 미확인, 진행중, 회신함, 완료/지연/오늘 완료 상태별 목록을 바로 볼 수 있게 했다.
- 담당자 업무 행에 상세 열기, 답장, 업무 완료 액션을 추가했다. 상세 열기는 업무 확인 상태로 전환하고, 완료 액션은 work item 완료 처리 후 화면을 새로고침한다.
- 기존 라우팅 배정 데이터에서 `work_items`를 백필하는 PostgreSQL 마이그레이션 구문을 추가했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 159 passed.
- `git diff --check`: passed.
- `docker compose exec -T web python -m app.tools.apply_postgres_schema`: applied 6 schema files, including `006_work_reply_tracking.sql`.
- Local dev DB 확인: `work_items` status `assigned` 1,275건.
- `docker compose restart web`: web restarted.
- 담당자 계정 `m.kim@dawonict.co.kr`으로 로그인한 컨테이너 내부 HTTP 확인에서 Assignments/Monitoring 모두 김민수 업무만 렌더링되고 박지현 업무는 제외됨을 확인했다.
- 같은 담당자 화면에서 `/work/reply-initiate`, `/work/complete` 액션 마크업이 렌더링됨을 확인했다.

## 남은 리스크와 후속 작업

- 전체 테스트 `uv run pytest -q`는 이번 변경과 직접 관련 없는 Documents 탭 기대값 2개가 실패했다. 현재 코드의 Documents 임시 숨김/내비게이션 상태와 테스트 기대값이 맞지 않는 기존 불일치로 보이며, 이번 담당자 권한 변경 범위에서는 수정하지 않았다.
- 담당자 계정/비밀번호가 포함된 Word 리포트는 로컬 산출물로 유지하고 커밋에서 제외한다.

---

# 2026-08-24 - Monitoring 상단 중복 제목 제거

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring tab, ops header, compact UI |
| 관련 파일 | `app/templates/views/ops.html`, `app/static/app.css` |

## 요청 또는 배경

- 사용자는 Monitoring 탭에 제목 영역이 2개 보이며, 검색 왼쪽에 있는 Monitoring 제목 영역과 아이콘을 제거해 달라고 요청했다.

## 확인한 사실

- Monitoring 화면 상단의 검색 폼 왼쪽에 `.ops-title` 블록이 별도로 있고, 여기에서 `monitoring` 아이콘과 `Monitoring` H1을 렌더링하고 있었다.
- 탭 내비게이션의 Monitoring 라벨은 별도 영역이므로 이번 요청 범위에서 유지해야 한다.

## 해결 방법

- `app/templates/views/ops.html`에서 검색 폼 왼쪽의 `.ops-title` 마크업을 제거했다.
- 더 이상 사용하지 않는 `.ops-title` 전용 CSS와 typography refinement 중복 선언을 정리했다.
- 검색, 카테고리 필터, 새로고침, 컬럼 선택 컨트롤은 그대로 유지했다.

## 검증

- `rg -n "ops-title|<h1>Monitoring</h1>|aria-hidden=\"true\">monitoring" app/templates app/static/app.css`: no matches.
- `uv run pytest tests/test_mail_decision_ui.py`: 155 passed.

## 남은 리스크와 후속 작업

- 브라우저 스크린샷 검증은 실행하지 않았다. 변경은 정적 템플릿/CSS 제거이며 관련 렌더링 테스트는 통과했다.
- 기존 `docs/development/reports/` untracked 디렉터리는 이번 작업 산출물이 아니므로 보존하고 커밋에서 제외한다.

---

# 2026-08-24 - Chats 이전 턴을 별도 conversation context로 전달

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Chats tab, conversation context, MailSearchService prompt contract |
| 관련 파일 | `app/services/mail_chat_service.py`, `app/services/mail_search_service.py`, `tests/test_mail_decision_ui.py`, `tests/test_mail_search_service.py` |

## 요청 또는 배경

- 사용자는 후속 질문이 생뚱맞은 답변을 하지 않게 하려면 해당 세션의 이전 채팅 기록을 context로 넣어줘야 한다고 지적했다.

## 확인한 사실

- 이전 구현은 대화 기록을 검색 query에 직접 섞는 문제를 제거했지만, `MailSearchService`에는 이전 턴이 별도 context로 전달되지 않았다.
- 후속 질문을 안정적으로 처리하려면 현재 질문은 검색 query로 보존하고, 이전 질문/답변은 planner와 answer prompt의 별도 conversation context로 제공해야 한다.

## 해결 방법

- `MailSearchService.search()`에 `conversation_context` 선택 인자를 추가했다.
- `MailChatService`가 서버 세션의 이전 turn을 `이전 질문/이전 답변/이전 검색 질의` 형식의 compact context로 만들어 search service에 전달하게 했다.
- Search planner와 answer prompt에 conversation context block을 추가하되, 현재 질문이 authoritative이고 context가 현재 질문의 구체적 식별자·의도·필터를 덮어쓰지 못한다는 규칙을 명시했다.
- 기존 단발 Search 호출은 `conversation_context=""` 기본값으로 유지했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "chats or mail_chat or shell_installs_search_fallback" -q`: 9 passed.
- `uv run pytest tests/test_mail_search_service.py -k "conversation_context or embedding_retrieval" -q`: 2 passed.
- `python -m py_compile app/server.py app/services/mail_chat_service.py app/services/mail_search_service.py`: passed.
- `git diff --check`: passed.
- `uv run pytest tests/test_mail_decision_ui.py tests/test_mail_search_service.py -q`: 174 passed.
- `docker compose restart web`: web restarted.
- 실제 서버에서 첫 질문 후 반환된 `session_id`로 후속 질문을 보내 같은 스레드에 이전 질문과 현재 질문이 함께 렌더링되는 것을 확인했다.
- 단위 테스트에서 후속 질문 search call이 현재 질문 기반 query와 별도 `conversation_context`를 함께 받는 것을 직접 캡처했다.

## 남은 리스크와 후속 작업

- Conversation context는 현재 prompt 입력에만 쓰이며, DB 영속 memory는 아직 없다.
- 참조 해소는 여전히 업무 식별자 중심이다. `그 발신자`, `그 첨부`, `방금 근거의 두 번째 문서` 같은 질의는 dedicated chat tool resolver가 필요하다.
- `docs/development/reports/` untracked 파일은 이번 작업 산출물이 아니므로 보존하고 커밋에서 제외한다.

---

# 2026-08-24 - Chats 탭 서버 세션 기반 Chat Service 분리

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Chats tab, MailChatService, server-side session, query grounding |
| 관련 파일 | `app/services/mail_chat_service.py`, `app/server.py`, `app/templates/views/chats.html`, `app/templates/partials/chats_results.html`, `app/templates/shell.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 이전 구현이 실제 챗봇처럼 보이지 않고 주먹구구식이라고 지적하며, 다른 챗봇을 만들듯이 구현해 달라고 요청했다.

## 확인한 사실

- 이전 구현은 `MailSearchService`에 hidden `history` JSON을 붙여 호출하는 방식이라 UI 상태와 검색 쿼리 해석 책임이 섞여 있었다.
- 실제 챗봇 기능의 최소 책임 경계는 세션, 메시지, 후속 질문 해석, 검색 tool 호출, 응답 렌더링이 분리되어야 한다.
- DB 영속 테이블까지 추가하지 않아도, 현재 단계에서는 서버 메모리 세션 저장소로 브라우저 hidden history 조작 문제를 제거할 수 있다.

## 해결 방법

- `app/services/mail_chat_service.py`를 추가해 `MailChatSessionStore`, `MailChatService`, `MailChatTurn`을 분리했다.
- Chats UI는 대화 history JSON 대신 `session_id`만 들고 다니도록 바꿨다.
- `/ui/chats-results`는 서버 세션의 이전 turn을 기준으로 후속 질문을 해석하고, `MailSearchService`는 chat service가 결정한 search query만 받는다.
- HTMX 응답은 OOB로 `chatSessionInput`만 갱신한다.
- 후속 질문 resolver는 명확한 현재 업무 식별자가 있으면 history를 섞지 않고, 생략형 질문일 때만 이전 turn에서 업무 식별자만 최소 보강한다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "chats or mail_chat or shell_installs_search_fallback" -q`: 9 passed.
- `python -m py_compile app/server.py app/services/mail_chat_service.py`: passed.
- `git diff --check`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 155 passed.
- `docker compose restart web`: web restarted.
- 실제 서버 `POST /ui/chats` 응답에서 hidden `history`가 사라지고 `chatSessionInput`만 렌더링되는 것을 확인했다.
- 실제 서버 첫 질문 응답에서 OOB `chatSessionInput`이 반환되는 것을 확인했다.
- 같은 `session_id`로 후속 질문을 보내 이전 질문과 후속 질문이 같은 스레드에 누적되는 것을 확인했다.

## 남은 리스크와 후속 작업

- 현재 세션 저장소는 서버 메모리 기반이라 web 프로세스 재시작 시 대화 이력은 사라진다. 운영형 챗봇으로 가려면 PostgreSQL chat sessions/messages 테이블과 사용자별 권한 범위를 추가해야 한다.
- 후속 질문 해석은 아직 업무 식별자 중심이다. `그 업체`, `그 발신자`, `마지막 근거의 첨부` 같은 참조는 별도 resolver/tool contract가 필요하다.
- `docs/development/reports/` untracked 파일은 이번 작업 산출물이 아니므로 보존하고 커밋에서 제외한다.

---

# 2026-08-24 - Chats 후속 질문 검색 오염 원인 수정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Chats tab, multi-turn query grounding, search relevance |
| 관련 파일 | `app/server.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Chats 탭이 입력 쿼리에 맞게 답변해야 하며, 질문과 생뚱맞은 답변을 하는 근본 원인을 파악해 해결해 달라고 요청했다.

## 확인한 사실

- 직전 multi-turn 구현은 후속 질문 처리를 위해 이전 질문과 이전 답변 전체를 현재 질문 앞에 붙여 `MailSearchService.search()`에 전달했다.
- 이 방식은 현재 사용자 입력보다 이전 턴의 `가장 최신 메일`, 긴 제목, 발신자, 날짜, 과거 식별자 토큰이 planner와 retrieval에 더 강하게 반영될 수 있다.
- 그 결과 사용자가 명확한 새 질문을 입력해도 이전 턴의 맥락이 검색 의도와 후보 랭킹을 오염시켜 엉뚱한 답변으로 이어질 수 있었다.

## 해결 방법

- Chats의 effective query 생성 정책을 바꿔 현재 사용자 입력을 기본 검색 쿼리로 보존한다.
- `그`, `해당`, `이전`, `이 메일`, `이 견적서` 같은 생략 표현이 있거나 `납기는?` 같은 짧은 필드 후속 질문일 때만 이전 턴에서 업무 식별자를 추출해 현재 질문 뒤에 최소 제약으로 붙인다.
- 이전 답변 전체, 이전 질문 전체, 설명 문장, 발신자 이메일 local-part는 더 이상 검색 쿼리에 섞지 않는다.
- 명확한 신규 업무 식별자가 현재 질문에 있으면 history를 전혀 보강하지 않는다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "chats_results_uses_history or concrete_query or chat_effective_query or chats or shell_installs_search_fallback" -q`: 9 passed.
- `python -m py_compile app/server.py`: passed.
- `git diff --check`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 154 passed.
- `docker compose restart web`: web restarted.
- 실제 서버에서 QT history를 포함한 `q=그 견적서 납기는?` 응답이 이전 턴과 현재 턴을 같은 스레드로 유지하고 history를 갱신하는 것을 확인했다.
- 실제 서버에서 같은 QT history를 포함한 명확한 새 질문 `q=URG-DEMO-2026-0810-01 긴급 장애 메일 찾아줘`가 현재 질문 턴으로 렌더링되는 것을 확인했다. 검색 서비스에 전달되는 쿼리가 history에 오염되지 않는지는 단위 테스트에서 직접 캡처했다.

## 남은 리스크와 후속 작업

- 현재 보강은 업무 식별자 기반의 1차 follow-up resolver다. `그 업체`, `그 발신자`, `그 메일의 첨부`처럼 식별자가 없는 참조 해소는 별도 대화 memory/tool contract가 필요하다.
- `docs/development/reports/` untracked 파일은 이번 작업 산출물이 아니므로 보존하고 커밋에서 제외한다.

---

# 2026-08-24 - Chats 탭 multi-turn 채팅으로 재구현

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Chats tab, multi-turn chat history, HTMX loading state, frontend QA |
| 관련 파일 | `app/server.py`, `app/templates/views/chats.html`, `app/templates/partials/chats_results.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Chats 탭을 더 채팅처럼 다시 구현하고, 로딩 화면과 채팅 스레드 경험을 포함해 달라고 요청했다.
- 이어서 Search 탭 기능을 그대로 옮긴 것이 아니라 Chats 기능에 맞게 계속 대화할 수 있도록 개선해 달라고 정정했다.

## 확인한 사실

- 기존 Chats 구현은 결과를 말풍선으로 보여주지만, 로딩 상태가 스레드 안의 메시지가 아니라 별도 패널처럼 분리되어 있었다.
- Search/Chats 예시 버튼은 입력값만 채우고 자동 submit하지 않아야 하는 기존 UX 규칙을 유지해야 한다.
- 현재 환경에는 Browser 플러그인과 Playwright 런타임이 없어 실제 스크린샷 검증은 불가능했다.
- 서버 세션 저장소를 새로 만들지 않고도 HTMX form의 hidden `history` payload로 같은 화면의 대화 턴을 이어갈 수 있다.

## 해결 방법

- Chats view에 `data-chat-thread`, `data-chat-composer`, hidden `history`, `chatPendingTemplate`을 추가했다.
- HTMX submit 직전 기존 스레드를 보존한 채 사용자 질문 말풍선과 AI typing/loading 말풍선을 뒤에 붙이도록 shell JS를 보강했다.
- 최종 결과 partial은 이전 턴과 새 턴을 모두 렌더링하고, 새 턴의 AI 답변과 근거 패널을 하나의 assistant message group 안에 표시하도록 재구성했다.
- `/ui/chats-results`가 이전 history를 받아 현재 질문과 함께 effective query를 만들고, 후속 질문의 생략 표현이 마지막 질문/답변 맥락을 보존하도록 했다.
- HTMX 응답은 `chatHistoryInput`을 OOB swap으로 갱신해 다음 질문이 직전 대화 history를 포함하게 한다.
- 오류도 일반 notice가 아니라 채팅 스레드 안의 오류 말풍선으로 표시한다.
- CSS에서 loading 중 결과 body를 숨기는 규칙을 제거하고, sticky composer, thread scroll 영역, typing dots animation, 모바일 보정을 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "chats or shell_installs_search_fallback or root_can_render_chats or direct_chats" -q`: 7 passed.
- `python -m py_compile app/server.py`: passed.
- `git diff --check`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 152 passed.
- `docker compose restart web`: web restarted.
- 실제 서버 `POST /ui/chats` 응답에서 `data-chat-thread`, `chatHistoryInput`, `chatPendingTemplate`이 렌더링되고 초기 hidden input이 한 번만 나타나는 것을 확인했다.
- 실제 서버 `GET /ui/chats-results?q=가장 최신 메일이 뭐야&limit=5` HTMX 응답에서 `chat-message-user`, `chat-message-group-assistant`, `chat-answer-bubble`, `chat-evidence-panel`, `근거`, OOB `chatHistoryInput`이 렌더링되는 것을 확인했다.
- 실제 서버에 이전 history를 포함해 `q=그 견적서 납기는?`를 요청했고, 응답에서 이전 질문과 현재 질문이 같은 스레드에 함께 렌더링되고 OOB history가 두 턴으로 갱신되는 것을 확인했다.

## 남은 리스크와 후속 작업

- Browser 플러그인과 Playwright가 없어 스크린샷, 실제 클릭, console 로그 검증은 수행하지 못했다.
- 서버 DB에 대화 이력을 영속 저장하지는 않는다. 현재 대화 지속은 브라우저 form history payload 기반이다.
- 생략형 후속 질문은 최근 질문/답변을 effective query에 포함하는 1차 보강이며, 별도 intent resolver나 대화 memory store는 아직 없다.
- `docs/development/reports/` untracked 파일은 이번 작업 산출물이 아니므로 보존하고 커밋에서 제외한다.

---

# 2026-08-24 - Demo Inbox 담당자 UUID 표시 근본 수정과 POST fragment 복원

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode, Inbox receiver display, Mail Decision panel, HTMX navigation |
| 관련 파일 | `app/server.py`, `app/templates/shell.html`, `app/templates/views/inbox.html`, `app/templates/partials/mail_rows.html`, `app/templates/partials/email_detail.html`, `app/templates/partials/document_type_sections.html`, `app/templates/views/assignee_work.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 데모 모드 Inbox에서 김민수 담당자가 `10000000-0000-0000-0000-000000000001`로 계속 표시된다고 재보고했다.
- Settings에는 김민수 이름과 이메일이 정상 저장되어 있고, Inbox 메일 영역에는 이메일이 보이므로 표면 치환이 아니라 데이터 병합 경로의 근본 원인 파악이 필요했다.
- 사용자는 어느 시점부터 탭과 Inbox 메일 전환이 GET으로 동작하는 것 같다고 지적했고, 이전처럼 POST 기반 동적 표시를 선호한다고 했다.

## 확인한 사실

- `mail_decision_decision_view()`는 `context.routing_users`가 비어 있는 Mail Decision 후보에 대해 후보 이름을 `user_id`로 채웠다.
- 이후 `manual_assignment_candidate_rows()`가 Settings/manual assignment option의 `assignee_name`을 가져오더라도 `{**option, **candidate}` 병합 순서 때문에 후보의 `name=UUID`가 김민수 표시명을 다시 덮어썼다.
- 템플릿은 `candidate.name or candidate.assignee_name` 순서로 렌더링하므로, Settings 데이터가 정상이어도 패널에서는 UUID가 이름 위치에 표시될 수 있었다.
- 실행 중인 web 컨테이너를 재시작하지 않으면 코드 수정 후에도 브라우저에서 이전 동작이 보일 수 있다.

## 해결 방법

- Mail Decision 후보 view에서 이름 fallback으로 `user_id`를 사용하지 않게 바꿨다.
- 수동 배정 옵션과 라우팅 후보를 합칠 때 Settings의 `assignee_name`, `email_address`, `department`, `position`이 표시 필드에서 우선되도록 병합 순서를 고쳤다.
- `context.routing_users`가 없는 후보도 Settings 배정 옵션으로 김민수와 이메일을 렌더링하는 회귀 테스트를 추가했다.
- 메인 탭 fragment 라우트와 Inbox 메일 목록/상세 선택 라우트에 POST handler를 추가하고, HTMX nav와 Inbox interaction을 `hx-post`로 되돌렸다. 직접 접근 호환을 위해 기존 GET handler는 유지했다.
- Docker web 컨테이너를 재시작해 실행 중인 데모 서버가 새 코드를 반영하도록 했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 149 passed.
- `docker compose restart web`: web restarted.
- 실제 서버에서 로그인 후 `POST /ui/inbox`, `POST /ui/mail-rows`, `POST /ui/emails/83085804-57f9-5ead-af71-a200fdae85db` fragment 응답을 확인했다.
- 실제 Mail Decision latest 응답에서 문제 담당자는 `<strong>김민수</strong>`와 `m.kim@dawonict.co.kr`로 표시되고, `<strong>10000000-0000-0000-0000-000000000001</strong>`는 나타나지 않았다.
- 실제 shell/inbox/mail-rows HTML에서 탭 및 Inbox 메일 선택 경로가 `hx-post`로 렌더링되고, 해당 범위의 `/ui/...` GET navigation은 남아 있지 않음을 확인했다.

## 남은 리스크와 후속 작업

- Search/Chats 결과 조회, Monitoring polling, Mail Decision 최신 상태 polling처럼 조회 의미가 강한 fragment는 GET을 유지했다.
- `docs/development/reports/` untracked 파일은 이번 작업 산출물이 아니므로 보존하고 커밋에서 제외한다.

---

# 2026-08-24 - Search 기반 Chats 탭 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Chats tab, Search RAG UI, HTMX navigation, context search feature contract |
| 관련 파일 | `app/server.py`, `app/templates/shell.html`, `app/templates/views/chats.html`, `app/templates/partials/chats_results.html`, `app/static/app.css`, `docs/features/context-search-qdrant-indexing.md`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 현재 Search 탭을 발전시킨 Chats 탭을 기획한 뒤 구현해 달라고 요청했다.

## 확인한 사실

- 기존 Search 탭은 `MailSearchService`를 통해 메일 본문, 첨부 분석, `MailFacts` 기반 근거 제한 RAG 답변을 생성한다.
- 이전 UI 규칙상 Search 예시 버튼은 검색을 자동 실행하지 않고 입력값만 채워야 한다.
- 현 단계에서 서버에 대화 이력을 저장하는 계약은 없으므로, Chats는 기존 검색 엔진을 공유하는 1턴 대화형 화면으로 시작하고 후속 질문 이력 저장은 별도 확장점으로 분리하는 것이 안전하다.

## 해결 방법

- Shell 네비게이션, root `view=chats`, `/ui/chats`, `/ui/chats-results`를 추가했다.
- `views/chats.html`과 `partials/chats_results.html`을 새로 만들어 질문/답변 말풍선, 로딩 상태, 근거 카드, 원본 메일 링크를 렌더링한다.
- 기존 Search fallback JS를 확장해 Chats 예시 버튼도 지정된 입력창만 채우고 자동 submit하지 않게 했다.
- Chats 전용 CSS와 공통 비대시보드 타이포그래피 스케일을 추가했다.
- 검색 기능 문서에 Chats 탭의 현재 범위와 서버 저장 이력 미구현 경계를 기록했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "chats or search_view or shell_installs_search_fallback or root_can_render_search or direct_search_results or shell_keeps_fragment" -q`: 11 passed.
- `python -m py_compile app/server.py`: passed.
- `git diff --check`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 148 passed.

## 남은 리스크와 후속 작업

- 현재 Chats는 1턴 질의 화면이며 서버 세션별 대화 이력, 이전 근거 참조, 생략형 후속 질문 resolve는 아직 구현하지 않았다.
- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 화면 회귀가 우려되면 데모 서버에서 desktop/mobile 렌더링을 추가 확인한다.

---

# 2026-08-24 - Implement work reply tracking foundation

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Work tracking, shared Gmail reply detection, user authentication, Monitoring, Assignee work |
| 관련 파일 | `db/postgresql/006_work_reply_tracking.sql`, `app/repositories/postgres_work_tracking_repository.py`, `app/repositories/postgres_user_repository.py`, `app/integrations/gmail/sync_client.py`, `app/services/gmail_mail_service.py`, `app/server.py`, `app/templates/partials/email_detail.html`, `app/templates/views/ops.html`, `app/templates/views/assignee_work.html`, `docs/architecture/postgresql_schema.md`, `docs/features/notifications-work-status.md`, `tests/test_gmail_persistent_mode.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 담당자별 배정 수만 보여주는 현재 Routing Overview/Monitoring을 넘어, 공용 Gmail 계정 환경에서 CoRA 로그인 사용자와 Gmail thread outbound activity를 결합해 담당자가 업무를 확인하고 실제 고객 회신까지 수행했는지 추적하는 기반 구현을 요청했다.

## 확인한 사실

- 기존 인증은 서명 쿠키에 username만 저장하고 DB `users.id`와 직접 연결하지 않았다.
- `routing_assignments.status`는 라우팅 상태와 수동 내부 전달 상태에 쓰이고 있어 `unread`, `in_progress`, `responded`, `completed` 같은 업무 수행 상태를 섞으면 의미 충돌이 생긴다.
- 기존 `fetch_inbox_messages()`와 `GmailMailboxService.sync()`는 `INBOX` 수신 메일 ingestion, 첨부 저장, 분석 job 생성 용도이며 SENT 발신 activity를 섞으면 기존 목록/분석/라우팅 대상이 오염된다.
- 공용 Gmail 계정에서는 Gmail `From`만으로 실제 직원 작성자를 식별할 수 없으므로, CoRA의 authenticated reply initiation actor와 이후 동일 Gmail thread outbound message를 연결하는 정책이 필요하다.

## 해결 방법

- `users.username`, `users.password_hash`, `work_items`, `work_events`, `gmail_outbound_messages`를 추가하는 새 PostgreSQL migration을 만들었다.
- DB 사용자 로그인은 PBKDF2 password hash를 사용하고, 기존 단일 관리자 `AUTH_USERNAME`/`AUTH_PASSWORD`는 migration 전 DB와 호환되도록 fallback으로 유지했다.
- 라우팅 자동 배정과 수동 확정 시 `work_items`를 생성/갱신하고, 재배정 시 이전 담당자의 확인/회신 시작/회신 완료 상태가 새 담당자에게 이어지지 않도록 현재 상태를 초기화한다.
- 담당자 본인이 업무 상세를 열 때만 `acknowledged`, `답장`을 누를 때만 `reply_initiated`, `업무 완료`를 누를 때만 `completed` 이벤트를 기록한다. 관리자나 다른 담당자는 서버에서 차단한다.
- Gmail SENT 조회 함수와 `GmailMailboxService.sync_outbound_activity()`를 추가해 Inbox ingestion과 분리된 발신 metadata sync를 구현했다. 동일 thread, reply initiation 이후, 아직 연결되지 않은 outbound message만 `responded`로 연결한다.
- Monitoring KPI는 미확인, 진행중, 회신함, 지연, 오늘 완료 중심으로 바꾸고, 담당자 업무 화면도 업무 수행 상태 중심으로 조정했다. 기존 분석 pipeline table과 수동 내부 전달 기능은 유지했다.
- 구조적 한계와 상태 모델을 `docs/architecture/postgresql_schema.md`, `docs/features/notifications-work-status.md`에 기록했다.

## 검증

- `uv run python -m app.tools.apply_postgres_schema --dry-run`: 6 files, 107 statements.
- `python -m py_compile app/server.py app/integrations/gmail/sync_client.py app/services/gmail_mail_service.py app/repositories/postgres_routing_repository.py app/repositories/postgres_user_repository.py app/repositories/postgres_work_tracking_repository.py app/services/postgres_mail_service.py app/repositories/postgres_mail_repository.py`: passed.
- `uv run pytest tests/test_gmail_persistent_mode.py tests/test_mail_decision_ui.py -q`: 154 passed.
- `uv run pytest -q`: 377 passed, 1 existing collection warning.

## 남은 리스크와 후속 작업

- Gmail URL은 `https://mail.google.com/mail/u/0/#inbox/{threadId}` 형식으로 열며, 여러 Google 계정 선택이나 Gmail UI 변경에는 한계가 있다.
- 공용 Gmail 구조상 실제 작성자를 Gmail만으로 증명할 수 없다. 현재 정책은 가장 최근 유효한 CoRA reply initiation actor를 outbound message 수행자로 연결한다.
- 복잡한 SLA 정책, LLM 자동 완료 판정, CoRA 내부 메일 작성/발송 UI는 이번 범위에서 제외했다.

---

# 2026-08-24 - Remove assignee UUID from Inbox navigation params

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox assignee chip, Assignee work view, Docker dev server reload |
| 관련 파일 | `app/templates/partials/mail_rows.html`, `app/server.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 이전 수정 후에도 데모 모드 Inbox에서 김민수 담당자가 UUID처럼 보인다고 재보고했다.

## 확인한 사실

- 실제 `/ui/inbox` 응답의 visible chip text는 `김민수`로 바뀌었지만, `hx-get="/ui/assignees?assignee=10000000-0000-0000-0000-000000000001"` 같은 UI 이동 파라미터가 남아 있었다.
- 담당자 업무 화면의 roster/filter 값도 `app/server.py`의 `_assignee_identifier()`가 `assignee_user_id`를 가장 먼저 선택해서 UUID를 계속 사용할 수 있었다.
- 실행 중인 8000번 서버는 Docker Compose `web` 컨테이너였고, 템플릿 변경은 반영됐지만 Python 함수 변경은 컨테이너 재시작 전까지 이전 코드가 유지됐다.

## 해결 방법

- Inbox 담당자 chip의 `assignee` query 값을 `assignee_email`, `assignee_name`, display text, `assignee_user_id` 순서로 선택하도록 변경했다.
- 담당자 업무 화면의 내부 identifier도 이메일/이름을 우선하고 UUID는 fallback으로만 쓰게 변경했다.
- `docker compose restart web`로 8000번 `web` 컨테이너를 재시작해 Python 함수 변경을 실제 서버에 반영했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "receiver_chip_prefers_assignee_name_over_stale_uuid_routing_display or assignee_work_template_prefers_email_over_user_id_for_navigation or receiver_chip_links_to_assignee_work_view or assignee_work_context" -q`: 5 passed, 138 deselected.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 143 passed.
- 로그인 쿠키로 `GET /ui/inbox`와 `GET /ui/assignees?assignee=m.kim%40dawonict.co.kr`를 확인했고, 두 HTML 모두 `10000000-0000-0000-0000-000000000001`가 남지 않음을 확인했다.

## 남은 리스크와 후속 작업

- 브라우저에 이전 HTMX DOM이 남아 있으면 새로고침이 필요할 수 있다. 서버 응답은 재시작 후 정상이다.

---

# 2026-08-24 - Fix stale assignee UUID display in Inbox demo mode

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode, Inbox mail rows, Dashboard routing overview, assignee display |
| 관련 파일 | `app/templates/partials/mail_rows.html`, `app/server.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 데모 모드에서 Settings에는 김민수 담당자가 이름으로 저장되어 있고 Inbox 상세에는 담당자 이메일이 보이지만, Inbox 담당자 표시가 `10000000-0000-0000-0000-000000000001` UUID로 노출되는 오류의 근본 원인 파악과 수정을 요청했다.

## 확인한 사실

- 데모 seed는 `sales` 담당자를 `10000000-0000-0000-0000-000000000001` 사용자 ID로 저장하고, Settings는 `users.name`을 통해 `김민수`를 표시한다.
- Inbox 목록 템플릿은 `email.routing_display`를 `email.assignee_name`보다 먼저 사용했다. 오래된 row 또는 classification payload에 `routing_display`가 사용자 ID로 남아 있으면, join된 이름과 이메일이 있어도 목록 chip에는 UUID가 그대로 표시될 수 있었다.
- Dashboard 라우팅 개요도 `routing_display`만 집계 키로 사용해 같은 stale UUID가 담당자명으로 집계되지 않는 취약점이 있었다.

## 해결 방법

- Inbox mail row의 담당자 표시 텍스트를 `assignee_name` 우선, 그 다음 `routing_display`와 classification fallback 순서로 계산하도록 변경했다.
- Dashboard 라우팅 개요 집계도 기존 `_assignee_display_name()` 표시 규칙을 사용하도록 변경해 이름이 있으면 UUID보다 우선되게 했다.
- `routing_display`가 `10000000-0000-0000-0000-000000000001`이어도 `assignee_name=김민수`가 있으면 Inbox와 overview 모두 김민수를 표시하는 회귀 테스트를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "receiver_chip_prefers_assignee_name_over_stale_uuid_routing_display or routing_overview_prefers_assignee_name_over_stale_uuid_routing_display or receiver_chip_links_to_assignee_work_view or routing_overview_renders_every_assignee_visible_in_mail_streams" -q`: 4 passed, 138 deselected.
- `uv run pytest tests/test_mail_decision_ui.py -k "assignee or routing_overview or receiver_chip or postgres_mail_row" -q`: 25 passed, 117 deselected.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 142 passed.

## 남은 리스크와 후속 작업

- 기존 실행 중인 서버 프로세스는 재시작하거나 정적/템플릿 reload가 적용되어야 수정된 템플릿을 반영한다.

---

# 2026-08-21 - Fix Dashboard urgent mail count source

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard urgent mail stats, Demo mode, Mail row filtering |
| 관련 파일 | `app/server.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 데모 모드에서 긴급 메일이 0건으로 보이지만 긴급 메일이 있는 것처럼 보이는 원인을 근본적으로 파악하고 해결해 달라고 요청했다.

## 확인한 사실

- fixture-only 데모 데이터에는 `urgency=high`인 긴급 메일 2건이 있으며 Dashboard summary도 2건으로 계산된다.
- 현재 프로세스의 기본 조회는 요청 컨텍스트 밖에서 Gmail service를 타고 있었고, 그 데이터에는 제목에 `긴급`이 포함된 과거 전달/입금 확인 메일이 있었지만 분석 결과는 `urgency=normal`, `attention_quadrant=normal`이었다.
- 아키텍처 기준상 긴급 메일은 제목 키워드나 중요도 축이 아니라 `urgency.level=high`를 기준으로 집계해야 한다.
- 기존 Dashboard helper는 `attention_quadrant`만 보았기 때문에 신규 목표 모델의 `urgency` 축과 구형 호환 필드가 불일치할 때 집계/필터 기준이 흔들릴 수 있었다.

## 해결 방법

- Dashboard 긴급 집계와 필터가 먼저 row 또는 classification payload의 `urgency` 값을 보고, 값이 없을 때만 구형 `attention_quadrant`를 fallback으로 쓰도록 변경했다.
- `urgency=high`이면 `attention_quadrant`가 없거나 normal이어도 긴급으로 포함하고, `urgency=normal`이면 구형 attention 값이나 제목 문구만으로 긴급 집계하지 않도록 회귀 테스트를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "dashboard_urgent or postgres_mail_row_does_not_restore_attention or postgres_mail_row_uses_deterministic_attention or demo_inbox_high_priority" -q`: 6 passed, 134 deselected.
- 직접 fixture demo service를 조회해 긴급 메일 2건이 `urgency=high` 기준으로 집계됨을 확인했다.

## 남은 리스크와 후속 작업

- 브라우저 쿠키가 Gmail 모드로 고정되어 있으면 실제 Gmail 분석 결과가 표시된다. 이 경우 화면 우상단 모드 토글 또는 `coramail_display_mode=demo` 쿠키 상태를 확인해야 한다.
- 기존 로컬 PostgreSQL demo seed가 오래된 경우 최신 fixture의 긴급 라벨이 DB에 반영되지 않을 수 있으므로 seed reload가 필요할 수 있다.

---

# 2026-08-21 - Align demo status across Overview Decision and Monitoring

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode status source, Mail Overview, Mail Decision, Monitoring |
| 관련 파일 | `app/services/demo_mail_service.py`, `app/services/demo_seed_service.py`, `app/repositories/postgres_seed_writer.py`, `app/server.py`, `tests/test_demo_seed_service.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 데모 모드에서 Mail Overview와 Mail Decision에 표시된 상태, Monitoring 탭의 상태, 실제 상태가 서로 다르게 보이는 근본 원인을 찾아 해결해 달라고 요청했다.

## 확인한 사실

- fixture-only 데모 경로의 `DemoMailService`는 `expected_demo_labels.assignee_area`를 `routing_display`로 노출했지만 `work_status`, `mail_decision_status`, `routing_status`, `manual_route_status`를 채우지 않았다.
- Monitoring은 `mail_decision_status`와 routing/forwarding 상태 필드를 기준으로 stage를 재계산하므로 같은 fixture row를 Mail Decision 미실행 또는 미전달처럼 표시할 수 있었다.
- Postgres demo seed는 모든 `routing_assignments.status`를 `forwarded`로 만들었지만 `mail_decision_runs`를 만들지 않아, DB 데모에서도 전달 완료와 Mail Decision 미실행이 동시에 표시될 수 있었다.
- DB 없는 데모 모드의 Mail Decision 패널은 runtime latest-run 조회를 시도해 fixture row와 별도 상태 경로를 탔다.

## 해결 방법

- fixture-only 데모 row에 `work_status=forwarded`, `mail_decision_status=completed`, `routing_status=forwarded`, `manual_route_status=sent`와 관련 label/time 필드를 함께 채웠다.
- DB 없는 데모 모드에서는 Mail Decision 패널이 runtime 호출 대신 fixture expected labels에서 만든 `demo-fixture-mail-decision:v1` 가상 completed run을 사용하게 했다.
- Postgres demo seed bundle에 각 synthetic message의 completed `mail_decision_runs`를 추가하고 `state_json`을 JSONB로 쓰도록 seed writer를 갱신했다.
- demo fixture 결과는 `demo_source=data/demo/*.fixture.json expected_demo_labels`로 표시해 운영 AI 결과와 구분되게 했다.

## 검증

- `uv run pytest tests/test_demo_seed_service.py tests/test_mail_decision_ui.py -k "demo_seed_bundle or fixture_demo_rows_share_status or ops_row_view_requires_decision or ops_view_renders_pipeline_stages or postgresql_mail_row_status_prioritizes_review" -q`: 4 passed, 142 deselected.
- `uv run pytest tests/test_demo_seed_service.py tests/test_mail_decision_ui.py -q`: 146 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 screenshot 검증은 수행하지 않았다.
- 기존 로컬 Postgres demo DB는 seed를 다시 로드해야 새 `mail_decision_runs`가 반영된다.

---

# 2026-08-21 - Restore Dashboard stats to a single row

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard stats layout |
| 관련 파일 | `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 대시보드 탭의 stats 카드들을 다시 1단으로 복구해 달라고 요청했다.

## 확인한 사실

- stats partial은 이미 6개 카드만 렌더링하고 있었고, 실제 2줄 배치는 하단 cascade lock의 `.dashboard-view #stats .stats`가 `repeat(3, ...)`로 덮어쓰면서 발생했다.
- 모바일/좁은 화면용 동일 선택자 override도 3열 기대값을 유지하고 있었다.

## 해결 방법

- 대시보드 stats 그리드를 6열로 되돌려 데스크톱에서 6개 카드가 한 줄에 표시되도록 했다.
- 좁은 화면 override도 6열과 가로 스크롤을 유지하도록 통일했다.
- CSS 회귀 테스트 기대값을 6열 기준으로 갱신했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "dashboard_stats or dashboard_stat or dashboard_typography" -q`: 7 passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 138 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 screenshot 검증은 수행하지 않았다.

---

# 2026-08-21 - Roll back failed Monitoring outside-click attempts

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring popover outside-click rollback |
| 관련 파일 | `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 모니터링 팝업 바깥 클릭 닫힘 문제가 해결되지 않았으므로, 추가 요청 이후 Codex가 적용한 변경을 모두 롤백해 달라고 요청했다.

## 해결 방법

- 히스토리를 지우지 않고 `git revert --no-commit`으로 다음 세 커밋을 되돌렸다.
- `8588543 fix: separate monitoring inspector surface`
- `3651f1c fix: consume monitoring outside clicks`
- `80d99c6 fix: harden monitoring popover close`
- 업무유형 title escaping 수정(`ee6b307`)과 최초 모니터링 팝오버 UI 개편(`492ec2a`)은 이번 롤백 범위 밖으로 보아 유지했다.

## 검증

- 롤백 후 `git diff --cached --stat`로 되돌림 범위를 확인했다.

## 남은 리스크와 후속 작업

- 바깥 클릭 닫힘 문제는 해결된 상태가 아니며, 후속 작업에서는 실제 브라우저 이벤트 재현이 가능한 환경에서 원인을 다시 추적해야 한다.

---

# 2026-08-21 - Fix Monitoring business type popover title escaping

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring business type popover |
| 관련 파일 | `app/templates/partials/ops_rows.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 모니터링 탭 업무유형 칼럼에 `'문의" aria-label="업무 유형 상세 보기">`처럼 HTML 속성이 깨진 텍스트가 표시된다고 보고했다.

## 확인한 사실

- 업무유형 셀은 `category_chip(row.business_label)`의 HTML 조각을 팝오버 summary 본문과 `title` 속성에 동시에 사용하고 있었다.
- 칩 HTML 안의 속성 따옴표가 바깥 `title` 속성을 깨면서 aria-label 일부가 화면 텍스트처럼 노출됐다.

## 해결 방법

- `ops_detail_menu`에 `title_text` 인자를 추가해 화면 표시 HTML과 title 속성 텍스트를 분리했다.
- 업무유형 칼럼은 title에 `row.business_label` 텍스트만 넣도록 변경했다.
- 업무유형 title 속성이 깨지지 않는 회귀 테스트를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "monitoring_popovers or monitoring or ops_" -q`: 17 passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 138 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 screenshot 검증은 수행하지 않았다.

---

# 2026-08-21 - Refine Monitoring popover details

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring table popovers, ops inspector close behavior |
| 관련 파일 | `app/templates/partials/ops_rows.html`, `app/templates/shell.html`, `app/static/app.css`, `app/server.py`, `app/services/postgres_mail_service.py`, `app/repositories/postgres_mail_repository.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 모니터링 탭에서 클릭하면 나오는 팝업창에서 컬럼명과 표 표시값을 반복하는 텍스트 영역을 제거해 달라고 요청했다.
- 팝업에는 표에 없는 담당자 소속/이메일, 단계 완료 시간, 전달 완료 시간, 분류 소요 시간 같은 보조 정보를 표시해야 했다.
- 전달, 재분석, 재생성 등 액션 버튼은 팝업 하단이 아니라 박스 우측에 배치해야 했다.
- 팝업은 다시 클릭할 때까지 남는 방식이 아니라 팝업 박스 밖을 클릭하면 닫혀야 했다.

## 확인한 사실

- 중복 텍스트의 직접 원인은 `partials/ops_rows.html`의 `ops_detail_menu`와 `ops_stage_menu`가 `label`, `strong`, `p` 구조로 컬럼명, 표 표시값, detail 값을 반복하는 구조였다.
- 분석 결과 테이블에는 별도 `completed_at`이 없으므로 current `email_analysis_results.updated_at`을 완료 시각으로, `updated_at - created_at`을 소요 시간으로 해석했다.
- 담당자 소속/직책은 `users.notification_preferences`에 저장된 `department`, `position` 값을 사용한다.

## 해결 방법

- 모니터링 팝오버를 메타 필드 목록 중심으로 재구성해 표에 이미 보이는 컬럼명/값 반복을 제거했다.
- 담당자 소속/직책/이메일/사용자 ID, 분류/요약/Mail Decision 완료 시간과 소요 시간, 라우팅/전달 기록 시간을 row 계약에 추가했다.
- 팝오버 액션 영역을 우측 열로 배치하도록 HTML/CSS를 변경하고 첨부파일 팝오버에도 같은 배치를 적용했다.
- 기존 transient popover 닫힘 핸들러에 `#opsInspector` 바깥 클릭 닫힘을 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "monitoring or ops_" -q`: 17 passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 138 passed.
- `CORAMAIL_DEV_PORT=8012 CORAMAIL_DEV_RELOAD=false ./scripts/dev_app.sh`로 새 서버를 띄우고 로그인 후 `/ui/monitoring` HTTP 렌더링을 확인했다. 새 팝오버 마크업과 바깥 클릭 닫힘 JS가 포함됐고, 기존 중복 패턴은 검색되지 않았다.

## 남은 리스크와 후속 작업

- Playwright가 설치돼 있지 않아 실제 브라우저 screenshot 검증은 수행하지 못했다.

---

# 2026-08-21 - Reorder Dashboard important quadrant label

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard priority map labels |
| 관련 파일 | `app/templates/partials/stats.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Priority Map의 중요 quadrant 라벨을 `중요O 긴급X` 대신 `긴급X 중요O`로 바꿔 달라고 요청했다.
- 기간 설정에 대한 제안도 함께 요청했다.

## 해결 방법

- Priority Map의 중요 quadrant 표시 순서를 다른 quadrant와 같은 긴급성 우선 순서로 맞춰 `긴급X 중요O`로 변경했다.
- 관련 UI 렌더링 테스트 기대값을 새 라벨에 맞췄다.
- 기간 설정은 코드 변경 없이 현재 Dashboard 구조와 기존 Daily Inflow 최근 7일 기준을 확인한 뒤 사용자에게 제안으로만 답변한다.

## 검증

- `.venv/bin/pytest tests/test_mail_decision_ui.py::test_dashboard_summary_excludes_unclassified_and_unassigned_rows tests/test_mail_decision_ui.py::test_dashboard_attention_matrix_counts_and_filters_by_quadrant_only`: 2 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 screenshot 검증은 수행하지 않았다.

---

# 2026-08-21 - Fix Dashboard normal matrix count fallback

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard Eisenhower matrix, normal mail filter |
| 관련 파일 | `app/templates/partials/stats.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Dashboard 아이젠하워 매트릭스에서 `일반 0건`으로 표시되는데, 클릭하면 전체 메일이 보인다고 보고했다.
- 표시 count와 Mail Streams 필터가 같은 attention 기준을 쓰도록 맞춰야 했다.

## 확인한 사실

- 정상 Demo PostgreSQL context에서는 `attention_normal_count=1151`이고 렌더된 row의 `data-dashboard-mail-attention="normal"`도 1151개다.
- 하지만 `partials/stats.html`은 `summary.attention_normal_count`가 없는 축소 context에서 `0`으로 fallback한다.
- 같은 화면의 row 렌더링은 attention 값이 없으면 `normal`로 fallback하므로, summary에 attention count가 빠진 상태에서는 `일반 0건` 표시와 normal 필터 결과가 불일치할 수 있다.

## 해결 방법

- `partials/stats.html`에서 summary의 attention count가 없을 때 같은 `emails` row와 같은 fallback 규칙으로 `urgent_important`, `urgent`, `important`, `normal` count를 계산하도록 보강했다.
- summary count가 있는 정상 Dashboard 경로는 기존 서버 계산값을 그대로 사용한다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py::test_dashboard_attention_matrix_counts_fall_back_to_rendered_rows tests/test_mail_decision_ui.py::test_dashboard_stats_cards_filter_mail_stream_rows tests/test_mail_decision_ui.py::test_dashboard_attention_matrix_counts_and_filters_by_quadrant_only tests/test_mail_decision_ui.py::test_shell_schedules_manual_route_polling_for_pending_dashboard_rows -q`: 4 passed.
- Docker web Demo context 렌더 확인: `normal_summary 1151`, `normal_html True`, `normal_rows 1151`.

## 남은 리스크와 후속 작업

- 실제 브라우저 클릭 검증은 수행하지 않았다. `curl` host 접속이 일시적으로 실패해 컨테이너 내부 Jinja 렌더와 서비스 함수로 확인했다.
- 기존 작업트리에 남아 있던 `app/agents/decision_agent.py` 변경은 이번 작업과 무관해 커밋하지 않았다.

---

# 2026-08-21 - Remove Dashboard Priority Map from product-facing triage

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard stats, mail urgency triage, attention model direction |
| 관련 파일 | `app/templates/partials/stats.html`, `app/static/app.css`, `app/templates/shell.html`, `tests/test_mail_decision_ui.py`, `docs/architecture/agentic_rag_mail_decision_system.md`, `docs/development/mail-attention-stabilization.md` |

## 요청 또는 배경

- 사용자는 업무메일 서비스에서 긴급성과 중요도 2축을 독립적으로 두는 것이 불필요하다고 판단했고, 중요 축을 제거하는 방향을 제시했다.
- 이에 따라 Dashboard의 Priority Map 카드 영역을 제거하고, 다음 작업으로 긴급 메일 분류 성능 개선 및 안정화를 진행하겠다고 했다.

## 확인한 사실

- Priority Map은 `partials/stats.html`에서 `attention_quadrant` 4분면 버튼으로 렌더링되고, shell JS에는 `attention:*` 필터 경로가 남아 있었다.
- `importance`와 `attention_quadrant`는 DB/API/fixture/evaluation 호환 필드로 여러 경로에 남아 있어 이번 UI 제거 작업에서 즉시 삭제하면 영향 범위가 크다.

## 해결 방법

- Dashboard stats에서 Priority Map 섹션과 `attention:*` 버튼을 제거했다.
- 사용하지 않는 `attention-matrix` CSS와 모바일 override를 제거하고 stats row를 단일 컬럼으로 정리했다.
- shell JS에서 사용자 진입점이 사라진 `attention:*` 필터 처리를 제거하고 Today/Urgent 필터만 유지했다.
- 아키텍처 문서의 제품 목표를 긴급성 단일 축으로 바꾸고, 기존 `importance`/`attention_quadrant` 필드는 다음 cleanup 전까지 호환 필드로 남긴다고 명시했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -q`: 135 passed.
- `python -m py_compile app/server.py`: passed.

## 남은 리스크와 후속 작업

- 다음 긴급 메일 분류 안정화 작업에서 `importance`, `attention_quadrant`, attention fixture/evaluation metric, row compatibility 필드의 제거 또는 마이그레이션 범위를 별도로 정해야 한다.
- 기존 저장 결과는 당분간 호환 필드로 유지되지만 신규 사용자 경험에서는 Priority Map을 노출하지 않는다.

---

# 2026-08-21 - Tighten urgency and importance high-signal guards

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Mail Decision attention classification, urgency/importance axes |
| 관련 파일 | `app/agents/decision_agent.py`, `tests/test_decision_agent.py`, `docs/development/mail-attention-stabilization.md` |

## 요청 또는 배경

- 사용자는 현재 코드 기준으로 긴급/중요 분류 방법을 분석하고 검토한 뒤, 개선 방향 판단과 구현까지 완료해 달라고 요청했다.
- 목표 아키텍처 기준상 긴급성은 대응 속도, 중요도는 사업 영향이며 둘은 독립 축으로 판단해야 한다.

## 확인한 사실

- 현재 구현은 `MailFacts.urgency_signals`와 `MailFacts.importance_signals`를 Decision Agent가 다시 검증하고, `attention_quadrant`는 코드에서 재계산하는 구조라 큰 방향은 문서와 맞다.
- 다만 최종 high 판정 guard가 `by `, `계약`, `contract`, `오늘` 같은 넓은 토큰으로 참이 될 수 있어, LLM이 넓게 추출한 신호를 넘기면 미래 일정이나 계약서 사본 요청이 high로 오탐될 여지가 있었다.

## 해결 방법

- 긴급 high 지원 조건을 정규식 기반으로 좁혀 `due today`, `by 14:00`, `within N hours`, 금일/내일 대응 기한, 현재 장애/중단 같은 구체 신호만 인정하도록 했다.
- 중요 high 지원 조건도 계약 일반 언급 대신 계약 위반, penalty, 금전 손실, 안전, 운항/생산/서비스 중단, 발주 규모/선박 프로젝트 영향 같은 구체 신호만 인정하도록 했다.
- `by next week meeting`, `계약서 사본 요청`, `오늘 자료 감사합니다`가 high로 승격되지 않는 회귀 테스트와, `금일 14시까지` 및 `계약 위반 penalty`는 high로 인정하는 회귀 테스트를 추가했다.
- `mail-attention-stabilization.md`에 broad token 금지와 LLM 추출 신호 재검증 원칙을 기록했다.

## 검증

- `uv run pytest tests/test_decision_agent.py tests/test_vision_fact_extraction.py tests/test_synthetic_evaluation.py -q`: 47 passed.
- `python -m py_compile app/agents/decision_agent.py`: passed.

## 남은 리스크와 후속 작업

- 운영 데이터의 실제 표현 분포가 확보되면 attention fixture를 확장해 한국어 상대 기한과 산업별 중요도 표현을 더 추가해야 한다.
- 기존 DB에 저장된 과거 `decision-agent:v2` 결과는 재분석 전까지 보수적으로 normal 처리되는 기존 정책을 유지한다.

---

# 2026-08-21 - Fix PostgreSQL demo urgent seed labels

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard urgent stats, PostgreSQL demo seed |
| 관련 파일 | `app/services/demo_seed_service.py`, `tests/test_demo_seed_service.py` |

## 요청 또는 배경

- 사용자는 Dashboard 탭의 `Urgent Mails` 카드가 `오늘 긴급 9건`을 표시하지만 실제 데모 모드 데이터에는 긴급으로 분류된 메일이 없는 것처럼 보인다고 보고했다.
- 근본 원인을 확인하고 카드 수치와 데모 분류 데이터가 같은 기준으로 맞도록 수정해야 했다.

## 확인한 사실

- fixture 직접 로딩 경로는 15건 중 긴급 2건, 최신 데모일 기준 오늘 긴급 0건으로 계산된다.
- PostgreSQL demo seed 경로는 fixture 15건에 deterministic bulk volume 1,198건을 추가해 총 1,213건을 만든다.
- 2026-08-12 bulk pattern에는 긴급 장애 8건이 있고, fixture의 긴급 견적 1건까지 합치면 Dashboard의 `오늘 긴급 9건` 수치가 된다.
- 하지만 bulk scenario의 `urgency`, `importance`, `attention_quadrant` 값이 `DemoMessage.expected_demo_labels`로 전달되지 않아 seed된 classification 결과에서는 긴급 장애 8건이 `normal` attention으로 저장됐다.

## 해결 방법

- `DemoSeedService._bulk_volume_messages()`가 scenario의 `urgency`, `importance`, `attention_quadrant`를 expected demo labels에 포함하도록 수정했다.
- seed bundle 테스트에서 최신 데모일 2026-08-12의 긴급 row가 실제 classification `attention_quadrant`로 9건이며, 긴급 장애 8건이 모두 `urgent_important`로 저장되는지 검증했다.

## 검증

- `uv run pytest tests/test_demo_seed_service.py -q`: 7 passed.
- `uv run pytest tests/test_mail_decision_ui.py::test_dashboard_summary_excludes_unclassified_and_unassigned_rows tests/test_mail_decision_ui.py::test_demo_dashboard_stats_and_timeline_use_latest_demo_data_day tests/test_mail_decision_ui.py::test_dashboard_urgent_filter_includes_only_urgent_attention_quadrants -q`: 3 passed.
- `python -m py_compile app/services/demo_seed_service.py`: passed.
- seed bundle 확인 결과 `attention_counts {'normal': 1151, 'urgent_important': 61, 'urgent': 1}`, 최신 데모일 2026-08-12 기준 `today_urgent 9`를 확인했다.

## 남은 리스크와 후속 작업

- 이미 적재된 로컬 PostgreSQL demo seed는 앱 재부트스트랩 또는 demo seed reload가 필요하다.
- 기존 작업트리에 남아 있던 `app/templates/partials/stats.html`, `tests/test_mail_decision_ui.py` 변경은 이번 커밋에 포함하지 않았다.

---

# 2026-08-21 - Update Dashboard priority map OX labels

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard priority map labels |
| 관련 파일 | `app/templates/partials/stats.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Dashboard 탭의 Priority Map에서 보이는 quadrant 텍스트를 `긴급중요`, `긴급중요아님`, `중요긴급아님`, `일반` 의미 대신 `긴급O 중요O`, `긴급O 중요X`, `중요O 긴급X`, `일반`로 바꿔 달라고 요청했다.

## 해결 방법

- Priority Map의 눈에 보이는 cell label을 `긴급O 중요O`, `긴급O 중요X`, `중요O 긴급X`, `일반` 체계로 맞췄다.
- 필터 action과 상세 aria-label은 기존 의미 설명을 유지해 동작과 접근성 설명은 바꾸지 않았다.
- 관련 렌더링 테스트 기대값을 새 표시 문구에 맞췄다.

## 검증

- `.venv/bin/pytest tests/test_mail_decision_ui.py::test_dashboard_summary_excludes_unclassified_and_unassigned_rows`: 1 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 screenshot 검증은 수행하지 않았다.

---

# 2026-08-21 - Correct Dashboard urgent mismatch root cause fix

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard priority map labels, category/stat filter interaction |
| 관련 파일 | `app/templates/partials/stats.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 직전 처리에서 matrix에 별도 O/X chip 영역을 추가한 것이 의도가 아니며, 기존 label 자체를 더 적절한 텍스트로 대체하길 원한다고 정정했다.
- `Urgent Mails` 문제도 필터 기능 자체가 아니라, `오늘 긴급 n건` 수치와 클릭 후 Mail Streams 결과가 불일치하는 근본 원인을 찾아 해결해야 한다고 정정했다.

## 확인한 사실

- `today_urgent_count`는 Dashboard 전체 row 기준으로 계산된다.
- Mail Streams에는 별도의 category chip filter가 있고, 이 상태가 `window.categoryFilterState.activeCategory`에 남아 stat filter와 동시에 적용된다.
- 따라서 특정 category가 활성화된 상태에서 `Urgent Mails`를 누르면, card count는 전체 기준인데 표시 row는 해당 category와 urgent의 교집합이 되어 0건처럼 보일 수 있다.
- 로컬 현재 데이터에서는 긴급 row가 0건이라 사용자가 본 `오늘 긴급 9건` 운영 상태를 그대로 재현하지는 못했다.

## 해결 방법

- 추가했던 O/X chip DOM과 CSS를 제거했다.
- matrix label 자체를 `긴급 · 중요 아님`, `중요 · 긴급 아님`으로 바꿔 exact quadrant 의미가 텍스트에서 드러나게 했다.
- `Urgent Mails` 보조 문구는 `오늘 긴급 n건`으로 유지했다.
- stat/matrix button 클릭 시 `window.applyCategoryFilter("__all__")`를 호출해 category filter를 전체로 초기화한 뒤 stat filter를 적용하도록 했다.
- 직전 오해로 넣었던 `/ui/mail-rows` 서버 endpoint 직접 stat filtering과 `dashboard_mail_filter` query 전달은 제거했다. row refresh 뒤 클라이언트 stat filter는 기존 hidden state로 다시 적용된다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "dashboard_summary_excludes_unclassified_and_unassigned_rows or dashboard_stats_and_attention_matrix_share_top_row or dashboard_stats_cards_filter_mail_stream_rows or shell_schedules_manual_route_polling_for_pending_dashboard_rows or dashboard_mail_stat_filters_select_today_and_urgent_rows" -q`: 5 passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 134 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 screenshot 검증은 수행하지 않았다.

---

# 2026-08-21 - Restore urgent card copy and clarify matrix quadrants

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard priority map labels, Urgent Mails helper text |
| 관련 파일 | `app/templates/partials/stats.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 직전 변경이 의도와 다르다고 지적했다.
- 의도는 `Urgent Mails`의 `오늘 긴급 n건` 표시를 없애는 것이 아니라, 해당 카드 클릭 시 Mail Streams가 비는 불일치 오류를 해결하는 것이었다.
- priority map에서는 `긴급`/`중요` 단일 quadrant가 전체 긴급/전체 중요처럼 보이지 않게, `긴급 O 중요 X`, `중요 O 긴급 X`라는 의미가 더 느껴져야 했다.

## 해결 방법

- `Urgent Mails` 보조 문구를 `오늘 긴급 n건`으로 복원했다.
- priority map cell 제목은 짧게 유지하되, 각 quadrant에 `긴급 O`, `중요 X` 같은 O/X state chip을 추가했다.
- `긴급` quadrant는 `긴급 O · 중요 X`, `중요` quadrant는 `중요 O · 긴급 X`로 표시되게 했다.
- 직전 커밋의 서버/HTMX active filter 전달 보강은 유지했다. 이는 클릭 후 refresh/polling 때 필터 상태가 서버 row 응답에도 적용되게 하기 위한 오류 수정이다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "dashboard_summary_excludes_unclassified_and_unassigned_rows or dashboard_mail_stat_filters_select_today_and_urgent_rows or dashboard_attention_matrix_counts_and_filters_by_quadrant_only or dashboard_mail_rows_endpoint_applies_active_stat_filter or dashboard_stats_cards_filter_mail_stream_rows or dashboard_stats_and_attention_matrix_share_top_row or shell_schedules_manual_route_polling_for_pending_dashboard_rows" -q`: 7 passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 135 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 screenshot 검증은 수행하지 않았다.

---

# 2026-08-21 - Clarify Dashboard priority filters

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard priority map labels, Mail Streams stat filtering |
| 관련 파일 | `app/server.py`, `app/templates/partials/stats.html`, `app/templates/shell.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 priority map의 `긴급`/`중요` 단일 영역이 모든 긴급 메일 또는 모든 중요 메일처럼 보일 수 있어 혼동된다고 지적했다.
- `Urgent Mails` 카드에는 `오늘 긴급 9건`처럼 표시되는데 클릭 필터 결과가 보이지 않는 불일치도 해결해야 했다.

## 해결 방법

- exact quadrant cell label을 `긴급만`, `중요만`으로 바꾸고 aria-label도 각각 `긴급하지만 중요도는 일반`, `중요하지만 긴급하지 않음` 의미로 명확히 했다.
- `Urgent Mails` 보조 문구에서 `오늘 긴급 n건`을 제거하고, 클릭 필터와 같은 전체 긴급성 high 의미인 `긴급 · 중요 포함`으로 바꿨다.
- 기존에 받기만 하던 `/ui/mail-rows`의 `dashboard_mail_filter`를 실제 서버 row filtering에 적용했다.
- `dashboardMailRowsUrl()`이 active filter 값을 query string으로 전달하도록 바꿔 HTMX refresh 후에도 서버와 클라이언트 필터 의미가 일치하게 했다.
- `today,urgent` 같은 조합 필터와 exact attention filter를 `filter_dashboard_mail_rows()`에서 함께 처리하도록 확장했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "dashboard_summary_excludes_unclassified_and_unassigned_rows or dashboard_mail_stat_filters_select_today_and_urgent_rows or dashboard_attention_matrix_counts_and_filters_by_quadrant_only or dashboard_mail_rows_endpoint_applies_active_stat_filter or dashboard_stats_cards_filter_mail_stream_rows or shell_schedules_manual_route_polling_for_pending_dashboard_rows" -q`: 6 passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 135 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 screenshot 검증은 수행하지 않았다.

---

# 2026-08-21 - Align Dashboard priority map title style

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard attention matrix typography |
| 관련 파일 | `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 `Priority Map` 제목 스타일을 다른 Dashboard stat 제목과 통일해 달라고 요청했다.

## 해결 방법

- `.attention-matrix-head h2`를 기존 `.stat .label`과 같은 12px/16px 제목 톤으로 맞추고 색상도 보조 제목 계열로 낮췄다.
- 테스트에서 matrix 제목 typography가 stat label과 같은 스케일을 쓰는지 확인하도록 보강했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "dashboard_stat_helper_text_uses_readable_tone or dashboard_summary_excludes_unclassified_and_unassigned_rows" -q`: 2 passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 134 passed.

---

# 2026-08-21 - Enlarge Dashboard priority map

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard attention matrix copy and sizing |
| 관련 파일 | `app/templates/partials/stats.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 attention matrix의 `긴급성 높음`, `중요도 높음` 축 텍스트 영역을 제거하고 matrix 크기를 키워 달라고 요청했다.
- `업무 우선 현황` 제목도 간결한 핵심 영어 텍스트로 바꿔 달라고 했다.

## 해결 방법

- matrix 제목을 `Priority Map`으로 변경했다.
- axis 텍스트 DOM과 관련 CSS selector를 제거했다.
- 오른쪽 matrix column 최소 폭과 비중, panel padding, cell 높이, label/count typography를 키웠다.
- 모바일 matrix cell 크기도 함께 키워 작은 화면에서 지나치게 납작해지지 않게 했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "dashboard_summary_excludes_unclassified_and_unassigned_rows or dashboard_stats_and_attention_matrix_share_top_row or dashboard_stats_cards_filter_mail_stream_rows" -q`: 3 passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 134 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 screenshot 검증은 수행하지 않았다.

---

# 2026-08-21 - Refine Dashboard attention matrix layout

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard stats layout, attention matrix UI |
| 관련 파일 | `app/templates/partials/stats.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Dashboard attention matrix가 가로 한 단을 모두 차지하지 않게 하고, 기존 stats 6개를 3×2로 몰아 왼쪽에 배치한 뒤 오른쪽에 아이젠하워 매트릭스를 넣어 달라고 요청했다.
- matrix의 부가 설명 텍스트 영역을 제거하고, `긴급성 높음` 축 라벨이 뒤집힌 문제도 수정해야 했다.

## 해결 방법

- `partials/stats.html`에 `stats-priority-row` wrapper를 추가해 왼쪽은 기존 stats 6개, 오른쪽은 attention matrix가 같은 row를 공유하도록 바꿨다.
- matrix 헤더의 보조 설명 문장과 각 quadrant cell의 설명 문구를 제거해 count/filter 중심 UI로 줄였다.
- Dashboard final cascade CSS에서 stats를 `repeat(3, minmax(0, 1fr))`로 고정하고, matrix는 오른쪽 column 안에서 compact 2×2 grid로 표시되게 조정했다.
- `긴급성 높음` 세로 축은 `rotate(180deg)`를 제거하고 `transform: none`으로 바꿔 뒤집히지 않게 했다.
- 좁은 화면에서는 stats/matrix가 세로로 접히고 stats는 3열 기준으로 가로 스크롤되도록 responsive override를 정리했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "dashboard_summary_excludes_unclassified_and_unassigned_rows or dashboard_stats_cards_filter_mail_stream_rows or dashboard_stat_helper_text_uses_readable_tone or dashboard_stats_and_attention_matrix_share_top_row or dashboard_typography_keeps_table_and_auxiliary_areas_compact" -q`: 5 passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 134 passed.

## 남은 리스크와 후속 작업

- 이번 변경도 template/CSS/unit 수준 검증이며 실제 브라우저 screenshot 검증은 수행하지 않았다.

---

# 2026-08-21 - Add Dashboard attention matrix filter

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard summary, stats UI, Mail Streams filtering |
| 관련 파일 | `app/server.py`, `app/templates/partials/stats.html`, `app/templates/partials/mail_rows.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 최근 `urgency`와 `importance` 독립 축 및 deterministic `attention_quadrant` 도입 상태를 기준으로 Dashboard 탭에 아이젠하워 매트릭스 형태의 업무 현황 stat/filter UI를 추가해 달라고 요청했다.
- 판단 구조 자체는 크게 수정하지 않고, Dashboard presentation/aggregation layer에서 이미 계산된 `attention_quadrant`만 사용해야 했다.

## 확인한 사실

- Dashboard context는 `dashboard_context()`에서 `mail_rows()` 결과를 가져와 `dashboard_summary(rows)`와 같은 row 집합으로 summary, chart, routing overview, Mail Streams를 구성한다.
- `mail_rows()`는 현재 모드에 따라 `PostgresMailboxService` 또는 `DemoMailService`를 사용하고, 장애 시 demo fixture로 fallback한다.
- Demo/PostgreSQL row 모두 `attention_quadrant`를 row 최상위와 classification payload에 노출한다.
- 기존 `summary.urgent_count`와 `today_urgent_count`는 `_is_priority_high_row()`를 통해 `urgent_important`와 `urgent`를 합친 긴급성 있음 의미로 계산된다.
- 기존 `today`/`urgent` stat 클릭은 shell JS의 hidden `dashboardMailFilter`와 row dataset을 사용해 Mail Streams row를 클라이언트에서 숨기는 방식으로 동작한다.

## 해결 방법

- `dashboard_summary()`에 `attention_urgent_important_count`, `attention_urgent_count`, `attention_important_count`, `attention_normal_count`를 추가해 기존 `urgent_count` 의미와 exact quadrant count를 분리했다.
- 사분면 집계와 filter helper는 제목, 업무 유형, priority, urgency/importance 문자열 조합을 재해석하지 않고 row의 `attention_quadrant`만 사용하도록 했다.
- `partials/stats.html`의 기존 stats 아래에 2×2 `업무 우선 현황` matrix를 추가하고 각 cell을 `data-dashboard-mail-filter-action="attention:*"` 버튼으로 만들었다.
- Mail Streams row에 `data-dashboard-mail-attention`을 추가하고 shell JS가 exact quadrant filter를 기존 `today` 필터와 조합해 적용하도록 확장했다.
- `urgent` 전체 stat와 exact quadrant matrix filter는 의미 충돌을 피하기 위해 서로 배타적으로 정리되게 했다.
- CSS는 기존 Dashboard 밀도와 폭 제약에 맞춰 matrix를 compact 2×2 grid로 표시하고 모바일에서는 축 라벨과 cell 높이를 줄이도록 조정했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "dashboard_summary_excludes_unclassified_and_unassigned_rows or dashboard_mail_stat_filters_select_today_and_urgent_rows or dashboard_attention_matrix_counts_and_filters_by_quadrant_only or dashboard_stats_cards_filter_mail_stream_rows or shell_schedules_manual_route_polling_for_pending_dashboard_rows or dashboard_mail_rows_exposes_pending_manual_route_status_for_polling" -q`: 6 passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 133 passed.

## 남은 리스크와 후속 작업

- 현재 검증은 template/JS source/unit 수준이며, 실제 브라우저 screenshot 검증은 별도로 수행하지 않았다.
- 기존 shell에는 `routing-settings-updated` 이벤트에서 `/ui/dashboard-mail-rows`를 호출하는 오래된 경로가 남아 있으나 이번 요청의 새 matrix 동작에는 기존 `/ui/mail-rows?view=dashboard` refresh 경로를 재사용했다.

---

# 2026-08-21 - Stabilize urgency and importance semantic judgments

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Mail Decision attention axes, evaluation metrics, UI compatibility |
| 관련 파일 | `app/agents/fact_extraction_agent.py`, `app/agents/decision_agent.py`, `app/evaluation/metrics.py`, `app/evaluation/runner.py`, `app/mail_content.py`, `data/evaluation/attention_quadrant_cases.fixture.json`, `docs/development/mail-attention-stabilization.md`, `tests/test_decision_agent.py`, `tests/test_vision_fact_extraction.py`, `tests/test_synthetic_evaluation.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 최근 커밋 `1fdb8e706d9b5cc5efcc2fe1349a7973e067eab4`의 후속으로 긴급성(`urgency`)과 중요도(`importance`) 독립 판단 구조가 실제 메일에서 의미적으로 올바른지 검증하고 안정화해 달라고 요청했다.
- 새 기능을 크게 추가하지 않고, 과잉 keyword 판정, quadrant 계산, 근거성, legacy `priority`, 기존 `decision-agent:v2` 결과 처리 방안을 점검하는 것이 목표였다.

## 확인한 사실

- `MailUrgency`, `MailImportance`, `importance_signals`, `decision-agent:v3`, PostgreSQL persistence, Demo/PostgreSQL UI contract, `attention_quadrant_for()` 기반 결정적 quadrant 계산은 최신 코드에 존재했다.
- `attention_quadrant`는 Decision Agent와 PostgreSQL UI adapter에서 애플리케이션 계산값으로 덮어쓰지만, LLM이 축별 high를 근거 없이 반환하는 경우 축 자체는 그대로 남을 수 있었다.
- row payload의 `priority`는 mail attention 호환 필드로 남아 있고, 별도로 라우팅 capability의 integer priority도 존재한다. 두 의미는 제거 조건이 다르다.
- 구형 `decision-agent:v2` classification payload에는 새 축이 없어 현재 UI는 보수적으로 `normal`로 표시한다.

## 해결 방법

- Fact Extraction의 deterministic signal 수집을 추상 라벨에서 원문 근거 조각으로 바꾸고, `긴급` 단어 단독·작은 claim·주요 고객 단순 요청·과거 해결 장애·quoted history가 high signal로 번지지 않게 보수화했다.
- Decision Agent는 LLM이 high를 반환해도 해당 축의 grounded signal이 없으면 `normal`로 낮추고, high 이유는 추출된 근거 signal을 우선 사용하도록 했다.
- evaluation report/case/trace에 `expected_urgency`, `expected_importance`, `expected_attention_quadrant`와 축별 accuracy를 추가했다.
- `data/evaluation/attention_quadrant_cases.fixture.json`에 4개 quadrant와 주요 경계 사례를 담은 최소 synthetic fixture를 추가했다.
- `docs/development/mail-attention-stabilization.md`에 현재 흐름 감사, `priority` 사용처 분류, v2 결과 운영 방안, 평가 확장 방식을 기록했다.

## 검증

- `python -m py_compile app/agents/fact_extraction_agent.py app/agents/decision_agent.py app/evaluation/metrics.py app/evaluation/runner.py app/mail_content.py`: passed.
- `uv run pytest -q tests/test_decision_agent.py tests/test_vision_fact_extraction.py tests/test_synthetic_evaluation.py tests/test_mail_decision_ui.py -q`: passed.
- 전역 `pytest` 명령은 PATH에 없어 실패했고, repo 환경에 맞춰 `uv run pytest`로 재실행했다.

## 남은 리스크와 후속 작업

- 기존 `decision-agent:v2` 운영 데이터는 조용히 `normal`로 보일 수 있으므로, attention 판단이 필요한 운영 메일은 `decision-agent:v3` 재분석 후 normal을 확정 판단으로 취급해야 한다.
- row-level `priority`는 UI 호환이 사라질 때 제거 가능하지만, 라우팅 capability priority와 혼동하지 않도록 별도 정리가 필요하다.
- 새 attention fixture는 평가 가능한 최소 데이터셋이며, 실제 운영 성능 주장은 운영 데이터 재분석과 end-to-end prediction 생성 뒤에만 가능하다.

---

# 2026-08-21 - Split urgency and importance axes for mail decisions

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Mail Decision schema, Decision Agent, inbox attention UI |
| 관련 파일 | `app/schemas/mail_decision.py`, `app/agents/fact_extraction_agent.py`, `app/agents/decision_agent.py`, `app/repositories/postgres_decision_result_repository.py`, `app/services/postgres_mail_service.py`, `app/services/demo_mail_service.py`, `app/templates/partials/mail_rows.html`, `app/static/app.css`, `tests/test_decision_agent.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 메일의 `priority`와 `urgency`를 사실상 같은 값처럼 쓰는 구조를 개선하고, 아이젠하워 매트릭스처럼 긴급성(`urgency`)과 중요도(`importance`)를 독립 축으로 분리해 달라고 요청했다.
- 확인 결과 `PostgresMailboxService`가 `classification_result_json.urgency`를 `priority`로 노출하고, 누락 시 제목·본문 키워드와 `긴급 장애`/`클레임` 업무 유형으로 high를 복원했다.
- 메일 목록 템플릿도 `priority == high` 또는 업무 유형 label을 직접 검사해 빨간 행 배경을 지정하고 있었다.

## 해결 방법

- `MailUrgency`, `MailImportance`, `attention_quadrant_for()`를 추가하고 `MailClassification`은 업무 유형 분류 역할만 유지했다.
- `MailFacts`에 `importance_signals`를 추가하고 Fact Extraction Agent는 최종 판단이 아니라 긴급성·중요도 근거 문구를 추출하도록 프롬프트와 grounded signal 수집을 수정했다.
- Decision Agent는 `urgency`와 `importance`를 독립 구조화 출력으로 받고, `attention_quadrant`는 AI 출력이 아니라 코드에서 `urgent_important`, `urgent`, `important`, `normal` 중 하나로 계산한다.
- PostgreSQL decision 결과는 `decision-agent:v3`로 저장하며, 별도 `urgency`, `importance`, `attention` analysis result와 UI 호환용 classification payload 필드를 함께 기록한다.
- PostgreSQL/Demo 메일 서비스와 목록·담당자 화면은 업무 유형 또는 문자열 keyword가 아니라 `attention_quadrant`만으로 행 강조를 결정하도록 바꿨다.
- 기존 demo fixture에는 명시적인 `urgency`, `importance`, `attention_quadrant` 필드를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_foundation.py tests/test_decision_agent.py tests/test_mail_decision_routing_service.py tests/test_mail_decision_runtime.py tests/test_vision_fact_extraction.py tests/test_routing_policy.py tests/test_mail_decision_ui.py -q`: 171 passed.
- `python -m py_compile app/schemas/mail_decision.py app/agents/fact_extraction_agent.py app/agents/decision_agent.py app/repositories/postgres_decision_result_repository.py app/services/postgres_mail_service.py app/services/demo_mail_service.py app/services/demo_seed_service.py app/services/postgres_email_analysis_worker.py app/server.py`: passed.

## 남은 리스크와 후속 작업

- 기존 `email_analysis_results`의 `decision-agent:v2` 또는 오래된 demo 결과는 새 판단 축이 없으면 `normal` attention으로 보수 표시된다. 운영 데이터는 필요한 경우 재분석해야 한다.
- 화면 호환을 위해 row payload의 `priority` 키는 당장 제거하지 않고 `attention_quadrant` 값으로 매핑했다. 외부 소비자가 사라지면 별도 정리할 수 있다.

---

# 2026-08-20 - Hide settings auto assignment policy panel

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Settings tab, routing policy UI |
| 관련 파일 | `app/templates/views/settings.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Settings 탭의 자동배정기준 영역을 잠시 숨기고, 요청하면 롤백해 달라고 했다.
- 자동 배정 정책 partial과 서버 저장 경로는 그대로 두고, Settings 화면에서 해당 패널 include만 임시로 제거하는 방식이 가장 작은 변경으로 판단했다.

## 해결 방법

- `views/settings.html`에서 자동 배정 기준 패널 렌더링을 숨겼다.
- 롤백 포인트를 알 수 있도록 템플릿에 임시 숨김 주석을 남겼다.
- Settings 화면 테스트는 자동 배정 기준 문구와 threshold 입력이 렌더되지 않는 조건으로 갱신했다.
- `partials/auto_assignment_policy.html` 자체와 partial 테스트는 유지해, 나중에 패널을 되살릴 때 기존 폼 동작을 그대로 사용할 수 있게 했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "settings_renders_synthetic_assignees or auto_assignment_policy_partial" -q`: 2 passed.

## 남은 리스크와 후속 작업

- 사용자가 롤백을 요청하면 `views/settings.html`의 숨김 주석 위치에 기존 자동 배정 기준 패널 include를 복원하면 된다.

---

# 2026-08-20 - Fix delayed main tab navigation

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Shell main navigation, HTMX tab switching |
| 관련 파일 | `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Dashboard, Inbox, Monitoring, Search, Settings 등 탭 전환 시 즉시 전환되지 않고 딜레이가 생긴다고 보고했다.
- 확인 결과 메인 탭 버튼에 HTMX `hx-get` 요청과 별도 `fetch()` 클릭 핸들러가 동시에 붙어 있어, HTMX가 로드된 정상 환경에서도 탭 클릭 한 번이 동일한 fragment 로딩 경로를 중복 실행할 수 있었다.
- 또한 활성 탭 표시는 응답 후 swap 단계에서만 정리되어 네트워크 또는 서버 렌더링 시간이 길면 사용자가 탭 전환이 늦는 것으로 보였다.

## 해결 방법

- 메인 탭 전환의 기본 경로를 HTMX 하나로 단일화했다.
- HTMX가 없는 CDN 실패 환경에서만 기존 직접 `fetch()` fallback이 동작하도록 제한했다.
- 탭 클릭 즉시 active nav 상태와 `#main-panel` busy 상태를 반영하고, HTMX swap 또는 request 완료 시 busy 상태를 해제하도록 했다.
- 검색 폼 fallback은 기존처럼 유지했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -q`: 129 passed.
- `CORAMAIL_AUTH_ENABLED=false CORAMAIL_DISPLAY_MODE=demo CORAMAIL_LOCAL_DEV_DEFAULTS=false uv run uvicorn app.server:app --host 127.0.0.1 --port 8017`로 로컬 서버를 띄운 뒤 `curl -i -H 'HX-Request: true' http://127.0.0.1:8017/ui/search`가 정상 HTML fragment를 반환하는 것을 확인했다.

## 남은 리스크와 후속 작업

- 이 환경에는 Node/Python Playwright 패키지가 없어 실제 브라우저 자동 클릭 검증은 실행하지 못했다. 대신 템플릿 회귀 테스트로 HTMX 사용 시 직접 fetch 경로를 타지 않는 조건을 고정했다.

---

# 2026-08-20 - Roll back inbox subject business number badges

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox Queue subject column |
| 관련 파일 | `app/templates/partials/mail_rows.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Inbox Queue의 제목 영역에 갑자기 업무번호가 표시된다며 이전 상태로 롤백해 달라고 요청했다.
- 확인 결과 2026-08-20 데모 식별 편의를 위해 Inbox subject 셀에 `business_refs` 배지를 추가했고, 이후 `Ref` 접두어만 제거되어 업무번호 값 자체가 제목 아래에 남아 있었다.

## 해결 방법

- Inbox Queue 목록의 subject 셀에서 `business_refs` 배지 렌더링을 제거했다.
- 메일 상세 Mail Overview와 검색용 `business_refs` 데이터는 유지했다.
- 회귀 테스트를 목록 HTML에 업무번호 값이 표시되지 않는 조건으로 갱신했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "high_priority_rows_are_visually_marked or demo_inbox_search_keeps_quotation_reference_out_of_rows" -q`: 2 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 생략했다. 변경은 서버 렌더링 partial과 관련 회귀 테스트로 확인했다.

---

# 2026-08-20 - Preserve completed routing display after monitoring rerun

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring tab status, inbox work status, high-priority display |
| 관련 파일 | `app/services/postgres_mail_service.py`, `app/server.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Monitoring 탭에서 Mail Decision 모두 재수행 버튼을 누른 뒤 기존에 inbox에서 decision 완료 및 전달 완료로 보이던 메일들이 `사람검토필요` 상태로 바뀌었다고 보고했다.
- 같은 재수행 이후 오늘 메일에 적용되어 있던 긴급 표시도 사라져 빠른 시연 전에 완료/긴급 표시를 우선 복구해야 했다.

## 해결 방법

- PostgreSQL 메일 행 표시 상태에서 이미 담당자 확정 또는 전달 완료가 있는 메일은 최신 Mail Decision Run이 `review_required`여도 기존 배정/전달 상태를 우선 표시하도록 했다.
- Monitoring Decision stage도 전달 완료 또는 배정 확정이 남아 있으면 `review_required` 대신 완료로 표시해 pipeline health가 완료로 계산되게 했다.
- classification 결과 JSON에서 긴급도 값이 비어 있어도 제목, snippet, 본문, 기존 카테고리의 긴급 신호가 있으면 표시용 `priority=high`를 복원하도록 했다.

## 검증

- `.venv/bin/python -m pytest tests/test_mail_decision_ui.py -k "review_required_rerun or high_priority_from_subject or confirmed_assignment_after_review_required or forwarded_work_status_after_review_required"`: 4 passed.
- `.venv/bin/python -m pytest tests/test_mail_decision_ui.py`: 128 passed.

## 남은 리스크와 후속 작업

- 이번 수정은 시연 안정성을 위한 표시 우선순위 복구다. 실제 라우팅 정책상 불확실한 신규 메일은 계속 사람 검토가 맞다.
- 운영 DB에 이미 생성된 `review_required` run 자체는 삭제하지 않고, UI 표시에서 확정 배정/전달 상태가 우선되게 처리했다.

---

# 2026-08-20 - Hide Documents navigation in demo mode again

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode shell navigation, Documents tab |
| 관련 파일 | `app/templates/shell.html`, `tests/test_document_type_navigation.py` |

## 요청 또는 배경

- 사용자는 데모 모드에서 Documents 탭을 다시 숨겨 두고, 요청하면 다시 보이게 해 달라고 했다.
- 급한 요청이므로 기존 데모 숨김 동작 복원에만 범위를 좁혔다.

## 해결 방법

- `shell.html`에서 데모 모드일 때 Documents navigation 버튼을 숨기는 조건을 복원했다.
- 데모 모드 shell 테스트도 Documents 버튼과 `/ui/documents` HTMX target이 표시되지 않는 기대값으로 되돌렸다.

## 검증

- `uv run pytest tests/test_document_type_navigation.py -q`: 6 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다.
- 작업트리에 기존 미커밋 변경이 있어 이번 요청 관련 변경만 선별 커밋한다.

---

# 2026-08-20 - Move Monitoring row actions into popovers

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring tab table alignment and stage actions |
| 관련 파일 | `app/templates/views/ops.html`, `app/templates/partials/ops_rows.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Monitoring 탭의 모든 칼럼명과 칼럼값을 가운데 정렬해 달라고 요청했다.
- 기존 버튼이 있던 칼럼에서는 버튼을 각 행이 아니라 칼럼명 옆으로 옮기고, 이 버튼은 현재 표시된 행 전체에 대해 실행해야 한다고 했다.
- 개별 실행은 해당 요소를 클릭해 열린 팝업 안에서 수행할 수 있어야 한다고 했다.

## 해결 방법

- Monitoring table header와 visible table cell 값을 중앙 정렬했다.
- `Attach`, `Summary`, `Classify`, `Decision`, `Forward` 헤더에 전체 실행 버튼을 추가했다.
- 행별 실행 버튼은 각 stage/detail popover 하단 액션으로 이동했다.
- 헤더 전체 실행 버튼은 현재 렌더된 행 중 같은 action key를 가진 disabled되지 않은 개별 버튼을 순차 실행하도록 했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "monitoring or ops or typography" -q`: 17 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저에서 다건 전체 실행 클릭 검증은 수행하지 않았다. 현재 검증은 서버 렌더링, CSS, shell JavaScript 회귀 테스트 기준이다.
- 작업트리에 기존 미커밋 UI/테스트 변경이 있어 이번 요청과 관련된 변경만 선별 커밋한다.

---

# 2026-08-20 - Limit monitoring status to completion dots

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring tab pipeline status |
| 관련 파일 | `app/server.py`, `app/templates/partials/ops_rows.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 모니터링 탭의 상태를 빨간색 원과 초록색 원 두 가지로만 표시하라고 요청했다.
- 한 메일의 모든 처리와 전달 완료가 끝난 경우에만 초록색 원이어야 하며, `Decision`이 미실행이면 정상/완료로 표시되면 안 된다고 정정했다.

## 해결 방법

- 파이프라인 상태 계산을 `완료`/`미완료` 두 상태로 축소했다.
- `Attach`는 첨부가 없는 경우 `skipped`를 완료로 인정하되, `Summary`, `Classify`, `Decision`, `Forward`는 완료 상태를 요구하고 전달 완료 전에는 미완료로 표시한다.
- 상태 셀은 텍스트 배지를 제거하고 접근성 설명만 가진 빨간색/초록색 원으로 렌더링한다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "ops_pipeline_status or ops_row_view_requires_decision or ops_view_renders_pipeline_stages" -q`: 5 passed.
- `python -m py_compile app/server.py`: passed.
- `git diff --check -- app/server.py app/templates/partials/ops_rows.html app/static/app.css tests/test_mail_decision_ui.py`: passed.

## 남은 리스크와 후속 작업

- 현재 작업트리에 다른 UI/테스트 변경이 남아 있어 이번 커밋에는 모니터링 상태 표시 관련 변경만 선별 포함한다.

---

# 2026-08-20 - Show Documents navigation in demo mode

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode shell navigation, Documents tab |
| 관련 파일 | `app/templates/shell.html`, `tests/test_document_type_navigation.py` |

## 요청 또는 배경

- 사용자는 데모 모드에서도 Documents 탭이 보이게 해 달라고 요청했다.
- 확인 결과 `/ui/documents` route와 UI state 처리는 이미 데모 모드에서도 동작하고, shell navigation 버튼만 데모 스크린샷용 조건으로 숨겨져 있었다.

## 해결 방법

- `shell.html`에서 데모 모드일 때 Documents navigation 버튼을 숨기던 조건을 제거했다.
- 데모 모드 shell 테스트를 Documents 버튼과 `/ui/documents` HTMX target이 표시되는 기대값으로 갱신했다.

## 검증

- `uv run pytest tests/test_document_type_navigation.py -q`: 6 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다.
- 작업트리에 기존 staged/unstaged 변경이 있어 이번 커밋에는 Documents navigation 관련 변경만 선별 포함한다.

---

# 2026-08-20 - Separate assignment roster text from selection background

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Assignments tab assignee roster |
| 관련 파일 | `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Assignments 탭의 각 담당자 박스 클릭 영역에서 배경색과 글씨색이 겹쳐 보이는 문제를 지적했다.

## 해결 방법

- 담당자 roster 버튼 배경을 흰색 불투명 배경으로 고정했다.
- 선택 상태는 박스 전체 색 채움 대신 파란 테두리와 왼쪽 accent로 표시하게 했다.
- 담당자별 메일 수 숫자는 별도 불투명 pill 배지로 분리해 배경색과 섞이지 않게 했다.
- CSS 회귀 테스트로 일반/선택 담당자 박스와 count 배지의 배경 분리를 확인했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "assignee_work or assignee_roster" -q`: 5 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다.
- 작업트리에 기존 staged/unstaged 변경이 있어 이번 커밋에는 Assignments roster 색상 hunk만 별도 index로 선별 포함한다.

---

# 2026-08-20 - Prevent urgent row tone from blending into routing buttons

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard Mail Streams urgent row, manual routing button |
| 관련 파일 | `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 이전 요청의 의미가 긴급 row의 붉은 배경이 수동 라우팅 버튼 배경과 오버랩되어 보이지 않게 하는 것이라고 정정했다.
- 이전 변경은 버튼 배경 아래에 긴급 배경 레이어를 추가해 실제 요구와 반대로 동작했다.

## 해결 방법

- 긴급 row 전용 수동 라우팅 버튼 background override를 제거했다.
- 뒤쪽에서 적용되는 수동 라우팅 버튼 상태별 배경을 투명 `rgba(...)`가 아닌 불투명 hex 색상으로 바꿨다.
- 회귀 테스트를 버튼이 긴급 row 배경과 blend되지 않도록 검증하는 내용으로 수정했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "high_priority or dashboard_typography" -q`: 5 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다.
- 작업트리에 기존 staged/unstaged 변경이 있어 이번 커밋에는 수동 라우팅 버튼 배경 정정 hunk만 별도 index로 선별 포함한다.

---

# 2026-08-20 - Re-center Monitoring stage action buttons

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring tab stage columns |
| 관련 파일 | `app/templates/views/ops.html`, `app/templates/partials/ops_rows.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Monitoring 탭의 stage별 액션 버튼을 각 컬럼에 맞는 위치로 옮긴 뒤에도 위치가 헷갈리게 보인다고 지적했다.
- 버튼이 옆 컬럼 경계에 붙어 보이지 않도록 padding을 신경 써 다시 배치해 달라고 요청했다.
- 이어서 Decision 컬럼의 `사람검토 필요` 라벨이 `사람검토...`로 잘리는 문제와 상태별 버튼 위치가 들쑥날쑥한 문제를 지적했다.
- 컬럼명과 컬럼 아래 요소도 컬럼 영역의 가운데로 정렬하고, 버튼과 상태 토글 사이 padding/gap을 줄여 달라고 요청했다.

## 해결 방법

- Monitoring table header와 stage cell 내용을 중앙 정렬했다.
- `Decision` 컬럼에 전용 폭을 부여해 `사람검토 필요` 같은 긴 상태 라벨이 잘리지 않도록 여유 폭을 확보했다.
- 버튼 포함 stage cell은 고정 label 칸과 고정 button 칸의 grid로 배치해 상태 라벨 길이가 바뀌어도 버튼 X좌표가 움직이지 않게 했다.
- 상태 pill과 버튼 사이 gap/padding을 줄여 같은 컬럼 안의 묶음처럼 보이게 했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "ops_view_renders_pipeline_stages or monitoring_typography_refinement_keeps_rows_dense or non_dashboard_typography_protects_dense_layouts" -q`: 3 passed, 119 deselected.
- `uv run pytest tests/test_mail_decision_ui.py -k "monitoring or ops or typography" -q`: 16 passed, 106 deselected.
- 실제 브라우저 좌표 검증은 Playwright가 설치되어 있지 않아 수행하지 못했다.

## 남은 리스크와 후속 작업

- 작업 시작 시점에 기존 staged/unstaged 변경이 있어 이번 커밋에는 Monitoring stage 버튼 배치와 직접 관련된 hunk만 선별 포함한다.

---

# 2026-08-20 - Keep unstarted Decision out of normal status

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring tab status column |
| 관련 파일 | `app/server.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Monitoring에서 Decision이 미실행인데 전체 상태가 `정상`으로 보이면 안 된다고 지적했다.
- 이어서 `확인` 상태명도 어색하다고 지적했다.

## 해결 방법

- `ops_pipeline_status()`에서 Decision 단계가 `not_started`이면 전달 단계가 완료처럼 보이더라도 `정상`으로 승격하지 않고 `처리중`으로 표시하게 했다.
- Decision 미실행 detail은 `Decision 미실행`으로 남겨 원인을 tooltip에서 확인할 수 있게 했다.
- 사람 검토가 필요한 상태 라벨은 `확인`에서 `검토`로 되돌리고 detail은 `검토 필요`로 표시한다.
- Decision 미실행이 `정상`으로 표시되지 않는 회귀 테스트를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "ops_pipeline_status or ops_view" -q`: 4 passed.
- `python -m py_compile app/server.py`: 통과.
- `git diff --check -- app/server.py tests/test_mail_decision_ui.py`: 통과.

## 남은 리스크와 후속 작업

- 작업트리에 기존 UI/문서 미커밋 변경이 있어 이번 커밋에는 Monitoring 상태 판정 hunk만 선별 포함한다.

---

# 2026-08-20 - Refine assignment summary labels by count meaning

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Assignments tab |
| 관련 파일 | `app/templates/views/assignee_work.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Assignments 탭 요약 라벨이 `배정`, `검토`, `전달`처럼 단어만 있으면 수치 의미가 불명확하다고 지적했다.
- 영어 `Assigned`, `Review`, `Forwarded`를 그대로 짧게 옮기기보다 실제 수치 의미에 맞게 `배정 완료`, `배정 메일`, `검토 필요`, `전달 완료` 같은 표현을 써야 한다고 요청했다.

## 해결 방법

- 전체 담당 메일 수인 `summary.mail_count` 라벨을 `배정 메일`로 변경했다.
- 사람 확인이 필요한 `summary.review_count` 라벨을 `검토 필요`로 변경했다.
- 긴급 건수인 `summary.urgent_count` 라벨을 `긴급 메일`로 변경했다.
- 실제 전달된 건수인 `summary.forwarded_count` 라벨을 `전달 완료`로 변경했다.

## 검증

- `.venv/bin/pytest tests/test_mail_decision_ui.py::test_assignee_work_template_renders_selected_workload`: 1 passed.

## 남은 리스크와 후속 작업

- 작업 시작 시점에 기존 미커밋 변경이 여러 파일에 있어 이번 커밋에는 Assignments 탭 라벨 정정 hunk만 선별 포함한다.

---

# 2026-08-20 - Layer urgent row tone under manual routing buttons

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard Mail Streams urgent row, manual routing button |
| 관련 파일 | `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 긴급 메일일 때 적용되는 배경색이 수동 라우팅 버튼 배경색 뒤에도 적용되도록 요청했다.

## 해결 방법

- 긴급 row 안의 수동 라우팅 버튼 상태별 배경을 2-layer `background`로 바꿔 버튼 tone 아래에 긴급 row tone을 깔았다.
- `ready`, `sent`, `failed`, `pending`, `unassigned` 상태 모두 같은 긴급 배경 레이어를 갖도록 했다.
- CSS 회귀 테스트를 추가해 긴급 row의 수동 라우팅 버튼이 `linear-gradient` 버튼 tone과 긴급 배경 레이어를 함께 갖는지 확인했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "high_priority or dashboard_typography" -q`: 5 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. CSS 레이어링은 정적 회귀 테스트로 확인했다.
- 작업 시작 시점에 기존 미커밋 변경이 여러 파일에 있어 이번 커밋에는 긴급 row/수동 라우팅 버튼 hunk만 선별 포함한다.

---

# 2026-08-20 - Allow combined dashboard stat filters

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard tab, stat card filters |
| 관련 파일 | `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 `Today Mails`와 `Urgent Mails`를 둘 다 눌러 활성화하면 오늘 수신된 긴급 메일만 표시되도록 요청했다.
- 이전 hover 변경으로 클릭 전 카드 hover가 다른 카드와 다르게 색상 테두리를 표시하는 문제도 되돌려야 했다.
- 활성화된 카드에 마우스를 올려도 활성 테두리가 사라지지 않아야 했다.

## 해결 방법

- Dashboard stat 필터 hidden 값을 단일 값이 아니라 `today,urgent` 같은 다중 값으로 관리하게 했다.
- 필터 판정은 활성화된 모든 조건을 만족하는 행만 보이도록 AND 조건으로 바꿨다.
- 비활성 stat 카드 hover는 기존 공통 `.stat:hover` 동작을 따르게 하고, 활성 카드 hover는 굵은 활성 테두리와 shadow를 유지하게 했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "urgent_stat or dashboard_mail_stat_filters or stats_cards_filter or manual_route_polling" -q`: 4 passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 120 passed.
- `python -m py_compile app/server.py`: passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 hover/click 검증은 수행하지 않았다. 동작은 shell JavaScript와 CSS 회귀 테스트로 확인했다.
- 작업트리에 기존 미커밋 변경이 섞여 있어 이번 커밋에는 Dashboard stat filter follow-up hunk만 선별 포함한다.

---

# 2026-08-20 - Localize assignment summary labels

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Assignments tab |
| 관련 파일 | `app/templates/views/assignee_work.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Assignments 탭의 `Assigned`, `Review`, `Urgent`, `Forwarded` 문구를 자연스럽고 간결한 한국어로 바꿔 달라고 요청했다.

## 해결 방법

- Assignments 탭 요약 카드 라벨을 `배정`, `검토`, `긴급`, `전달`로 변경했다.
- 같은 화면의 검색 placeholder도 `담당 메일 검색`으로 바꿔 영어 표현을 줄였다.
- 상태 enum과 서버 데이터 계약은 변경하지 않고 표시 문구만 수정했다.

## 검증

- `.venv/bin/pytest tests/test_mail_decision_ui.py::test_assignee_work_template_renders_selected_workload`: 1 passed.

## 남은 리스크와 후속 작업

- 작업 시작 시점에 기존 미커밋 변경이 여러 파일에 있어 이번 커밋에는 Assignments 탭 라벨 변경 hunk만 선별 포함한다.

---

# 2026-08-20 - Close Monitoring popovers on outside click and move actions into columns

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring tab popovers, Monitoring table actions |
| 관련 파일 | `app/templates/shell.html`, `app/templates/views/ops.html`, `app/templates/partials/ops_rows.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Monitoring 탭의 각 컬럼 상세 팝업이 다시 같은 요소를 눌러야만 닫히는 문제를 지적했다.
- 열린 팝업이 계속 누적되지 않도록 팝업 박스 영역 밖을 클릭하면 자동으로 닫히게 해 달라고 요청했다.
- 또한 우측 Control 컬럼에 몰려 있던 아이콘 버튼들을 각 기능에 해당하는 컬럼으로 옮겨 달라고 요청했다.

## 해결 방법

- 열린 `details` 팝업을 닫는 `closeTransientPopovers()`가 실제 팝업 박스 내부 클릭만 예외로 두도록 바꿨다.
- 클릭 시점에 이미 열려 있던 팝업을 다음 tick에 닫아 native `details/summary` 토글 타이밍 때문에 다시 열리는 문제를 피했다.
- Attach, Summary, Classify, Decision, Forward 액션 버튼을 각 해당 컬럼의 상태 pill 옆으로 이동했다.
- Monitoring table의 Control 컬럼과 컬럼 선택 항목을 제거하고, 새로고침 버튼은 Monitoring 헤더로 옮겼다.
- stage pill과 action icon이 함께 들어가도록 `ops-stage-control`/`ops-stage-action` CSS를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "shell_closes_open_popovers or monitoring or ops or typography" -q`: 16 passed, 104 deselected.

## 남은 리스크와 후속 작업

- 실제 브라우저 클릭 검증은 수행하지 않았다. 동작은 shell JavaScript와 Monitoring 템플릿/CSS 회귀 테스트로 확인했다.
- 작업트리에 기존 Dashboard 필터와 Monitoring 컬럼 폭 관련 미커밋 변경이 있어 이번 커밋에는 현재 요청과 직접 관련된 hunk만 선별 포함한다.

---

# 2026-08-20 - Filter dashboard Mail Streams from stat cards

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard tab, Mail Streams |
| 관련 파일 | `app/server.py`, `app/templates/partials/stats.html`, `app/templates/views/dashboard.html`, `app/templates/partials/mail_rows.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Dashboard 탭의 `오늘 수신 메일 수` stat 카드를 누르면 Mail Streams에 오늘 수신 메일만 표시되고, `Urgent Mails` 카드를 누르면 긴급 메일만 표시되도록 요청했다.
- 이어서 클릭 적용이 되지 않는다고 알렸고, 클릭한 카드가 활성 상태처럼 표시되며 필터 해제 시 비활성 표시로 돌아가야 한다고 요청했다.
- 추가로 이 동작은 메일 유형 필터와 같은 방식으로 즉각 처리되어야 하며, 활성화 시 테두리가 더 굵게 표시되면 좋겠다고 요청했다.
- Dashboard의 오늘 기준은 기존 `dashboard_summary()`와 동일하게 demo mode에서는 로드된 메일 중 최신 수신일, 운영 mode에서는 현재 표시 timezone의 실제 오늘 날짜를 따른다.

## 해결 방법

- Mail Streams row에 수신일 키와 긴급 여부를 `data-*` 속성으로 추가했다.
- Today/Urgent stat 카드를 JS 위임 클릭 버튼으로 전환해 서버 재요청 없이 현재 렌더된 행을 즉시 숨김/표시하도록 했다.
- 같은 카드를 다시 누르면 필터를 해제하고 전체 Mail Streams로 돌아가도록 했다.
- Dashboard 행 자동 갱신과 수동 라우팅 후 재렌더링은 전체 행을 받은 뒤 현재 stat 필터를 다시 적용하게 했다.
- stat 필터와 기존 카테고리 칩 필터가 서로 덮어쓰지 않도록 hidden class를 `email-row-hidden-by-stat`, `email-row-hidden-by-category`로 분리했다.
- 활성 카드에는 `is-active`와 `aria-pressed=true`를 적용하고 Today/Urgent 카드별 굵은 안쪽 테두리와 shadow로 상태를 표시했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "dashboard_summary or dashboard_mail_stat_filters or stats_cards_filter or urgent_stat or manual_route_polling or dashboard_category_filter" -q`: 6 passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 120 passed.
- `python -m py_compile app/server.py`: passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 클릭 검증은 수행하지 않았다. 동작은 서버 필터 함수, 렌더링 HTML, shell JavaScript 문자열 회귀 테스트로 확인했다.
- 작업트리에 기존 미커밋 변경이 섞여 있어 이번 커밋에는 Dashboard stat card filtering 관련 hunk만 선별 포함한다.

---

# 2026-08-20 - Halve Monitoring sender column width

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring tab table layout |
| 관련 파일 | `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Monitoring 탭의 발신자 컬럼을 현재 폭의 절반 정도로 더 줄여 달라고 요청했다.
- 업무 유형과 담당자 컬럼 폭은 그대로 두고 발신자 컬럼만 추가 축소해야 했다.

## 해결 방법

- Monitoring table의 기본/중간 폭 기준에서 발신자 컬럼을 134px에서 67px로 줄였다.
- 최종 typography refinement 기준에서 발신자 컬럼을 164px에서 82px로 줄였다.
- 줄어든 발신자 컬럼 폭에 맞춰 Monitoring table 최소 폭을 최종 기준 1860px에서 1778px로 낮췄다.
- UI CSS 회귀 테스트의 기대 최소 폭을 새 기준에 맞췄다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "non_dashboard_typography_protects_dense_layouts or monitoring_typography_refinement_keeps_rows_dense or monitoring_table_cells_keep_native_table_layout"`: 3 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경은 CSS 규칙과 관련 UI 회귀 테스트로 확인했다.
- 작업트리에 별도 미커밋 변경이 있어 이번 커밋에는 Monitoring 발신자 컬럼 폭 조정 관련 hunk만 선별 포함한다.

---

# 2026-08-20 - Remove Ref prefix from inbox business numbers

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox tab, Mail Overview |
| 관련 파일 | `app/templates/partials/mail_rows.html`, `app/templates/partials/email_detail.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 inbox 탭의 Mail Overview에서 업무번호 앞에 붙는 `Ref` 텍스트를 제거해 달라고 요청했다.
- 동일한 업무번호 배지가 받은편지함 리스트에도 표시되어 일관되게 `Ref` 접두어 없이 업무번호 값만 보이도록 정리했다.

## 해결 방법

- 받은편지함 메일 행의 업무 참조번호 배지에서 `Ref ` 접두어를 제거했다.
- 메일 상세 `Mail Overview`의 업무번호 pill에서도 `Ref ` 접두어를 제거했다.
- 관련 UI 테스트 기대값을 접두어 미표시와 업무번호 값 유지 조건으로 갱신했다.

## 검증

- `pytest tests/test_mail_decision_ui.py -k "polishes_demo_summary_key_request or high_priority_rows_are_visually_marked or search_and_rows_expose_quotation_reference"`: 전역 `pytest` 미설치로 실패.
- `uv run pytest tests/test_mail_decision_ui.py -k "polishes_demo_summary_key_request or high_priority_rows_are_visually_marked or search_and_rows_expose_quotation_reference"`: 3 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경 범위는 서버 렌더링 HTML 문자열과 관련 UI 회귀 테스트로 확인했다.

---

# 2026-08-20 - Rename Monitoring status labels naturally

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring tab status column |
| 관련 파일 | `app/server.py`, `app/templates/partials/ops_rows.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Monitoring 상태값의 `진행` 표현이 실제 운영 화면처럼 자연스럽지 않다고 지적했다.
- 디자인 변경 없이 상태 표현만 자연스럽게 바꿔야 했다.

## 해결 방법

- 첫 컬럼 표시 라벨을 `정상`, `처리중`, `확인`, `오류`로 정리했다.
- 사람 확인이 필요한 상태는 칩에 `확인`, tooltip에 `확인 필요`로 표시해 compact layout을 유지했다.
- `진행` fallback도 `처리중`으로 바꿔 빈 상태가 발생해도 어색한 표현이 나오지 않게 했다.
- 상태 라벨 회귀 테스트를 새 라벨 집합에 맞췄다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "monitoring or ops or typography" -q`: 15 passed.
- `uv run python - <<'PY' ...`: Monitoring row render sample이 `<strong>정상</strong>`으로 출력되는 것을 확인했다.
- `python -m py_compile app/server.py`: 통과.
- `git diff --check`: 통과.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경은 서버 렌더링 HTML과 관련 UI 회귀 테스트로 확인했다.

---

# 2026-08-20 - Remove numeric fallback from Monitoring status

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring tab status column |
| 관련 파일 | `app/server.py`, `app/templates/partials/ops_rows.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Monitoring 상태가 여전히 이전처럼 숫자로 표시된다고 보고했다.
- 첫 컬럼은 숫자 진행률이 아니라 축약 상태값만 보여야 했다.

## 해결 방법

- Monitoring 첫 컬럼 템플릿에서 `pipeline_score` 표시와 `--ops-score` inline style을 제거했다.
- `pipeline_status.label`이 없을 때도 숫자로 fallback하지 않고 `진행`으로 fallback하게 했다.
- Tooltip detail에서도 진행률 숫자를 제거하고 세부 상태명만 남겼다.
- 회귀 테스트에 `--ops-score`가 렌더링되지 않는 조건을 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "monitoring or ops or typography" -q`: 15 passed.
- `uv run python - <<'PY' ...`: Monitoring row render sample이 `<strong>정상</strong>`으로 출력되고 숫자 점수가 없는 것을 확인했다.
- `python -m py_compile app/server.py`: 통과.
- `git diff --check`: 통과.

## 남은 리스크와 후속 작업

- 실행 중인 로컬 서버가 이전 프로세스이면 최신 템플릿이 반영되지 않을 수 있다. 이 경우 서버 재시작 또는 브라우저 강력 새로고침이 필요하다.

---

# 2026-08-20 - Reduce Monitoring status labels to four states

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring tab status column |
| 관련 파일 | `app/server.py`, `app/templates/partials/ops_rows.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Monitoring 첫 컬럼 상태값이 빈 상태로 보이며, 상태값 종류도 너무 많다고 보고했다.
- 디자인은 유지하고 표시 방식만 더 직관적이어야 했다.

## 해결 방법

- 첫 컬럼 표시값을 `정상`, `진행`, `검토`, `실패` 4개로 축소했다.
- `전달 대기`, `미시작`, `대기`, `전달 완료`, `처리 완료` 같은 세부 상태는 tooltip detail에만 남겼다.
- 템플릿은 `pipeline_status.label`을 표시하게 바꾸고, 값이 없을 때 `pipeline_score`로 fallback해 빈칸이 나오지 않도록 했다.
- 상태 라벨 집합이 4개로 제한되는 회귀 테스트를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "monitoring or ops or typography" -q`: 15 passed.
- `python -m py_compile app/server.py`: 통과.
- `git diff --check`: 통과.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경은 서버 렌더링 HTML과 관련 UI 회귀 테스트로 확인했다.

---

# 2026-08-20 - Restore compact Monitoring status display

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring tab status column |
| 관련 파일 | `app/server.py`, `app/templates/partials/ops_rows.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Monitoring 상태값을 더 직관적으로 표시하라는 요청이 디자인 변경 의도가 아니었다고 정정했다.
- 직전 변경의 큰 라벨 pill은 이전 숫자 칩보다 가독성이 떨어졌고, 요구사항은 상태값 표현 방식 개선이었다.

## 해결 방법

- Monitoring 첫 컬럼을 이전 compact `ops-health-ring` 형태로 되돌렸다.
- 표시값은 가중 점수 숫자 대신 `검토`, `진행`, `전달`, `대기`, `완료`, `실패`, `미시작` 같은 짧은 상태값으로 바꿨다.
- 전체 의미와 기존 진행률은 tooltip에 `검토 필요 · 파이프라인 진행률 94%`처럼 남겼다.
- 큰 status pill 전용 CSS를 제거하고, 검토 필요 상태만 기존 compact 칩 색상 체계에 맞는 warning tone으로 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "monitoring or ops or typography" -q`: 14 passed.
- `python -m py_compile app/server.py`: 통과.
- `git diff --check`: 통과.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경은 서버 렌더링 HTML, CSS 규칙, 관련 UI 회귀 테스트로 확인했다.

---

# 2026-08-20 - Replace Monitoring score with status labels

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring tab status column, pipeline progress display |
| 관련 파일 | `app/server.py`, `app/templates/partials/ops_rows.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Monitoring 탭의 숫자형 상태값이 직관적이지 않다고 보고 더 이해하기 쉬운 상태값으로 변경해 달라고 요청했다.
- 기존 첫 컬럼은 6개 파이프라인 단계의 가중 평균 점수만 보여 주어 사용자가 지금 필요한 조치가 무엇인지 바로 알기 어려웠다.

## 해결 방법

- Monitoring 행에 `pipeline_status`를 추가해 `실패`, `검토 필요`, `진행 중`, `전달 완료`, `전달 대기`, `처리 완료`, `미시작`, `대기` 라벨을 계산하게 했다.
- 기존 파이프라인 점수는 라벨 옆의 작은 `%`와 tooltip detail로 남겨 진행률 확인과 디버깅이 가능하게 했다.
- 첫 컬럼을 라벨 pill 폭에 맞게 넓히고 상태별 색상을 적용했다.
- 서버 렌더링 테스트와 상태 라벨 우선순위 테스트를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "monitoring or ops or typography" -q`: 14 passed.
- `python -m py_compile app/server.py`: 통과.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경은 서버 렌더링 HTML, CSS 규칙, 관련 UI 회귀 테스트로 확인했다.
- 작업트리에 이전 Monitoring 컬럼 폭 조정 변경이 남아 있어 커밋 범위를 선별해야 한다.

---

# 2026-08-20 - Narrow Monitoring sender business assignee columns

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring tab table layout |
| 관련 파일 | `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Monitoring 탭에서 발신자, 업무 유형, 담당자 컬럼이 과하게 넓어 가로 폭을 줄여 달라고 요청했다.
- 과하게 좁히지는 말고 현재보다 적당히 당기는 수준이 필요했다.

## 해결 방법

- Monitoring table의 기본/중간 폭 기준에서 발신자, 업무 유형, 담당자 컬럼 폭을 각각 150/108/132px에서 134/96/118px로 줄였다.
- 최종 typography refinement 기준에서는 발신자, 업무 유형, 담당자 컬럼 폭을 188/128/158px에서 164/112/138px로 줄였다.
- 줄어든 컬럼 폭에 맞춰 Monitoring table 최소 폭을 최종 기준 1860px에서 1800px로 낮췄다.
- UI CSS 회귀 테스트의 기대 최소 폭을 새 기준에 맞췄다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "non_dashboard_typography_protects_dense_layouts or monitoring_typography_refinement_keeps_rows_dense or monitoring_table_cells_keep_native_table_layout"`: 3 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경은 CSS 규칙과 관련 UI 회귀 테스트로 확인했다.
- 작업트리에 별도 미커밋 변경이 있어 이번 커밋에는 Monitoring 컬럼 폭 조정 관련 파일만 선별 포함한다.

---

# 2026-08-20 - Increase Monitoring table typography

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring tab table typography, dense status table |
| 관련 파일 | `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Monitoring 탭에서 특히 표 칼럼명과 표 안의 텍스트가 작아 가독성이 낮다고 다시 지적했다.
- 이전 요청의 기준처럼 핵심 요소와 부가 요소의 폰트 차이를 유지하되, 행별 높이는 여전히 작게 유지해야 했다.

## 해결 방법

- Monitoring table header를 12px/15px로 키워 칼럼명을 더 읽기 쉽게 했다.
- Table body를 13px/17px로 키우고 subject는 14px/18px로 더 강조했다.
- Cell padding은 4px/9px로만 늘려 행 높이 증가를 제한했다.
- 글자 확대에 맞춰 table min-width와 주요 column 폭을 넓혀 텍스트가 눌리거나 배치가 꼬이지 않도록 했다.
- Business chip과 stage pill도 12px 기준으로 조정해 표 본문과 시각 계층이 맞도록 했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "monitoring or ops or typography" -q`: 13 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경은 CSS 규칙과 Monitoring 관련 UI 회귀 테스트로 검증했다.

---

# 2026-08-20 - Show delivery status label in Mail Decision panel

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox Mail Decision panel, Mail Overview alignment |
| 관련 파일 | `app/server.py`, `app/templates/partials/mail_decision_panel.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Mail Decision 패널의 `Status` 표시를 `전달 상태`로 바꾸고, 행 높이 기준 가운데 정렬되도록 요청했다.

## 해결 방법

- Mail Decision 패널 첫 행 레이블을 `Status`에서 `전달 상태`로 변경했다.
- 현재 메일에 `manual_route_status_label`이 있으면 Mail Decision 패널 첫 행 값으로 `미전달`, `전달 완료`, `전달 중`, `전달 실패` 같은 전달 상태를 우선 표시하게 했다.
- 전달 상태별 badge tone을 success/warning/danger/slate로 매핑했다.
- 전달 상태 필드가 없는 런타임 API mock이나 직접 패널 렌더링에서는 기존 Mail Decision run 상태 표시를 유지하게 했다.
- `info-table td`에 `vertical-align: middle`을 적용해 Overview와 Decision의 정보 행 내용이 행 높이 기준 세로 중앙에 놓이도록 했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -q`: 116 passed.
- `python -m py_compile app/server.py`: 통과.
- `git diff --check`: 통과.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경은 서버 렌더링 HTML과 CSS 회귀 테스트로 확인했다.

---

# 2026-08-20 - Refine Monitoring typography while preserving density

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring tab typography, dense status table |
| 관련 파일 | `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Monitoring 탭에도 Dashboard/Search/Settings와 같은 방식으로 폰트 조정을 적용해 달라고 요청했다.
- 단, Monitoring은 한 화면에서 많은 메일 상태를 보는 탭이므로 행별 높이가 작을수록 좋고, 현재는 글씨가 너무 작다는 점을 함께 지적했다.
- 핵심 요소와 부가 요소의 폰트 차이를 유지하고, 제목·컬럼 영역은 불필요하게 커지지 않아야 했다.

## 해결 방법

- Monitoring 제목, 필터, metric 숫자, table 본문, subject, stage pill, popover 텍스트에 전용 typography refinement를 추가했다.
- Table 본문은 12px/16px로 키우고 subject는 13px/17px로 더 강조했다.
- Header는 10px 계층을 유지하고, cell padding은 3px 기준으로 유지해 row height 증가를 제한했다.
- 글자 확대에 맞춰 table min-width와 subject/sender/business/assignee/stage column 폭을 늘려 가로 스크롤 기반으로 배치가 눌리지 않게 했다.
- Stage pill은 22px, action icon은 24px로 유지해 상태 확인성은 올리되 행 높이는 조밀하게 유지했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "monitoring_typography or non_dashboard_typography or ops_view or monitoring_table" -q`: 4 passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "monitoring or ops or typography" -q`: 13 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경은 CSS 규칙과 Monitoring 관련 서버 렌더링/UI 회귀 테스트로 검증했다.
- 작업트리에 별도 미커밋 변경이 남아 있어 이번 커밋에는 Monitoring typography 관련 hunk만 선별 포함한다.

---

# 2026-08-20 - Remove Monitoring tab N+1 detail lookups

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring tab performance, PostgreSQL mail attachments |
| 관련 파일 | `app/server.py`, `app/repositories/postgres_mail_repository.py`, `app/services/postgres_mail_service.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Monitoring 탭 클릭 후 탭 진입 때마다 약 5초 딜레이가 발생한다고 보고했다.
- 딜레이의 근본 원인을 분석하고 해결해 달라고 요청했다.

## 원인

- `ops_console_context()`가 Monitoring 행 80개를 만들 때 각 행마다 `_email_detail_by_ref()`를 호출했다.
- PostgreSQL 서비스의 상세 조회는 `message_by_uid()`에서 전체 메일 목록을 다시 훑고, 이어서 첨부파일과 수신자 조회를 추가로 수행한다.
- 결과적으로 Monitoring 탭 진입 한 번이 목록 조회 1회가 아니라 행 수만큼 상세 조회를 반복하는 N+1 패턴이 되었고, 실제 DB에서는 5초급 지연으로 커질 수 있었다.

## 해결 방법

- Monitoring 행 조립에서 메일 상세 조회를 제거했다.
- PostgreSQL 저장소에 여러 메일의 첨부파일을 한 번에 조회하는 `attachments_for_messages()`를 추가했다.
- PostgreSQL mailbox 서비스에 `attachments_for_messages_payload()`를 추가해 Monitoring 표가 필요한 첨부 표시 정보만 배치로 만들게 했다.
- `ops_console_context()`는 목록 조회 1회와 첨부 배치 조회 1회만 사용하고, 행별 상세 조회를 호출하지 않도록 바꿨다.
- 행별 상세 조회가 다시 들어오지 않도록 UI 테스트를 추가했다.

## 검증

- `python -m py_compile app/server.py app/repositories/postgres_mail_repository.py app/services/postgres_mail_service.py`: 통과.
- `uv run pytest -q tests/test_mail_decision_ui.py -k "monitoring or ops_console_context or postgres_detail"`: 8 passed, 106 deselected.
- `uv run pytest -q tests/test_mail_decision_ui.py`: 116 passed.
- `git diff --check`: 통과.

## 남은 리스크와 후속 작업

- 실제 브라우저에서 운영 DB를 붙인 시간 측정은 수행하지 않았다. 코드 경로상 Monitoring 탭의 행별 상세 조회는 제거되었으며, 실제 DB에서는 기존 `1 + 행별 상세 조회` 구조가 `목록 1회 + 첨부 배치 1회` 구조로 축소된다.

---

# 2026-08-20 - Fix inconsistent forwarded status between Mail Overview and Mail Decision

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox Mail Overview, Mail Decision status, routing delivery state |
| 관련 파일 | `app/services/postgres_mail_service.py`, `app/server.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Inbox에서 `[긴급 장애] 현장 네트워크 장비 통신 불안정` 메일을 확인할 때 Mail Overview의 담당자 옆 상태는 `미전달`인데 Mail Decision의 `Status`는 `전달 완료`로 표시되는 불일치를 보고했다.
- 원인 파악 후 두 상태 표시의 오류 수정을 요청했다.

## 원인

- Mail Decision 패널 상태 계산이 최신 Mail Decision Run 상태와 현재 메일의 합성 `work_status`를 섞어 사용했다.
- `work_status`는 목록과 상세의 업무 상태를 위한 값인데, 패널이 이를 그대로 가져오면서 Mail Decision의 실행/배정 판단 상태가 실제 전달 상태처럼 표시될 수 있었다.
- PostgreSQL mailbox row 변환에서도 `routing_forwarded_at` 값만 있으면 `routing_status='forwarded'` 또는 최신 수동 전달 알림 `sent`가 아니어도 `전달 완료`로 판단할 수 있었다. 이로 인해 오래되었거나 불완전한 forwarded timestamp가 상태를 오염시킬 수 있었다.

## 해결 방법

- `PostgresMailboxService._work_status()`에서 실제 전달 완료 판정은 `routing_status='forwarded'`, 최신 `manual_route_status='sent'`, 또는 `manual_route_sent_at`만 사용하도록 했다.
- 실제 전달 완료는 `auto_assigned`보다 구체적인 상태이므로 우선 평가되게 했다.
- `mail_decision_panel_status()`는 현재 메일의 합성 `work_status`를 더 이상 반환하지 않고, 현재 라우팅 배정 상태 또는 Mail Decision Run 상태만 사용하도록 분리했다.
- stale `routing_forwarded_at`만 있는 경우 `미전달`과 `자동 배정`이 함께 표시되는 회귀 테스트를 추가했다.
- Mail Decision 패널이 전달 상태가 아니라 배정 상태를 표시하는 회귀 테스트를 갱신했다.

## 검증

- `pytest tests/test_mail_decision_ui.py -q`: 전역 `pytest` 명령이 없어 실행 불가.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 113 passed.

## 남은 리스크와 후속 작업

- 실제 운영 DB의 기존 `routing_forwarded_at` 값은 보존된다. 이제 표시 판정에는 단독으로 사용하지 않으므로 UI 불일치는 해소되지만, 데이터 정합성 점검이 필요하면 별도 마이그레이션 또는 진단 쿼리를 추가할 수 있다.

---

# 2026-08-20 - Rename sender column labels from recipient to sender

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard, Inbox, assignee work table headers |
| 관련 파일 | `app/templates/views/dashboard.html`, `app/templates/views/inbox.html`, `app/templates/views/assignee_work.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 메일 목록 표의 `수신자` 칼럼명이 실제 표시 데이터 의미에 맞지 않으므로 `발신자`로 바꿔 달라고 요청했다.

## 해결 방법

- Dashboard 메일 목록, Inbox 메일 목록, 담당자 업무 메일 목록의 sender column header를 `발신자`로 변경했다.
- Dashboard/Inbox 헤더 순서 검증 테스트의 기대값도 `발신자`로 갱신했다.

## 검증

- `rg -n "수신자" app/templates tests/test_mail_decision_ui.py`: 잔여 결과 없음.
- `uv run pytest tests/test_mail_decision_ui.py -q -k "mail_list_table_headers"`: 1 passed, 119 deselected.
- 전체 `uv run pytest tests/test_mail_decision_ui.py -q`는 현재 작업트리에 있던 별도 dashboard/shell 변경의 `test_shell_closes_open_popovers_on_outside_click` 실패로 통과하지 못했다. 이번 헤더 변경 hunk와는 무관한 기존 미커밋 변경 영향이다.

## 남은 리스크와 후속 작업

- 작업 시작 시점에 Dashboard/Shell/CSS 관련 미커밋 변경이 작업트리에 있어 이번 커밋에는 칼럼명 변경 hunk만 분리해 포함한다.

---

# 2026-08-20 - Make side inspector email body height dynamic

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring side inspector email body iframe |
| 관련 파일 | `app/templates/partials/email_detail.html`, `app/templates/shell.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Monitoring 사이드탭의 본문 영역이 본문 분량보다 작게 고정되어, 본문 내용을 모두 확인하려면 본문 영역 내부에서 스크롤해야 한다고 지적했다.
- 본문 영역은 실제 본문 분량에 맞게 유동적으로 설정되어야 한다고 요청했다.

## 원인

- 본문은 `srcdoc` iframe으로 렌더링되는데, iframe sandbox에 `allow-same-origin`이 없어 부모 JS가 iframe 내부 문서의 실제 높이를 안정적으로 읽지 못할 수 있었다.
- 높이 측정이 실패하면 사이드탭 전용 최소 높이만 적용되어 긴 본문이 iframe 내부 스크롤 영역에 갇힐 수 있었다.

## 해결 방법

- email body iframe sandbox에 `allow-same-origin`을 추가하되, `allow-scripts`는 추가하지 않아 메일 본문 스크립트 실행은 계속 막았다.
- iframe에 `scrolling="no"`를 추가해 본문 iframe 자체 스크롤을 만들지 않도록 했다.
- `resizeEmailBodyFrames()`에서 iframe 내부 `body`와 `documentElement` overflow를 숨기고, 높이를 `auto`로 초기화한 뒤 실제 scroll/offset height로 재계산하도록 했다.
- 이미지나 지연 렌더링으로 본문 높이가 뒤늦게 바뀌는 경우를 위해 `ResizeObserver`와 80ms/300ms 지연 재계산을 추가했다.
- iframe 속성과 높이 조정 JS를 UI 테스트로 고정했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -q`: 115 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경은 srcdoc iframe 접근 권한, JS source, 템플릿 렌더링, UI 테스트로 검증했다.
- 작업 시작 시점에 Monitoring attachment bulk lookup 관련 미커밋 변경이 이미 작업트리에 있었으므로 이번 커밋에는 본문 iframe 높이 조정 hunk만 분리해 포함한다.

---

# 2026-08-20 - Fit Monitoring inspector body content

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring mail inspector body layout |
| 관련 파일 | `app/templates/partials/ops_email_inspector.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Monitoring 사이드탭에서 본문 영역이 실제 본문 분량에 맞게 설정되길 요청했다.
- 사이드탭 안의 가장 바깥 박스 영역을 제거하고 내부 박스 영역들이 바로 바깥에 놓이게 해 달라고 요청했다.
- 사이드탭 헤더의 `Mail Detail` 텍스트 영역을 제거해 달라고 요청했다.

## 해결 방법

- `ops_email_inspector.html`에서 `Mail Detail` label을 제거하고 메일 제목과 닫기 버튼만 남겼다.
- iframe 기반 본문 영역을 로드 시 내부 문서 높이에 맞춰 조정하는 `resizeEmailBodyFrames()`를 추가하고 초기 로드, Inbox/Monitoring 상세 swap 후 호출하도록 했다.
- Monitoring 사이드탭 내부에서만 `.detail-card`의 border, radius, shadow, background를 제거해 공용 Inbox 상세 카드 스타일은 유지하면서 사이드탭의 외곽 박스만 시각적으로 없앴다.
- Monitoring 사이드탭 내부의 `.detail-layout` padding을 제거하고, 사이드탭 본문 iframe 최소 높이를 낮춰 짧은 본문이 큰 빈 영역을 만들지 않도록 했다.
- 관련 JS source와 CSS 상태를 UI 테스트로 고정했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -q`: 112 passed.
- `python -m py_compile app/server.py`: 통과.
- `git diff --check`: 통과.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. iframe 높이 조정은 srcdoc 기반 동일 출처 문서를 전제로 하며, 접근할 수 없는 외부 iframe에는 조용히 실패하도록 했다.

---

# 2026-08-20 - Close Monitoring popovers and relabel Classify DB results

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring popovers, Monitoring Classify stage label |
| 관련 파일 | `app/templates/shell.html`, `app/server.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 버튼 클릭 후 열린 팝업이 다른 곳을 클릭하면 사라지도록 요청했다.
- 이어서 Monitoring 표의 `Classify` 단계 라벨이 `DB`로 표시되는 대신 `완료`로 표시되도록 요청했다.

## 해결 방법

- `details.ops-detail-menu`, `details.ops-column-menu`, `details[data-cc-popover]`처럼 떠 있는 팝오버 성격의 `details`를 대상으로 바깥 클릭 시 `open=false` 처리하는 `closeTransientPopovers()`를 추가했다.
- 팝오버 내부 클릭은 유지되도록 `details.contains(target)`인 경우 닫지 않게 했다.
- 첨부파일 펼침처럼 콘텐츠 영역에 남아야 하는 일반 `details.attachment`는 닫힘 대상에 포함하지 않았다.
- `ops_classification_stage()`에서 완료 상태의 `classification_state_label == DB`는 사용자 표시 라벨을 `완료`로 보정했다.
- 팝오버 닫힘 JS와 Classify 라벨 보정을 각각 UI 테스트로 고정했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -q`: 110 passed.
- `python -m py_compile app/server.py`: 통과.

## 남은 리스크와 후속 작업

- 실제 브라우저 클릭 검증은 수행하지 않았다. 변경은 템플릿 JS source 테스트와 서버 표시 로직 테스트로 확인했다.

---

# 2026-08-20 - Fix Monitoring table borders and inspector width

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring table layout, Monitoring mail inspector |
| 관련 파일 | `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Monitoring 표에서 발신자와 담당자 컬럼의 행 밑줄이 어긋나 표 구조와 행 구분이 깨져 보인다고 지적했다.
- 메일 클릭 시 열리는 사이드 탭이 너무 좁고, Monitoring 탭 영역에서 넓은 사이드 패널로 보여야 한다고 요청했다.

## 해결 방법

- `td.ops-text-cell`과 `td.ops-time-cell` 자체에 적용되던 `display: block`을 제거했다. 이 스타일 때문에 발신자·담당자 같은 테이블 셀이 native table-cell 레이아웃을 잃고 행 border가 정상 행 경계에 맞지 않았다.
- 말줄임 처리는 셀 자체가 아니라 내부 `summary` 요소에만 적용되도록 범위를 좁혔다.
- 인스펙터가 열릴 때 `.ops-workspace`를 2컬럼 그리드로 바꾸던 CSS를 제거해 테이블 폭이 줄어들지 않게 했다.
- Monitoring view를 상대 위치 컨테이너로 두고, `#opsInspector`를 오른쪽 absolute 오버레이 패널로 배치해 기존 420~520px 영역보다 넓게 표시되도록 했다.
- CSS 회귀 테스트를 추가해 테이블 셀 display와 인스펙터 overlay 배치가 다시 깨지지 않도록 했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -q`: 108 passed.
- `python -m py_compile app/server.py`: 통과.
- 8000번 로컬 서버에서 로그인 후 `/ui/monitoring` HTML 응답 200을 확인했다.
- `git diff --check`: 통과.

## 남은 리스크와 후속 작업

- 로컬 환경에 브라우저 자동화 런타임이 없어 실제 스크린샷 검증은 수행하지 못했다. 변경은 CSS 원인 수정, 렌더링 HTML 확인, UI 테스트로 검증했다.

---

# 2026-08-20 - Simplify Search evidence metadata

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search tab evidence results |
| 관련 파일 | `app/templates/partials/search_results.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Search 탭의 근거 영역에서 모델명과 `채택`, `검토` 표시를 제거해 달라고 요청했다.
- 근거 카드에 `quote`처럼 문서 유형이 표시되는 배지도 불필요해 보여 제거해 달라고 요청했다.

## 해결 방법

- Search 근거 헤더에서 답변 모델명과 채택/검토 카운트 배지를 제거했다.
- 근거 카드 우측 액션 영역에서 문서 유형 category chip 렌더링을 제거했다.
- 제거된 search evidence metric 전용 CSS를 정리했다.
- 검색 UI 렌더링 테스트를 갱신해 모델명, 채택/검토 문구, 문서 유형 값이 HTML에 노출되지 않음을 확인하게 했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "search" -q`: 12 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경은 템플릿 렌더링 테스트로 확인했다.

---

# 2026-08-20 - Localize mail list column headers

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard, Inbox, assignee work list, Monitoring table headers |
| 관련 파일 | `app/templates/views/dashboard.html`, `app/templates/views/inbox.html`, `app/templates/views/assignee_work.html`, `app/templates/views/ops.html`, `app/templates/shell.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Dashboard 탭과 Inbox 탭의 메일 목록 칼럼명을 한국어로 바꾸고, 같은 방식으로 표시되는 다른 목록도 동일한 용어를 쓰도록 요청했다.
- Dashboard 목록은 `#`, `상태`, `수신자`, `제목`, `업무 유형`, `담당자`, `수신일시`, `수동 라우팅` 순서가 필요했다.
- Inbox 목록은 `#`, `상태`, `수신자`, `제목`, `업무 유형`, `담당자`, `수신일시` 순서가 필요했다.

## 해결 방법

- Dashboard와 Inbox 메일 목록 헤더를 요청한 한국어 용어와 순서로 변경했다.
- 동일한 메일 목록 형식으로 보이는 담당자 업무 목록의 `Status`, `Sender`, `Subject`, `Type`, `Time` 헤더도 `상태`, `수신자`, `제목`, `업무 유형`, `수신일시`로 통일했다.
- Monitoring 목록에서 메일 식별과 배정 의미의 컬럼 선택 라벨 및 테이블 헤더를 같은 한국어 용어로 정리했다.
- 수동 라우팅 확인 모달의 영문 eyebrow를 `수동 라우팅`으로 변경했다.
- Dashboard와 Inbox 헤더 순서를 검증하는 UI 테스트를 추가하고 Monitoring 헤더 기대값을 갱신했다.

## 검증

- `python -m pytest tests/test_mail_decision_ui.py -q`: 실행 환경에 `pytest` 모듈이 없어 실패했다.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 106 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경은 서버 템플릿 렌더링 기반 UI 테스트로 확인했다.
- `수신자` 헤더는 기존 셀이 표시하던 발신자 표시 데이터와 용어가 다를 수 있지만, 이번 요청의 지정 용어를 우선 적용했다.

---

# 2026-08-20 - Repair Monitoring table structure and side peek behavior

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring table layout, Notion-style side peek, column detail popovers |
| 관련 파일 | `app/templates/views/ops.html`, `app/templates/partials/ops_rows.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 이전 버전이 더 낫다고 느껴질 정도로 Monitoring 표 내부 구조가 뒤틀려 있어 우선 복구해야 한다고 지적했다.
- 메일 클릭 시 Inbox 이동이나 전체 overlay가 아니라 Notion처럼 같은 화면의 사이드탭을 열고 닫는 경험을 원했다.
- 첨부파일처럼 다른 칼럼도 상세 표시 여지가 있는 요소는 같은 방식의 상세 팝오버를 제공해야 했다.
- 요약문 생성과 분류 액션 아이콘은 다시 더 적절한 것으로 바꿔야 했다.

## 해결 방법

- Monitoring 표와 메일 상세 패널을 `ops-workspace` 안에 배치하고, 패널이 열릴 때만 `has-inspector` 클래스로 오른쪽 side peek 컬럼이 생기도록 바꿨다.
- 기존 fixed overlay 방식의 inspector를 제거하고 sticky side peek으로 바꿔 표와 같은 Monitoring 화면 안에서 열리고 닫히게 했다.
- action icon grid를 줄바꿈 없는 단일 행으로 고정하고, stage pill overflow를 ellipsis 처리해 행 높이와 칼럼 폭이 흔들리지 않도록 했다.
- 발신자, 업무 유형, 담당자, 수신일시, 첨부, Summary, Classify, Decision, 라우팅, Forward에 공통 `ops-detail-popover` 상세 패턴을 적용했다.
- Summary 재생성 아이콘은 `subject`, 분류 재실행 아이콘은 `label`로 교체했다.
- Monitoring sender 헤더를 `수신자`에서 실제 데이터 의미에 맞는 `발신자`로 수정했다.

## 검증

- `.venv/bin/python -m py_compile app/server.py`: 통과.
- `.venv/bin/python -m pytest tests/test_mail_decision_ui.py`: 106 passed.
- `docker compose restart web` 후 8000번 포트에서 `/ui/monitoring` 응답 200을 확인했다.
- 8000번 Monitoring HTML에서 `ops-workspace`, `ops-detail-popover`, `ops-attachment-popover`, `subject`, `label`, `발신자`, `opsInspector` 포함을 확인했다.
- 8000번 포트에서 `/ui/monitoring/emails/889e6fa9-5052-5a38-b056-1b798ce84304` 응답 200과 side peek wrapper 포함을 확인했다.

## 남은 리스크와 후속 작업

- 이 repo에는 Playwright 설정이 없어 브라우저 스크린샷 자동 검증은 수행하지 않았다. HTML 구조, CSS 규칙, 단위 테스트, 8000번 런타임 응답으로 검증했다.
- 모든 행에 상세 팝오버 DOM을 포함하므로 80행 이상의 대량 표시를 더 늘릴 때는 lazy detail endpoint 방식으로 바꾸는 것이 좋다.

---

# 2026-08-20 - Refine Monitoring row interactions and columns

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring tab row interactions, attachment popover, mail detail drawer |
| 관련 파일 | `app/server.py`, `app/templates/views/ops.html`, `app/templates/partials/ops_rows.html`, `app/templates/partials/ops_email_inspector.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Monitoring 탭에서 메일 행별 상호작용을 MLOps/LLMOps 모니터링 UI처럼 더 세밀하게 다듬고 싶다고 요청했다.
- 메일 클릭 시 Inbox로 이동하지 않고 Monitoring 안에서 열고 닫을 수 있는 사이드 패널이 필요했다.
- Attach 칼럼은 단순 재분석 버튼보다 첨부파일 목록을 즉시 확인할 수 있는 상호작용이 필요했다.
- 기존 Mail 칼럼은 제목, 발신자, 업무 유형, 담당자, 날짜가 한 칸에 섞여 가독성과 행 밀도가 떨어졌다.
- Mail 칼럼명은 이메일 제목으로 바꾸고, 요약문 생성과 분류 액션 아이콘도 더 적절하게 바꿔야 했다.

## 해결 방법

- Monitoring 전용 `/ui/monitoring/emails/{email_ref}` 엔드포인트와 `ops_email_inspector.html` 래퍼를 추가해, 제목 클릭 시 같은 Monitoring 화면의 우측 드로어에서 기존 메일 상세를 확인하도록 했다.
- Attach 칼럼에서 첨부가 있는 행은 상태 pill 클릭으로 첨부파일명, 문서 유형, 분석 상태, 크기, 보기 링크를 담은 경량 팝오버를 열도록 했다.
- 기존 Mail 단일 칼럼을 `이메일 제목`, `Sender`, `Type`, `Owner`, `Date` 칼럼으로 분리하고 컬럼 선택 저장 로직에도 새 키를 반영했다.
- Monitoring 행 padding, stage pill, 액션 버튼 크기를 줄여 한 화면에서 더 많은 행을 볼 수 있게 조정했다.
- 오른쪽 액션 아이콘 중 요약문 재생성은 `format_list_bulleted`, 메일 유형 재분류는 `schema` 아이콘으로 교체했다.

## 검증

- `.venv/bin/python -m py_compile app/server.py`: 통과.
- `.venv/bin/python -m pytest tests/test_mail_decision_ui.py`: 105 passed.
- `docker compose restart web` 후 8000번 포트에서 `/ui/monitoring` 응답 200을 확인했다.
- 8000번 포트에서 `/ui/monitoring/emails/889e6fa9-5052-5a38-b056-1b798ce84304` 응답 200과 `ops-inspector-shell`, 닫기 버튼, `detail-card` 포함을 확인했다.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. HTML, CSS, 단위 테스트, 8000번 런타임 응답으로 동작 경로를 확인했다.
- Attach 팝오버는 테이블 스크롤 영역 안에서 동작한다. 추후 긴 첨부 목록이나 화면 하단 행에서 잘림이 불편하면 동일한 우측 드로어 패턴으로 확장할 수 있다.

---

# 2026-08-20 - Stop Search examples from auto-running

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search tab example question behavior |
| 관련 파일 | `app/templates/shell.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Search 탭의 예시 질문 버튼을 클릭하면 자동으로 검색까지 수행되는 동작을 이전처럼 질문 입력만 자동 생성하는 동작으로 되돌려 달라고 요청했다.
- 답변 생성은 검색 버튼 클릭 시에만 수행되어야 한다.

## 해결 방법

- `installSearchExamples()`에서 예시 질문 클릭 후 `fetch`로 `/ui/search-results`를 호출하던 로직을 제거했다.
- 예시 질문 클릭은 입력값을 채우고 input event만 발생시키도록 제한했다.
- Search fallback submit 로직은 유지해 HTMX가 없을 때도 검색 버튼 submit은 계속 동작하도록 했다.
- UI 테스트에서 예시 핸들러 본문에 `fetch` 또는 `form.submit` 호출이 없고 입력값만 채우는지 검증했다.

## 검증

- `uv run pytest -q tests/test_mail_decision_ui.py -k "search"`: 12 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 클릭 검증은 수행하지 않았다. 변경은 템플릿 JS source 기반 회귀 테스트로 검증했다.
- 작업 시작 전부터 Operations 관련 미커밋 변경이 작업트리에 있어 이번 커밋에는 Search 예시 동작 hunk만 분리해 포함한다.

---

# 2026-08-20 - Align Inbox overview and Mail Decision table spacing

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox detail Mail Overview, Mail Decision panel |
| 관련 파일 | `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Inbox 탭의 Mail Overview에서 필드명 영역 오른쪽에 padding을 추가하고, Mail Decision과 열이 맞도록 조정해 달라고 요청했다.
- Mail Decision 내부 요소는 Status 위쪽 padding만 도드라져 보이는 문제가 있어 함께 정리했다.

## 해결 방법

- Inbox 상세 화면의 Mail Overview `info-table`을 Mail Decision 본문과 같은 16px 좌우 inset 안에서 표시되도록 조정했다.
- Mail Overview와 Mail Decision의 필드명 열에 동일한 오른쪽 padding을 적용해 값 열과 간격을 맞췄다.
- Mail Decision panel body의 위쪽 padding을 제거하고 좌우·하단 padding만 유지해 Status 위 여백이 과하게 보이지 않도록 했다.
- 관련 CSS 선택자를 확인하는 UI 테스트를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "inbox_detail_overview_and_decision_tables_share_field_spacing or search_and_settings_typography_refinement_targets_core_elements or non_dashboard_typography" -q`: 3 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 이번 변경은 CSS 선택자와 간격 규칙 단위로 검증했다.
- 작업 시작 전부터 같은 파일에 Search/Settings 관련 미커밋 변경이 있어 이번 요청 hunk만 선별 커밋한다.

---

# 2026-08-20 - Refine Search and Settings typography

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search tab typography, Settings tab typography |
| 관련 파일 | `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Search 탭과 Settings 탭에 대해 폰트 크기 조정을 다시 진행해 달라고 요청했다.
- 이전 non-dashboard 공통 조정보다 두 탭의 핵심 요소를 더 명확하게 키우고, 입력·검색 결과·설정 테이블의 밀도와 넘침을 함께 고려할 필요가 있었다.

## 해결 방법

- Search 탭에서 검색 입력, 검색 버튼, 예시 질문 버튼, 답변 본문, 근거 카드 제목과 본문을 별도 typography refinement로 키웠다.
- Search 결과 카드의 rank, source title, meta, loading/empty state 텍스트 계층을 조정해 검색 질문과 결과 본문이 더 크게 보이도록 했다.
- Settings 탭에서 자동 배정 기준 입력, 담당자 우선순위 row, 담당자 관리 table의 input/select/chip/font-size를 키웠다.
- Settings routing table의 최소 폭과 label/manage column 폭을 늘려 글자 확대 시 table 내용이 찌그러지지 않도록 했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "search_and_settings_typography or non_dashboard_typography or search_view or settings_renders" -q`: 9 passed.
- `env CORAMAIL_AUTH_ENABLED=false CORAMAIL_DEMO_MODE=true uv run pytest tests/test_mail_decision_ui.py tests/test_document_type_navigation.py -q`: 103 passed, 6 failed. 실패는 현재 작업트리의 Mail Decision/Gmail settings 관련 별도 미커밋 변경에서 발생했고, 이번 CSS refinement와 직접 관련된 실패는 아니었다.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경은 CSS 규칙과 관련 서버 렌더링 테스트로 검증했다.
- 작업트리에 별도 미커밋 변경이 남아 있어 이번 커밋에는 Search/Settings typography 관련 hunk만 선별 포함한다.

---

# 2026-08-20 - Increase urgent mail row background one more step

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox urgent row visual tone |
| 관련 파일 | `app/static/app.css` |

## 요청 또는 배경

- 사용자는 직전 긴급메일 배경색 조정 후 조금만 더 진하게 해도 될 것 같다고 요청했다.

## 해결 방법

- `tr.is-priority-high` 기본 배경 opacity를 `0.05`에서 `0.065`로 한 단계 더 올렸다.
- hover 배경 opacity를 `0.085`에서 `0.10`으로 조정했다.
- 긴급 판단 기준, 템플릿, badge 문구는 변경하지 않았다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "high_priority or urgent_stat" -q`: 3 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경은 CSS 색상 opacity 두 값에 한정했다.

---

# 2026-08-20 - Rename operations to monitoring and compact rows

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Monitoring tab, column visibility, dense mail status table |
| 관련 파일 | `app/server.py`, `app/templates/shell.html`, `app/templates/views/ops.html`, `app/templates/partials/ops_rows.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 최대한 많은 메일의 모든 현황을 파악하는 것이 목적이므로 가로 스크롤은 허용된다고 했다.
- 사용자가 MLOps/LLMOps 모니터링 화면처럼 확인할 컬럼을 추가/제거할 수 있어야 한다고 요청했다.
- `Operations`보다 `Monitoring` 탭 명칭이 적합하다고 했다.
- `Health`와 `Mail` 컬럼 때문에 한 메일당 row 높이가 큰 문제를 지적했고, padding과 row density를 줄여 달라고 요청했다.

## 해결 방법

- 사이드바 탭, page title, primary route를 `Monitoring`과 `/ui/monitoring`으로 변경했다.
- 기존 `/ui/ops`, `/ui/ops-rows`는 롤백과 기존 링크 호환을 위해 alias로 유지했다.
- Monitoring header에 컬럼 선택 메뉴를 추가하고, `localStorage`에 사용자의 컬럼 표시 상태를 저장하도록 했다.
- table `col`, header, body cell에 `data-monitoring-column`을 부여해 Health, Mail, Attach, Summary, Classify, Decision, Routing, Forward, Control 컬럼을 숨기거나 다시 표시할 수 있게 했다.
- Health를 큰 원형 score에서 38x22 compact score badge로 줄이고, Mail cell을 subject/sender/category/assignee/time 한 줄 구조로 바꿨다.
- table padding, stage pill, action icon, metric, input 크기를 줄이고, Monitoring table min-width를 키워 가로 스크롤을 허용하는 대신 row height를 낮췄다.

## 검증

- `python -m py_compile app/server.py app/services/postgres_mail_service.py`: 통과.
- `env CORAMAIL_AUTH_ENABLED=false uv run pytest tests/test_mail_decision_ui.py tests/test_document_type_navigation.py`: 108 passed.
- `env CORAMAIL_AUTH_ENABLED=false CORAMAIL_DEMO_MODE=true uv run python ...`: Monitoring templates 렌더 검증 통과. 첫 시도는 uv cache lock이 sandbox에서 실패해 권한 상승으로 재실행했다.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 서버 렌더링과 UI 회귀 테스트로 검증했다.
- 내부 함수/템플릿 파일명은 기존 `ops` 명칭을 일부 유지한다. 사용자 노출 경로와 탭 명칭은 Monitoring으로 변경했다.

---

# 2026-08-20 - Remove Inbox overview decision header actions

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox email detail UI |
| 관련 파일 | `app/templates/partials/email_detail.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Inbox 상세에서 `confidence`, `재분류`, `재배정` 버튼을 제거해 달라고 요청했다.
- 직전 요청 기준에 따라 `Mail Overview`와 `Mail Decision` 제목 영역 자체는 유지하고, 제목 영역 안의 액션 요소만 제거해야 했다.
- 나중에 요청 시 롤백 가능해야 하므로 별도 커밋으로 분리한다.

## 해결 방법

- `Mail Overview` 패널 헤더에서 confidence badge와 메일 유형 재분류 버튼을 제거했다.
- `Mail Decision` 패널 헤더에서 업무 판단 실행/재배정 버튼을 제거했다.
- Mail Decision 최신 결과 lazy-load 영역은 유지해 기존 결과 조회 흐름은 그대로 두었다.
- UI 렌더링 테스트가 제거된 액션 요소와 남아 있는 제목/lazy-load 계약을 함께 검증하도록 갱신했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "email_detail_renders_mail_decision_latest_lazy_load or email_detail_keeps_mail_overview_and_decision_panels_separate" -q`: 2 passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 102 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경은 서버 렌더링 테스트로 검증했다.
- 작업 시작 전부터 `app/server.py`, `app/static/app.css`, `app/templates/partials/ops_rows.html`, `app/templates/shell.html`, `app/templates/views/ops.html`, `tests/test_mail_decision_ui.py`에 다른 미커밋 변경이 존재해 이번 변경만 분리해 커밋한다.
- 롤백이 필요하면 이 작업의 커밋을 `git revert`로 되돌린다.

---

# 2026-08-20 - Remove Inbox Message panel title area

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox email detail UI |
| 관련 파일 | `app/templates/partials/email_detail.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Inbox 탭의 Message, Mail Overview, Mail Decision 제목 영역 제거를 요청했다.
- 이후 제목 영역에 있던 모든 요소까지 제거하는 의미라고 정정했고, 마지막으로 Mail Overview와 Mail Decision 제목 영역은 남겨 달라고 다시 조정했다.
- 최종 수락 범위는 Inbox 상세의 Message 패널 제목 영역 전체 제거이며, Mail Overview와 Mail Decision 제목 영역 및 액션은 유지하는 것이다.

## 해결 방법

- `email_detail.html`의 Message 패널에서 `panel-head` 전체를 제거해 `Message` 제목, 안내 tooltip, 첨부 재분석 버튼/첨부 개수 배지가 표시되지 않게 했다.
- Mail Overview와 Mail Decision의 제목 영역은 기존 렌더링과 액션 버튼을 유지했다.
- UI 렌더링 테스트에 Message 제목 및 첨부 재분석 버튼이 다시 나타나지 않아야 한다는 기대값을 추가했다.

## 검증

- `pytest tests/test_mail_decision_ui.py -k "email_detail_renders_mail_decision_latest_lazy_load or email_detail_keeps_mail_overview_and_decision_panels_separate"`: 실패, 로컬 PATH에 `pytest` 실행 파일이 없었다.
- `uv run pytest tests/test_mail_decision_ui.py -k "email_detail_renders_mail_decision_latest_lazy_load or email_detail_keeps_mail_overview_and_decision_panels_separate" -q`: 2 passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 102 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경은 서버 렌더링 테스트로 검증했다.
- 작업 시작 전부터 `app/server.py`, `app/static/app.css`, `app/templates/partials/ops_rows.html`, `app/templates/shell.html`, `app/templates/views/ops.html`, `tests/test_mail_decision_ui.py`에 다른 미커밋 변경이 존재해 이번 변경만 분리해 커밋한다.
- 롤백이 필요하면 이 작업의 커밋을 `git revert`로 되돌린다.

---

# 2026-08-20 - Extend typography scale to non-dashboard tabs

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox, Operations, Assignments, Documents, Search, Settings, Evaluation typography |
| 관련 파일 | `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Dashboard 외 모든 탭에도 같은 방식으로 폰트를 키우되 핵심 요소와 부가 요소의 차이를 유지해 달라고 요청했다.
- 글씨 증가로 인한 넘침이나 배치 꼬임을 막고, 제목 영역과 column header 같은 부수 영역이 불필요하게 커지지 않아야 한다는 Dashboard 조정 기준을 동일하게 적용해야 했다.

## 해결 방법

- Inbox, Operations, Assignments, Documents, Search, Settings, Evaluation 뷰에 non-dashboard typography scale override를 추가했다.
- 본문 표 셀, 메일 제목, 주요 metric 숫자, 검색 결과 본문, 담당자/문서 목록 제목은 14px 이상 중심으로 키웠다.
- column header, label, 보조 meta, pill류는 11-13px 계층으로 유지해 핵심/부가 정보 차이가 남도록 했다.
- Inbox, Operations, Assignments, Settings의 dense table은 폰트 증가에 맞춰 최소 폭과 주요 열 너비를 늘려 가로 찌그러짐 대신 scroll 가능한 레이아웃으로 유지했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "typography or stat_helper_text or urgent_stat" -q`: 5 passed.
- `uv run pytest tests/test_mail_decision_ui.py tests/test_document_type_navigation.py -q`: 108 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경은 CSS 규칙과 서버 렌더링/UI 회귀 테스트로 검증했다.
- Search 탭 관련 별도 미커밋 변경이 작업트리에 존재해 이번 커밋에서는 제외했다.

---

# 2026-08-20 - Move Search loading state into results area

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search tab UI, loading state, search form layout |
| 관련 파일 | `app/templates/views/search.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Search 탭에서 검색 버튼 오른쪽에 표시되던 로딩 상태를 빈 결과 안내 문구가 있던 영역에 표시해 달라고 요청했다.
- 검색 버튼 위치가 로딩 표시 때문에 움직이지 않아야 하며, 질문 입력 박스, 검색 버튼, 예시 질문 버튼을 감싸던 바깥 박스를 제거해 요소들을 바깥으로 꺼내 달라고 요청했다.

## 해결 방법

- Search 입력 영역의 `panel` wrapper를 제거하고 입력창, 검색 버튼, 예시 질문 버튼을 unframed 레이아웃으로 배치했다.
- HTMX target을 `#search-results-body`로 좁히고 indicator를 `#search-results`에 연결해 결과 영역 안의 로딩 패널이 표시되도록 했다.
- 로딩 패널은 기존 빈 결과 안내 영역과 같은 panel/body/empty-state 구조를 사용하며, 검색 중에는 결과 본문을 숨겨 버튼 옆 공간을 차지하지 않게 했다.
- HTMX CDN이 동작하지 않는 fallback fetch 경로에도 같은 결과 영역 로딩 클래스를 적용했다.
- Search 렌더링 테스트에 새 target, indicator, 로딩 문구, 제거된 wrapper를 검증하는 기대값을 추가했다.

## 검증

- `uv run pytest -q tests/test_mail_decision_ui.py -k "search"`: 11 passed.
- `uv run pytest -q tests/test_mail_decision_ui.py`: 100 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경은 서버 렌더링, CSS 상태 전환, JS fallback 회귀 테스트로 검증했다.
- 작업 중 같은 CSS/test 파일에 Search와 무관한 typography 관련 미커밋 변경이 함께 존재해, 이번 커밋에는 Search 관련 hunks만 분리해 포함한다.

---

# 2026-08-20 - Darken urgent mail row background slightly

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox urgent row visual tone |
| 관련 파일 | `app/static/app.css` |

## 요청 또는 배경

- 사용자는 긴급메일 배경색을 아주 살짝만 더 진하게 바꿔 달라고 요청했다.

## 해결 방법

- 긴급/클레임 메일 행에 적용되는 `tr.is-priority-high` 기본 배경 opacity를 `0.035`에서 `0.05`로 조정했다.
- hover 배경도 기존 대비 같은 방향으로 `0.07`에서 `0.085`로 조정해 상호작용 톤이 자연스럽게 이어지도록 했다.
- 템플릿 구조, 긴급 판단 기준, badge 문구는 변경하지 않았다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "high_priority or urgent_stat" -q`: 3 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경은 CSS 색상 opacity 두 값에 한정했다.

---

# 2026-08-20 - Adjust dashboard typography scale

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard typography, stats readability, mail stream density |
| 관련 파일 | `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 테스트 목적으로 Dashboard 전반의 폰트가 작은 문제를 확인하고 싶다고 요청했다.
- 폰트를 키우되 핵심 요소와 부가 요소의 크기 차이를 유지하고, 글씨가 넘치거나 배치가 꼬이지 않도록 padding과 열 너비를 함께 조정해 달라고 요청했다.
- 제목 영역과 column header 같은 부수 영역이 불필요하게 커지지 않아야 한다는 조건을 제시했다.

## 해결 방법

- Dashboard stats 숫자, 보조 문구, chart/routing 수치, Mail Streams 본문 텍스트를 한 단계 키웠다.
- Dashboard 카드 제목, scope toggle, table header는 작은 보조 계층으로 유지하되 기존보다 읽기 쉬운 크기로만 조정했다.
- Mail Streams 본문 폰트 증가에 맞춰 status/classification/receiver/time/manual route 열 너비, 행 높이, chip, 전달 버튼 크기를 함께 조정했다.
- 좁은 화면에서는 stats 카드 최소 폭과 dashboard table 최소 폭을 늘려 텍스트가 찌그러지는 대신 가로 스크롤로 유지되도록 했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "urgent_stat or stat_helper_text or dashboard_typography" -q`: 3 passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "dashboard_summary or demo_dashboard_context or demo_dashboard_stats or category_timeline or urgent_stat or stat_helper_text or dashboard_typography" -q`: 7 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 이번 변경은 CSS 규칙과 dashboard 서버 렌더링 회귀 테스트로 검증했다.
- 사용자가 화면에서 확인한 뒤 더 크게 또는 더 조밀하게 조정할 수 있도록, 변경은 dashboard 전용 CSS에 한정했다.

---

# 2026-08-20 - Reduce operations tab explanatory text

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Operations tab UI density |
| 관련 파일 | `app/templates/views/ops.html`, `app/templates/partials/ops_rows.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Operations UI에서 부수적인 설명 텍스트 영역을 최소화하고 중요한 상태와 제어 요소가 돋보이게 구성해 달라고 요청했다.

## 해결 방법

- Operations table 위의 정적 패널 제목 영역을 제거하고 refresh action을 table header 안으로 이동했다.
- stage별 상세 설명 문구를 화면에서 제거하고 상태 pill의 tooltip으로만 유지했다.
- table viewport 높이와 cell padding을 조정해 메일 상태 rows가 더 많이 보이도록 했다.
- 회귀 테스트를 새 UX에 맞춰 갱신했다.

## 검증

- `python -m py_compile app/server.py app/services/postgres_mail_service.py`: 통과.
- `env CORAMAIL_AUTH_ENABLED=false uv run pytest tests/test_mail_decision_ui.py tests/test_document_type_navigation.py`: 106 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 서버 렌더링과 UI 회귀 테스트로 검증했다.

---

# 2026-08-20 - Add mail operations control tab

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard operations, pipeline status, Mail Decision control |
| 관련 파일 | `app/server.py`, `app/services/postgres_mail_service.py`, `app/templates/shell.html`, `app/templates/views/ops.html`, `app/templates/partials/ops_rows.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Dashboard에서 분류 유형, 담당자, 전달 완료 여부 외에 첨부파일 문서유형 분석 상태, 요약문 생성 상태, Mail Decision 실행 여부와 결과를 한 번에 확인하고 제어할 수 있는 새 탭을 요청했다.
- 새 화면은 MLOps/LLMOps 콘솔처럼 현재 상태를 한눈에 보여주되, 부수적인 설명 텍스트는 최소화하고 중요한 요소가 돋보이도록 구성해 달라고 요청했다.
- 새 탭으로 추가해 기존 Dashboard/Inbox 동작을 유지하고 커밋 단위로 롤백 가능하게 남기는 방향을 선택했다.

## 해결 방법

- `Operations` 사이드바 탭과 `GET /ui/ops`, `GET /ui/ops-rows`, `/?view=ops` 렌더링 경로를 추가했다.
- 메일별 pipeline stage view model을 추가해 첨부파일 분석, 요약, 분류, Mail Decision, 담당자 배정, 전달 상태를 한 행에서 표시하도록 했다.
- PostgreSQL mailbox row에 summary 상태, 최신 Mail Decision 상태, 분석 job 상태를 UI 계약으로 노출했다.
- Operations 표에서 첨부파일 재분석, 요약 재생성, 메일 유형 재분류, Mail Decision 실행, 담당자 수동 전달 버튼을 제공한다. DB가 없는 fixture 모드에서는 제어 버튼을 비활성화한다.
- 작업 완료 이벤트 후 Operations row partial이 갱신되도록 HTMX trigger와 client-side refresh helper를 연결했다.
- 고정 설명 문구는 제거하고 metric, stage pill, health score, action icon 중심의 조밀한 운영 화면으로 구성했다.

## 검증

- `python -m py_compile app/server.py app/services/postgres_mail_service.py`: 통과.
- `env CORAMAIL_AUTH_ENABLED=false uv run pytest tests/test_mail_decision_ui.py tests/test_document_type_navigation.py`: 105 passed.
- `CORAMAIL_DEMO_MODE=true` 상태에서 직접 Jinja 렌더로 `views/ops.html`, `partials/ops_rows.html`가 렌더되는지 확인했다.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경은 서버 렌더링과 UI 회귀 테스트로 검증했다.
- Operations row는 현재 80건까지 표시하고 메일별 상세를 조회해 첨부 상태를 계산한다. 운영 데이터량이 커지면 repository 수준의 집계 query로 최적화해야 한다.

---

# 2026-08-20 - Darken dashboard stat helper text

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard stats readability |
| 관련 파일 | `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Dashboard 탭 stats의 `전체 수신 메일 수`, `오늘 수신 메일 수`, `분류 요망 건`, `배정 요망 건`, `전달 요망 건` 문구가 연해서 가독성이 떨어진다고 보고했다.

## 해결 방법

- Dashboard stat 하단 보조 문구 색상을 기존 muted 계열에서 더 진한 `#475569`로 변경했다.
- 긴급 stat의 빨간 보조 문구는 기존 dashboard 전용 override가 유지되도록 했다.
- 해당 CSS 규칙이 유지되는지 확인하는 회귀 테스트를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "urgent_stat or stat_helper_text" -q`: 2 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 수동 확인은 수행하지 않았다. 변경은 CSS 규칙과 좁은 UI 테스트로 검증했다.

---

# 2026-08-20 - Add assignee workload view

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox routing, assignee workload tab, UI authorization |
| 관련 파일 | `app/server.py`, `app/templates/views/assignee_work.html`, `app/templates/partials/mail_rows.html`, `app/templates/shell.html`, `app/static/app.css`, `docs/features/assignee-routing.md`, `docs/features/inbox-list-detail.md`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 담당자별 현재 할당 업무 메일을 확인할 수 있는 탭을 요청했다.
- 현재 admin 로그인에서는 전체 담당자 업무를 볼 수 있어야 하고, 향후 담당자 계정 로그인에서는 본인 및 권한 허용 담당자의 업무만 볼 수 있어야 한다고 요청했다.
- 새 화면은 메일 목록의 Receiver 담당자 이름 클릭 시 이동하는 화면이며, 부수 설명보다 핵심 요소가 돋보이는 UI를 원했다.

## 해결 방법

- `GET /ui/assignees` 담당자 업무 화면과 `/?view=assignees` 초기 렌더링을 추가했다.
- Inbox/Dashboard 메일 행의 Receiver 칩을 담당자 업무 화면으로 이동하는 독립 클릭 대상으로 변경했다.
- Assignments 사이드바 탭, page title, history query 보존을 추가했다.
- 담당자 업무 화면은 선택 담당자의 배정 건수, 검토 필요, 긴급, 전달 완료 수치를 먼저 보여주고, 권한 범위 내 담당자 전환 목록과 메일 테이블을 제공한다.
- 현재 인증 구조가 단일 서명 쿠키 username만 제공하므로 임시 권한 규칙을 구현했다. `admin` 또는 `CORAMAIL_ADMIN_USERNAMES` 포함 계정은 전체 조회, 담당자 계정은 로그인명과 담당자 user id/email/name/display가 일치하는 메일 및 `CORAMAIL_ASSIGNEE_ACCESS_JSON`에 허용된 담당자만 조회한다.
- 관련 기능 문서에 새 UI 계약과 임시 권한 환경변수, 운영 교체 지점을 기록했다.

## 검증

- `python -m py_compile app/server.py`: 통과.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 96 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 수동 확인은 수행하지 않았다. 서버 렌더링과 UI 회귀 테스트로 검증했다.
- 운영 단계에서는 임시 환경변수 권한 정책을 `users.role`과 조직 권한 테이블 기반 정책으로 교체해야 한다.

---

# 2026-08-20 - Remove urgent stat card background

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard stats, urgent mail visual emphasis |
| 관련 파일 | `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Dashboard의 긴급 stat 요소에서 카드 배경색만 제거해 달라고 요청했다.

## 해결 방법

- `.dashboard-view .stat-urgent`의 빨간 gradient 배경을 제거했다.
- 긴급 카드의 빨간 테두리, 라벨, 숫자, 아이콘, 보조 문구 색상은 유지했다.
- CSS 회귀 테스트에 긴급 카드 자체에는 `background:` 지정이 없음을 확인하는 검증을 추가했다.

## 검증

- `.venv/bin/pytest tests/test_mail_decision_ui.py -k "urgent_stat or dashboard_summary"`: 2 passed.
- `.venv/bin/pytest tests/test_mail_decision_ui.py`: 92 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 수동 확인은 수행하지 않았다. 변경은 CSS 규칙과 서버 렌더링 테스트로 검증했다.

---

# 2026-08-20 - Remove duplicate overview summary boxes

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox selected mail detail, Mail Overview duplicate content |
| 관련 파일 | `app/templates/partials/email_detail.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 이전 변경에서 Mail Overview 안에 박스 영역으로 들어간 요약 내용이 중복이라고 지적했다.
- 박스 영역으로 넣은 부분을 모두 제거해 달라고 요청했다.

## 해결 방법

- Mail Overview 아래에 추가했던 `mail-overview-body` 보조 박스 영역을 제거했다.
- 해당 영역 안의 summary 진행률, executive summary 카드 목록, 실패/대기 문구를 제거했다.
- 박스 영역과 연결되어 보이던 핵심 요청 재생성 버튼과 전용 CSS를 제거했다.
- Mail Overview 표 안의 카테고리, 담당자, 핵심 요청, 업무번호 등 핵심 필드 배치는 유지했다.
- 회귀 테스트에 `mail-overview-body`와 `executive-summary-list--overview`가 렌더링되지 않는지 확인하는 검증을 추가했다.

## 검증

- `.venv/bin/python -m pytest tests/test_mail_decision_ui.py -q`: 92 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 수동 확인은 수행하지 않았다. 변경은 서버 렌더링 HTML과 UI 회귀 테스트로 검증했다.

---

# 2026-08-20 - Merge summary content into mail overview

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox selected mail detail, Mail Overview, summary content density |
| 관련 파일 | `app/templates/partials/email_detail.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Inbox 탭 상세 화면에서 Summary 영역의 내용이 Mail Overview에 다시 나타나므로 별도 Summary 패널이 필요한지 모르겠다고 지적했다.
- Summary에 있던 핵심 요청과 업무번호 같은 요소를 Mail Overview 안에 자연스럽게 넣고, 간결하고 핵심적인 카테고리와 담당자 정보를 상위에 배치해 달라고 요청했다.

## 해결 방법

- 독립 `Summary` 패널을 제거하고 요약 재생성 버튼, 진행률, executive summary 세부 항목을 `Mail Overview` 내부 보조 정보로 이동했다.
- Mail Overview 정보 순서를 카테고리, 담당자, 핵심 요청, 업무번호, 거래처, 선박/프로젝트 순으로 재배치했다.
- 업무번호는 `business_refs`를 compact token 형태로 표시해 핵심 요청과 함께 한 화면에서 확인할 수 있게 했다.
- 새 Overview 내부 보조 정보와 업무번호 token list가 좁은 패널에서도 줄바꿈되도록 CSS를 추가했다.
- UI 회귀 테스트를 갱신해 Summary 헤더가 제거되고, Overview 내 핵심 정보 순서와 업무번호 표시가 유지되는지 확인했다.

## 검증

- `python -m pytest tests/test_mail_decision_ui.py -q`: 실패, 시스템 Python에 `pytest`가 설치되어 있지 않음.
- `.venv/bin/python -m pytest tests/test_mail_decision_ui.py -q`: 92 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 수동 확인은 수행하지 않았다. 변경은 서버 렌더링 HTML과 UI 회귀 테스트로 검증했다.

---

# 2026-08-20 - Highlight urgent dashboard stat in red

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard stats, urgent mail visual emphasis |
| 관련 파일 | `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Dashboard stats 중 긴급 건 요소만 빨간색으로 표시해 달라고 요청했다.

## 해결 방법

- Dashboard의 `.stat-urgent` 카드에만 danger 톤 배경, 테두리, 숫자, 라벨, 아이콘, 보조 문구 색상을 적용했다.
- stats HTML에 `stat-urgent` 클래스가 유지되고 CSS가 danger 색상 규칙을 포함하는지 회귀 테스트를 추가했다.

## 검증

- `.venv/bin/pytest tests/test_mail_decision_ui.py -k "dashboard_summary or urgent_stat"`: 2 passed.
- `.venv/bin/pytest tests/test_mail_decision_ui.py`: 92 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 수동 확인은 수행하지 않았다. 변경은 CSS 규칙과 서버 렌더링 테스트로 검증했다.

---

# 2026-08-20 - Move urgency signal from detail overview to dashboard stats

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Mail detail overview, dashboard stats, urgent mail summary |
| 관련 파일 | `app/templates/partials/email_detail.html`, `app/templates/partials/stats.html`, `app/server.py`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 긴급도 행 추가를 롤백해 이전처럼 긴급 메일은 목록 색상으로만 표시되게 해 달라고 요청했다.
- 대신 Dashboard의 `Total Mails`, `Today Mails`가 있는 stat 영역에 긴급 메일 현황을 추가해 달라고 요청했다.

## 해결 방법

- Mail Overview에서 `긴급도` 행과 관련 템플릿 변수를 제거해 상세 화면은 이전처럼 카테고리, 핵심 요청, 담당자 중심으로 유지했다.
- Dashboard summary에 목록 강조 기준과 같은 `priority == "high"` 또는 `긴급 장애`/`클레임` 카테고리 기준의 긴급 메일 집계를 추가했다.
- Dashboard stat 영역에 `Urgent Mails` 카드를 추가해 전체 긴급 메일 수와 오늘 긴급 메일 수를 표시했다.
- Dashboard stat grid를 5개에서 6개 카드 기준으로 조정했다.
- 긴급 메일 상세에는 `긴급도` 행이 나오지 않고, Dashboard stat에는 긴급 메일 카운트가 표시되는 회귀 테스트를 갱신했다.

## 검증

- `.venv/bin/pytest tests/test_mail_decision_ui.py -k "dashboard_summary or high_priority or normal_priority or keeps_mail_overview"`: 5 passed.
- `.venv/bin/pytest tests/test_mail_decision_ui.py`: 91 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 수동 확인은 수행하지 않았다. 변경은 서버 렌더링 HTML, Dashboard summary 계산, UI 회귀 테스트로 검증했다.

---

# 2026-08-20 - Limit urgency row to urgent mail only

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Selected mail overview, urgency display density, demo UI tests |
| 관련 파일 | `app/templates/partials/email_detail.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Mail Overview에 `긴급도` 행을 항상 추가하면 긴급하지 않은 메일까지 `보통`이 표시되어 비효율적이라고 지적했다.
- 긴급한 메일에만 표시할 수 있는 방법을 요청했다.

## 해결 방법

- `Mail Overview`의 `긴급도` 행 렌더링 조건을 `classification.urgency == "high"`로 제한했다.
- 일반/낮음 긴급도 표시용 계산값을 제거하고, 긴급 메일에만 `긴급` 및 `우선 확인` badge와 긴급 처리 기준 문구를 표시하도록 단순화했다.
- 일반 데모 견적 메일의 상세 화면에는 `긴급도` 행과 `우선 확인` 문구가 렌더링되지 않는 회귀 테스트를 추가했다.

## 검증

- `.venv/bin/pytest tests/test_mail_decision_ui.py -k "high_priority or normal_priority or keeps_mail_overview"`: 4 passed.
- `.venv/bin/pytest tests/test_mail_decision_ui.py`: 91 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 수동 확인은 수행하지 않았다. 변경은 서버 렌더링 HTML과 UI 회귀 테스트로 검증했다.

---

# 2026-08-20 - Show urgent classification in mail overview

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo inbox, selected mail overview, urgency classification display |
| 관련 파일 | `app/templates/partials/email_detail.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 데모모드 이메일 목록에서 긴급 메일이 붉은색으로 표시되지만, 색상 외에는 해당 메일이 긴급으로 분류되었다는 단서를 확인하기 어렵다고 보고했다.
- 이전에 Mail Overview에서 긴급 항목을 임시로 제외한 것이 원인일 수 있으므로, 내부 동작 결과를 확인하고 자연스러운 위치에 표시해 달라고 요청했다.

## 확인한 사실

- 데모 fixture의 `priority: high` 값은 `DemoMailService`에서 목록 row의 `priority`와 상세 classification의 `urgency`로 전달된다.
- 메일 목록은 `priority == "high"` 또는 `긴급 장애`/`클레임` 카테고리를 기준으로 `is-priority-high` 클래스를 붙여 붉은 배경과 `긴급`/`주의` badge를 표시한다.
- 상세 화면은 이미 `urgency_raw`, `urgency_display`, `urgency_tone` 값을 계산하고 있었지만 Mail Overview 표에는 렌더링하지 않았다.

## 해결 방법

- Mail Overview의 카테고리 바로 아래에 `긴급도` 행을 추가했다.
- `urgency == "high"`인 경우 `긴급` badge와 `우선 확인` badge를 표시하고, `긴급 장애 · 긴급 서비스 기준으로 긴급 처리 대상입니다.`처럼 카테고리와 라우팅 기준을 함께 보여주도록 했다.
- 일반/낮음 긴급도도 같은 위치에서 badge로 표시되게 해 색상만이 아니라 분류 결과 자체를 확인할 수 있게 했다.
- 데모 긴급 메일 상세가 `classification.urgency == "high"`를 받아 Mail Overview에 긴급도 단서를 렌더링하는 회귀 테스트를 추가했다.

## 검증

- `.venv/bin/pytest tests/test_mail_decision_ui.py -k "high_priority or keeps_mail_overview"`: 3 passed.
- `.venv/bin/pytest tests/test_mail_decision_ui.py`: 90 passed.
- PATH에 `pytest`가 없어 첫 실행은 실패했고, 저장소 가상환경의 `.venv/bin/pytest`로 재실행했다.

## 남은 리스크와 후속 작업

- 실제 브라우저 수동 확인은 수행하지 않았다. 변경은 서버 렌더링 HTML과 UI 회귀 테스트로 검증했다.

---

# 2026-08-20 - Prevent quotation attachment unit price overlap

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox selected mail, attachment quotation details, responsive CSS |
| 관련 파일 | `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Inbox 탭의 selected mail에서 견적서 첨부파일이 있는 메일을 열면 품목 상세의 `Unit` 데이터와 `U/Price` 데이터가 겹쳐 보인다고 보고했다.
- 필드 영역을 좁히고 오른쪽 데이터 영역을 더 넓혀 겹침을 해결하고 방지해 달라고 요청했다.

## 확인한 원인

- 첨부 분석 Details 표의 line item 레이아웃은 왼쪽 라벨 열을 `34%`로 두고 오른쪽에 5개 데이터 열을 배치했다.
- `Unit`, `U/Price`, `Amount` 같은 뒤쪽 셀은 `white-space: nowrap` 상태라 좁은 영역에서 값이 인접 셀로 넘쳐 겹칠 수 있었다.
- 파일 하단의 `.info-table td:first-child` override도 같은 `34%` 폭을 다시 적용하고 있었다.

## 해결 방법

- 첨부 상세의 왼쪽 필드/라벨 영역을 `24%`로 줄여 오른쪽 데이터 영역을 넓혔다.
- `U/Price`와 `Amount` 열의 최소 폭과 비율을 키우고 셀 값은 줄바꿈 가능하게 바꿔 인접 열 침범을 막았다.
- 모바일 폭에서는 품목 상세 grid에 가로 스크롤과 최소 폭을 적용해 과도한 압축으로 인한 겹침을 방지했다.
- CSS 회귀 테스트를 추가해 라벨 폭, 가격 열 폭, 줄바꿈/스크롤 규칙이 되돌아가지 않게 했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py::test_email_detail_renders_attachment_line_items_as_field_grid tests/test_mail_decision_ui.py::test_email_detail_attachment_line_item_grid_prevents_unit_price_overlap`: 통과.
- `uv run pytest tests/test_mail_decision_ui.py`: 89 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 수동 확인은 수행하지 않았다. 변경은 서버 렌더링 HTML과 CSS 회귀 테스트로 검증했다.

---

# 2026-08-20 - Remove Inbox Queue title area

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox list header, UI rendering test |
| 관련 파일 | `app/templates/views/inbox.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Inbox 탭에서 `Inbox Queue`라는 제목 영역을 제거해 달라고 요청했다.

## 해결 방법

- Inbox 목록 패널의 제목줄 전체를 제거해 `Inbox Queue` 제목, 안내 tooltip, `loaded` 배지가 표시되지 않도록 했다.
- 초기 Inbox 렌더링 테스트가 제목 영역 제거를 검증하도록 기대값을 갱신했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py::test_inbox_initial_queue_renders_mail_rows`: 통과.
- `uv run pytest tests/test_mail_decision_ui.py`: 88 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 수동 확인은 수행하지 않았다. 변경은 서버 렌더링 HTML과 관련 UI 테스트로 검증했다.

---

# 2026-08-19 - Add more quotation attachment demo emails

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo data, received quotation fixtures, PostgreSQL seed validation |
| 관련 파일 | `data/demo/received_quotations.fixture.json`, `data/demo/README.md`, `docs/development/demo-data-standard.md`, `tests/test_demo_seed_service.py` |

## 요청 또는 배경

- 사용자는 데모모드 데이터에서 `[견적서 송부] 산업용 네트워크 장비 및 전원모듈`처럼 첨부파일로 견적서가 있는 메일을 시연용으로 몇 개 더 만들어 달라고 요청했다.

## 확인한 사실

- 데모 fixture는 `data/demo/*.fixture.json`에서 로딩되며, 견적서 첨부 상세 시연용 canonical fixture는 `received_quotations.fixture.json`이었다.
- PostgreSQL seed 검증은 attachment parent와 storage file 존재 여부를 확인하므로 fixture 카운트, 문서 설명, 테스트 기대값을 함께 갱신해야 했다.
- 기존 PDF 하나만 실제 synthetic asset으로 존재하며, 검색 미리보기는 PDF 파싱 결과가 아니라 fixture의 `expected_demo_labels`를 사용한다.

## 해결 방법

- `received_quotations.fixture.json`에 견적서 송부 메일 3건을 추가해 총 4건으로 확장했다.
- 새 메일은 모두 합성 업체, 발신자, 견적번호, 품목, 금액, 납기, 요청 행동을 사용하고, distinct attachment filename과 expected quote fields를 갖게 했다.
- 새 첨부 rows는 기존 representative synthetic PDF asset을 재사용하도록 명시했다.
- demo README, demo data standard, seed service 테스트 카운트를 총 1,213건, 첨부 4건, 2026-08-12 165건 기준으로 갱신했다.

## 검증

- `python -m json.tool data/demo/received_quotations.fixture.json`: 통과.
- `uv run pytest tests/test_demo_seed_service.py tests/test_mail_decision_ui.py::test_demo_search_service_uses_demo_mailbox_documents_with_attachment_facts`: 8 passed.

## 남은 리스크와 후속 작업

- 새 attachment rows는 데모 표시와 검색 fixture에는 독립적으로 보이지만, 실제 다운로드 파일은 기존 representative PDF를 재사용한다. 실제 PDF 내용까지 견적번호별로 달라야 하는 시연이 필요하면 synthetic PDF asset을 추가 생성해야 한다.
- 작업 전부터 존재한 `app/agents/fact_extraction_agent.py`, `app/mail_content.py`, `tests/test_vision_fact_extraction.py`의 미커밋 변경은 이번 요청과 분리했다.

---

# 2026-08-19 - Scope dashboard category filtering away from Inbox rows

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard category filter, Inbox Queue rendering, HTMX request parameters |
| 관련 파일 | `app/templates/partials/dashboard_distribution.html`, `app/templates/partials/mail_rows.html`, `app/templates/shell.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 이전 수정 후에도 Inbox에서 `전체` 선택 시 카테고리 필터가 해제되지 않고, 건드리지 않아야 할 Inbox Queue 행 높이만 길어진다고 보고했다.

## 확인한 원인

- Dashboard 카테고리 칩 스크립트의 `htmx:afterSwap` 핸들러가 전역 `tr[data-business-label], tr[data-mail-category]`를 대상으로 삼아 Inbox 메일 행까지 다시 숨겼다.
- 따라서 Inbox 상단 셀렉트에서 `전체`를 선택해 서버에서 전체 목록을 받아도, swap 직후 이전 Dashboard 카테고리 상태가 클라이언트에서 다시 적용됐다.
- Dashboard 행에 추가했던 `hx-vals`는 기능상 필요하더라도 행 마크업을 바꾸므로, 사용자가 지적한 Inbox Queue 표시 변화와 분리하기 위해 제거하는 편이 맞다고 판단했다.

## 해결 방법

- Dashboard 카테고리 필터 적용 범위를 `#dashboardMailRows` 내부 행으로 제한했다.
- Dashboard 메일 테이블이 없는 화면에서는 Dashboard 필터 `htmx:afterSwap` 재적용을 중단하게 해 Inbox 목록을 건드리지 않도록 했다.
- 메일 행 템플릿에서 추가 `hx-vals`를 제거해 행 마크업 변경을 되돌렸다.
- 대신 shell의 `htmx:configRequest`에서 Dashboard 행이 `/ui/inbox`로 이동하는 요청에만 현재 활성 카테고리를 파라미터로 추가하게 했다.

## 검증

- `.venv/bin/python -m pytest tests/test_mail_decision_ui.py`: 88 passed.
- `python -m py_compile app/server.py`: passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 수동 확인은 수행하지 않았다. 다만 실패 원인이었던 전역 Dashboard 필터의 Inbox 행 재적용 경로는 테스트와 diff로 제거했다.

---

# 2026-08-19 - Keep dashboard category filter when opening Inbox

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard category filter, Inbox list filtering, HTMX navigation |
| 관련 파일 | `app/server.py`, `app/templates/views/inbox.html`, `app/templates/partials/mail_rows.html`, `app/templates/shell.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Dashboard에서 `발주` 같은 카테고리로 메일 목록을 필터링한 뒤 본문/행을 클릭해 Inbox로 넘어가면 필터링된 메일 목록이 보이는 상태에서, 상단 `All Categories`를 클릭해 필터가 해제되기를 기대했지만 변화가 없다고 보고했다.
- `All Categories` 텍스트를 `전체`로 바꾸고, `전체` 선택 시 필터가 해제되도록 요청했다.

## 확인한 원인

- Dashboard 행 클릭은 `/ui/inbox?email_index=...&email_uid=...`만 요청했고 현재 Dashboard 카테고리 필터 상태를 서버에 전달하지 않았다.
- Inbox 서버 컨텍스트도 `category` 파라미터를 받지 않아 초기 `<select>` 선택값과 초기 목록이 필터 상태를 표현하지 못했다.
- 루트 히스토리 URL 생성에서도 `category`를 보존하지 않아 새로고침 또는 history 복원 시 필터 상태가 빠질 수 있었다.

## 해결 방법

- `/ui/inbox`와 루트 `view=inbox` 경로가 `q`, `category`를 받아 같은 기준으로 Inbox 목록과 선택 메일을 렌더링하도록 수정했다.
- Inbox 카테고리 선택의 기본 옵션 텍스트를 `전체`로 변경하고, 선택된 카테고리를 `<option selected>`로 렌더링했다.
- Dashboard 메일 행에 HTMX 동적 `hx-vals`를 추가해 현재 Dashboard 카테고리 칩이 `전체`가 아닐 때만 `category`를 Inbox 요청에 전달하게 했다.
- main view history URL에 `category`를 포함해 직접 URL, 새로고침, 뒤로가기 흐름에서도 필터 상태가 유지되도록 했다.

## 검증

- `.venv/bin/python -m pytest tests/test_mail_decision_ui.py`: 87 passed.
- `python -m py_compile app/server.py`: passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 수동 확인은 수행하지 않았지만, 서버 렌더링과 HTMX 파라미터 생성 경로를 회귀 테스트로 고정했다.

---

# 2026-08-19 - Fix Mail Decision customer labels from Gemini output

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Mail Decision facts, customer extraction, Gemini demo output |
| 관련 파일 | `app/mail_content.py`, `app/agents/fact_extraction_agent.py`, `tests/test_vision_fact_extraction.py` |

## 요청 또는 배경

- 사용자는 LLM API 전환 후 Mail Decision의 `거래처` 필드가 의도와 달리 `견적 요청`, `납기 확인` 같은 업무 유형으로 표시된다고 보고했고, 근본 원인 분석과 해결을 요청했다.

## 확인한 원인

- Gemini Flash-Lite가 `customer_name`에 제목 말머리(`[견적 요청]`, `[납기 확인]`, `[발주서 접수]`)를 넣는 경우가 있었다.
- 기존 후처리의 `NON_CUSTOMER_SUBJECT_LABELS`는 `견적서`, `견적의뢰서` 같은 문서 라벨은 막았지만 `견적 요청`, `납기 확인`, `발주서 접수` 같은 업무 유형 라벨은 막지 못했다.
- 본문 회사명 보정 정규식은 `안녕하세요. 새롬테크 이도현입니다.`에서 회사명을 추출할 때 `안녕하세요. 새롬테크`처럼 인사말까지 후보에 포함할 수 있었다.

## 해결 방법

- 제목 대괄호에서 거래처로 사용하면 안 되는 업무 유형 라벨을 `NON_CUSTOMER_SUBJECT_LABELS`에 추가했다.
- `FactExtractionAgent` 후처리에 customer candidate normalization을 추가해 `안녕하세요. 네오팩토리솔루션` 같은 후보를 `네오팩토리솔루션`으로 정리한다.
- LLM이 이미 `customer_name`에 업무 유형 라벨을 넣어도 후처리에서 제거하고, 정상 후보가 있으면 그 값을 `customer_name`으로 승격하도록 했다.

## 검증

- `uv run pytest tests/test_vision_fact_extraction.py -q`: 13 passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "customer or bracketed" -q`: 6 passed, 95 deselected.
- `uv run ruff check app/mail_content.py app/agents/fact_extraction_agent.py tests/test_vision_fact_extraction.py`: passed.
- 실제 실행 경로 확인:
  - `[견적 요청] 자동화 제어 부품 견적 확인`: `customer_name=네오팩토리솔루션`, `customer_candidates=['네오팩토리솔루션']`.
  - `[납기 확인] 출고 예정일 및 부분 납품 문의`: `customer_name=새롬테크`, `customer_candidates=['새롬테크']`.

## 남은 리스크와 후속 작업

- 제목 말머리 기반 업무 라벨은 계속 늘어날 수 있으므로 실제 운영 메일을 보며 non-customer label 사전을 보강해야 한다.
- 장기적으로는 거래처 canonical registry/contact domain linking을 추가해 LLM 출력보다 조직 데이터 기반 거래처 식별을 우선해야 한다.

---

# 2026-08-19 - Switch Gemini demo to Flash-Lite for faster free-tier runs

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gemini demo provider, Mail Decision demo latency |
| 관련 파일 | `.env.example` |

## 요청 또는 배경

- 사용자는 Gemini free tier에서 가장 빠르고 안정적인 성능을 기대할 수 있는 모델로 진행해 달라고 요청했다.
- 또한 전체 Mail Decision workflow를 매번 동기 실행한다는 설명이 무엇인지 물었다.

## 확인한 사실과 판단

- 사용 가능한 모델 목록에 `gemini-3.5-flash-lite`, `gemini-flash-lite-latest`, `gemini-3.6-flash` 등이 있었다.
- 빠른 시연과 안정적 모델명 고정을 함께 고려해 alias인 `gemini-flash-lite-latest` 대신 GA 모델명인 `gemini-3.5-flash-lite`를 선택했다.
- 기존 `gemini-3.6-flash`는 품질 중심 데모에는 적합하지만 현재 “빠르게 결과 확인” 목적에는 비용 대비 지연이 컸다.

## 해결 방법

- 로컬 `.env`의 `CORAMAIL_TEXT_MODEL`, `CORAMAIL_VISION_MODEL`을 `gemini-3.5-flash-lite`로 변경하고 web 컨테이너를 재생성했다.
- `.env.example`의 Gemini 데모 권장 모델도 `gemini-3.5-flash-lite`로 갱신했다.

## 검증

- Gemini 최소 probe: 구조화 생성 약 925ms, embedding 약 442ms, embedding dimension 768 확인.
- 실제 Mail Decision Run `b072def5-5f5f-42f1-86fc-0896b5f4f747`: `completed`, `generation_mode=llm`.
- 같은 run의 주요 step latency: `extract_facts` 3233ms, `generate_decision` 1969ms, `retrieve_context` 585ms, 전체 HTTP 응답 약 5초.

## 남은 리스크와 후속 작업

- Flash-Lite는 빠른 시연에 유리하지만 복잡한 첨부/라우팅 판단 품질은 `gemini-3.6-flash`보다 낮을 수 있다.
- 더 빠른 체감이 필요하면 전체 Mail Decision을 HTTP 요청 안에서 끝까지 기다리지 않고, queued run을 즉시 반환한 뒤 UI에서 진행 상태를 polling하는 비동기 구조가 필요하다.

---

# 2026-08-19 - Fix Gemini demo model and embedding dimensions

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gemini demo provider, Mail Decision Run, Qdrant retrieval |
| 관련 파일 | `app/llm/gateway.py`, `.env.example`, `tests/test_vision_fact_extraction.py` |

## 요청 또는 배경

- 사용자는 웹에서 “모델 호출 실패”가 보이며, API 설정 오류 가능성이 높으니 근본 원인을 분석해 달라고 요청했다.

## 확인한 원인

- API key는 컨테이너에 전달되어 있었고 `/api/health`의 Gemini model list 호출도 성공했다.
- 실패 원인은 `CORAMAIL_TEXT_MODEL`과 `CORAMAIL_VISION_MODEL`이 `gemini-2.5-flash`로 설정되어 있었기 때문이다. 실제 Gemini API 응답은 신규 사용자에게 해당 모델이 더 이상 제공되지 않으며 `gemini-3.6-flash`를 사용하라는 404를 반환했다.
- 두 번째 원인은 embedding 차원 불일치였다. Gemini embedding 기본 출력은 3072 차원이고, 현재 Qdrant collection은 768 차원을 기대해 similar case retrieval에서 vector dimension error가 발생했다.

## 해결 방법

- 로컬 `.env`의 텍스트/비전 모델을 `gemini-3.6-flash`로 바꾸고 web 컨테이너를 재생성했다.
- `.env.example`의 Gemini 데모 모델 예시도 `gemini-3.6-flash`로 갱신했다.
- Gemini embedding 요청에 `CORAMAIL_QDRANT_VECTOR_SIZE` 기반 `outputDimensionality`를 명시해 Qdrant collection 차원과 맞췄다.

## 검증

- 직접 Gemini probe: 구조화 생성 성공, embedding dimension 768 확인.
- `POST /api/emails/c884df63-c253-51ed-a863-6e0d908a7c50/mail-decision-runs`: `status=completed`, `generation_mode=llm`, `review_required=false`, Qdrant dimension error 없음.
- `uv run pytest tests/test_vision_fact_extraction.py tests/test_hosting_defaults.py -q`: 16 passed.
- `uv run ruff check app/llm/gateway.py tests/test_vision_fact_extraction.py tests/test_hosting_defaults.py`: passed.

## 남은 리스크와 후속 작업

- Gemini free tier는 rate limit과 데이터 처리 정책상 실제 고객 메일·첨부에는 사용하지 않는다.
- 데모에서 이미 실패로 남은 이전 Mail Decision Run은 과거 기록이며, 새 실행은 정상 완료된다.

---

# 2026-08-19 - Temporary Gemini API demo provider

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | LLM Gateway, demo runtime configuration, healthcheck |
| 관련 파일 | `app/llm/gateway.py`, `app/server.py`, `.env.example`, `docker-compose.yml`, `tests/test_vision_fact_extraction.py`, `tests/test_hosting_defaults.py` |

## 요청 또는 배경

- 사용자는 로컬 GPU 사양이 부족해 시연용으로 로컬 LLM 호출부를 무료 Gemini API로 잠시 대체할 수 있는지 판단하고, 가능하면 구현 방식 보고 후 실행해 달라고 요청했다.

## 확인한 사실과 판단

- 목표 아키텍처와 DECISION-004는 운영 기본값을 로컬 LLM으로 두고, 도메인 코드는 `app/llm/` Gateway를 통해서만 LLM을 호출하도록 정하고 있다.
- 따라서 Gemini를 운영 기본값으로 바꾸는 것은 맞지 않지만, `CORAMAIL_LLM_PROVIDER=gemini`인 경우에만 동작하는 시연용 provider 분기로 격리하면 현재 구조와 충돌하지 않는다.
- Gemini API free tier는 테스트 목적의 낮은 rate limit이며, free tier 입력은 Google 제품 개선에 사용될 수 있으므로 실제 고객 메일과 민감 첨부에는 사용하면 안 된다.

## 해결 방법

- `LocalLLMGateway`에 Gemini REST 분기를 추가해 구조화 텍스트 생성, 이미지 inline data 기반 Vision 요청, embedding, 모델 목록 healthcheck를 지원했다.
- API 키는 `GEMINI_API_KEY` 또는 `GOOGLE_API_KEY` 환경변수에서만 읽고 저장소에는 예시 값만 남겼다.
- 기본 Ollama URL이 남아 있어도 provider가 `gemini`이면 Google Gemini REST endpoint로 요청하도록 해 데모 전환 설정을 줄였다.
- Docker Compose web 서비스에 Gemini API key 환경변수 전달을 추가했다.
- `/api/health`의 LLM readiness가 Gemini `models` 응답도 인식하도록 보강했다.

## 검증

- `uv run pytest tests/test_vision_fact_extraction.py tests/test_hosting_defaults.py -q`: 16 passed.
- `uv run ruff check app/llm/gateway.py app/server.py tests/test_vision_fact_extraction.py tests/test_hosting_defaults.py`: passed.
- 추가로 `uv run pytest tests/test_vision_fact_extraction.py tests/test_hosting_defaults.py tests/test_mail_decision_runtime.py -q`를 실행했으며, 변경 대상 테스트 16개는 통과했지만 기존 `tests/test_mail_decision_runtime.py`의 stub `execute()` 시그니처가 현재 서비스의 `retrieval_scope` 인자와 맞지 않아 3개가 실패했다.

## 남은 리스크와 후속 작업

- 실제 Gemini API 호출은 로컬에 API 키가 없어 수행하지 않았다.
- 무료 API rate limit과 데이터 처리 정책은 데모 전에 Google AI Studio 설정에서 다시 확인해야 한다.
- 실제 고객 메일, 첨부 원문, 개인정보가 포함된 데이터로는 Gemini provider를 사용하지 않는다.

---

# 2026-08-19 - Inbox email body horizontal overflow fix

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode Inbox, email detail body rendering |
| 관련 파일 | `app/mail_content.py`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 데모모드 Inbox 탭에서 메일 본문 내용이 가로 폭을 넘어 가로 스크롤이 생기며, 이런 상황 자체가 발생하지 않도록 근본 원인을 찾아 해결해 달라고 요청했다.

## 확인한 원인

- Inbox 상세 본문은 `email_detail.html`에서 iframe `srcdoc`로 렌더링된다.
- plain text 본문은 `<pre>`만 넣은 srcdoc를 사용하고 있어 바깥 `.email-body--plain` CSS가 iframe 내부 `<pre>`에 적용되지 않았다.
- HTML 메일도 긴 URL, 고정폭 table, `white-space: nowrap`, 큰 `min-width` 같은 메일 원문 스타일이 iframe 내부 document의 scroll width를 키울 수 있었다.

## 해결 방법

- `email_body_srcdoc()`의 iframe 내부 기본 CSS에 `box-sizing`, `max-width`, `min-width`, `overflow-x`, table 폭 제한, 긴 단어 wrapping, `<pre>` wrapping을 추가했다.
- `plain_email_body_srcdoc()`도 같은 안전 wrapper를 사용하게 바꿔 plain text와 HTML 본문이 동일한 overflow 방어를 갖도록 했다.
- 바깥 `.email-body`와 `.email-body-frame`에도 `min-width: 0`, `max-width: 100%`, `overflow-x: hidden`을 보강했다.
- 긴 URL과 고정폭 table에 대한 회귀 테스트를 추가하고, plain text 선행 줄바꿈 보존 테스트를 새 wrapper 기준으로 갱신했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "body_srcdoc or plain_text_leading_newlines or cid_images or inbox_initial_queue" -q`: 4 passed.
- Playwright Chromium 실제 레이아웃 측정: 390px viewport에서 parent document와 iframe 모두 `scrollWidth == clientWidth == 390`.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 84 passed.

## 남은 리스크와 후속 작업

- 외부 HTML 메일의 인라인 레이아웃 스타일 일부는 iframe 내부에서 wrapping 우선으로 재해석된다. 본문 판독성과 가로 스크롤 방지가 목적이라 허용한 tradeoff다.
- 작업 시작 전부터 존재한 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 이번 커밋에 포함하지 않는다.

---

# 2026-08-19 - Demo scenarios rewritten without urgent flow

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo presentation script, non-urgent scenario coverage |
| 관련 파일 | `docs/development/demo-presentation-scenarios-2026-08-19.md`, `docs/development/demo-presentation-scenarios-2026-08-19.docx` |

## 요청 또는 배경

- 사용자는 데모모드에서 정확히 어떤 데이터를 쓰고, 어떤 버튼을 눌러 무엇을 확인하는지 순서대로 시연 시나리오를 다시 작성해 달라고 요청했다.
- 긴급 관련 시연은 제외하고, 구현된 기능이 다양하게 포함되도록 구성해 달라고 했다.

## 해결 방법

- 기존 긴급 장애 시나리오를 제거하고 문서 전체에서 `긴급`, `장애`, `URG-DEMO`, `urgent` 관련 문구가 남지 않게 했다.
- 시나리오를 Dashboard 현황, Inbox 발주 필터, Inbox 견적 첨부 Details, Search 근거 기반 견적 답변과 원본 메일 이동, 최신 메일 질의와 Settings 운영 설정 확인으로 재구성했다.
- 각 시나리오마다 사용할 데이터(`PO-DEMO-2026-0812-01`, `QT-2026-0812-03`, `Quotation_QT-2026-0812-03.pdf`, `가장 최신 메일이 뭐야`)와 클릭 순서, 확인할 화면 문구를 명시했다.
- Markdown 원본과 Word `.docx`를 같은 내용으로 재생성했다.

## 검증

- `.docx` 내부에 `PO-DEMO-2026-0812-01`, `Quotation_QT-2026-0812-03.pdf`, `가장 최신 메일이 뭐야`, `자동 배정 기준`이 포함되는지 확인했다.
- `.docx` 내부에 `긴급`, `장애`, `URG-DEMO`, `urgent`가 포함되지 않는지 확인했다.
- Playwright로 `http://127.0.0.1:8001`에서 Dashboard, Inbox `발주` 필터와 `PO-DEMO-2026-0812-01` 상세, Inbox `QT-2026-0812-03` 첨부 Details, Search `견적서 납기·총액`, 원본 메일 이동, Search `최신 메일`, Settings 패널을 실제 클릭 검증했다.
- 최종 검증에서 `dashboard_visible`, `po_filter_and_detail`, `quote_attachment_details`, `search_quote_answer`, `source_mail_link`, `latest_answer`, `settings_panels`, `console_health`가 모두 PASS였다.

## 남은 리스크와 후속 작업

- 검증은 Chromium headless 기준이며 Microsoft Word에서 `.docx` 최종 시각 검수는 별도다.
- 신규 Gmail 계정 연결 자체는 이번 시나리오에서 설명 대응으로만 포함했고, 실제 OAuth 연결은 검증하지 않았다.
- 작업 시작 전부터 존재한 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 이번 커밋에 포함하지 않는다.

---

# 2026-08-19 - Demo presentation scenario validation

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode QA, presentation scenario document |
| 관련 파일 | `docs/development/demo-presentation-scenarios-2026-08-19.md`, `docs/development/demo-presentation-scenarios-2026-08-19.docx` |

## 요청 또는 배경

- 사용자는 작성한 Word 시연 시나리오 기준으로 현재 데모 모드가 문제 없이 동작하는지 검증해 달라고 요청했다.
- 검증 대상은 Dashboard, Inbox 견적 검색, Search 견적서 답변, 원본 메일 이동, 긴급 장애 메일, 최신 메일, Settings/Gmail 설명 흐름이었다.

## 해결 방법

- `http://127.0.0.1:8001`의 실행 중인 데모 서버를 Playwright로 실제 클릭 검증했다.
- Browser 플러그인은 현재 세션에 없어 정규 Playwright를 사용했다.
- Playwright Chromium은 기본 sandbox에서 실행 실패하여 승인된 unsandboxed 실행으로 검증했다.
- 시나리오 2에서 총액은 첨부 카드의 `expand_more`를 눌러 Details를 펼쳐야 확인되는 것으로 드러나, Word/Markdown 문서에 해당 클릭 단계를 명시했다.

## 검증

- 로그인, Dashboard, Inbox `QT-2026-0812-03` 검색, 첨부 Details 확장, Search `견적서 납기·총액`, `원본 메일 보기`, Search `긴급 장애 메일`, Inbox 긴급 badge와 `긴급 서비스`, Search `최신 메일`, Settings, 모바일 Search 예시 버튼 흐름을 통과했다.
- 최종 Playwright 검증에서 `login_page_identity`, `dashboard_has_summary`, `inbox_quote_detail_visible`, `search_quote_answer_delivery`, `search_quote_answer_total`, `source_mail_navigation_url`, `urgent_row_highlighted`, `latest_answer_visible`, `settings_view_visible`, `mobile_search_examples_visible`, `console_health`가 모두 PASS였다.
- 스크린샷은 `/tmp/coramail_doc_scenario_01_dashboard.png`, `/tmp/coramail_doc_scenario_02_inbox_quote.png`, `/tmp/coramail_doc_scenario_03_search_quote.png`, `/tmp/coramail_doc_scenario_03_source_mail.png`, `/tmp/coramail_doc_scenario_04_urgent.png`, `/tmp/coramail_doc_scenario_05_latest.png`, `/tmp/coramail_doc_scenario_05_settings.png`, `/tmp/coramail_doc_scenario_mobile.png`에 저장했다.

## 남은 리스크와 후속 작업

- 검증은 Chromium headless 기준이며 Microsoft Word에서 `.docx` 최종 시각 검수는 별도다.
- 신규 Gmail 계정 연결은 문서의 설명/대응 시나리오만 검증했고, 실제 OAuth 신규 연결은 이번 데모 검증 범위에서 제외했다.
- 작업 시작 전부터 존재한 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 이번 커밋에 포함하지 않는다.

---

# 2026-08-19 - Demo presentation scenario Word document

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo presentation script, Word document handoff |
| 관련 파일 | `docs/development/demo-presentation-scenarios-2026-08-19.md`, `docs/development/demo-presentation-scenarios-2026-08-19.docx` |

## 요청 또는 배경

- 사용자는 `openai-templates` 플러그인을 지정하며 시연 시나리오를 Word 문서로 작성해 달라고 요청했다.
- 문서는 시나리오별로 순서대로 해야 하는 동작을 나열하는 방식이어야 했다.

## 해결 방법

- 연결된 도구에는 Word 직접 제어 기능이 없어 로컬 `.docx` 파일을 생성하는 방식으로 처리했다.
- 같은 내용을 Markdown 원본으로도 남겨 이후 수정과 diff 검토가 가능하게 했다.
- 문서에는 Dashboard 브리핑, Inbox 견적 메일 확인, Search 견적서 질의, 긴급 장애 메일 흐름, 최신 메일 및 새 Gmail 계정 요청 대응까지 5개 시나리오를 순서형 액션 리스트로 정리했다.

## 검증

- `.docx`가 필수 OOXML part인 `[Content_Types].xml`, `_rels/.rels`, `word/document.xml`, `word/styles.xml`, `word/numbering.xml`을 포함하는지 확인했다.
- `word/document.xml` 안에 제목, 시나리오 3 제목, `URG-DEMO-2026-0810-01`, `새 Gmail 계정` 문구가 포함되는지 확인했다.

## 남은 리스크와 후속 작업

- Word 파일은 로컬 생성 OOXML 문서이며, Microsoft Word에서의 최종 시각 검수는 별도로 수행해야 한다.
- 작업 시작 전부터 존재한 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 이번 문서 커밋에 포함하지 않는다.

---

# 2026-08-19 - Demo scenario affordances and urgent flow

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo search examples, urgent Inbox highlighting, Search source navigation |
| 관련 파일 | `app/services/demo_mail_service.py`, `app/templates/views/search.html`, `app/templates/partials/mail_rows.html`, `app/templates/partials/search_results.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Inbox 카테고리가 이미 한글로 표시된다고 정정했고, 시나리오별로 추가 구현해야 하는 부분을 바로 진행하라고 요청했다.
- 시연 품질을 위해 기존 데이터를 활용하되 대표가 직접 클릭하기 쉬운 흐름과 긴급/클레임 사례의 설득력을 높이는 보강이 필요했다.

## 해결 방법

- Demo Search 화면에 `견적서 납기·총액`, `긴급 장애 메일`, `최신 메일` 예시 버튼을 추가했다.
- 예시 버튼은 HTMX submit 상태와 무관하게 `/ui/search-results` fragment를 직접 조회해 결과 영역을 갱신하게 했다.
- Demo fixture의 세부 업무 유형과 담당 영역 label을 한글 표시로 보강했다.
- 긴급/클레임 행은 `is-priority-high` row tone과 `긴급` 또는 `주의` badge로 표시하게 했다.
- Search 결과의 `원본 메일 보기`는 전체 Inbox URL로 이동하는 일반 링크로 바꿔 시연 중 URL과 상세 상태가 안정적으로 맞게 했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "search or demo_inbox or shell_installs" -q`: 12 passed.
- `uv run pytest tests/test_mail_search_service.py -q`: 18 passed.
- `uv run python -m py_compile app/services/demo_mail_service.py app/services/mail_search_service.py app/server.py`: 통과.
- `http://127.0.0.1:8001`에서 Playwright로 Dashboard, Search 예시 버튼, 견적서 답변, 원본 메일 이동, 긴급 메일 검색과 badge, 모바일 Search 예시 버튼 표시를 검증했다.
- 최종 Playwright 검증에서 `dashboard_ok`, `examples_visible_ok`, `quote_example_answer_ok`, `source_mail_ok`, `urgent_badge_ok`, `mobile_search_examples_ok`가 모두 true였고 콘솔 오류는 없었다.

## 남은 리스크와 후속 작업

- 이번 보강은 내일 시연을 위한 대표 시나리오 UX 안정화이며 전체 임의 질의 품질 보장은 아니다.
- 작업 시작 전부터 worktree에 다수의 별도 미커밋 변경과 `node_modules/`, `package.json`, `package-lock.json`가 존재했다. 이번 커밋에는 시나리오 보강 hunk와 이 세션 로그 항목만 포함한다.

---

# 2026-08-19 - Demo presentation happy path hardening

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode, Inbox search, Search RAG answer, HTMX dynamic view handling |
| 관련 파일 | `app/services/demo_mail_service.py`, `app/services/mail_search_service.py`, `app/templates/partials/mail_rows.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py`, `tests/test_mail_search_service.py` |

## 요청 또는 배경

- 사용자는 대표가 내일까지 외부 시연 가능한 데모 모드 화면을 요구했으며, 스크린샷이 아니라 실제 동작 테스트까지 되는 시연 흐름을 오늘 마무리하고 싶다고 했다.
- 모든 데이터가 완벽할 필요는 없고, 정해진 시연 시나리오에 해당하는 데이터만 정상 동작하면 된다고 범위를 좁혔다.
- 시연 해피패스는 Dashboard 확인, Inbox에서 `QT-2026-0812-03` 견적 메일 검색·상세 확인, Search에서 해당 견적서의 납기와 총액 질의, Settings 확인으로 잡았다.

## 해결 방법

- Demo Inbox 검색 대상에 business ref, 선박명, 장비명, 주요 사양 필드를 포함해 `QT-2026-0812-03`로 대표 견적 메일을 찾을 수 있게 했다.
- Inbox subject 셀에 `Ref ...` badge를 표시해 시연자가 대표 메일을 화면에서 바로 식별할 수 있게 했다.
- 동적으로 삽입된 HTMX fragment에 `htmx.process(target)`를 호출해 Search form의 `hx-get`이 실제로 활성화되게 했다.
- 구조화 첨부 근거에 `expected_delivery`와 `total_amount`가 있는 필드형 질문은 LLM citation 선택 실패에 의존하지 않고 deterministic answer를 생성하게 했다.

## 검증

- `uv run pytest tests/test_mail_search_service.py tests/test_mail_decision_ui.py -k "search or demo_inbox_search or shell_installs" -q`: 28 passed.
- `uv run python -m py_compile app/services/demo_mail_service.py app/services/mail_search_service.py app/server.py`: 통과.
- `http://127.0.0.1:8001`에서 Playwright로 로그인, Dashboard, Inbox `QT-2026-0812-03` 검색과 상세, Search 질의, Settings, 모바일 Inbox를 실제 클릭 검증했다.
- 최종 Playwright 검증에서 `dashboard_ok`, `inbox_filtered_ref_ok`, `detail_ref_ok`, `detail_total_ok`, `detail_routing_ok`, `search_delivery_ok`, `search_total_ok`, `search_ref_ok`, `search_evidence_ok`, `settings_policy_ok`, `settings_assignee_ok`, `mobile_inbox_ok`가 모두 true였고 콘솔 오류는 없었다.

## 남은 리스크와 후속 작업

- 이번 작업은 전체 메일 데이터 품질 보장이 아니라 대표 시연용 해피패스 보강이다.
- 작업 시작 전부터 worktree에 다수의 별도 코드·문서·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`가 존재했다. 이번 커밋에는 시연 해피패스 관련 hunk와 이 세션 로그 항목만 포함한다.

---

# 2026-08-14 - Inbox row number column width adjustment

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox table layout, row number column, subject column |
| 관련 파일 | `app/static/app.css` |

## 요청 또는 배경

- 사용자는 Inbox 탭의 `#` 컬럼에서 세 자리 수가 표시될 때 공간 부족으로 말줄임표가 나오는 문제를 보고했다.
- `#` 컬럼을 조금 넓히되, 넓힌 만큼 Subject 컬럼을 좁혀 전체 테이블 폭은 유지해 달라고 요청했다.

## 해결 방법

- Inbox 전용 테이블 규칙에서 `#` 컬럼 폭을 `44px`에서 `56px`로 늘렸다.
- 같은 `12px`만큼 Subject 컬럼 계산값을 `calc(38% + 78px)`에서 `calc(38% + 66px)`로 줄였다.
- Dashboard 테이블의 공통 `#` 컬럼 폭은 변경하지 않았다.

## 검증

- Playwright로 `http://127.0.0.1:8000/login` 로그인 후 `http://127.0.0.1:8000/ui/inbox`를 확인했다.
- 1440px viewport에서 `#` 컬럼이 `56px`, Subject 컬럼이 `478px`로 렌더링되고 콘솔 오류가 없음을 확인했다.
- 800px viewport에서 `#` 컬럼이 `56px`로 유지되고 콘솔 오류가 없음을 확인했다.

## 남은 리스크와 후속 작업

- 작업 시작 전부터 worktree에 다수의 별도 코드·문서·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`가 존재했다. 이번 커밋에는 inbox 컬럼 폭 조정과 이 세션 로그만 포함한다.

---

# 2026-08-14 - Gmail UI demo-only change isolation

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gmail/Demo UI mode isolation, Search tab, browser history |
| 관련 파일 | `app/templates/shell.html`, `app/templates/views/search.html`, `app/server.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Gmail 모드에도 유지할 변경으로 Dashboard stats 문구/계산 방식 변경과 Inbox 초기 렌더링 방식 변경을 명시했다.
- 그 외 데모 모드 요청에서 Gmail 모드로 흘러간 변경, 특히 `/ui/search` 같은 fragment URL이 주소창에 남는 동작과 데모 견적번호 Search 예시를 데모 모드에만 격리해 달라고 요청했다.

## 해결 방법

- 메인 네비게이션의 `window.history.pushState`를 `demo_mode`일 때만 실행하도록 묶어 Gmail 모드 탭 이동이 브라우저 주소를 변경하지 않게 했다.
- Search form은 데모 모드에서만 `/ui/search` action과 `QT-2026-0812-03` 예시를 유지하고, Gmail 모드에서는 `/ui/search-results` fallback action과 일반 견적서 예시를 사용하게 했다.
- `/ui/search-results` non-HTMX 직접 접근 redirect는 데모 모드에서 기존 `/ui/search?...`를 유지하고, Gmail 모드에서는 root shell `/?view=search...`로 보내 fragment URL 노출을 피하게 했다.
- 사용자가 유지하기로 한 Dashboard stats 변경과 Inbox 초기 렌더링 변경은 보존했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "search or shell_keeps_fragment or gmail_shell" -q`: 11 passed.
- `python -m py_compile app/server.py`: 통과.

## 남은 리스크와 후속 작업

- 작업 시작 전부터 worktree에 다수의 별도 코드·문서·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`가 존재했다. 이번 커밋에는 Gmail/Demo 격리 hunk와 이 세션 로그만 포함한다.

---

# 2026-08-14 - Inbox summary prompt v3 롤백

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox summary regeneration, Decision Agent prompt, stale analysis jobs |
| 관련 파일 | `app/agents/decision_agent.py`, `app/services/mail_decision_runtime_service.py`, `app/repositories/postgres_decision_result_repository.py`, `app/services/postgres_email_analysis_worker.py`, `app/repositories/postgres_job_repository.py`, `tests/test_decision_agent.py` |

## 요청 또는 배경

- 사용자는 직전 `fix: improve inbox summary prompt` 변경 결과가 별로라고 평가했고 롤백을 요청했다.
- 직전 커밋 `9afec95`에는 summary v3 prompt, 첨부/강조 payload, stale job 처리, 테스트, 세션 로그가 포함되어 있었다.

## 해결 방법

- `DecisionAgent` prompt와 helper, runtime attachment payload 전달, `decision-agent:v3` 저장/조회 변경, stale job 만료 처리 변경을 이전 상태로 되돌렸다.
- 이번 턴에 추가한 summary v3 전용 회귀 테스트만 제거했다.
- 작업 전부터 존재하던 별도 미커밋 변경과 세션 로그의 다른 항목은 보존했다.

## 검증

- `.venv/bin/python -m pytest tests/test_decision_agent.py tests/test_gmail_persistent_mode.py`: 통과.
- `.venv/bin/python -m py_compile app/agents/decision_agent.py app/services/mail_decision_runtime_service.py app/repositories/postgres_decision_result_repository.py app/services/postgres_email_analysis_worker.py app/repositories/postgres_job_repository.py`: 통과.

## 남은 리스크와 후속 작업

- inbox summary 품질 개선은 보류한다. 다음 시도는 프롬프트를 크게 바꾸기보다 실패 사례와 기대 출력부터 더 명확히 모아야 한다.
- 이번 작업 전부터 worktree에 다수의 별도 코드·문서·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`가 존재했다. 롤백 커밋에는 직전 summary prompt 변경의 되돌림만 포함한다.

---

# 2026-08-14 - UI fragment route history cleanup

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gmail UI shell navigation, HTMX fragment routes, browser history |
| 관련 파일 | `app/templates/shell.html`, `app/server.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 데모 모드 대상으로 조정했던 UI 동작 일부가 Gmail 모드에도 적용된 것으로 보이며, 사이트 주소가 `/ui/search` 같은 GET fragment route로 노출되는 것이 맞는지 확인을 요청했다.
- 확인 결과 `/ui/search` 등은 HTMX fragment/full-view 겸용 서버 라우트로 유지할 필요가 있지만, 네비게이션 fallback JS가 해당 fragment URL을 그대로 `window.history.pushState`에 넣어 주소창까지 바꾸고 있었다.

## 해결 방법

- 메인 네비게이션 클릭 시 내부 요청 URL을 루트 셸 URL로 변환하는 `mainViewHistoryUrl`을 추가했다. 이제 검색 탭은 `/ui/search` 대신 `/?view=search`로 기록된다.
- `/` 라우트가 `view`, `q`, `limit`, `email_index`, `email_uid`를 받아 Dashboard, Inbox, Documents, Search, Settings 초기 화면을 직접 렌더링할 수 있게 했다.

## 검증

- `.venv/bin/pytest tests/test_mail_decision_ui.py::test_shell_keeps_fragment_routes_out_of_browser_history tests/test_mail_decision_ui.py::test_root_can_render_search_view_without_ui_fragment_url tests/test_mail_decision_ui.py::test_shell_installs_search_fallback_when_htmx_cdn_is_unavailable tests/test_mail_decision_ui.py::test_direct_search_results_request_redirects_to_full_search_view`: 통과.
- `pytest` 명령은 PATH에 없어 `.venv/bin/pytest`로 실행했다.

## 남은 리스크와 후속 작업

- `/ui/search-results` 직접 접근은 기존 테스트와 같이 전체 검색 화면으로 redirect한다. 검색 결과 fragment 자체는 내부 요청 경로로 계속 유지된다.
- 작업 시작 전부터 존재한 다수의 코드·문서·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 보존했다.

---

# 2026-08-14 - Production Qdrant provenance indexing

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Qdrant production similar-case indexing, provenance contract, legacy reindex |
| 관련 파일 | `app/retrieval/qdrant_indexing.py`, `app/tools/qdrant_similar_case_index.py`, `app/repositories/postgres_routing_repository.py`, `app/services/mail_decision_runtime_service.py`, `app/services/mail_decision_routing_service.py`, `app/server.py`, `tests/test_qdrant_production_indexing.py`, `docs/architecture/qdrant_point_schema.md`, `docs/features/context-search-qdrant-indexing.md`, `docs/features/llmops-observability-evaluation.md` |

## 요청 또는 배경

- 사용자는 runtime `RetrievalScope`가 강제하는 Qdrant provider, dataset, synthetic/evaluation, account, confirmed-assignment scope를 production indexing payload와 일치시키고 legacy point 재색인 절차를 완성해 달라고 요청했다.
- 실제 코드 추적 결과 production similar-case point를 생성해 Qdrant에 upsert하는 운영 경로가 없었고, 기존 bootstrap은 빈 collection 생성 수준이었다. Attachment/document indexing은 routing similar-case collection과 별개다.

## 해결 방법

- PostgreSQL `email_messages`, `email_accounts`, `routing_assignments`, current facts/analysis 결과를 source of truth로 삼는 `ProductionSimilarCaseIndexer`와 `QdrantCaseIndexClient`를 추가했다.
- Production Gmail similar-case payload에 `provider`, `dataset_type=production`, `synthetic=false`, `evaluation=false`, `email_account_id`, `assignment_confirmed`, assignment/source/status, schema/content hash provenance를 저장한다.
- `assignment_confirmed`는 assignee가 있고 status가 `assigned`, `forwarded`, `completed`인 최신 routing assignment로 정의했다. `review_required`는 미확정으로 유지한다.
- 자동 배정, 수동 배정, 재배정, 수동 전달 완료 후 같은 deterministic point id를 best-effort upsert해 stale assignee metadata를 덮어쓰게 했다.
- Legacy point는 production으로 추정 backfill하지 않고 새 collection version에 PostgreSQL에서 재색인한 뒤 `CORAMAIL_QDRANT_CASE_COLLECTION`을 전환하는 절차와 verification CLI를 문서화했다.

## 검증

- `uv run pytest tests/test_qdrant_production_indexing.py tests/test_qdrant_retrieval_scope.py tests/test_agentic_retrieval.py tests/test_assignment_context_builder.py tests/test_mail_decision_routing_service.py tests/test_synthetic_evaluation.py tests/test_e2e_evaluation_runner.py`: 통과. 기존 `TestRetrievalService` collection warning은 유지.
- `python -m py_compile app/retrieval/qdrant_indexing.py app/tools/qdrant_similar_case_index.py app/repositories/postgres_routing_repository.py app/services/mail_decision_runtime_service.py app/services/mail_decision_routing_service.py app/server.py`: 통과.
- `uv run python -m app.tools.qdrant_similar_case_index --help`, `reindex-production --help`, `verify --help`: 통과.

## 남은 리스크와 후속 작업

- Qdrant/LLM stack 장애 시 routing transaction은 source of truth로 유지하고 sync 실패는 삼킨다. 운영에서는 `reindex-production`과 `verify`를 배포 절차에 포함해야 한다.
- 기존 legacy collection은 새 scope에서 계속 fail-closed되므로 운영 전 새 collection 재색인과 환경변수 전환이 필요하다.
- Attachment chunk/document search provenance 확대, AssignmentContext runtime integration, RoutingPolicy 변경, Graph/Search Agent/entity/sLLM 작업은 이번 범위에서 제외했다.
- 작업 시작 전부터 존재한 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 보존했다.

---

# 2026-08-14 - Qdrant 담당자 배정 retrieval isolation

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Qdrant similar-case retrieval, provider/dataset isolation, evaluation leakage |
| 관련 파일 | `app/schemas/retrieval.py`, `app/retrieval/qdrant_client.py`, `app/retrieval/service.py`, `app/services/mail_decision_runtime_service.py`, `app/repositories/postgres_mail_decision_repository.py`, `app/evaluation/synthetic_dataset.py`, `app/evaluation/loader.py`, `app/evaluation/leakage.py`, `tests/test_qdrant_retrieval_scope.py`, `tests/test_agentic_retrieval.py`, `tests/test_mail_decision_routing_service.py`, `docs/architecture/qdrant_point_schema.md`, `docs/features/context-search-qdrant-indexing.md`, `docs/features/llmops-observability-evaluation.md` |

## 요청 또는 배경

- 사용자는 운영 Gmail 담당자 배정 retrieval에 synthetic, demo, evaluation Qdrant point가 similar-case evidence로 섞이지 않도록 실제 코드 흐름을 확인하고 안전하게 차단해 달라고 요청했다.
- 확인 결과 runtime `QdrantSimilarCaseRetriever`는 `assignment_confirmed=True`만 적용했고 provider, dataset, synthetic/evaluation provenance를 최종 Qdrant query에서 강제하지 않았다.

## 해결 방법

- `RetrievalScope` 계약을 추가하고 Mail Decision runtime이 현재 메일 provider/account와 명시적 evaluation env를 기준으로 scope를 생성하게 했다.
- `QdrantSimilarCaseRetriever`가 scope 없이는 fail-closed로 실패하고, planner filter와 mandatory provider/dataset/synthetic/evaluation/confirmed filter를 최종 query에서 합성하게 했다.
- Synthetic evaluation Qdrant payload와 loader에 `provider`, `dataset_type`, `evaluation` provenance를 추가하고, leakage validator가 provenance 누락도 탐지하게 했다.
- Search 탭은 현재 mailbox document search 경로를 유지하며, assignment routing Qdrant scope와 전역으로 묶지 않았다.

## 검증

- `uv run pytest tests/test_qdrant_retrieval_scope.py tests/test_agentic_retrieval.py tests/test_assignment_context_builder.py tests/test_mail_decision_routing_service.py tests/test_synthetic_evaluation.py tests/test_e2e_evaluation_runner.py`: 통과. 기존 `TestRetrievalService` collection warning은 유지.
- `python -m py_compile app/schemas/retrieval.py app/retrieval/qdrant_client.py app/retrieval/service.py app/services/mail_decision_runtime_service.py app/evaluation/loader.py app/evaluation/synthetic_dataset.py app/evaluation/leakage.py`: 통과.

## 남은 리스크와 후속 작업

- 운영 production Qdrant indexing path는 아직 별도 구현이 없어 새 provenance 필드가 실제 운영 point에 upsert되는 경로는 후속 색인 작업에서 연결해야 한다.
- 기존 Qdrant collection의 legacy point는 metadata가 없으면 production routing에서 검색되지 않는다. 운영 전 재색인 또는 collection 교체가 필요하다.
- Graph DB, Graph Retriever, AssignmentContext runtime integration은 이번 범위에서 구현하지 않았다.
- 작업 시작 전부터 존재한 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 보존했다.

---

# 2026-08-14 - Assignment Context Builder P0 구현

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Assignment Context, Retrieval evidence normalization, 담당자 배정 기반 |
| 관련 파일 | `app/schemas/retrieval.py`, `app/retrieval/assignment_context.py`, `tests/test_assignment_context_builder.py`, `docs/architecture/knowledge-graph-context-and-search-agent.md`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Graph DB가 아니라 현재 `RetrievalContext`와 `RoutingPolicy` 사이에 빠져 있는 `AssignmentContextBuilder` 계층과 typed assignment evidence contract를 먼저 구현해 달라고 요청했다.
- 기존 `RoutingPolicy` 판단 로직과 결과는 최대한 변경하지 말고, 기존 retrieval 결과를 검증 가능한 assignment context로 정규화하는 기반까지만 요구했다.

## 해결 방법

- `AssignmentEvidenceType`, `AssignmentEvidence`, `AssignmentCandidateContext`, `AssignmentContext` schema를 추가했다.
- `AssignmentContextBuilder`를 추가해 `RetrievalContext.selected_hits`를 `exact_history`, `routing_rule`, `assignee_capability`, `similar_case` evidence로 변환하고 담당자별 context로 그룹화했다.
- builder는 `assignee_user_id`를 metadata에서 typed field로 승격하지만 없는 값을 만들지 않고, invalid UUID나 source 누락은 warning으로 남긴다.
- 기존 `RoutingPolicy`와 Mail Decision workflow에는 연결하지 않아 기존 점수, 선택 담당자, review/auto-assignment 판단을 변경하지 않았다.

## 검증

- `uv run pytest tests/test_assignment_context_builder.py -q`: 통과.
- `uv run pytest tests/test_routing_policy.py tests/test_agentic_retrieval.py tests/test_mail_decision_routing_service.py -q`: 통과. 기존 `TestRetrievalService` collection warning은 유지.
- `uv run pytest tests/test_mail_decision_runtime.py tests/test_decision_agent.py -q`: 통과.

## 남은 리스크와 후속 작업

- `AssignmentContext`는 아직 runtime state에 저장되거나 `RoutingPolicy` 입력으로 사용되지 않는다. 다음 단계에서 병렬 생성 후 trace/API 노출 여부를 정해야 한다.
- Qdrant runtime retriever는 여전히 `assignment_confirmed=True`만 필터링하고 provider/dataset 격리를 강제하지 않는다. 이번 P0 범위 밖이라 수정하지 않았다.
- 작업 시작 전부터 존재한 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 보존했다.

---

# 2026-08-14 - Knowledge Graph Context 기준 문서 정리

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Knowledge Graph, GraphRAG, Assignment Context Retrieval, Search Agent 문서 정합성 |
| 관련 파일 | `docs/architecture/knowledge-graph-context-and-search-agent.md`, `docs/architecture/graph-routing-architecture.md`, `docs/decisions/DECISION-011-routing-knowledge-graph.md`, `docs/decisions/README.md`, `docs/architecture/agentic_rag_mail_decision_system.md`, `docs/features/context-search-qdrant-indexing.md`, `docs/product/data-reality-gap.md` |

## 요청 또는 배경

- 사용자는 Knowledge Graph의 1차 목적을 최종 담당자 직접 결정이 아니라 담당자 배정에 필요한 관계 기반 Context/Evidence 검색으로 정리해 달라고 요청했다.
- 기존 Graph routing 문서와 DECISION-011에는 Graph DB 최종 도입, Apache AGE 1순위 목표 구현안, 실제 데이터 검증 전 상세 ontology 확정 전제가 남아 있어 최신 방향과 충돌했다.
- 이번 요청에서는 문서 변경만 수행하고 commit, push, branch 생성, rebase는 하지 말라는 제한이 있었다.

## 해결 방법

- 신규 기준 문서 `knowledge-graph-context-and-search-agent.md`를 추가해 PostgreSQL/Qdrant/KG 역할 분리, Assignment Context Retriever 책임, 고정 Graph Query 우선 원칙, 미래 Search Agent 구조, Fact/Inference/Provenance/Temporal Context, Context Builder 계약, 합성 데이터 한계를 정리했다.
- `graph-routing-architecture.md`는 삭제하지 않고 Deprecated 안내를 추가해 과거 설계 이력으로 보존했다.
- `DECISION-011-routing-knowledge-graph.md`는 상태를 `대체됨`으로 바꾸고 새 기준 문서와 대체 사유를 기록했다.
- Agentic RAG, Context Search, 데이터 현실 차이 문서에는 새 기준 문서 링크와 합성 데이터 해석 제한을 최소 문구로 보강했다.

## 검증

- `git diff --stat`와 관련 문서 diff를 확인했다.
- 코드 파일은 수정하지 않았고 테스트는 실행하지 않았다. 변경 범위가 문서 정합성 정리로 제한되어 문서 diff 검토로 확인했다.

## 남은 리스크와 후속 작업

- 실제 수신 메일, 담당자 전달 이력, entity alias 평가 데이터가 확보되기 전까지 Graph Context의 운영 품질 개선 여부는 미검증 상태다.
- Graph DB 제품, Text-to-SQL, Text-to-Cypher, production ontology는 계속 보류 상태다.
- 작업 시작 전부터 존재한 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 보존했다.

---

# 2026-08-13 - 견적서 첨부 Details 라벨 범위 조정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox attachment Details, quote attachment presentation |
| 관련 파일 | `app/presentation/attachment_analysis.py`, `app/templates/partials/email_detail.html`, `tests/test_quote_attachment_field_labels.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 데모 모드에서만 의도했던 견적서 첨부 Details 필드명 한국어 표시가 Gmail 모드에도 적용되는 것을 발견했다.
- 우선 견적서 첨부문서만 대상으로 `To`, `Date`, `Our Ref No`, `Total Price`, `Your Ref No`, `In Charge`, `Tel`, `Vessel` 표시 라벨을 지정했다.

## 해결 방법

- 첨부 Details 필드 라벨 필터가 문서 유형을 인자로 받아 `quote` 문서에서만 견적서 전용 한국어 라벨을 적용하게 했다.
- 템플릿에서 첨부파일의 `document_type` 또는 `document_category`를 라벨 필터에 넘겨 같은 원본 필드명이 다른 문서 유형에서는 기존 표시를 유지하게 했다.
- 견적서 라벨 매핑 범위 회귀 테스트를 추가했다.

## 검증

- `uv run pytest tests/test_quote_attachment_field_labels.py tests/test_mail_decision_ui.py::test_email_detail_keeps_attachment_details_for_business_extracted_information -q`: 통과.

## 남은 리스크와 후속 작업

- 품목 테이블 컬럼(`Description`, `Qty`, `Unit`, `U/Price`, `Amount`)과 `Attn`은 이번 요청에서 지정되지 않아 기존 영어 표시를 유지한다.
- 작업 시작 전부터 존재한 다른 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 남겨 둔다.

---

# 2026-08-13 - Documents 카드 집계 문구 제거

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Documents UI, attachment document type navigation |
| 관련 파일 | `app/templates/partials/document_type_sections.html`, `tests/test_document_type_navigation.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Documents 탭 카드 헤더에 표시되는 `3 emails · 3 attachments` 형태의 집계 텍스트 영역을 제거해 달라고 요청했다.

## 해결 방법

- Documents 문서 유형 카드 헤더에서 이메일 수와 첨부파일 수를 렌더하던 `<p>`를 제거했다.
- 렌더 테스트에 해당 집계 문구가 출력되지 않는 회귀 assertion을 추가했다.

## 검증

- `uv run pytest tests/test_document_type_navigation.py`: 통과.

## 남은 리스크와 후속 작업

- 문서 유형별 집계 값은 서버 context에는 계속 존재하지만 화면에는 표시하지 않는다.
- 작업 시작 전부터 존재한 다른 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 남겨 둔다.

---

# 2026-08-13 - Documents 탭 화면 고정 레이아웃

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Documents UI, attachment document type navigation |
| 관련 파일 | `app/static/app.css`, `app/templates/shell.html`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Documents 탭에서 탭 화면 스크롤이 생기지 않도록 모든 영역이 한 화면 안에 들어오고 항상 화면이 고정되게 영역 크기를 조정해 달라고 요청했다.

## 해결 방법

- Documents 뷰 진입 시 `documents-viewport-locked` body 클래스를 적용해 content, view, card grid의 외부 스크롤을 막았다.
- 카드 개수와 그리드 가용 높이를 기준으로 카드 높이를 계산하는 `syncDocumentsViewportLayout()`을 추가해 데스크톱과 모바일에서 카드 하단이 뷰포트 안에 들어오게 했다.
- 고정 화면에서 카드 내부 정보가 겹치지 않도록 Documents 카드 행을 제목 중심의 압축 목록으로 정리하고, 모바일에서는 보이는 행 수를 제한했다.

## 검증

- `uv run pytest tests/test_document_type_navigation.py`: 통과.
- Playwright로 `http://127.0.0.1:8012/ui/documents`를 1440x900, 390x844에서 확인했다. 두 뷰포트 모두 `body`, `.content`, `.document-types-view`, `.document-type-card-grid`의 overflow가 hidden이고 `gridScrollHeight == gridClientHeight`, 카드 하단이 뷰포트 안에 있음을 확인했다.
- Browser 플러그인은 제공되지 않아 일반 Playwright를 사용했다. 첫 Playwright 실행은 Chromium sandbox 권한 오류로 실패했고, 승인된 외부 실행으로 재검증했다.

## 남은 리스크와 후속 작업

- 화면 고정 조건 때문에 모바일에서는 각 문서 유형 카드의 미리보기 행을 최대 4개만 보이게 한다. 카드 클릭으로 기존 Inbox 상세 이동은 유지된다.
- 작업 시작 전부터 존재한 다른 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 남겨 둔다.

---

# 2026-08-13 - Mail Decision 업무번호 단일 표시 강제

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo Mail Decision display |
| 관련 파일 | `app/templates/partials/mail_decision_panel.html`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 업무번호 중복 제거 후에도 Mail Decision 화면에 중복이 남아 있다고 보고했고, 시연을 위해 즉시 제거를 요청했다.

## 해결 방법

- Mail Decision 패널 템플릿에서 업무번호 목록을 join하지 않고 첫 번째 업무번호만 렌더하도록 강제했다.
- Docker web 컨테이너를 재시작해 시연 서버에 반영했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py::test_mail_decision_panel_deduplicates_business_refs_for_display -q`: 통과.

## 남은 리스크와 후속 작업

- 화면 표시만 단일화하며 저장 데이터는 변경하지 않는다.

---

# 2026-08-13 - Mail Decision 업무번호 중복 표시 제거

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo Mail Decision display |
| 관련 파일 | `app/server.py`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Mail Decision 패널의 업무번호가 같은 값 2개로 중복 표시되므로 하나만 남겨 달라고 요청했다.

## 해결 방법

- Mail Decision 표시 payload를 만들 때 `summary.business_refs`를 순서 보존 방식으로 중복 제거하게 했다.
- 중복 업무번호가 한 번만 렌더되는 UI 회귀 테스트를 추가했다.
- Docker web 컨테이너를 재시작해 실행 중인 시연 서버에 반영했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py::test_mail_decision_panel_deduplicates_business_refs_for_display -q`: 통과.

## 남은 리스크와 후속 작업

- 저장 데이터 자체는 유지하고 화면 표시만 중복 제거한다.
- 작업 시작 전부터 존재한 다른 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 남겨 둔다.

---

# 2026-08-13 - Inbox 탭 500 복구

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox UI, summary display |
| 관련 파일 | `app/server.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Inbox 탭 클릭 시 `화면을 불러오지 못했습니다: HTTP 500`으로 화면이 보이지 않는다고 보고했고, 시연 스크린샷을 위해 즉시 복구를 요청했다.

## 해결 방법

- 최신 서버 로그에서 `partials/email_detail.html`의 `polish_summary`가 undefined라서 Inbox include 렌더링이 실패하는 것을 확인했다.
- `polish_summary`를 개별 context에만 넣지 않고 Jinja 전역 함수로 등록해 Inbox, email detail partial, shell include 어디서든 사용할 수 있게 했다.
- Docker web 컨테이너를 재시작해 실행 중인 8000 서버에 반영했다.

## 검증

- `uv run python`으로 `ui_inbox` 직접 렌더링이 `200`과 `Inbox Queue`를 반환하는 것을 확인했다.
- `uv run pytest tests/test_mail_decision_ui.py -k "inbox or polishes_demo_summary" -q`: 5 passed.
- 인증 쿠키로 `curl -v -b /tmp/coramail_cookie.txt -H 'HX-Request: true' http://127.0.0.1:8000/ui/inbox` 호출 시 `HTTP/1.1 200 OK`와 Inbox HTML을 확인했다.

## 남은 리스크와 후속 작업

- 작업 시작 전부터 존재한 다른 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 남겨 둔다.

---

# 2026-08-13 - 데모 스크린샷용 Mail Decision 표시 정리

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo Mail Decision, attachment analysis display, summary display |
| 관련 파일 | `app/server.py`, `app/templates/partials/mail_decision_panel.html`, `app/templates/partials/email_detail.html`, `app/presentation/attachment_analysis.py`, `app/presentation/summary_text.py`, `tests/test_mail_decision_ui.py`, `tests/test_decision_agent.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 `[견적서 송부] 산업용 네트워크 장비 및 전원모듈` 메일의 시연 스크린샷을 준비 중이며, Mail Decision 거래처가 `견적서 송부`로 보이는 문제를 `다원`으로 대체해 달라고 요청했다.
- 같은 화면에서 `검토 상태 - 판단되지 않음`과 담당 후보 우측 `%` 점수 표시를 숨겨 달라고 요청했다.
- 첨부파일 분석 결과의 `To`, `Date`, `Our Ref No`, `Total Price` 라벨을 각각 `거래처`, `날짜`, `거래처측 업무번호`, `총액`으로 표시해 달라고 요청했다.
- Summary의 업무번호 반복과 핵심 요청 앞의 `견적서 송부` 접두를 제거해 달라고 요청했다.

## 해결 방법

- 데모 스크린샷 대상 견적 메일의 Mail Decision 거래처 표시 보정값을 `다원`으로 바꿨다.
- 데모 모드 Mail Decision 패널에서 검토 상태 행을 숨기는 `hide_review_reason` 플래그를 추가했다. 기존 담당 후보 `%` 숨김은 유지했다.
- 첨부 분석 필드 라벨 표시 필터를 추가해 저장 필드명은 유지하면서 화면 라벨만 한국어로 바꿨다.
- Summary polish 함수에 반복 업무번호 제거와 `견적서 송부` 접두 제거 규칙을 추가하고, 이메일 상세 핵심 요청 표시에도 적용했다.

## 검증

- `uv run python -m py_compile app/server.py app/presentation/summary_text.py app/presentation/attachment_analysis.py tests/test_mail_decision_ui.py tests/test_decision_agent.py`: 통과.
- `uv run pytest tests/test_mail_decision_ui.py -k "attachment_details_for_business or polishes_demo_summary or demo_mail_decision_panel or replaces_demo_quotation or replaces_demo_subject" tests/test_decision_agent.py::test_summary_polish_removes_demo_quotation_prefix_and_repeated_business_ref -q`: 6 passed.

## 남은 리스크와 후속 작업

- 이번 변경은 시연용 표시 보정이다. 운영 데이터의 거래처/요약 정합성은 Mail Decision Run 재실행 및 fact extraction 품질로 별도 검증해야 한다.
- 작업 시작 전부터 존재한 다른 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 남겨 둔다.

---

# 2026-08-13 - 데모 Search 예시 업무번호 교체

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo Search UI, data security |
| 관련 파일 | `app/templates/views/search.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 데모 모드 Search 탭의 예시 질문에 포함된 `FM` 업무번호가 플루맥스 기업을 나타내므로 데이터 보안 위반 가능성이 있어 다른 업무번호로 대체해 달라고 요청했다.

## 해결 방법

- Search 탭 입력 placeholder의 예시를 `FM250016318 견적서의 납기와 총액`에서 중립적인 데모 견적번호 `QT-2026-0812-03 견적서의 납기와 총액`으로 교체했다.
- 해당 placeholder를 검증하는 UI 테스트 기대값도 함께 갱신했다.
- 검색 서비스 내부 회귀 테스트의 `FM` fixture는 사용자에게 보이는 데모 예시가 아니라 검색 동작 검증용 데이터이므로 이번 변경 범위에서 건드리지 않았다.

## 검증

- `pytest tests/test_mail_decision_ui.py::test_search_view_has_no_fake_prefilled_query`: 로컬 PATH에 `pytest` 실행 파일이 없어 실패했다.
- `uv run pytest tests/test_mail_decision_ui.py::test_search_view_has_no_fake_prefilled_query -q`: 통과.

## 남은 리스크와 후속 작업

- 작업 시작 전부터 존재한 다른 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 남겨 둔다.

---

# 2026-08-13 - 데모 Mail Decision 재보정과 후보 점수 숨김

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo Mail Decision, routing candidate display |
| 관련 파일 | `app/server.py`, `app/templates/partials/mail_decision_panel.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 이전 거래처 보정 후에도 데모 Mail Decision 화면이 그대로 `견적서 송부`를 표시한다고 보고했다.
- 추가로 시연 스크린샷을 위해 Mail Decision 담당 후보의 `%` 점수 표시를 숨겨 달라고 요청했다.

## 해결 방법

- 기존 보정은 `current_email.classification.counterparty`가 있을 때만 동작했으나, 실제 PostgreSQL 데모 상세 경로에서는 해당 값이 비어 있을 수 있었다.
- 데모 견적 메일의 고정 UID 또는 제목이 확인되고 `customer_name`이 비거래처 제목 라벨이면, 표시값을 `미래산업기술`로 직접 보정하게 했다.
- 데모 모드 Mail Decision 패널에 `hide_candidate_scores` 플래그를 추가하고, 담당 후보의 점수 배지를 렌더하지 않게 했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py::test_mail_decision_panel_replaces_demo_subject_label_customer_with_counterparty tests/test_mail_decision_ui.py::test_mail_decision_panel_replaces_demo_quotation_subject_label_without_counterparty tests/test_mail_decision_ui.py::test_demo_mail_decision_panel_hides_candidate_score_percent_for_screenshots tests/test_vision_fact_extraction.py -q`: 통과.

## 남은 리스크와 후속 작업

- 실행 중인 개발 서버가 자동 reload를 못 했다면 서버 재시작 후 화면에 반영된다.
- 작업 시작 전부터 존재한 다른 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 남겨 둔다.

---

# 2026-08-13 - 데모 Mail Decision 거래처 표시 보정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo Mail Decision, fact extraction, Mail Decision panel |
| 관련 파일 | `app/mail_content.py`, `app/agents/fact_extraction_agent.py`, `app/server.py`, `tests/test_vision_fact_extraction.py`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 데모 모드의 `[견적서 송부] 산업용 네트워크 장비 및 전원모듈` Mail Decision에서 거래처가 `견적서 송부`로 표시되는 오답을, 시연 스크린샷을 위해 정답으로 표시되게 바꿔 달라고 요청했다.

## 해결 방법

- 제목 대괄호 라벨 `견적서 송부`를 거래처 후보에서 제외하는 비거래처 라벨로 추가했다.
- LLM fallback/grounded fact extraction에서 본문 한 줄의 `미래산업기술 박서진입니다`처럼 발신자 이름 앞 회사명이 명시된 경우 이를 거래처 후보로 사용하게 했다.
- 이미 저장된 데모 Mail Decision Run에 `customer_name: 견적서 송부`가 남아 있어도, 현재 메일 fixture classification의 `counterparty`가 있으면 Mail Decision 패널 표시값을 `미래산업기술`로 보정한다.

## 검증

- `uv run pytest tests/test_vision_fact_extraction.py tests/test_mail_decision_ui.py::test_mail_decision_panel_replaces_demo_subject_label_customer_with_counterparty -q`: 통과.

## 남은 리스크와 후속 작업

- 표시 보정은 데모 fixture의 `counterparty`에 근거한 시연용 보정이다. 운영 데이터의 거래처 정합성은 Mail Decision Run 재실행과 fact extraction 품질 개선으로 별도 검증해야 한다.
- 작업 시작 전부터 존재한 다른 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 남겨 둔다.

---

# 2026-08-13 - Routing Overview 5명 기준 높이 조정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard Routing Overview |
| 관련 파일 | `app/static/app.css`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 현재 Routing Overview 화면 상태는 원하는 대로이며, 담당자 6명 정도가 보이던 고정 높이를 5명 정도가 보이는 높이로만 낮춰 달라고 요청했다.

## 해결 방법

- Routing Overview scope/workload 고정 슬롯 높이를 `226px`에서 `188px`로 낮췄다.
- Today/All 전환 시 동일 슬롯 높이를 유지하는 기존 구조와 scrollbar gutter 제거 방식은 그대로 유지했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "routing_overview" -q`: 통과.

## 남은 리스크와 후속 작업

- 작업 시작 전부터 존재한 다른 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 남겨 둔다.

---

# 2026-08-13 - Routing Overview 고정 영역과 총계 겹침 보정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard Routing Overview, scroll behavior |
| 관련 파일 | `app/static/app.css`, `app/templates/shell.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 스크롤바 커스텀 구현을 스크롤 변경 요청 전 상태로 복구해 달라고 요청했다.
- Routing Overview 영역 크기는 고정되어야 하며, 담당자 수 때문에 카드 크기가 커지면 안 된다고 지적했다.
- 기존처럼 약 6명 정도는 보여야 하고, `총 N건` 영역이 마지막 담당자 그래프와 겹치면 안 된다.

## 해결 방법

- `.scroll-managed`, `.floating-scrollbar`, `installTransientScrollbars()` 등 커스텀 scrollbar 구현을 제거했다.
- DOMContentLoaded, HTMX swap, resize에 연결했던 scrollbar 재스캔 로직도 제거했다.
- Routing Overview workload는 Today/All 전환 시에도 동일한 226px 슬롯을 유지하게 해 영역 박스 크기가 바뀌지 않도록 했다.
- 해당 슬롯 안에서 약 6명까지 보이고, 초과분만 내부 스크롤되게 했다.
- native scrollbar gutter가 그래프 폭을 밀거나 빈 공간을 만들지 않도록 Routing Overview workload scrollbar를 숨기고 wheel/trackpad 스크롤만 유지했다.
- `총 N건`은 absolute positioning에서 normal flow로 옮겨 담당자 그래프와 겹치지 않게 했다.

## 검증

- `python -m py_compile app/server.py`: 통과.
- `uv run pytest tests/test_mail_decision_ui.py -k "routing_overview or dashboard_summary or demo_dashboard_context or inbox_initial_queue" -q`: 6 passed.
- `scroll-managed`, `floating-scrollbar`, `installTransientScrollbars` 잔여 문자열이 없음을 확인했다.
- demo context에서 Routing Overview All workload 담당자 7명이 모두 렌더되는 것을 확인했다.

## 남은 리스크와 후속 작업

- 이번 변경은 Routing Overview 영역의 고정 크기와 겹침 방지에 집중했다.
- 작업 시작 전부터 존재한 다른 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 남겨 둔다.

---

# 2026-08-13 - Routing Overview 소량 담당자 막대 표시 보정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode Dashboard, Routing Overview workload bars |
| 관련 파일 | `app/server.py`, `app/templates/partials/dashboard_routing_overview.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 1건만 배정된 담당자의 Routing Overview 보라색 막대가 보이지 않는다고 보고했다.
- 데모 데이터 기준 stats와 상태가 일관되더라도, 소량 담당자가 시각적으로 사라지면 결과를 신뢰하기 어렵다.

## 확인된 원인

- 담당자 막대 width는 `round(count / max_count * 100)`로 계산된다.
- 데모 데이터에서 1건 담당자는 `round(1 / 542 * 100) = 0`이 되어 CSS width가 `0%`로 렌더링됐다.

## 해결 방법

- 원래 비율값 `bar_percent`는 그대로 유지하고, 표시용 `bar_display_percent`를 추가했다.
- 1건 이상인 담당자는 최소 2% width를 갖도록 해 작은 건수도 막대가 보이게 했다.
- 템플릿은 `bar_display_percent`를 우선 사용하고 없으면 기존 `bar_percent`로 fallback한다.

## 검증

- `python -m py_compile app/server.py`: 통과.
- `uv run pytest tests/test_mail_decision_ui.py -k "routing_overview" -q`: 2 passed.
- demo mode 계산에서 `정우석 1건`은 `bar_percent=0`, `bar_display_percent=2`로 확인했다.
- `docker compose restart web`: 완료.

## 남은 리스크와 후속 작업

- 표시용 최소폭은 시각 가독성 보정이며 실제 count와 원래 비율값은 바꾸지 않는다.
- 작업 시작 전부터 존재한 다른 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 남겨 둔다.

---

# 2026-08-13 - Routing Overview 담당자 표시 일관성 보정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode Dashboard, Mail Streams, Routing Overview |
| 관련 파일 | `app/server.py`, `app/templates/partials/dashboard_routing_overview.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 데모 데이터 자체의 사실성보다 데모 데이터 기준 상태와 stats의 일관성이 중요하다고 지적했다.
- Mail Streams에는 배정된 담당자가 보이는데 Routing Overview에는 일부 담당자가 나타나지 않아 overview 결과를 신뢰할 수 없다고 보고했다.

## 확인된 원인

- PostgreSQL demo seed와 서버 row 기준으로는 synthetic 메일 1,210건 모두 담당자와 `forwarded` 상태가 있다.
- 서버 `routing_overview()`도 담당자 7명 분포를 만들고 있었지만, `dashboard_routing_overview.html`에서 `workload_assignees[:4]`로 렌더링을 4명으로 제한해 나머지 담당자가 화면에서 사라졌다.

## 해결 방법

- Routing Overview가 담당자별 workload row를 자르지 않고 모두 렌더링하게 했다.
- 담당자 분포는 건수 내림차순, 동률 이름순으로 정렬해 표시 순서를 안정화했다.
- Mail Streams에 보이는 담당자가 Routing Overview HTML에도 모두 포함되는 회귀 테스트를 추가했다.

## 검증

- `python -m py_compile app/server.py`: 통과.
- `uv run pytest tests/test_mail_decision_ui.py -k "routing_overview or dashboard_summary or demo_dashboard_context or demo_dashboard_stats" -q`: 4 passed.
- demo mode 서버 계산 확인: Mail Streams 담당자 분포와 Routing Overview 담당자 분포가 모두 `김민수 542`, `박지현 182`, `최서연 181`, `이준호 122`, `강태훈 121`, `최유진 61`, `정우석 1`로 일치한다.
- 실제 Routing Overview partial 렌더에서 7명 모두 포함됨을 확인했다.

## 남은 리스크와 후속 작업

- 이번 변경은 Routing Overview 표시 일관성만 보정했다.
- 작업 시작 전부터 존재한 다른 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 남겨 둔다.

---

# 2026-08-13 - Demo mode 메일 전건 전달 완료 처리

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode seed data, Dashboard Forwarded stats |
| 관련 파일 | `app/services/demo_seed_service.py`, `app/repositories/postgres_seed_writer.py`, `tests/test_demo_seed_service.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 데모모드에 있는 메일을 모두 전달 완료 상태로 만들고, 관련 stats에도 같은 상태가 반영되길 요청했다.
- Dashboard `Forwarded` stats는 mail row의 `work_status`, `routing_status`, `forwarded_at` 계열 필드를 기준으로 계산된다.

## 해결 방법

- demo seed의 모든 `routing_assignments.status`를 `forwarded`로 생성하고 각 row에 `forwarded_at`을 채우게 했다.
- 기존 PostgreSQL demo DB 재적재 시 과거 `assigned` 상태가 남지 않도록, `assignment_source = demo_fixture`인 routing assignment는 seed 재적재 때 상태와 전달 시각을 갱신하게 했다.
- seed bundle 회귀 테스트가 모든 demo routing assignment의 `forwarded` 상태와 `forwarded_at` 존재를 검증하게 했다.

## 검증

- `python -m py_compile app/services/demo_seed_service.py app/repositories/postgres_seed_writer.py app/server.py`: 통과.
- `uv run pytest tests/test_demo_seed_service.py -q`: 7 passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "dashboard_summary or demo_dashboard_stats or demo_dashboard_context" -q`: 3 passed.
- `uv run python -m app.tools.load_demo_seed_postgres --database-url postgresql://coramail:coramail@127.0.0.1:5432/coramail`: validated `email_messages=1210`, `routing_assignments=1210`.
- PostgreSQL synthetic provider 기준 `routing_assignments`는 `forwarded=1210`이고, demo dashboard summary 계산은 `total=1210`, `forwarded=1210`, `unforwarded=0`이다.

## 남은 리스크와 후속 작업

- Gmail provider의 실제/동기화 메일 라우팅 상태는 변경하지 않았다.
- 작업 시작 전부터 존재한 다른 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 남겨 둔다.

---

# 2026-08-13 - Demo Dashboard 일별 유입량과 카테고리 비중 조정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode seed data, Dashboard Daily Inflow, Category Distribution |
| 관련 파일 | `app/services/demo_seed_service.py`, `app/repositories/postgres_seed_writer.py`, `data/demo/README.md`, `tests/test_demo_seed_service.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Daily Inflow가 우측으로 갈수록 계속 증가해 부자연스럽다고 보고했다.
- 메일 비중은 `발주`와 `문의` 합계가 대략 60% 언저리가 되길 요청했다.

## 해결 방법

- 총 1,210건 스케일은 유지하되 7일 유입량을 168, 142, 196, 151, 184, 207, 162건으로 조정했다.
- bulk scenario 순서를 20건 주기로 조정해 `발주`와 `문의` 합계가 전체 59.8%가 되게 했다.
- bulk count가 줄어든 날짜의 이전 demo-volume 메일이 DB에 남지 않도록 seed writer가 현재 seed에 없는 synthetic message를 삭제한 뒤 upsert하게 했다.

## 검증

- `python -m py_compile app/services/demo_seed_service.py app/repositories/postgres_seed_writer.py`: 통과.
- `uv run pytest tests/test_demo_seed_service.py -q`: 7 passed.
- `docker compose restart web`: bootstrap demo seed 재적재 완료.
- PostgreSQL synthetic message 수는 1,210건이고 일별 분포는 2026-08-06 168건, 08-07 142건, 08-08 196건, 08-09 151건, 08-10 184건, 08-11 207건, 08-12 162건이다.
- Category Distribution 기준 `문의` 362건, `발주` 362건, `서비스` 183건, `기술` 183건, `기타` 120건으로 `발주+문의`는 59.8%다.

## 남은 리스크와 후속 작업

- 이번 변경은 demo synthetic seed에만 적용했다.
- 커밋과 푸시는 수행하지 않았다.

---

# 2026-08-13 - Demo Dashboard Routing Overview 스타일 정리

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode Dashboard, Routing Overview, Dashboard scope toggle styling |
| 관련 파일 | `app/templates/partials/dashboard_distribution.html`, `app/templates/partials/dashboard_routing_overview.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Routing Overview의 `Assigned`/`Unassigned` 박스 영역을 제거하고, `Today`/`All` 토글 아래에 현재 범위 총 건수를 표시해 달라고 요청했다.
- 담당자별 그래프 막대와 Dashboard scope toggle 색상을 전체 시스템 스타일과 일관되게 정리해야 했다.

## 해결 방법

- Routing Overview에서 Assigned/Unassigned metric card 렌더링을 제거했다.
- 우측 scope control 아래에 `총 N건`을 표시하고, 토글 전환 시 JS가 현재 scope의 총 건수로 갱신하게 했다.
- 담당자 workload bar는 기존 파란-초록 그라데이션을 제거하고 전역 `--secondary` 색상과 `--surface-mid` track을 사용하게 했다.
- `Today`/`All` 토글은 배경 박스 없이 전역 `--muted`/`--secondary` 색상과 underline active state를 사용하도록 정리했다.

## 검증

- `python -m py_compile app/server.py`: 통과.
- `uv run pytest tests/test_mail_decision_ui.py -k 'dashboard_summary or demo_dashboard_context or demo_dashboard_stats or category_timeline'`: 4 passed.
- Demo partial 렌더 확인: `routing-overview-metric`, `Assigned`, `Unassigned`가 제거됐고 `총 248건`, today/all total data가 렌더된다.
- Chromium 렌더 검증에서 `/ui/dashboard` demo mode 진입 후 Routing Overview `Today -> All` 토글 클릭을 확인했다. 총계는 `총 248건`에서 `총 1210건`으로 전환됐다.
- `docker compose restart web`: 완료.

## 남은 리스크와 후속 작업

- Browser 플러그인은 사용할 수 없어 Node Playwright로 검증했다.
- 커밋과 푸시는 수행하지 않았다.

---

# 2026-08-13 - Demo Dashboard Today/All 토글과 요망 건수 표시

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode Dashboard stats, Category Distribution, Routing Overview |
| 관련 파일 | `app/server.py`, `app/templates/partials/stats.html`, `app/templates/partials/dashboard_distribution.html`, `app/templates/partials/dashboard_routing_overview.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Dashboard 탭의 카드 제목은 유지하면서 `Classified`, `Routed`, `Forwarded`의 하단 문구를 완료 건수가 아니라 요망 건수로 바꾸길 요청했다.
- `Category Distribution`과 `Routing Overview`는 데모 화면에서 기본 Today 기준으로 보이고, 우측 상단 텍스트 토글로 Today/All 전환이 가능해야 했다.

## 해결 방법

- `dashboard_summary()`에 미분류, 미배정, 미전달 건수를 추가하고 stats 보조 문구에 표시했다.
- Demo mode `dashboard_context()`에서 오늘 수신 메일 기준 summary/routing과 전체 기준 summary/routing을 함께 전달한다.
- `Category Distribution`은 기본 Today 차트와 목록을 렌더하고, `Today`/`All` 토글 클릭 시 Chart.js 데이터와 목록을 전환한다.
- `Routing Overview`는 같은 토글로 Today/All metrics와 workload 패널을 전환한다.
- Gmail mode는 기존 단일 전체 데이터 context를 유지하고 토글을 렌더하지 않는다.

## 검증

- `python -m py_compile app/server.py`: 통과.
- `uv run pytest tests/test_mail_decision_ui.py -k 'dashboard_summary or demo_dashboard_context or demo_dashboard_stats or category_timeline'`: 4 passed.
- Demo context 계산값: stats total 1,210, today 248, 분류 요망 0, 배정 요망 0, 전달 요망 487, distribution today 248/all 1,210, routing today 248/all 1,210.
- Chromium 렌더 검증에서 로그인 후 demo cookie로 `/ui/dashboard`를 열고 `Today -> All` 토글을 클릭했다. Distribution 총계는 248건에서 1,210건으로 전환됐고 Routing Overview도 All 패널이 표시됐다.
- `docker compose restart web`: 완료.

## 남은 리스크와 후속 작업

- Browser 플러그인은 사용할 수 없어 Node Playwright로 검증했다.
- 커밋과 푸시는 수행하지 않았다.

---

# 2026-08-13 - 데모 스크린샷용 Documents 탭 임시 숨김

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode main navigation |
| 관련 파일 | `app/templates/shell.html`, `tests/test_document_type_navigation.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 데모 모드에서 시연용 스크린샷을 찍기 위해 `Documents` 탭을 잠시 숨겨 달라고 요청했다.
- 요청 시 바로 복구할 수 있어야 한다.

## 해결 방법

- `shell.html`에 `hide_documents_nav_for_demo_screenshot` 임시 플래그를 두고, 기본값을 `demo_mode`로 연결했다.
- 데모 모드에서는 사이드바의 `Documents` 버튼만 렌더링하지 않는다.
- `/ui/documents` 라우트, Documents 화면 템플릿, 기존 JS title/state mapping은 유지해 복구와 직접 접근 영향을 최소화했다.
- 복구 시 `hide_documents_nav_for_demo_screenshot` 값을 `false`로 바꾸거나 해당 조건문만 제거하면 된다.

## 검증

- `uv run pytest tests/test_document_type_navigation.py -q`: 6 passed.

## 남은 리스크와 후속 작업

- 이 변경은 스크린샷용 임시 UI 조정이다. 데모 후 Documents 탭 노출이 다시 필요하면 위 플래그 조건을 되돌린다.
- 작업 시작 전부터 존재한 여러 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 남겨 둔다.

---

# 2026-08-13 - Search 답변 확인 멘트 제거

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search answer style |
| 관련 파일 | `app/services/mail_search_service.py`, `tests/test_mail_search_service.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Search 답변이 `견적서 총액은 5,346,000원입니다. 확인했습니다.`처럼 뒤에 불필요한 확인 멘트를 붙인다고 보고했다.
- 원하는 답변은 확인 멘트 없이 앞의 업무 답변 문장만 한 번에 나오는 형태다.

## 해결 방법

- 검색 답변 프롬프트에서 `확인했습니다` 같은 확인 filler를 붙이지 말라고 명시했다.
- LLM 답변의 앞뒤 `확인했습니다.`를 후처리에서 제거하게 했다.
- 납기·총액 필드 질의는 `납기는 ...이고, 총액은 ...입니다.` 구조를 우선 사용하게 해 `납기 총액은 ...` 같은 어색한 문장을 피했다.

## 검증

- `uv run pytest tests/test_mail_search_service.py -q`: 17 passed.
- `python -m py_compile app/services/mail_search_service.py`: passed.
- 실제 Demo 검색 `QT-2026-0812-03 납기 총액` 결과가 `QT-2026-0812-03 기준으로 납기는 발주 후 14일 이내이고, 총액은 5,346,000원입니다.`로 나오는 것을 확인했다.

## 남은 리스크와 후속 작업

- 현재 후처리는 납기·총액 중심이다. 다른 필드에서도 같은 톤 문제가 반복되면 필드별 문장 생성 규칙을 확장한다.
- 작업 시작 전부터 존재한 여러 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 남겨 둔다.

---

# 2026-08-13 - Search 결과 화면과 챗봇 답변 톤 보정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search tab result rendering, mailbox RAG answer style |
| 관련 파일 | `app/server.py`, `app/templates/views/search.html`, `app/templates/shell.html`, `app/services/mail_search_service.py`, `tests/test_mail_decision_ui.py`, `tests/test_mail_search_service.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Demo Search 결과가 Gmail 모드처럼 같은 화면 구조로 나와야 하며, 깨진 partial 화면이 보이면 안 된다고 재요청했다.
- 이후 결과 화면은 맞지만 답변이 `5,346,000원`처럼 값 조각만 나와 챗봇 답변 스타일로 보이게 해 달라고 요청했다.

## 원인

- `/ui/search-results`는 partial 전용 endpoint인데 non-HTMX 기본 제출이나 직접 접근에서 partial HTML이 단독으로 열릴 수 있었다.
- 검색 답변 LLM은 근거 값은 찾았지만 문장 형식이 지나치게 짧거나, 필드 질의에서 요청한 납기·총액 대신 일반 요청사항 요약을 반환할 수 있었다.

## 해결 방법

- Search form의 기본 `action`을 full page route인 `/ui/search`로 바꾸고, HTMX와 JS fallback만 `/ui/search-results` partial을 호출하게 했다.
- `/ui/search`가 `q`와 `limit` query를 받아 전체 Search 화면 안에서 결과를 렌더하게 했다.
- `/ui/search-results`에 일반 요청이 들어오면 `/ui/search?q=...`로 redirect해 깨진 partial 화면을 차단했다.
- 검색 답변 프롬프트에 값만 답하지 말고 완전한 한국어 업무 챗봇 문장으로 답하라는 지침을 추가했다.
- LLM 답변이 값 조각이거나 요청한 필드 값을 누락하면 선택된 근거 preview에서 납기·총액 값을 추출해 `확인했습니다. <업무번호> 기준으로 납기는 ...이고, 총액은 ...입니다.` 형태로 보정한다.

## 검증

- `uv run pytest tests/test_mail_search_service.py -q`: 16 passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "search" -q`: 6 passed.
- `python -m py_compile app/server.py app/services/mail_search_service.py`: passed.
- 실제 Demo 검색 `QT-2026-0812-03 납기 총액` 결과가 `확인했습니다. QT-2026-0812-03 기준으로 납기는 발주 후 14일 이내이고, 총액은 5,346,000원입니다.`로 나오는 것을 확인했다.

## 남은 리스크와 후속 작업

- 현재 챗봇 톤 보정은 납기·총액 등 명확한 필드 질의를 우선 대상으로 한다. 향후 품번, 수량, 유효기간 같은 필드도 같은 방식으로 확장할 수 있다.
- 작업 시작 전부터 존재한 여러 코드·데이터 변경과 `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 남겨 둔다.

---

# 2026-08-13 - Search 제출 새로고침 fallback 복구

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search tab, HTMX CDN fallback, demo search form submit |
| 관련 파일 | `app/templates/views/search.html`, `app/templates/shell.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 데모 Search 탭에서 질문 후 검색을 누르면 검색이 실행되지 않고 페이지가 새로고침된다고 보고했다.
- 이전 변경은 검색 근거 데이터만 보강했지만, 실제 증상은 form submit이 HTMX에 의해 가로채지지 않는 프론트엔드 동작 문제였다.

## 원인

- Search form은 `hx-get="/ui/search-results"`에만 의존하고 `action`과 `method`가 없었다.
- shell은 HTMX CDN이 실패할 때 navigation 버튼만 fetch fallback으로 처리했지만, Search form에는 fallback이 없었다.
- 따라서 HTMX가 로드되지 않거나 처리되지 않는 환경에서는 브라우저 기본 submit이 현재 `/ui/search` 페이지를 query string과 함께 다시 열어 새로고침처럼 보였다.

## 해결 방법

- Search form에 표준 `action="/ui/search-results"`와 `method="get"`를 추가했다.
- HTMX가 없을 때 shell이 `form.search-box` submit을 직접 가로채 `/ui/search-results`를 `HX-Request` 헤더로 fetch하고 `#search-results`만 교체하게 했다.
- HTMX가 정상 로드된 경우에는 기존 HTMX 처리에 맡기도록 fallback을 비활성화했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "search" -q`: 5 passed.
- `python -m py_compile app/server.py app/services/demo_mail_service.py`: passed.
- Playwright Chromium에서 HTMX CDN 요청을 강제 차단하고 Search 제출을 실행해 URL이 `/ui/search`로 유지되고 `/ui/search-results` 응답이 `#search-results`에 렌더링되는 것을 확인했다.

## 남은 리스크와 후속 작업

- 현재 fallback은 Search form 전용이다. 다른 HTMX form에서 같은 문제가 나오면 동일한 방식의 local fallback 또는 HTMX vendoring을 검토해야 한다.
- 작업 시작 전부터 존재한 여러 코드·데이터·세션 로그 변경과 `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 남겨 둔다.

---

# 2026-08-13 - Demo Dashboard 업무 메일 수신량 스케일 확대

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode, Dashboard scale, synthetic bulk seed |
| 관련 파일 | `app/services/demo_seed_service.py`, `data/demo/README.md`, `tests/test_demo_seed_service.py` |

## 요청 또는 배경

- 사용자는 최종 서비스가 하루 수백 건 업무 메일 수신을 대상으로 하므로, demo dashboard의 stats와 그래프도 실제 서비스처럼 더 큰 스케일을 보여주길 요청했다.
- 후속으로 시연 스크린샷 기준으로 각 영역 숫자가 모순되지 않으면 된다고 명시했다.

## 해결 방법

- 기존 상세 시연 메일과 curated list rows는 유지하고, seed 단계에서 deterministic synthetic bulk 메일을 추가 생성하게 했다.
- 총 demo 메일 수는 1,210건으로 확장했다.
- Daily Inflow는 7일 합계가 Total Mails와 일치하게 했다: 08-06 110건, 08-07 132건, 08-08 152건, 08-09 166건, 08-10 188건, 08-11 214건, 08-12 248건.
- 첫 상세 시연 메일 `[견적서 송부] 산업용 네트워크 장비 및 전원모듈`은 08-12 09:24로 유지해 index 0을 보존했다.
- bulk 메일은 첨부 없이 생성해 synthetic attachment는 기존 견적서 1건만 유지했다.
- bulk routing assignments 일부를 `forwarded`로 생성해 Dashboard Forwarded 수치도 업무 진행량처럼 보이게 했다.

## 검증

- `uv run pytest tests/test_demo_seed_service.py tests/test_mail_decision_ui.py -k 'demo_seed_bundle or demo_dashboard_stats or category_timeline or inbox_initial_queue'`: 4 passed.
- `python -m py_compile app/services/demo_seed_service.py app/server.py`: 통과.
- seed bundle 검증 결과: `email_messages=1210`, `email_attachments=1`, `routing_assignments=1210`, `forwarded=722`.
- `uv run python -m app.tools.load_demo_seed_postgres --database-url postgresql://coramail:coramail@127.0.0.1:5432/coramail`: validated `email_messages=1210`, `email_attachments=1`, `routing_assignments=1210`.
- DB 기준 synthetic provider는 1,210건, attachment sum은 1건이고 Gmail provider와 분리되어 있다.
- Demo dashboard 계산 결과: Total 1,210, Today 248, Classified 1,210, Routed 1,210, Forwarded 723, Category total 1,210, Daily Inflow total 1,210, Routing total 1,210.
- `docker compose restart web`: 완료했고 bootstrap 로그에서 동일 seed count 재적재를 확인했다.

## 남은 리스크와 후속 작업

- Inbox도 같은 rows를 사용하므로 현재는 1,210건을 렌더한다. 시연 중 Inbox 성능이나 스크롤 부담이 크면 별도 pagination 또는 Dashboard-only aggregation layer가 필요하다.
- 커밋과 푸시는 수행하지 않았다.

---

# 2026-08-13 - Demo Dashboard 통계와 그래프 일관성 보정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode, Dashboard stats, category distribution, daily inflow, routing overview |
| 관련 파일 | `app/server.py`, `data/demo/mail_list_samples.fixture.json`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 demo 데이터로 Dashboard stats와 그래프를 더 그럴싸하게 만들되, 각 영역의 숫자가 서로 모순되지 않아야 한다고 요청했다.
- 첫 상세 시연 메일은 index 0으로 유지해야 하므로, 그 메일보다 최신 시각의 목록용 메일을 추가하거나 날짜를 올릴 수 없었다.

## 해결 방법

- Demo mode Dashboard에서만 기준일을 실제 현재일이 아니라 demo 데이터의 최신 수신일로 잡게 했다.
- `Today Mails`와 `Daily Inflow`가 같은 기준일을 사용하므로, 최신 demo 날짜의 유입 수가 stats와 그래프 마지막 막대에서 일치한다.
- 목록용 synthetic 메일 날짜를 7일 범위에 분산했다: 08-06 1건, 08-07 1건, 08-08 2건, 08-09 1건, 08-10 1건, 08-11 2건, 08-12 4건.
- 기존 첫 상세 메일 `[견적서 송부] 산업용 네트워크 장비 및 전원모듈`은 최신 08-12 09:24로 유지해 index 0을 보존했다.

## 검증

- `python -m json.tool data/demo/mail_list_samples.fixture.json`: 통과.
- `uv run pytest tests/test_demo_seed_service.py tests/test_mail_decision_ui.py -k 'demo_seed_bundle or demo_dashboard_stats or category_timeline or inbox_initial_queue'`: 4 passed.
- `python -m py_compile app/server.py`: 통과.
- `uv run python -m app.tools.load_demo_seed_postgres --database-url postgresql://coramail:coramail@127.0.0.1:5432/coramail`: validated `email_messages=12`, `email_attachments=1`, `routing_assignments=12`.
- PostgreSQL synthetic 날짜 분포가 7일 합계 12건으로 확인됐다.
- Demo dashboard 계산 결과: Total 12, Today 4, Classified 12, Routed 12, Forwarded 1, category total 12, timeline total 12, routing total 12.
- `docker compose restart web`: 완료.

## 남은 리스크와 후속 작업

- Demo mode에서만 최신 demo 데이터 날짜를 Dashboard 기준일로 사용한다. Gmail mode는 실제 현재일 기준을 유지한다.
- 커밋과 푸시는 수행하지 않았다.

---

# 2026-08-13 - Inbox Selected Mail 초기 상세 렌더 복구

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode, Inbox Queue, Selected Mail detail |
| 관련 파일 | `app/server.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Inbox Queue 수정 후 selected mail 영역이 아예 표시되지 않는다고 보고했다.
- 첫 번째 synthetic 견적 메일은 이미 본문, 요약, 첨부 분석 검증이 끝난 상태이므로 상세 영역이 유지되어야 했다.

## 해결 방법

- `inbox_context()`가 선택된 row의 `email_uid`로 상세 payload를 즉시 조회해 `email`에 넣도록 수정했다.
- 상세 payload가 있으면 `initial_email_detail_url`을 비워 첫 렌더에서 빈 상태가 보였다가 HTMX로 교체되는 흐름을 피했다.
- Inbox 초기 렌더 테스트에 `Selected Mail`, 첫 데모 제목, 본문 표시 검증을 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k 'inbox_initial_queue or inbox_search_controls'`: 2 passed.
- `python -m py_compile app/server.py`: 통과.
- `docker compose restart web`: 완료.
- `uv run python` 렌더 검증에서 demo cookie context 기준 `Selected Mail=True`, 첫 데모 제목=True, 본문=True, 빈 상태=False를 확인했다.

## 남은 리스크와 후속 작업

- 커밋과 푸시는 수행하지 않았다.

---

# 2026-08-13 - Inbox Queue 초기 렌더에 데모 목록 메일 반영

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode, Inbox Queue, HTMX mail rows |
| 관련 파일 | `app/server.py`, `app/templates/views/inbox.html`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 데모 목록 메일 12건이 Dashboard에는 보이지만 Inbox 화면의 Inbox Queue에는 적용되지 않는다고 보고했다.

## 해결 방법

- 원인은 Dashboard는 `dashboard_context()`의 rows를 서버 렌더에 바로 포함하지만, Inbox는 `inbox_context()`에서 `emails=[]`로 비워 두고 HTMX load 요청에만 의존한 점이었다.
- `inbox_context()`가 현재 mail rows를 함께 전달하고 `mail_rows_mode="inbox"`를 명시하게 했다.
- `views/inbox.html`의 초기 `<tbody id="mailRows">`에도 `partials/mail_rows.html`을 포함해 Dashboard와 동일하게 첫 렌더부터 목록이 보이게 했다.
- 기존 HTMX `hx-get="/ui/mail-rows"`는 유지해 검색, 필터, 이후 갱신은 기존 방식대로 동작한다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k 'inbox_initial_queue or inbox_search_controls'`: 2 passed.
- `python -m py_compile app/server.py`: 통과.
- `docker compose restart web`: 완료.
- 재시작 로그에서 demo seed `email_messages=12`, `email_attachments=1` 재적재와 `/ui/inbox`, `/ui/mail-rows` 200 응답을 확인했다.

## 남은 리스크와 후속 작업

- 커밋과 푸시는 수행하지 않았다.

---

# 2026-08-13 - 데모 목록 표시용 synthetic 메일 12건 구성

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode, PostgreSQL demo seed, Inbox/Dashboard list display |
| 관련 파일 | `data/demo/mail_list_samples.fixture.json`, `data/demo/README.md`, `app/services/demo_seed_service.py`, `app/repositories/postgres_seed_writer.py`, `tests/test_demo_seed_service.py` |

## 요청 또는 배경

- 사용자는 Inbox 상세 시연 메일은 1건이면 충분하지만 Dashboard와 Inbox 목록에는 데모 제목과 칼럼값이 채워진 메일이 총 12건 정도 필요하다고 요청했다.
- 데모 데이터에는 플루맥스, 딘텍, 실제 업무번호, 실제 거래처·직원·선박·프로젝트·품목 정보를 포함하지 않아야 한다고 재확인했다.

## 해결 방법

- 기존 `data/demo/*.fixture.json` 자동 로딩 경로를 그대로 사용해 `mail_list_samples.fixture.json`에 목록 표시용 합성 메일 11건을 추가했다.
- 기존 상세 견적서 메일 1건이 최신 index 0으로 남도록 목록용 메일의 수신 시각을 모두 더 이른 시각으로 배치했다.
- PostgreSQL demo source 화면에서 카테고리, 요약, 담당자 칼럼이 채워지도록 demo seed가 fixture expected label에서 category, summary, routing assignment를 생성하게 했다.
- `routing_assignments` seed는 기존 수동 라우팅 변경을 덮어쓰지 않도록 `email_message_id` 충돌 시 `DO NOTHING`으로 보존한다.

## 검증

- `python -m json.tool data/demo/mail_list_samples.fixture.json`: 통과.
- `python -m py_compile app/services/demo_seed_service.py app/repositories/postgres_seed_writer.py`: 통과.
- `uv run pytest tests/test_demo_seed_service.py`: 7 passed.
- `uv run python -m app.tools.load_demo_seed_postgres --database-url postgresql://coramail:coramail@127.0.0.1:5432/coramail`: validated `email_messages=12`, `email_attachments=1`, `routing_assignments=12`.
- `docker compose restart web`: bootstrap seed 재적재 후 동일 count 확인.
- PostgreSQL 확인 결과 `synthetic=12`, `gmail=62`로 provider 분리되어 있고, 새 데모 제목은 `synthetic` provider에만 존재했다.
- Synthetic provider 메일 제목/본문에서 `딘텍`, `플루맥스`, `FB24291770` 검색 결과 0건을 확인했다.

## 남은 리스크와 후속 작업

- `/ui/inbox`와 `/ui/mail-rows`는 인증이 없으면 303으로 로그인 흐름에 들어가므로, 무인 `curl` 검증은 `/api/emails`와 DB provider 분리 확인으로 대체했다.
- 이번 요청에 따라 커밋과 푸시는 수행하지 않았다.

---

# 2026-08-13 - Demo Search 탭 근거 데이터 보강

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo mode Search tab, MailSearchService demo mailbox documents |
| 관련 파일 | `app/services/demo_mail_service.py`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 데모 버전의 Search 탭이 Gmail 모드에서처럼 동작하되, 대상 데이터는 데모데이터가 되도록 요청했다.
- 문서 기준상 Search 탭과 `/api/search`는 같은 `MailSearchService`를 사용하고, 현재 표시 모드의 메일 본문·분류·사실·첨부 분석 결과만 검색해야 한다.

## 해결 방법

- 데모 fixture 검색 문서 생성 시 메일 본문 근거에 snippet, demo classification summary, 거래처, 업무번호, 선박, 장비, key spec fields를 포함하게 했다.
- 데모 첨부 근거에도 파일명, mapping basis, 문서 유형, summary, 업무번호, 장비, key spec fields를 포함해 Gmail/Postgres 검색 경로처럼 첨부 값 질의가 같은 검색 서비스에서 후보가 되도록 했다.
- 데모 표시 모드에서 `mail_search_service()`가 `DemoMailService` 문서를 쓰고, 데모 견적서 첨부 근거에 납기와 총액 필드가 포함되는 회귀 테스트를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "search" -q`: 4 passed.
- `uv run pytest tests/test_mail_search_service.py -q`: 15 passed.
- `python -m py_compile app/services/demo_mail_service.py`: passed.

## 남은 리스크와 후속 작업

- 이번 변경은 fixture 기반 데모 검색 근거 보강이며, 실제 PDF 텍스트 추출을 새로 실행하지 않는다.
- 작업 시작 전부터 존재한 여러 코드·데이터·세션 로그 변경과 `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 남겨 둔다.

---

# 2026-08-12 - Routing Knowledge Graph 최종 목표 설계 재검토

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Routing Knowledge Graph, Graph DB 제품 선정, Apache AGE, entity resolution, projection gate |
| 관련 파일 | `docs/architecture/graph-routing-architecture.md`, `docs/decisions/DECISION-011-routing-knowledge-graph.md`, `docs/decisions/README.md`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Graph DB를 지금 구현하는지와 무관하게 언젠가는 구현해야 한다는 전제에서 최종적으로 어떤 설계가 최적인지 충분히 검토하고 문서화하라고 요청했다.
- 기존 문서의 “조건부 보류” 결론은 목표 설계 채택으로 보기 어렵기 때문에 방향을 다시 잡았다.

## 해결 방법

- `graph-routing-architecture.md` 앞부분에 최종 권고 설계를 추가했다.
- 최종 목표 구현안을 PostgreSQL source of truth + Qdrant + Apache AGE 기반 Routing Knowledge Graph projection으로 정리했다.
- Neo4j와 Memgraph는 Apache AGE proof 실패 시 대체 후보로 두는 조건을 명확히 했다.
- projection 방식은 PostgreSQL transactional outbox + idempotent worker를 목표 설계로 확정하고 full rebuild는 proof/recovery path로 분리했다.
- canonical registry, entity linking, merge/unmerge, projection, graph retrieval, routing evaluation, auto assignment integration 순서로 구현 phase를 재정의했다.
- DECISION-011 상태를 `채택, 구현 보류`로 바꾸고 “Routing Knowledge Graph 목표 설계 채택” ADR로 갱신했다.

## 결정

- Graph DB는 최종 목표 설계에 포함한다.
- 첫 구현 대상은 범용 Knowledge Graph가 아니라 Routing Knowledge Graph다.
- Graph engine의 1순위 목표 구현안은 Apache AGE다.
- 구현은 즉시 시작하지 않고 canonical registry와 entity resolution/projection/evaluation gate를 먼저 통과해야 한다.

## 검증

- Apache AGE, Neo4j, Memgraph 공식 문서를 다시 확인해 제품 비교와 Apache AGE 우선 근거를 보강했다.
- 문서 작업만 수행했으므로 애플리케이션 테스트는 실행하지 않았다.

## 남은 리스크와 후속 작업

- Apache AGE의 실제 PostgreSQL 버전 호환성, traversal latency, rebuild 시간, Python client ergonomics는 proof 단계에서 검증해야 한다.
- 실제 고객·선박·제품·프로젝트 alias와 담당자 이력 데이터가 부족하므로 entity resolution 평가셋을 별도로 만들어야 한다.

---

# 2026-08-12 - Graph DB 도입 사전 기획과 Routing Knowledge Graph 설계

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Graph DB 도입 검토, Routing Knowledge Graph, entity resolution, retrieval, routing evaluation |
| 관련 파일 | `docs/architecture/graph-routing-architecture.md`, `docs/decisions/DECISION-011-routing-knowledge-graph.md`, `docs/decisions/README.md`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Graph DB를 즉시 구현하지 말고, 현재 코드·DB 스키마·문서·제품 목표를 분석한 뒤 Graph DB 도입 타당성과 적용 범위를 문서로 먼저 설계해 달라고 요청했다.
- 구현, migration, Docker Compose, 라이브러리 추가, 테스트 코드 작성, 서비스/retriever 구현은 이번 단계에서 금지했다.

## 확인한 사실

- 현재 `Mail Decision Run`, `MailFacts`, retrieval planner/service, deterministic `RoutingPolicy`, `routing_candidates`, `assignee_capabilities`는 이미 구현되어 있다.
- 현재 PostgreSQL 스키마에는 `customers`, `contacts`, `vessels`, `projects`, `products`, `product_groups`, `business_cases` 같은 canonical entity registry가 없다.
- 현재 retrieval type은 `EXACT`, `ROUTING_RULE`, `SIMILAR_CASE`, `ASSIGNEE_CAPABILITY`까지이고 Graph retriever는 없다.
- 합성 seed의 `product_group` capability와 코드의 `product` capability 매칭처럼 Graph 도입 전에 정합화해야 할 taxonomy 차이가 있다.

## 해결 방법

- `docs/architecture/graph-routing-architecture.md`를 추가해 Graph DB 필요성, Routing Knowledge Graph 범위, domain model, entity resolution, provenance, routing algorithm, retrieval integration, projection, fallback, Business Case 확장, 기술 후보 비교, 평가 계획, Implementation Gate, Implementation Readiness를 정리했다.
- `docs/decisions/DECISION-011-routing-knowledge-graph.md`를 추가해 Graph DB 즉시 도입 보류, PostgreSQL derived projection 원칙, Apache AGE proof 우선 검토, 채택/중단 기준을 ADR로 기록했다.
- `docs/decisions/README.md`에 DECISION-011과 Graph DB 보류 상태를 반영했다.

## 결정

- Graph DB는 PostgreSQL 또는 Qdrant를 대체하지 않는다.
- 현재 상태는 `READY WITH CONDITIONS`다.
- 구현 전에는 PostgreSQL canonical entity registry, entity alias/merge 정책, routing weight 평가, Graph projection 방식, Graph 제품 proof 범위를 먼저 결정해야 한다.

## 검증

- 문서 작업만 수행했으므로 애플리케이션 테스트는 실행하지 않았다.
- 공식 문서 기준으로 Neo4j, Memgraph, Apache AGE의 라이선스와 운영 특성을 확인해 기술 후보 비교에 반영했다.

## 남은 리스크와 후속 작업

- 실제 고객·선박·제품·프로젝트 alias 데이터와 담당자 전달 이력이 부족해 Graph 도입 효과는 아직 운영 성능으로 주장할 수 없다.
- Graph 구현 승인 전 `canonical_entities`, `entity_aliases`, projection/outbox, `RetrieverType.GRAPH` 설계와 평가셋을 별도 작업으로 확정해야 한다.
- 이번 작업 시작 전부터 존재한 `data/demo/received_quotations.fixture.json`, `tests/test_mail_decision_ui.py`, `node_modules/`, `package.json`, `package-lock.json`, 세션 로그의 기존 diff는 이번 변경과 분리한다.

---

# 2026-08-11 - Documents 카드형 문서 유형 화면 정리

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Documents view, attachment document type navigation UI |
| 관련 파일 | `app/templates/views/document_types.html`, `app/templates/partials/document_type_sections.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_document_type_navigation.py` |

## 요청 또는 배경

- 사용자는 Documents 화면에서 검색박스 영역과 단순 숫자 stats 영역을 제거하길 요청했다.
- 문서 유형별 섹션을 단순 목록보다 카드형으로 구성해 한 화면에서 어떤 문서 유형들이 있고, 각 유형에 어떤 최신 메일이 있는지 파악할 수 있게 해 달라고 요청했다.
- 이후 문서 유형별 카드 크기를 모두 같게 고정하고, 섹션 내부 요소는 스크롤되게 하라고 요청했다.

## 해결 방법

- Documents view 상단 검색 input과 숫자 summary block을 제거했다.
- `document_type_sections` partial을 문서 유형별 카드 그리드로 재구성하고, 카드 헤더에 유형 아이콘, 라벨, 이메일/첨부 수, canonical type chip을 배치했다.
- 각 카드 안에 최신 메일 preview list를 배치하고, 카드 높이를 `520px`로 고정했다.
- 메일이 많은 문서 유형은 카드 내부 preview list만 세로 스크롤되도록 `overflow-y: auto`를 적용했다.
- 검색 input 제거에 맞춰 shell의 Documents polling URL에서 `documentTypeSearch` 의존 로직을 제거했다.
- 렌더 테스트에 카드형 구조와 검색/summary 미노출 조건을 추가했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_document_type_navigation.py tests/test_mail_decision_ui.py -q`: 62 passed.
- `docker compose restart web`로 8000 web container를 최신 코드로 재시작했다.
- Playwright Chromium으로 `http://127.0.0.1:8000` Documents 화면을 확인했다: 카드 6개, 검색 영역 없음, summary 영역 없음, 모든 카드 높이 `520px`, 가로 overflow 없음, 메일이 많은 카드만 내부 스크롤 발생.

## 남은 리스크와 후속 작업

- 카드당 높이는 현재 화면 밀도 기준으로 `520px`로 고정했다. 실제 운영 메일 제목/파일명이 더 길어지는 경우 카드 내부 typography와 attachment chip max-width는 추가 조정할 수 있다.
- 작업 시작 전부터 존재한 `tests/test_mail_decision_ui.py`, `node_modules/`, `package.json`, `package-lock.json` 변경은 이번 커밋과 분리한다.

---

# 2026-08-11 - Documents 탭 클릭 무응답 원인 보정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Main navigation, Documents view lifecycle |
| 관련 파일 | `app/templates/shell.html`, `app/server.py`, `tests/test_document_type_navigation.py` |

## 요청 또는 배경

- 사용자는 `Documents` 탭을 클릭해도 아무 일도 일어나지 않는다고 보고했다.
- 기존 탭들과 같은 방식으로 구현됐는지, 근본 원인을 파악해 해결해 달라고 요청했다.

## 원인

- 새 탭은 nav 버튼과 route는 있었지만 shell의 UI view lifecycle에는 완전히 편입되지 않았다.
- `currentUiView()`가 `dashboard`와 `inbox`만 정식 polling view로 인정해 `Documents`는 상태 동기화 대상에서 빠졌다.
- 기존 nav fallback은 `window.htmx`가 존재하면 비활성화되어, HTMX가 요청을 처리하지 못하거나 실패해도 클릭 실패 피드백이 없었다.

## 해결 방법

- 모든 메인 nav 버튼에 `type="button"`을 명시했다.
- HTMX 의존 fallback을 `installMainNavigation()` 공통 handler로 바꿔 Dashboard, Inbox, Documents, Search, Settings가 같은 fetch/swap/active/title 초기화 흐름을 타게 했다.
- `Documents`를 `currentUiView()`와 `/api/ui-state`의 `document_sections` version에 추가했다.
- nav handler와 Documents UI state를 테스트로 고정했다.

## 검증

- `python -m py_compile app/server.py app/services/postgres_mail_service.py app/services/demo_mail_service.py app/services/gmail_mail_service.py`: passed.
- `uv run pytest tests/test_document_type_navigation.py -q`: 5 passed.
- `uv run pytest tests/test_document_type_navigation.py tests/test_mail_decision_ui.py -q`: 62 passed.
- `uv run python`으로 `/ui/documents` fragment 직접 렌더링이 200을 반환하고 `data-view="documents"`를 포함하는 것을 확인했다.
- `uv run python`으로 `/api/ui-state?view=documents` 상당 호출이 `document_sections` version을 반환하는 것을 확인했다.

## 남은 리스크와 후속 작업

- 실제 브라우저 클릭은 현재 환경에서 Playwright/브라우저 도구 없이 직접 확인하지 못했다. 다만 nav click path가 HTMX에만 의존하지 않도록 서버 fragment fetch로 고정됐다.
- 작업 시작 전부터 존재한 `tests/test_mail_decision_ui.py`, `node_modules/`, `package.json`, `package-lock.json` 변경은 이번 커밋과 분리한다.

---

# 2026-08-11 - Documents 탭 명칭과 라우트 보정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Documents navigation, HTMX UI |
| 관련 파일 | `app/server.py`, `app/templates/shell.html`, `app/templates/views/document_types.html`, `docs/features/attachment-document-type-navigation.md`, `tests/test_document_type_navigation.py` |

## 요청 또는 배경

- 사용자는 새로 추가된 문서 유형 탭이 열리지 않는다고 보고했다.
- 탭 이름은 한국어 `문서 유형` 대신 더 적절한 영어 이름으로 바꾸기를 요청했다.

## 해결 방법

- 탭 표시명을 `Documents`로 변경했다.
- 네비게이션 route를 `/ui/documents`로 정리하고 기존 `/ui/document-types`는 호환 alias로 유지했다.
- Documents 화면의 `data-view`와 page title mapping을 새 view 이름에 맞췄다.
- route 등록과 새 이름 렌더링을 테스트에 추가했다.

## 검증

- `uv run python`으로 `/ui/documents` fragment 직접 렌더링 결과가 200과 Documents HTML을 반환하는 것을 확인했다.
- `python -m py_compile app/server.py app/services/postgres_mail_service.py app/services/demo_mail_service.py app/services/gmail_mail_service.py`: passed.
- `uv run pytest tests/test_document_type_navigation.py -q`: 4 passed.
- `uv run pytest tests/test_document_type_navigation.py tests/test_mail_decision_ui.py -q`: 61 passed.

## 남은 리스크와 후속 작업

- 현재 환경의 `TestClient`는 `httpx2` 미설치로 사용할 수 없어 ASGI client 요청 검증은 직접 route 렌더링으로 대체했다.
- 작업 시작 전부터 존재한 `tests/test_mail_decision_ui.py`, `node_modules/`, `package.json`, `package-lock.json` 변경은 이번 커밋과 분리한다.

---

# 2026-08-11 - 첨부 문서 유형별 메일 탐색 탭 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Document type navigation, attachment analysis, UI |
| 관련 파일 | `app/server.py`, `app/services/postgres_mail_service.py`, `app/services/demo_mail_service.py`, `app/services/gmail_mail_service.py`, `app/templates/views/document_types.html`, `app/templates/partials/document_type_sections.html`, `app/static/app.css`, `docs/features/attachment-document-type-navigation.md`, `tests/test_document_type_navigation.py` |

## 요청 또는 배경

- 사용자는 첨부파일 문서 유형 기준으로 해당 유형이 포함된 이메일을 확인할 수 있는 새 탭을 원했다.
- 추가로 화면은 단일 필터 목록보다 문서 유형별 섹션으로 나뉜 구성을 선호한다고 밝혔다.

## 해결 방법

- `문서 유형` 탭과 `/ui/document-types`, `/ui/document-type-sections` fragment 라우트를 추가했다.
- PostgreSQL, Gmail 위임, 데모 fixture 서비스에 문서 유형 섹션 조회 계약을 추가했다.
- 섹션은 이메일 수와 매칭 첨부파일 수를 따로 집계하고, 한 이메일이 여러 유형 첨부를 포함하면 각 섹션에 노출되도록 했다.
- `purchase_order`/`발주서`를 첨부 문서 유형 taxonomy와 파일명·텍스트 기반 분류기에 추가했다.
- F-13 기능 문서를 추가하고 F-06 첨부 분석 문서의 허용 카테고리를 갱신했다.

## 검증

- `python -m py_compile app/server.py app/services/postgres_mail_service.py app/services/demo_mail_service.py app/services/gmail_mail_service.py app/presentation/attachment_analysis.py app/document_processing/attachment_classifier.py`: passed.
- `uv run pytest tests/test_document_type_navigation.py -q`: 3 passed.
- `uv run pytest tests/test_attachment_analysis_presentation.py tests/test_attachment_parsers.py -q`: 32 passed.
- `uv run pytest tests/test_document_type_navigation.py tests/test_mail_decision_ui.py -q`: 60 passed.

## 남은 리스크와 후속 작업

- 실제 운영 DB의 대량 데이터에서는 JSONB 기반 current 분석 결과 조인 성능을 확인해야 한다.
- 작업 시작 전부터 존재한 `tests/test_mail_decision_ui.py`, 기존 `session-log.md` 수정, `node_modules/`, `package.json`, `package-lock.json` 변경은 이번 기능 변경과 분리한다.

---

# 2026-08-11 - Codex 변경 기록 단위 명확화

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Codex repo guidance, change recording workflow |
| 관련 파일 | `AGENTS.md`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Codex가 한 요청 안에서 git status, diff, 세션 로그, commit, push 관련 작업을 과하게 반복해 토큰과 시간이 낭비된다고 보고했다.
- 사용자는 "항상 기록" 원칙은 유지하되, 기록 단위가 한 요청당 한 번이어야 한다고 명확히 했다.

## 해결 방법

- `AGENTS.md`의 Change Recording Rules를 `meaningful file change` 단위에서 `user request` 단위로 바꿨다.
- 한 요청 안의 개별 편집, 파일, 테스트 실행, 중간 수정마다 기록 워크플로우를 반복하지 말고 최종에 한 번만 묶어 처리하도록 명시했다.
- 중간 진행 업데이트가 git status, diff, 세션 로그 수정, commit, push를 유발하지 않는다고 명시했다.

## 검증

- 문서 문구 변경이므로 별도 자동 테스트는 실행하지 않았다.
- `git diff -- AGENTS.md`로 최종 지침 변경 범위를 확인했다.

## 남은 리스크와 후속 작업

- 기존 작업트리에 남아 있던 `tests/test_mail_decision_ui.py`, `node_modules/`, `package.json`, `package-lock.json`, 세션 로그의 이전 diff는 이번 변경에 포함하지 않는다.

---

# 2026-08-11 - Mail Decision 거래처 문서유형 오탐 방지

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Mail Decision fact extraction, Inbox detail |
| 관련 파일 | `app/mail_content.py`, `app/agents/fact_extraction_agent.py`, `tests/test_vision_fact_extraction.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Inbox 탭의 Mail Decision 거래처 결과가 나오는 과정을 설명해 달라고 요청했다.
- 특정 전달 제목 `Fw: [FW][FW][RE]FWD :<사양확인 요청건> [견적서] ...`에서 거래처 필드가 `견적서`로 표시되는 오류가 있다고 보고했다.

## 원인

- Mail Decision 패널은 최신 run의 `facts.customer_name`을 그대로 표시한다.
- 사실 추출 보정 로직은 제목의 대괄호 값을 거래처 후보로 사용할 때 `RE`, `FW`, 참조번호만 제외하고 `견적서` 같은 문서 유형 라벨은 제외하지 않았다.
- LLM이 같은 문서 유형 라벨을 `customer_name`으로 반환해도 저장 전 검증이 없어 UI까지 전달될 수 있었다.

## 해결 방법

- 제목 대괄호 거래처 후보에서 문서 유형·스레드 라벨(`견적서`, `견적의뢰서`, `RFQ`, `invoice` 등)을 제외했다.
- Fact Extraction Agent의 프롬프트에 문서 유형 라벨을 거래처로 쓰지 말라는 제약을 추가했다.
- LLM 및 grounded fallback 결과 저장 전에 `customer_name`과 `customer_candidates`에서 비거래처 라벨을 제거하고, 거래처가 없으면 사람 검토용 `customer_requires_review`를 남기게 했다.
- 사용자가 보고한 제목과 LLM 오출력 케이스를 회귀 테스트로 추가했다.

## 검증

- `uv run pytest tests/test_vision_fact_extraction.py -q`: 6 passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "mail_decision_panel" -q`: 10 passed, 47 deselected.
- `python -m py_compile app/mail_content.py app/agents/fact_extraction_agent.py`: passed.

## 남은 리스크와 후속 작업

- 실제 운영 DB의 기존 run에 이미 저장된 `customer_name=견적서` 값은 재실행 또는 데이터 보정이 필요하다.
- 이번 작업 전부터 존재한 `tests/test_mail_decision_ui.py`, `session-log.md`, `node_modules/`, `package.json`, `package-lock.json` 변경은 별도 변경으로 남겨 둔다.

---

# 2026-08-11 - Dashboard Forwarded stats 실제 전달 상태 집계 보정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard stats UI, PostgreSQL mailbox rows |
| 관련 파일 | `app/server.py`, `app/repositories/postgres_mail_repository.py`, `app/services/postgres_mail_service.py`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Dashboard stats에 추가된 `Forwarded` 카드 UI는 의도대로 보이지만 실제 전달 완료 데이터가 반영되지 않아 0%로 표시된다고 보고했다.
- 전달 완료는 수동 검토 후 담당자에게 실제 전달되는 흐름에서 발생하므로, 기존 Mail Decision 상태가 `review_required`로 남아 있는 데이터와 함께 존재할 수 있다.

## 원인

- PostgreSQL mailbox row 조회가 `routing_assignments.forwarded_at`을 내려주지 않아 실제 전달 시각 기반 집계가 불가능했다.
- row의 종합 `work_status` 계산에서 `review_required`가 `forwarded`보다 먼저 평가되어, 전달 완료 후에도 기존 Mail Decision 검토 상태가 전달 완료 표시를 가릴 수 있었다.
- Dashboard `forwarded_count`는 일부 상태 문자열만 보아 전달 완료 라벨이나 전달 완료 시각이 있는 row를 놓칠 수 있었다.

## 해결 방법

- 메일 row 조회에 `routing_forwarded_at`을 추가하고 UI row 계약으로 노출했다.
- `work_status` 계산에서 `routing_status=forwarded`, `routing_forwarded_at`, `manual_route_status=sent`, `manual_route_sent_at`이 있으면 `review_required`보다 먼저 `forwarded`로 판정하도록 보정했다.
- Dashboard `Forwarded` 집계가 `work_status`, `routing_status`, 전달 완료 라벨, `routing_forwarded_at`, `manual_route_sent_at`을 함께 보도록 확장했다.
- `review_required` run이 남은 전달 완료 row와 전달 완료 라벨/시각만 가진 row를 회귀 테스트로 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "dashboard_summary or forwarded_work_status" -q`: 4 passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 55 passed.
- `python -m py_compile app/server.py app/repositories/postgres_mail_repository.py app/services/postgres_mail_service.py`: passed.

## 남은 리스크와 후속 작업

- 실제 운영 DB 직접 집계 쿼리는 이번 환경에서 실행하지 않았다.

---

# 2026-08-11 - Dashboard Forwarded stats 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard stats UI |
| 관련 파일 | `app/server.py`, `app/templates/partials/stats.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Dashboard 탭의 stats 항목 단 제일 오른쪽에 `Forwarded` 항목을 추가해 달라고 요청했다.
- 메인 stat은 담당자에게 전달 완료한 비율이고, 보조 문구는 `~건 전달 완료` 형식이어야 한다.

## 해결 방법

- `dashboard_summary`에 `forwarded_count`를 추가하고 `work_status=forwarded`, `routing_status=forwarded`, `manual_route_status=sent`를 전달 완료로 집계했다.
- stats partial에 기존 카드와 동일한 구조의 `Forwarded` 카드를 추가했다.
- 대시보드 stats grid를 5개 카드 기준으로 조정했다.
- 대시보드 summary 테스트에 전달 완료 집계와 문구 검증을 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "dashboard_summary" -q`: 1 passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 54 passed.

## 남은 리스크와 후속 작업

- 브라우저 스크린샷 검증은 실행하지 않았다.

---

# 2026-08-11 - Mail Decision Status 업무 상태 동기화

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox Mail Decision panel, work status |
| 관련 파일 | `app/server.py`, `app/templates/partials/mail_decision_panel.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 inbox queue에 보이는 status와 Mail Decision 패널의 `Status`가 같아야 한다고 요청했다.
- 실제로 Mail Decision Run은 `review_required`였지만 수동 배정 후 전달 완료된 메일에서 패널은 여전히 `사람 검토 필요`로 표시됐다.
- 사람 검토 필요 상태에서 `시스템 오류가 아니라 자동 판단에 필요한 정보가 충분하지 않아 사람의 검토가 필요합니다.` 도움말 문구를 제거해 달라고 요청했다.
- 수동 배정 완료 후 Mail Decision 패널의 담당 후보 목록에서 `배정` 버튼을 숨겨 달라고 요청했다.

## 해결 방법

- Mail Decision 패널 표시 status를 run 원본 status만 쓰지 않고 현재 이메일의 `work_status`/`work_status_label`이 있으면 그 값을 우선 사용하도록 변경했다.
- `assigned`, `forwarded`, `unclassified` 상태 라벨과 성공 색상 매핑을 Mail Decision 패널 status에 추가했다.
- 사람 검토 필요 상태의 장문 도움말을 제거했다.
- 담당 후보의 `배정` 버튼 표시 조건을 `run.status == review_required`에서 패널의 실제 표시 상태가 `review_required`인 경우로 바꿨다.
- 전달 완료 상태에서는 후보 정보는 남기되 배정 form/action이 렌더링되지 않는 회귀 테스트를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "mail_decision_panel or latest_mail_decision_run_for_panel" -q`: 11 passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "work_status or manual_route or mail_decision_panel" -q`: 19 passed.

---

# 2026-08-11 - Mail Decision Status 표 행 배치

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox Mail Decision panel |
| 관련 파일 | `app/templates/partials/mail_decision_panel.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 inbox Mail Decision 패널에서 status가 표 밖에 별도로 표시되는 대신 업무 유형, 거래처, 업무번호가 있는 표 안에 들어가도록 요청했다.
- 필드명은 `Status`로 지정했다.

## 해결 방법

- Mail Decision 패널의 별도 status row를 제거하고 `info-table` 첫 행에 `Status` 필드를 추가했다.
- 기존 상태 배지와 review help 문구는 `Status` 값 칸 안에서 함께 표시되도록 유지했다.
- 더 이상 사용하지 않는 `.mail-decision-status-row` CSS 선택자를 제거했다.
- status가 업무 유형보다 먼저 같은 표 안에 렌더링되는지 UI 테스트를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "mail_decision_panel" -q`: 9 passed.

---

# 2026-08-11 - 첨부 토글 아이콘 문서 유형 뒤 배치

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox email detail attachment row UI |
| 관련 파일 | `app/templates/partials/email_detail.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 첨부 토글 아이콘을 문서 유형 표시 오른쪽에 두도록 요청했다.

## 해결 방법

- 펼침 가능한 첨부 행의 토글 아이콘을 파일명 앞이 아니라 파일명/문서 유형이 있는 title row의 끝으로 이동했다.
- 토글 아이콘의 크기와 open 회전 CSS를 복구했다.
- 문서 유형 텍스트가 토글 아이콘보다 먼저 렌더링되는지 테스트로 확인했다.

## 검증

- `.venv/bin/pytest tests/test_mail_decision_ui.py -k "attachment_details"`: 2 passed.

## 남은 리스크와 후속 작업

- 브라우저 스크린샷 검증은 실행하지 않았다.

---

# 2026-08-11 - 첨부 행 토글 아이콘 제거와 정렬 통일

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox email detail attachment row UI |
| 관련 파일 | `app/templates/partials/email_detail.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 첨부파일 영역에서 Details 토글 유무에 따라 파일 아이콘과 파일명 위치가 달라지는 문제를 지적했다.
- 토글 아이콘은 없애고, 아이콘 없이 접었다 펴는 기능만 유지하는 방향을 요청했다.

## 해결 방법

- 분석 결과가 있는 첨부 행의 `<summary>`에서 `expand_more` 토글 아이콘을 제거했다.
- `<details>` 구조는 유지해 첨부 행 클릭 시 Details 접기/펼치기 기능은 그대로 동작한다.
- 더 이상 렌더링되지 않는 `.attachment-toggle` CSS와 open 회전 규칙을 제거했다.
- 펼침 가능한 첨부에서도 `attachment-toggle`이 렌더링되지 않는 회귀 테스트를 추가했다.

## 검증

- `.venv/bin/pytest tests/test_mail_decision_ui.py -k "attachment_details"`: 2 passed.

## 남은 리스크와 후속 작업

- 브라우저 스크린샷 검증은 실행하지 않았다.

---

# 2026-08-11 - Mail Decision 재배정 버튼 라벨 정리

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox Mail Decision panel |
| 관련 파일 | `app/templates/partials/email_detail.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Mail Decision 제목 영역 버튼의 아이콘을 재분류/재생성 버튼과 같은 refresh 아이콘으로 바꾸고, 텍스트를 `재배정`으로 변경해 달라고 요청했다.

## 해결 방법

- Mail Decision 헤더 버튼 아이콘을 `account_tree`에서 `refresh`로 변경했다.
- 버튼 텍스트를 `Mail Decision`에서 `재배정`으로 변경했다.
- 관련 UI 렌더링 테스트 기대값을 갱신했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k latest_lazy_load -q`: passed.

## 남은 리스크와 후속 작업

- 없음.

---

# 2026-08-11 - Inbox Mail Decision 중복 정보 정리

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox email detail UI, Mail Decision panel |
| 관련 파일 | `app/templates/partials/email_detail.html`, `app/templates/partials/mail_decision_panel.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Inbox 탭의 Mail Decision 영역에서 담당 후보를 top3만 표시하도록 요청했다.
- Mail Decision 제목 영역의 padding과 높이를 Mail Overview, Summary와 통일하고, 실행 버튼도 두 패널의 액션 버튼과 같은 위치와 디자인으로 배치해 달라고 요청했다.
- Mail Decision에서 Mail Overview와 중복되는 배정 완료 담당자 표시를 제거하고, Summary와 중복되는 판단 요약 및 필요 조치 영역도 제거해 달라고 요청했다.

## 해결 방법

- Mail Decision 실행 버튼을 결과 partial 내부에서 오른쪽 패널 헤더 액션 영역으로 이동하고, 기존 재분류/재생성 버튼과 같은 `route-now-btn summary-regenerate-btn` 디자인을 사용했다.
- Mail Decision 결과 partial에서 배정 완료 배너, 판단 요약, 필요 조치, 선택 담당자 행을 제거했다.
- 담당 후보 렌더링 범위를 `panel.assignment_candidates[:3]`으로 제한했다.
- 더 이상 쓰이지 않는 Mail Decision 내부 액션 행과 배정 완료 배너 CSS를 제거했다.
- UI 테스트를 새 버튼 위치, top3 후보 제한, 중복 영역 미표시에 맞게 갱신했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -q`: 53 passed.

## 남은 리스크와 후속 작업

- 브라우저 스크린샷 기반 시각 검증은 실행하지 않았다.
- 작업 시작 전부터 존재한 `app/templates/views/settings.html`, 세션 로그의 기존 미커밋 변경, `node_modules/`, `package.json`, `package-lock.json`은 이번 변경과 무관하게 유지했다.

---

# 2026-08-11 - Settings 자동 배정 기준 복구

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Settings tab UI |
| 관련 파일 | `app/templates/views/settings.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 시연용으로 숨겼던 Settings 탭의 `자동 배정 기준` 영역을 다시 복구해 달라고 요청했다.

## 해결 방법

- Settings 화면에 자동 배정 기준 패널과 `partials/auto_assignment_policy.html` include를 복구했다.
- Settings 렌더링 테스트 기대값을 자동 배정 기준 표시로 되돌렸다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "settings_renders_synthetic_assignees or auto_assignment_policy_partial" -q`: 2 passed.

---

# 2026-08-11 - Settings 자동 배정 기준 임시 숨김

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Settings tab UI, demo screenshot |
| 관련 파일 | `app/templates/views/settings.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 시연용 스크린샷을 위해 Settings 탭의 `자동 배정 기준` 영역을 잠시 숨기고, 추후 지시하면 복구해 달라고 요청했다.

## 해결 방법

- Settings 화면에서 `자동 배정 기준` 패널 렌더링을 제거했다.
- `partials/auto_assignment_policy.html`와 `/ui/settings/auto-assignment-policy` 동작은 삭제하지 않아 복구 시 화면 include만 되살리면 된다.
- Settings 렌더링 테스트 기대값을 자동 배정 기준 미노출로 갱신했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "settings_renders_synthetic_assignees or auto_assignment_policy_partial" -q`: passed.

## 남은 리스크와 후속 작업

- 이번 변경은 시연용 UI 숨김이며 자동 배정 정책 자체는 그대로 유지된다.
- 사용자가 복구를 지시하면 `views/settings.html`에 자동 배정 기준 패널 include를 되돌린다.

---

# 2026-08-11 - Search 답변 패널 제목 단순화

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search tab answer panel |
| 관련 파일 | `app/templates/partials/search_results.html`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Search 탭의 `RAG 답변` 텍스트를 `답변`으로 빠르게 변경해 달라고 요청했다.

## 해결 방법

- 답변 패널 제목을 `답변`으로 변경했다.
- 툴팁 접근성 label도 `답변 설명`으로 맞췄다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k search -q`: 3 passed, 50 deselected.

## 남은 리스크와 후속 작업

- 작업 시작 전부터 존재한 다른 미커밋 변경은 이번 수정과 무관하게 그대로 두었다.

---

# 2026-08-11 - Search 빈 상태 안내 문구 정리

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search tab empty state |
| 관련 파일 | `app/templates/partials/search_results.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Search 탭 빈 상태의 `일반 대화가 아니라...` 설명 문단을 제거하고, `질문을 입력하면 답변과 근거를 함께 정리합니다.` 문구를 정식 한국어 서비스에 자연스러운 안내 문구로 바꿔 달라고 요청했다.

## 해결 방법

- 설명 문단을 제거했다.
- 빈 상태 핵심 안내를 `메일함과 첨부 문서에서 확인할 내용을 질문해 주세요.`로 변경했다.
- UI 테스트에 새 문구와 제거된 문구를 고정했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k search -q`: 3 passed, 50 deselected.

## 남은 리스크와 후속 작업

- 작업 시작 전부터 존재한 `app/templates/views/settings.html`, 세션 로그의 기존 미커밋 diff, `node_modules/`, `package.json`, `package-lock.json`은 이번 수정과 무관하게 그대로 두었다.

---

# 2026-08-11 - Search 쿼리 입력 하단 보조 영역 제거

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search tab UI |
| 관련 파일 | `app/templates/views/search.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Search 탭이 옛 버전으로 돌아가 쿼리 박스 아래 `범위`, `확인 항목`, `바로 시작` 보조 영역이 보인다며, 쿼리 박스 밑에는 아무것도 없게 해 달라고 요청했다.

## 해결 방법

- Search 화면에서 `search-question-helper` 보조 칩 영역을 제거했다.
- 더 이상 쓰이지 않는 검색 작성 도우미 JS와 CSS를 제거했다.
- UI 테스트를 보조 영역이 렌더링되지 않는 기대값으로 갱신했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k search -q`: 3 passed, 50 deselected.

## 남은 리스크와 후속 작업

- 작업 시작 전부터 존재한 다른 미커밋 변경과 `node_modules/`, `package.json`, `package-lock.json` 미추적 파일은 이번 수정과 무관하게 그대로 두었다.

---

# 2026-08-11 - 기존 저장 요약 즉시 보정 적용

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Stored summary presentation, PostgreSQL executive summary |
| 관련 파일 | `app/presentation/summary_text.py`, `app/agents/decision_agent.py`, `app/services/postgres_mail_service.py`, `app/server.py`, `tests/test_decision_agent.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 납품일정 요약 표현 수정이 새 요약 재생성 후에만 반영되는 것이 아니라, 현재 화면에 바로 적용되도록 요청했다.

## 해결 방법

- 한국어 요약 표현 보정 함수를 presentation 공통 모듈로 분리했다.
- 신규 Decision Agent 생성 경로와 PostgreSQL mailbox 조회 경로, Mail Decision 패널 view 변환 경로가 모두 같은 보정을 적용하게 했다.
- 이미 저장된 현재 executive summary 중 `드라이독을 예정하고`가 남아 있는 1건을 PostgreSQL에서 직접 `드라이독 예정이어서`로 보정했다.
- Docker Compose web 컨테이너를 재시작해 새 코드가 즉시 적용되게 했다.

## 검증

- `python -m py_compile app/agents/decision_agent.py app/services/postgres_mail_service.py app/server.py app/presentation/summary_text.py`: passed.
- `uv run pytest tests/test_decision_agent.py -q`: 7 passed.
- PostgreSQL current executive summary에서 `드라이독을 예정하고` 잔여 건수 확인: 0건.

## 남은 리스크와 후속 작업

- 이번 DB 보정은 보고된 표현 1건을 즉시 고친 것이다. 다른 부자연스러운 한국어 표현은 별도 품질 규칙으로 추가해야 한다.
- 작업 시작 전부터 존재한 Search UI, CSS, shell, `tests/test_mail_decision_ui.py`, `node_modules/`, `package.json`, `package-lock.json` 변경은 이번 커밋 범위에서 제외한다.

---

# 2026-08-11 - 납품일정 요약문 예정 표현 보정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Mail Decision summary generation, Korean summary polish |
| 관련 파일 | `app/agents/decision_agent.py`, `tests/test_decision_agent.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 `[딘텍] FB24291770 / 납품일정문의` 메일의 핵심 요청 요약이 `드라이독을 예정하고`처럼 부자연스럽게 생성되므로 `드라이독 예정이고` 또는 `드라이독 예정이어서`처럼 자연스럽게 나오도록 요청했다.

## 해결 방법

- Decision Agent 프롬프트에 한국어 일정 문맥에서 `을/를 예정하고` 표현을 피하고 `예정이어서` 또는 `예정이고`를 쓰도록 지시를 추가했다.
- LLM이 같은 표현을 다시 생성해도 저장 전 한 줄 요약에서 `...을/를 예정하고, ...요청합니다` 패턴을 `... 예정이어서, ...요청합니다`로 보정하도록 했다.
- 문제 메일 문장을 재현하는 단위 테스트를 추가해 `드라이독을 예정하고`가 다시 저장되지 않도록 고정했다.

## 검증

- `python -m py_compile app/agents/decision_agent.py`: passed.
- `uv run pytest tests/test_decision_agent.py -q`: 6 passed.

## 남은 리스크와 후속 작업

- 이미 저장된 과거 요약은 자동 변경하지 않는다. 해당 메일 화면에서 요약 재생성을 실행하면 새 규칙이 반영된다.
- 작업 시작 전부터 존재한 `node_modules/`, `package.json`, `package-lock.json` 미추적 파일은 이번 수정과 무관하다.

---

# 2026-08-11 - Inbox Mail Decision 제목 영문화

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox email detail UI |
| 관련 파일 | `app/templates/partials/email_detail.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Inbox의 `업무 판단 및 담당자 추천` 제목을 적절하고 심플한 영어 제목 텍스트로 바꿔 달라고 요청했다.

## 해결 방법

- 메일 상세 패널 제목을 `Mail Decision`으로 변경했다.
- 해당 제목 렌더링을 검증하는 UI 테스트 기대값도 함께 갱신했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "latest_lazy_load" -q`: passed.

## 남은 리스크와 후속 작업

- 툴팁과 로딩 문구의 한국어 문장은 이번 요청 범위 밖이라 유지했다.
- 작업 시작 전부터 존재한 다른 수정 파일과 미추적 `node_modules/`, `package.json`, `package-lock.json`은 이번 변경과 무관하다.

---

# 2026-08-11 - 수동 배정 완료 즉시 갱신

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox manual assignment UI refresh |
| 관련 파일 | `app/server.py`, `app/templates/partials/mail_decision_panel.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Inbox 담당자 `배정` 버튼 클릭 후 저장은 됐지만 화면 변화가 없어 같은 버튼을 다시 누르게 되고, 그때 이미 배정되었다는 오류가 떠서 혼란스럽다고 보고했다.

## 해결 방법

- 수동 배정 성공 POST 응답에 `mail-manual-assignment-completed` HTMX trigger를 추가했다.
- 프론트에서 해당 trigger를 받으면 현재 선택 메일 UID를 다시 고정하고 메일 상세, Inbox 목록, 라우팅 요약을 즉시 새로고침한다.
- Mail Decision 패널에는 완료 상태에서 `배정 완료` 배지와 담당자명을 표시한다.
- 완료 trigger, shell 즉시 새로고침 핸들러, 완료 배지 표시 회귀 테스트를 추가했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "manual_assignment or manual_route_polling or completed" -q`: 6 passed, 47 deselected.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 53 passed.

## 남은 리스크와 후속 작업

- 브라우저 클릭 검증은 서버 재시작 후 사용자가 실제 화면에서 확인한다.
- 작업 시작 전부터 존재한 세션 로그 정리 diff와 `node_modules/`, `package.json`, `package-lock.json` 미추적 파일은 이번 수정과 무관하다.

---

# 2026-08-11 - Inbox 수동 담당자 배정 멈춤 해결

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox mail decision panel, manual assignment refresh |
| 관련 파일 | `app/server.py`, `app/templates/partials/mail_decision_panel.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Inbox에서 담당자를 수동으로 `배정`하는 버튼을 누르면 페이지가 멈추는 문제의 근본 원인을 찾아 해결해 달라고 요청했다.

## 확인한 사실

- 수동 배정 POST 핸들러는 배정 저장 후 패널을 다시 렌더링하기 위해 `_latest_mail_decision_run_for_panel()`을 호출했다.
- 해당 함수는 기본 설정에서 현재 요청의 base URL을 runtime URL로 사용해 같은 FastAPI 앱의 `/api/emails/{id}/mail-decision-runs/latest`를 동기 HTTP로 다시 호출했다.
- 이 경로가 `async` 수동 배정 핸들러 안에서 실행되면 단일 이벤트 루프를 막은 채 자기 자신에게 HTTP 응답을 기다릴 수 있어, 브라우저에서는 배정 버튼이 비활성 상태로 멈춘 것처럼 보일 수 있다.

## 해결 방법

- PostgreSQL이 설정된 로컬 앱에서는 수동 배정 후 최신 Mail Decision Run을 HTTP self-call 없이 `PostgresMailDecisionRepository`에서 직접 조회하도록 변경했다.
- 로컬 repository 조회 실패 시에도 외부 `CORAMAIL_MAIL_DECISION_RUNTIME_URL`이 명시된 경우에만 HTTP fallback을 허용해 같은 서버 자기 호출을 피했다.
- 담당 후보 배정 form에 클릭 전파 차단을 추가해 주변 HTMX 클릭 이벤트와 섞이지 않게 했다.
- 로컬 repository 경로가 runtime HTTP client를 호출하지 않는 회귀 테스트와 form 전파 차단 검증을 추가했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -k "manual_assignment or latest_mail_decision_run_for_panel" -q`: 3 passed, 48 deselected.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 51 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 수동 클릭 검증은 실행하지 않았다.
- 작업 시작 전부터 존재한 세션 로그 정리 diff와 `node_modules/`, `package.json`, `package-lock.json` 미추적 파일은 이번 수정 원인과 무관하다.

---

# 2026-08-11 - 시연 스크린샷용 Inbox 표시 정리

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox Mail Overview, shell navigation |
| 관련 파일 | `app/templates/partials/email_detail.html`, `app/templates/shell.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 시연 스크린샷을 위해 Inbox 탭의 Mail Overview에서 긴급도를 임시로 가짜 데이터로 채우거나 숨기고 싶다고 요청했다.
- 담당자 항목에서 담당자 이름 아래에 `-`만 표시되는 문제를 고쳐 달라고 요청했다.
- Evaluation 탭도 시연 스크린샷을 위해 임시로 숨겨 달라고 요청했다.

## 해결 방법

- 데이터와 라우팅 계약은 그대로 두고 표시 계층에서만 Mail Overview의 긴급도 행을 숨겼다.
- 담당자 이름 아래 부서, 직책, 이메일이 비어 있으면 placeholder `-`를 렌더링하지 않도록 했다.
- Evaluation 페이지와 API는 유지하되, 사이드바 네비게이션의 Evaluation 버튼만 제거해 시연 화면에서 보이지 않게 했다.
- UI 렌더링 회귀 테스트에 긴급도 행 숨김, 빈 담당자 submeta placeholder 제거, Evaluation 탭 숨김 검증을 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -q`: 50 passed.
- `pytest tests/test_mail_decision_ui.py -q`: 로컬 셸에 `pytest` 명령이 없어 실행되지 않았다.

## 남은 리스크와 후속 작업

- 긴급도와 Evaluation 기능 자체는 제거하지 않은 임시 화면 숨김이다. 시연 이후 다시 노출해야 하면 템플릿 행과 네비게이션 버튼을 복구하면 된다.
- 작업 시작 전부터 첨부 분석 관련 수정 파일, `node_modules/`, `package.json`, `package-lock.json` 미추적 파일이 작업트리에 남아 있었다.

---

# 2026-08-11 - 견적서 금액 KRW 원화 표기 후처리

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Attachment Details UI, quote money formatting |
| 관련 파일 | `app/presentation/attachment_analysis.py`, `app/static/app.css`, `tests/test_attachment_analysis_presentation.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 견적서 첨부 Details에서 품목 `U/Price`, `Amount`와 `Total Price`의 `KRW` 표기를 `원`으로 바꾸는 후처리를 요청했다.

## 해결 방법

- 저장된 추출값은 변경하지 않고, Details 표시 row를 만드는 presentation layer에서 `KRW 130,000` 형태를 `130,000원`으로 변환하게 했다.
- 변환 대상은 `Total Price`, `U/Price`, `Amount`로 제한했다.
- 모바일에서 `130,000원`이 줄바꿈되지 않도록 품목 금액 컬럼의 `white-space`와 컬럼 폭을 보정했다.

## 검증

- `.venv/bin/pytest tests/test_attachment_analysis_presentation.py tests/test_mail_decision_ui.py -q`: 72 passed.
- `python -m py_compile app/presentation/attachment_analysis.py`: passed.
- Playwright로 `FM250016389_C0000105.pdf` Details를 열어 `KRW`가 남지 않고 `Total Price = 130,000원 (Vat Excluded)`, `U/Price = 6,500원`, `Amount = 130,000원`으로 표시되는 것을 확인했다.

## 남은 리스크와 후속 작업

- 현재 후처리는 표시 계층에만 적용되며 DB의 원본 추출 JSON은 유지된다.
- 이번 작업 전부터 존재한 `tests/test_mail_decision_ui.py`, 세션 로그 재정렬 diff, `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 남겨 둔다.

---

# 2026-08-11 - 견적서 품목 UI 배경 박스 제거

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Attachment Details UI, quote line items |
| 관련 파일 | `app/static/app.css`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 견적서 품목 UI가 하얀 배경 박스처럼 묶여 불필요하게 자리를 차지한다고 보고, 품목별 배경 박스를 제거해 달라고 요청했다.
- 배경색과 폰트 색상은 다른 Details 필드와 통일해 달라고 요청했다.

## 해결 방법

- 품목 내부 `.attachment-line-item`의 하얀 배경, 1px border, border-radius, 내부 padding을 제거했다.
- 품목 라벨은 기존 Details label과 같은 muted 색상/굵기를 사용하고, 값은 Details 값과 같은 text 색상과 13px 크기를 사용하게 했다.
- 품목 컬럼은 유지하되 Details 표 row의 기존 border와 spacing 안에서 표시되도록 조정했다.

## 검증

- `.venv/bin/pytest tests/test_attachment_analysis_presentation.py tests/test_mail_decision_ui.py -q`: 72 passed.
- `python -m py_compile app/presentation/attachment_analysis.py`: passed.
- Playwright로 `FM250016389_C0000105.pdf` Details를 열어 품목 UI를 검증했다. DOM상 `.attachment-line-item`은 `borderTopWidth=0px`, `borderTopStyle=none`, `backgroundColor=rgba(0, 0, 0, 0)`, `paddingTop=0px`이고, 품목 값과 컬럼 값은 유지된다.
- Desktop 1440x900과 mobile 390x844 스크린샷에서 품목별 흰색 박스가 제거되고 Details 표 톤과 맞는 것을 확인했다.

## 남은 리스크와 후속 작업

- Playwright 검증은 Chromium headless에서만 수행했다.
- 이번 작업 전부터 존재한 `tests/test_mail_decision_ui.py`, 세션 로그 재정렬 diff, `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 남겨 둔다.

---

# 2026-08-11 - 견적서 품목 UI 컬럼 표시

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Attachment Details UI, quote line items |
| 관련 파일 | `app/presentation/attachment_analysis.py`, `app/templates/partials/email_detail.html`, `app/static/app.css`, `tests/test_attachment_analysis_presentation.py`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 견적서 첨부 품목이 `Description O-RING / Qty 5 / Unit EA / U/Price 1,000 / Amount 5,000`처럼 한 줄 문자열로 표시되는 대신, 품목별로 `Description`, `Qty`, `Unit`, `U/Price`, `Amount` 컬럼과 값 행이 보이도록 UI를 수정해 달라고 요청했다.
- 품목별 행 테두리로 각 품목을 구분해 달라고 요청했다.

## 해결 방법

- `analysis_rows`의 품목 row에 `kind=line_item`과 `columns` 구조를 추가했다.
- 첨부 Details 템플릿에서 품목 row만 전체 폭을 쓰는 컬럼형 미니 그리드로 렌더링하게 했다.
- 품목별 1px 테두리, 라벨/값 5컬럼 정렬, 모바일 폭 축소 규칙을 CSS로 추가했다.

## 검증

- `.venv/bin/pytest tests/test_attachment_analysis_presentation.py tests/test_mail_decision_ui.py -q`: 72 passed.
- `python -m py_compile app/presentation/attachment_analysis.py`: passed.
- Playwright로 `http://127.0.0.1:8000/ui/inbox?email_uid=ee192748-01a0-5072-82d6-359941845f8e`를 열어 `FM250016389_C0000105.pdf` Details 품목 UI를 확인했다. Browser 플러그인은 사용할 수 없어 일반 Playwright를 사용했고, Chromium 설치 및 Docker web 재시작 후 검증했다.
- DOM 검증 결과 header는 `Description`, `Qty`, `Unit`, `U/Price`, `Amount`, 값은 `FILTER ELEMENT`, `20`, `EA`, `KRW 6,500`, `KRW 130,000`이며 품목 박스 border는 `1px solid`이다.

## 남은 리스크와 후속 작업

- Playwright 검증은 Chromium headless의 desktop 1440x900, mobile 390x844에서만 수행했다.
- 이번 작업 전부터 존재한 Settings 테스트 기대값 변경, 세션 로그 재정렬 diff, `node_modules/`, `package.json`, `package-lock.json`는 별도 변경으로 남겨 둔다.

---

# 2026-08-11 - 전체 견적서 첨부 재분석 및 세로형 PDF 표 보정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Attachment analysis, quote reanalysis |
| 관련 파일 | `app/document_processing/parsers.py`, `tests/test_attachment_parsers.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 고정 견적서 필드 기준으로 전체 메일 첨부파일 중 견적서를 재분석해 달라고 요청했다.
- 첫 실행에서 전체 non-inline 첨부 58개를 스캔했고, 현재 견적서 결과 22개와 파일명/텍스트 후보 30개를 확인했다.
- 모든 첨부를 파싱해 `quote`로 판별되는 항목을 저장했으나, 제목상 `견적의뢰서`와 일부 기술 문서가 섞여 들어와 새 current 결과 중 비견적서 12개를 확인했다.

## 해결 방법

- 비견적서로 저장된 새 current 결과는 이전 current가 있던 7개를 복원하고, 이전 결과가 없던 항목은 새 current에서 제외했다.
- 최종 재분석 대상은 제목에 `[견적서]`가 있고 `견적의뢰서`가 아닌 non-inline 첨부 28개로 제한했다.
- 기준 메일 `FM250016389`의 실제 PDF 텍스트에서 `Total Price`와 표 행이 여러 줄 토큰으로 분해되는 것을 확인하고, 세로형 금액/품목 토큰 복원 로직을 추가했다.
- 보정 후 28개 견적서 첨부를 `local-parser-v3-quote-vertical-schema` 결과로 current 저장했다.

## 검증

- `.venv/bin/pytest tests/test_attachment_parsers.py tests/test_attachment_analysis_presentation.py tests/test_postgres_attachment_analysis_repository.py -q`: 31 passed.
- `python -m py_compile app/document_processing/parsers.py`: passed.
- DB 검증 결과 current v3 견적서 결과는 28개, 비견적서 current v3 결과는 0개, line item이 있는 current v3 결과는 18개다.
- 기준 메일 `FM250016389_C0000105.pdf`는 `Total Price = KRW 130,000 (Vat Excluded)`와 품목 `FILTER ELEMENT / Qty 20 / Unit EA / U/Price KRW 6,500 / Amount KRW 130,000`을 current 결과에 저장했다.

## 남은 리스크와 후속 작업

- 28개 중 10개는 PDF 텍스트 구조상 품목 행을 복원하지 못해 `fixed_quote_schema_missing` warning이 남아 있다.
- 이번 작업 전부터 존재한 `session-log.md`, `tests/test_mail_decision_ui.py`, `node_modules/`, `package.json`, `package-lock.json` 변경은 별도 작업으로 남아 있다.

---

# 2026-08-11 - 견적서 첨부 고정 필드 추출 강화

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Attachment analysis, quote field extraction |
| 관련 파일 | `app/document_processing/parsers.py`, `app/document_processing/text_analyzer.py`, `app/document_processing/vision_analyzer.py`, `app/presentation/attachment_analysis.py`, `docs/features/attachment-analysis.md`, `tests/test_attachment_parsers.py`, `tests/test_attachment_analysis_presentation.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 시연 스크린샷 기준 메일 `Fw: [견적서] 플루맥스 FM250016389 / FRONT OTRA / Hyundai Samho Heavy Industries S777 / A-25021919 / 이병수`의 첨부 문서 유형이 견적서이며, 견적서에서 반드시 추출해야 하는 field 풀을 고정해 달라고 요청했다.
- 고정 필드는 `To`, `Attn`, `Your Ref No`, `Date`, `Our Ref No`, `In Charge`, `Tel`, `Vessel`, `Total Price`와 표 행별 `Description`, `Qty`, `Unit`, `U/Price`, `Amount`로 제한한다.
- 정보 추출에는 추출 후 검증, 재검토, 재실행에 해당하는 보정 흐름이 포함되어야 한다고 요청했다.

## 해결 방법

- 견적서(`quote`)의 고정 스키마에서 `No`, `Code`, `REMARK`, 납기 조건 같은 부가 필드를 제거하고, 표 데이터는 `line_items` 내부의 `Description`, `Qty`, `Unit`, `U/Price`, `Amount`만 보존하게 했다.
- `validated_predefined_document_fields`를 추가해 1차 필터링, 파싱 텍스트 기반 결정적 재추출, 최종 누락 검증을 한 흐름으로 실행하게 했다.
- 재추출 후에도 누락된 견적서 필드는 `fixed_quote_schema_missing:<field list>` warning으로 저장해 후속 재분석과 사람 검토 근거로 남긴다.
- 텍스트 LLM 보강과 비전 분석 결과도 같은 검증 함수를 통과하도록 연결했다.
- 공백 기반 견적서 표에서 `No` 열을 버리고 품목명, 수량, 단위, 단가, 금액을 추출하는 회귀 테스트를 추가했다.

## 검증

- `.venv/bin/pytest tests/test_attachment_parsers.py tests/test_attachment_analysis_presentation.py tests/test_postgres_attachment_analysis_repository.py -q`: 30 passed.
- `.venv/bin/pytest tests/test_mail_decision_ui.py tests/test_attachment_parsers.py tests/test_attachment_analysis_presentation.py tests/test_postgres_attachment_analysis_repository.py -q`: 79 passed.
- `python -m py_compile app/document_processing/parsers.py app/document_processing/text_analyzer.py app/document_processing/vision_analyzer.py app/presentation/attachment_analysis.py`: passed.

## 남은 리스크와 후속 작업

- 실제 FM250016389 원본 첨부파일은 저장소에서 확인되지 않아, 동일 제목 패턴과 FRONT OTRA/이병수/참조번호를 반영한 합성 텍스트 회귀 테스트로 검증했다.
- 현재 작업트리에는 이번 요청 전부터 존재한 `session-log.md` 정리 diff와 `node_modules/`, `package.json`, `package-lock.json` 미추적 파일이 남아 있다.

---

# 2026-08-11 - 첨부 유형 추정 summary Details 차단

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Attachment Details presentation |
| 관련 파일 | `app/presentation/attachment_analysis.py`, `tests/test_attachment_analysis_presentation.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 `~ 유형으로 추정됩니다` 같은 문서/이미지 유형 추정 문구를 Details로 출력하지 말고, 그런 경우 첨부파일 영역을 클릭해도 Details 영역이 열리지 않아야 한다고 정정했다.

## 해결 방법

- 표시용 `analysis_rows` 생성 단계에서 `analysis_summary`가 `유형으로 추정됩니다` 문구뿐이면 사용자용 `내용` row를 만들지 않도록 했다.
- 이 결과 템플릿의 기존 조건에 따라 해당 첨부는 정적 행으로 렌더링되고 Details가 열리지 않는다.
- `field_photo`처럼 사전 정의 필드 순서가 없는 문서 유형에서도 유형 추정 summary가 Details로 출력되지 않는 회귀 테스트를 추가했다.

## 검증

- `.venv/bin/pytest tests/test_attachment_analysis_presentation.py tests/test_mail_decision_ui.py`: 64 passed.

## 남은 리스크와 후속 작업

- 의미 있는 자유형 `analysis_summary`는 기존처럼 `내용` row로 표시한다. 운영에서 summary 문구 패턴이 달라지면 차단 조건을 확장해야 한다.

---

# 2026-08-11 - 첨부파일 빈 Details 제거

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox email detail, attachment analysis display |
| 관련 파일 | `app/templates/partials/email_detail.html`, `app/services/demo_mail_service.py`, `app/services/gmail_mail_service.py`, `app/static/app.css`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 첨부파일 클릭 시 표시할 정보 추출 결과가 없는 Details 영역이 열리는 동작을 제거해 달라고 요청했다.
- 문서 유형이나 이미지 유형만 Details로 출력하는 것도 의미 없는 정보이므로 같은 방식으로 처리해 달라고 요청했다.

## 해결 방법

- 첨부 `analysis_rows`가 있을 때만 `<details class="attachment">`와 `Details` 테이블을 렌더링하게 했다.
- 추출 결과가 없는 첨부는 정적 첨부 행으로 표시해 클릭해도 Details 영역이 열리지 않게 했다.
- 데모 첨부의 `Document`, `Checksum`, `Mapping` 행과 Gmail metadata-only 첨부의 `Content-Type`, `Gmail Attachment ID`, `Inline` 행을 제거했다.
- 정적 첨부 행은 클릭 가능한 커서로 보이지 않도록 CSS를 보정했다.

## 검증

- `.venv/bin/pytest tests/test_mail_decision_ui.py tests/test_attachment_analysis_presentation.py`: 63 passed.
- 시스템 `pytest` 명령은 설치되어 있지 않아 프로젝트 가상환경의 pytest로 재실행했다.

## 남은 리스크와 후속 작업

- 브라우저 스크린샷 검증은 실행하지 않았다.
- 이번 요청 전부터 존재한 업무 판단 패널, 세션 로그 정리, `node_modules/`, `package.json`, `package-lock.json` 변경은 이번 커밋 범위에서 제외한다.

---

# 2026-08-11 - 업무 판단 패널 확정 담당자 문구 제거

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox mail decision panel |
| 관련 파일 | `app/templates/partials/mail_decision_panel.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Inbox 탭의 `업무 판단 및 담당자 추천` 영역 하단에 표시되는 `~ 담당자로 확정됨` 텍스트 영역을 제거해 달라고 요청했다.

## 해결 방법

- 업무 판단 결과 패널에서 현재 확정 담당자 이름과 `담당자로 확정됨` 문구를 렌더링하던 `manual-assignment-confirmed` 블록을 제거했다.
- 검토 필요 상태에서 담당 후보가 없을 때 표시되는 `manual_assign_disabled_reason` 안내는 유지했다.
- 기존 확정 담당자 배너 렌더링 테스트를 배너 미표시 회귀 테스트로 변경했다.

## 검증

- `rg -n "담당자로 확정됨|manual-assignment-confirmed" app/templates/partials/mail_decision_panel.html app/templates app/static/app.css`로 템플릿 문구 제거를 확인했다.
- CSS에는 더 이상 렌더링되지 않는 `.manual-assignment-confirmed` 선택자가 남아 있지만, 이번 요청 전 CSS 변경 이력과 섞지 않기 위해 수정하지 않았다.
- `uv run pytest tests/test_mail_decision_ui.py -k mail_decision_panel_omits_confirmed_manual_assignment_banner_after_review -q`: passed.

## 남은 리스크와 후속 작업

- 템플릿 표시 제거만 수행했으며 별도 브라우저 스크린샷 검증은 실행하지 않았다.
- 이번 요청 전부터 존재한 세션 로그 정리 diff와 `node_modules/`, `package.json`, `package-lock.json` 미추적 파일은 이번 커밋 범위에서 제외한다.

---

# 2026-08-11 - Inbox TIME 컬럼 Pretendard 적용

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox Queue time column typography |
| 관련 파일 | `app/static/app.css`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 메일 목록의 `TIME` 컬럼에 표시되는 텍스트에도 한글 폰트를 적용해 달라고 요청했다.

## 확인한 사실

- Inbox row의 시간 셀은 `mono inbox-time-cell` class를 함께 사용하고 있어 전역 Pretendard 대신 monospace 계열이 적용될 수 있었다.

## 해결 방법

- Inbox 목록 내부의 `.inbox-time-cell`에 Pretendard 우선 `font-family` override를 추가했다.
- template class 구조는 유지해 Dashboard 등 다른 표의 시간 표시는 건드리지 않았다.

## 검증

- CSS diff를 확인했다.

## 남은 리스크와 후속 작업

- 시각 변경만 수행했으며 별도 브라우저 스크린샷 검증은 실행하지 않았다.
- 이번 요청 전부터 존재한 `app/templates/partials/mail_decision_panel.html` 수정, 세션 로그 정리 변경, `node_modules/`, `package.json`, `package-lock.json` 미추적 파일은 이번 커밋 범위에서 제외한다.

---

# 2026-08-11 - Inbox Queue Status 컬럼 폭 미세 조정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox Queue table layout |
| 관련 파일 | `app/static/app.css`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Inbox의 Inbox Queue에서 `Status` 컬럼 너비를 아주 살짝 키우고, 키운 너비만큼 `Subject` 컬럼을 줄여 달라고 요청했다.

## 해결 방법

- Inbox Queue 데스크톱 테이블의 최종 `inbox-status-col` 폭을 82px에서 88px로 6px 키웠다.
- 같은 6px만큼 `inbox-subject-col` 계산식의 고정 보정값을 84px에서 78px로 줄였다.
- 모바일 breakpoint의 별도 컬럼 폭은 이번 범위에서 유지했다.

## 검증

- CSS diff를 확인했다.

## 남은 리스크와 후속 작업

- 시각 변경만 수행했으며 별도 브라우저 스크린샷 검증은 실행하지 않았다.
- 이번 요청 전부터 존재한 세션 로그 정리 변경과 `node_modules/`, `package.json`, `package-lock.json` 미추적 파일은 이번 커밋 범위에서 제외한다.

---

# 2026-08-11 - 웹 UI 한글 폰트 Pretendard 적용

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Web UI typography |
| 관련 파일 | `app/static/app.css`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 현재 웹 서비스에서 한글 폰트를 바꾸고 싶다고 했고, 현재 디자인과 이질감이 적은 상업 무료 폰트를 추천해 달라고 요청했다.
- Pretendard를 추천한 뒤 사용자가 해당 폰트로 적용해 달라고 요청했다.

## 확인한 사실

- 앱 CSS는 앞쪽 `body` 선언에서 `Inter`를 사용하지만, 뒤쪽 Corporate Trust redesign override에서 `Plus Jakarta Sans`가 전역 폰트를 다시 덮어쓰고 있었다.
- Pretendard는 Inter 기반 UI와 어울리는 한글 UI 폰트이며, SIL Open Font License로 배포된다.

## 해결 방법

- `app/static/app.css` 상단에 Pretendard Variable dynamic subset 웹폰트 import를 추가했다.
- 앞쪽 기본 `body` 선언과 뒤쪽 최종 override의 `font-family`를 모두 Pretendard 우선 stack으로 바꿨다.
- Material Symbols와 monospace 본문 영역의 전용 폰트 선언은 유지했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- CSS diff를 확인했다.

## 남은 리스크와 후속 작업

- 현재 설정은 jsDelivr CDN의 Pretendard 웹폰트를 사용한다. 온프레미스/폐쇄망 배포에서는 Pretendard 파일을 정적 자산으로 self-hosting하는 방식으로 바꾸는 것이 좋다.
- 이번 요청 전부터 존재한 세션 로그 정리 변경과 `node_modules/`, `package.json`, `package-lock.json` 미추적 파일은 이번 커밋 범위에서 제외한다.

---

# 2026-08-11 - 웹 디자인 변경 롤백

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search UI, shell script, app CSS |
| 관련 파일 | `app/server.py`, `app/static/app.css`, `app/templates/shell.html`, `app/templates/views/search.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 웹 디자인이 망가졌다고 보고했고 다시 롤백해 달라고 요청했다.

## 해결 방법

- 미커밋 상태로 남아 있던 Search 화면, shell JS, CSS, Search 보조 서버 코드, 관련 UI 테스트 변경을 `HEAD` 기준으로 되돌렸다.
- 이미 커밋된 서버 안정화 변경과 Docker reload 제거 변경은 유지했다.
- Docker 기본 실행은 hot reload가 꺼져 있으므로 `web` 서비스를 재시작해 되돌린 파일을 실제 서버에 반영했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 47 passed.
- host 네트워크 기준 `curl http://127.0.0.1:8000/api/health`는 HTTP 200, 약 48ms로 응답했다.
- host 네트워크 기준 `curl http://127.0.0.1:8000/`는 인증 redirect인 HTTP 303, 약 1ms로 응답했다.

## 남은 리스크와 후속 작업

- `node_modules/`, `package.json`, `package-lock.json`는 미추적 상태로 남아 있다.
- 세션 로그 파일에는 이번 요청 전부터 존재한 미커밋 정리 변경이 남아 있으므로 이번 커밋에는 롤백 기록 hunk만 포함한다.

---

# 2026-08-11 - Docker reload 무한 로딩 재발 방지

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Docker dev server, attachment reanalysis, manual assignment UI |
| 관련 파일 | `docker-compose.yml`, `docs/development/docker-dev-environment.md`, `app/server.py`, `app/templates/partials/mail_decision_panel.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 배정 버튼 또는 첨부파일 분석 버튼을 여러 번 누른 뒤 웹 서버가 다시 무한 로딩된 것처럼 보인다고 보고했고, 근본 원인과 예방 방법을 요청했다.

## 확인한 사실

- 로그에서 첨부파일 재분석 요청 자체는 `204 No Content`로 빠르게 완료됐다.
- 무한 로딩이 발생한 직접 원인은 `StatReload detected changes in ...`가 여러 번 발생하며 uvicorn server process가 요청 처리 중 반복 재시작된 것이었다.
- 이전 수정에서 reload 감시 범위를 줄였지만 `docs`와 `tests`를 포함해 두었기 때문에 세션 로그나 테스트 수정만으로도 웹 서버가 재시작됐다.
- 첨부파일 재분석은 동기식으로 첨부 파싱과 LLM enrich를 수행하므로, 여러 메일에서 동시에 실행되면 서버 thread와 Ollama를 점유할 수 있다.

## 해결 방법

- Compose `web` 서비스의 기본 uvicorn 실행에서 `--reload`를 제거해 Docker 기본 실행을 안정 모드로 전환했다.
- Docker 개발 문서에 코드 변경 반영은 `docker compose restart web`로 명시 재시작하고, 자동 reload가 필요하면 host 디버깅 경로를 사용한다고 기록했다.
- 첨부파일 재분석에 서버 측 non-blocking lock을 추가해 한 번에 하나만 실행되도록 했고, 중복 요청은 HTTP 409로 거절한다.
- 담당 후보 배정 form에도 `hx-disabled-elt="find button"`을 추가해 제출 중 같은 form 버튼이 다시 눌리지 않게 했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 51 passed.
- `uv run pytest tests/test_mail_decision_routing_service.py tests/test_routing_policy.py -q`: 7 passed.
- `docker compose restart web` 후 `docker compose top web`에서 `python -m uvicorn app.server:app --host 0.0.0.0 --port 8000`만 실행되고 `--reload`가 없는 것을 확인했다.
- host 네트워크 기준 `curl http://127.0.0.1:8000/api/health`는 HTTP 200, 약 56ms로 응답했다.
- host 네트워크 기준 `curl http://127.0.0.1:8000/`는 인증 redirect인 HTTP 303, 약 1ms로 응답했다.

## 남은 리스크와 후속 작업

- Docker 기본 실행에서는 코드 수정 후 자동 반영되지 않는다. 변경을 반영하려면 `docker compose restart web`가 필요하다.
- 현재 작업트리에는 이번 요청 전부터 존재한 Search UI 관련 미커밋 변경과 `node_modules/`, `package.json`, `package-lock.json`가 남아 있다. 이번 커밋에는 재발 방지 hunk만 포함한다.

---

# 2026-08-11 - Inbox Message 헤더 높이 보정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox detail UI |
| 관련 파일 | `app/static/app.css`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Inbox에서 `Message` 제목 영역의 높이가 `Mail Overview`, `Summary` 제목 영역과 같도록 padding을 조정해 달라고 요청했다.

## 해결 방법

- Inbox detail의 `Message` 패널 제목 행에 최소 높이를 지정해 버튼이 있는 우측 패널 헤더와 같은 내용 높이를 유지하도록 조정했다.
- 기존 작업트리에 있던 unrelated 변경은 되돌리거나 포함하지 않았다.

## 검증

- `python -m py_compile app/server.py`: passed.

## 남은 리스크와 후속 작업

- 시각적 회귀 확인은 별도 브라우저 스크린샷 없이 CSS hunk 검토로 제한했다.

---

# 2026-08-11 - 업무 판단 패널 담당 후보 점수 표시 보정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Mail Decision panel, assignee candidate scores |
| 관련 파일 | `app/server.py`, `app/templates/partials/mail_decision_panel.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Inbox의 미할당 메일에서 담당 후보자별 `%` 정보를 추가해 달라고 요청했다.
- 이후 요청 범위가 Inbox 목록이나 Mail Overview가 아니라 `업무 판단 및 담당자 추천` 패널에만 해당한다고 정정했고, 다른 변경은 롤백해 달라고 요청했다.

## 해결 방법

- 범위를 벗어난 Inbox 목록, Mail Overview, PostgreSQL 메일 목록 후보 집계, 관련 CSS와 테스트 변경은 되돌렸다.
- `업무 판단 및 담당자 추천` 패널의 담당 후보 데이터에 `score_label`을 추가해 후보별 점수를 `%` 문자열로 명확히 전달한다.
- 템플릿은 `score_label`을 렌더링하도록 바꿔 `0%` 후보도 누락되지 않게 했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -q`: passed, 50 passed.

## 남은 리스크와 후속 작업

- 현재 작업트리에는 이번 요청 전부터 존재한 Search UI, shell, CSS, 세션 로그 관련 미커밋 변경과 `node_modules/`, `package.json`, `package-lock.json`가 남아 있다. 이번 변경은 업무 판단 패널 관련 hunk만 선별 커밋해야 한다.

---

# 2026-08-11 - 웹 서버 무응답 원인 수정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Docker dev server, routing assignment |
| 관련 파일 | `docker-compose.yml`, `app/repositories/postgres_routing_repository.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 웹 서버가 갑자기 접속되지 않고 무한 로딩되는 문제의 근본 원인을 찾아 해결해 달라고 요청했다.

## 확인한 사실

- host에서 `/api/health`, `/`, `/api/client-version` 요청이 TCP 연결 후 응답 없이 대기하거나 간헐적으로 연결 실패했다.
- `web` 컨테이너 로그에는 브라우저의 `api/ui-state`/`api/client-version` 반복 요청과 함께 직접 담당자 배정 시 PostgreSQL 오류가 남아 있었다.
- 오류 원인은 `routing_assignments LEFT JOIN users ... FOR UPDATE`가 nullable side를 포함한 join 전체에 잠금을 시도해 PostgreSQL에서 `FOR UPDATE cannot be applied to the nullable side of an outer join`을 발생시킨 것이었다.
- `web` 서비스는 `--reload`가 `/app` 전체를 감시해, 바인드 마운트된 `node_modules` 같은 큰 로컬 디렉터리까지 reloader가 훑는 상태였다. 이로 인해 dev server가 요청 처리보다 파일 감시에 CPU를 쓰며 무응답 상태로 빠질 수 있었다.

## 해결 방법

- 수동 배정 조회 SQL의 잠금 대상을 `FOR UPDATE OF ra`로 제한해 `routing_assignments` 행만 잠그도록 수정했다.
- Docker dev server의 uvicorn reload 감시 범위를 `app`, `db`, `docs`, `data`, `scripts`, `tests`로 제한해 `node_modules`와 기타 불필요한 루트 파일 감시를 제외했다.
- `web` 컨테이너를 recreate해 compose command 변경을 실제 실행 프로세스에 반영했다.

## 검증

- `python -m py_compile app/repositories/postgres_routing_repository.py app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 49 passed.
- `uv run pytest tests/test_mail_decision_routing_service.py tests/test_routing_policy.py -q`: 7 passed.
- `docker compose logs web`에서 reload 감시 경로가 `/app/app`, `/app/data`, `/app/db`, `/app/docs`, `/app/scripts`, `/app/tests`로 제한된 것을 확인했다.
- host 네트워크 기준 `curl http://127.0.0.1:8000/api/health`는 HTTP 200, 약 45ms로 응답했다.
- host 네트워크 기준 `curl http://127.0.0.1:8000/`는 인증 redirect인 HTTP 303, 약 2ms로 응답했다.

## 남은 리스크와 후속 작업

- 현재 작업트리에는 이번 요청 전부터 존재한 Search UI 관련 미커밋 변경, `node_modules/`, `package.json`, `package-lock.json`가 남아 있다. 이번 커밋에는 장애 수정과 세션 로그만 포함한다.

---

# 2026-08-11 - Inbox message 첨부 영역 간격 보정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox selected mail, message attachments spacing |
| 관련 파일 | `app/templates/partials/email_detail.html`, `app/static/app.css`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 첨부파일이 있는 Message에서 제목 하단 테두리와 첨부파일 사이 padding을 복원하고, 첨부파일 영역과 본문 사이 공백은 줄여야 했다.

## 해결 방법

- 첨부파일이 있는 Message body에 전용 class를 추가했다.
- 첨부파일이 있는 경우에만 top padding을 `8px`로 두고 내부 gap을 `6px`로 줄였다.

## 검증

- CSS/템플릿 diff를 확인했다.

---

# 2026-08-11 - Dashboard summary cards title relocation

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard category distribution, daily inflow, routing overview |
| 관련 파일 | `app/templates/views/dashboard.html`, `app/templates/partials/dashboard_distribution.html`, `app/templates/partials/dashboard_category_timeline.html`, `app/templates/partials/dashboard_routing_overview.html`, `app/static/app.css`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Dashboard 탭의 `Category Distribution`, `Daily Inflow`, `Routing Overview` 제목 영역을 제거하고, `Total Mails`, `Today Mails` 같은 stats 제목 스타일과 위치를 참고해 각 영역 내부 좌측 상단에 같은 스타일로 배치해 달라고 요청했다.

## 해결 방법

- 세 개 summary 패널의 외부 `panel-head` 제목 영역을 제거했다.
- 각 dashboard partial 내부 최상단에 `.label` 기반 제목과 기존 tooltip을 배치해 htmx partial 갱신 후에도 제목이 유지되도록 했다.
- dashboard 전용 CSS로 내부 제목 행, chart section 상단 정렬, summary panel body padding을 조정했다.

## 검증

- `pytest tests/test_mail_decision_ui.py`: failed. 로컬 PATH에 `pytest` 명령이 없어 실행하지 못했다.
- `uv run pytest tests/test_mail_decision_ui.py`: passed, 49 passed.

## 남은 리스크와 후속 작업

- 작업 시작 시점에 여러 기존 미커밋 변경과 staged CSS hunk가 있었으므로 이번 커밋에는 이 요청과 관련된 hunk만 선별 반영한다.
- 브라우저 스크린샷 검증은 수행하지 못했으며, 템플릿 렌더링 회귀 테스트로 확인했다.

---

# 2026-08-11 - Settings 담당자 관리 카운터 문구 단순화

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Settings 담당자 관리 헤더 |
| 관련 파일 | `app/templates/views/settings.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Settings 탭의 `담당자 관리` 제목 영역 오른쪽 텍스트에서 `운영`, `합성` 카운터를 제거하고 `전체`만 남겨 달라고 요청했다.

## 해결 방법

- 담당자 관리 패널 헤더의 라벨을 `전체 {{ assignees | length }}`만 표시하도록 변경했다.
- 설정 화면 회귀 테스트가 기존 `전체 · 운영 · 합성` 문자열이 사라지고 `전체` 카운터만 남는지 확인하도록 갱신했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py::test_settings_renders_synthetic_assignees_as_read_only_data_in_both_modes -q`: passed.

## 남은 리스크와 후속 작업

- 작업 시작 시점에 여러 기존 미커밋 변경이 있었으므로 이번 커밋에는 이 요청과 관련된 hunk만 선별 반영한다.

---

# 2026-08-11 - Inbox 검색/카테고리 필터 박스 제거

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox toolbar |
| 관련 파일 | `app/templates/views/inbox.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Inbox 탭 상단에서 검색 input과 카테고리 필터 select를 감싸는 박스 영역을 제거하고, 두 항목을 밖으로 꺼낸 뒤 위아래 padding을 줄여 달라고 요청했다.

## 해결 방법

- `views/inbox.html`에서 `panel toolbar-panel` 래퍼를 제거하고 검색/필터 컨트롤을 `inbox-toolbar` 안에 직접 배치했다.
- `inbox-toolbar`에는 border, background, shadow 없이 정렬과 작은 vertical padding만 적용했다.
- Inbox 템플릿이 `toolbar-panel` 없이 검색/필터 컨트롤을 유지하는지 확인하는 회귀 테스트를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k inbox_search_controls_are_not_wrapped_in_toolbar_panel`: passed.
- `http://127.0.0.1:8027/ui/inbox`에서 Playwright로 desktop 1440x900과 mobile 390x844 viewport를 확인했다.
- Playwright 확인 결과 `toolbarPanelCount`는 0이고, `#mailSearch` 입력 후 값이 `pump`로 유지되며 Inbox 본문이 렌더링됐다.
- 콘솔 404는 `/favicon.ico` 요청으로 확인되어 이번 변경과 무관하다.

## 남은 리스크와 후속 작업

- 현재 작업트리에 기존 미커밋 변경이 많아 이번 요청 hunk만 선별 staging한다.

---

# 2026-08-11 - Dashboard Mail Streams 제목 영역 padding 축소

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard Mail Streams header |
| 관련 파일 | `app/static/app.css`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Dashboard 탭에서 `Mail Streams`의 제목 영역 내부 요소에는 영향이 가지 않을 정도로 위아래 padding을 줄여 달라고 요청했다.

## 해결 방법

- `dashboard-mail-panel`의 직접 자식 `.panel-head`에만 dashboard 전용 `min-height`와 vertical padding을 적용했다.
- 제목, 툴팁, 필터 칩 같은 내부 요소의 margin, size, gap은 변경하지 않았다.
- 좁은 화면의 기존 반응형 header padding도 같은 기준으로 맞췄다.

## 검증

- CSS diff를 확인했다.
- 스타일 조정만 수행했으며 별도 브라우저 회귀 테스트는 실행하지 않았다.

## 남은 리스크와 후속 작업

- 현재 작업트리에 기존 미커밋 변경이 많고, `app/static/app.css`와 세션 로그에도 이번 작업 전 변경이 있어 이번 커밋에는 이번 요청 hunk만 선별 반영한다.

---

# 2026-08-11 - Inbox Mail Overview와 Summary 순서 및 제목 높이 조정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox selected mail detail, analysis panels |
| 관련 파일 | `app/templates/partials/email_detail.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Inbox 상세 화면에서 `Mail Overview` 항목과 `Summary` 항목의 순서를 바꾸고, `Message`, `Summary`, `Mail Overview`, `업무 판단 및 담당자 추천` 제목 영역의 padding을 줄여 제목 영역 높이를 낮춰 달라고 요청했다.

## 해결 방법

- `Mail Overview` 패널을 오른쪽 분석 스택의 `Summary` 패널보다 먼저 렌더링하도록 템플릿 순서를 바꿨다.
- Inbox 상세 카드 내부의 `.panel-head`에만 더 낮은 `min-height`와 작은 vertical padding을 적용해 다른 화면의 패널 헤더 기본값은 유지했다.
- Mail Overview가 Summary보다 먼저 렌더링되는지 확인하는 회귀 테스트를 추가했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py::test_email_detail_keeps_mail_overview_and_decision_panels_separate -q`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: failed. 현재 작업 전부터 수정되어 있던 `app/server.py`의 `mail_decision_panel_view()` 호출 인자와 함수 시그니처 불일치(`manual_assignment_options`)로 Mail Decision 패널 관련 6개 테스트가 실패했다.

## 남은 리스크와 후속 작업

- Browser 플러그인은 세션에 없어 렌더링 스크린샷 검증은 수행하지 못했다.
- 현재 작업트리에 기존 미커밋 변경이 많아 이번 변경과 무관한 diff가 함께 존재한다.

---

# 2026-08-11 - Inbox message 헤더 높이 유지 및 본문 간격만 축소

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox selected mail, message header and body spacing |
| 관련 파일 | `app/static/app.css`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Message 제목 영역 높이를 Mail Overview와 Summary 같은 다른 패널 헤더와 통일하고, 실제로 줄이려던 대상은 Message 헤더 하단 테두리와 이메일 본문 내용 사이의 공백이라고 정정했다.

## 해결 방법

- Message 헤더에는 별도 높이 축소 규칙을 추가하지 않고 공통 panel header 스타일을 따르게 유지했다.
- 앞쪽에 있던 Message body top padding 선언을 제거하고, 뒤쪽 cascade 위치에서 Inbox Message body의 top padding만 `2px`로 덮어쓰도록 했다.

## 검증

- CSS diff를 확인했다.
- 스타일 조정만 수행했으며 별도 브라우저 회귀 테스트는 실행하지 않았다.

## 남은 리스크와 후속 작업

- 현재 작업트리에 사용자의 기존 미커밋 변경이 있어 이번 변경 외 diff도 함께 존재한다.

---

# 2026-08-11 - Inbox message 헤더 하단 padding 최소화

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox selected mail, message body spacing |
| 관련 파일 | `app/static/app.css`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Inbox 탭 selected mail의 Message 제목 경계선과 본문 시작 사이 padding을 더 줄여 최소한의 padding만 남겨 달라고 요청했다.

## 해결 방법

- Message 패널 본문 top padding을 `8px`에서 `2px`로 줄였다.

## 검증

- CSS diff를 확인했다.
- 스타일 조정만 수행했으며 별도 브라우저 회귀 테스트는 실행하지 않았다.

## 남은 리스크와 후속 작업

- 현재 작업트리에 사용자의 기존 미커밋 변경이 있어 이번 변경 외 diff도 함께 존재한다.

---

# 2026-08-11 - Inbox message 헤더와 본문 간격 축소

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox selected mail, message body spacing |
| 관련 파일 | `app/static/app.css`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Inbox 탭의 selected mail 내부 Message 제목 영역의 밑 경계선부터 본문 내용 시작까지의 padding을 줄여 달라고 요청했다.

## 해결 방법

- Message 패널 본문 영역의 top padding을 줄였다.
- 본문 wrapper의 추가 top margin을 제거해 헤더 경계선과 본문 시작 사이의 빈 공간을 줄였다.

## 검증

- CSS diff를 확인했다.
- 스타일 조정만 수행했으며 별도 브라우저 회귀 테스트는 실행하지 않았다.

## 남은 리스크와 후속 작업

- 현재 작업트리에 사용자의 기존 미커밋 변경이 있어 이번 변경 외 diff도 함께 존재한다.

---

# 2026-08-11 - Inbox message 본문 내부 박스 제거

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox selected mail, message body UI |
| 관련 파일 | `app/static/app.css`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Inbox 탭의 selected mail 내부 Message 항목에서 본문을 둘러싸는 박스 테두리 한 겹과 과한 공백/padding을 제거해 달라고 요청했다.

## 해결 방법

- 본문 wrapper의 위쪽 여백을 줄였다.
- HTML 본문과 plain text 본문 wrapper의 border, radius, background, padding을 제거해 Message 패널 내부에서 본문이 불필요한 추가 박스 없이 표시되도록 했다.

## 검증

- CSS diff를 확인했다.
- 스타일 조정만 수행했으며 별도 브라우저 회귀 테스트는 실행하지 않았다.

## 남은 리스크와 후속 작업

- 현재 작업트리에 사용자의 기존 미커밋 변경이 있어 이번 변경 외 diff도 함께 존재한다.

---

# 2026-08-11 - Gmail 권한 설정 안내 문구 축소

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gmail settings modal, OAuth permission UI |
| 관련 파일 | `app/templates/shell.html`, `app/templates/partials/gmail_sync_settings.html`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Gmail 계정 권한 설정 창에서 `Gmail Sync` 라벨, 연결 계정 권한 안내 문장, 요청 권한의 상세 설명과 `https://mail.google.com/` scope 표시 영역을 제거하라고 요청했다.

## 해결 방법

- Gmail 설정 모달 헤더의 `Gmail Sync` 보조 라벨을 제거했다.
- 연결 상태 hero에서 계정별 Gmail 권한 처리 안내 문단을 제거했다.
- 요청 권한 섹션에서 권한 상세 설명 문장과 scope chip 목록 렌더링을 제거했다.

## 검증

- 제거 요청 문자열이 UI 템플릿에 남아 있지 않은 것을 `rg`로 확인했다.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 47 passed.

## 남은 리스크와 후속 작업

- 문구 제거만 수행했으며 OAuth scope 자체와 Gmail 동기화 동작은 변경하지 않았다.

---

# 2026-08-11 - 상단 탭 제목 간소화

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Topbar UI, Shell template |
| 관련 파일 | `app/templates/shell.html`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 상단 탭/페이지 제목의 긴 영문 라벨을 짧은 탭 이름으로 바꾸라고 요청했다.
- 변경 대상은 Dashboard, Inbox, Search, Settings 표시 문자열이다.

## 해결 방법

- 초기 Dashboard 제목을 `Dashboard`로 바꿨다.
- HTMX 화면 전환 후 `syncPageTitle()`이 쓰는 제목 매핑을 `Dashboard`, `Inbox`, `Search`, `Settings`로 바꿨다.
- 탭 버튼 자체는 이미 짧은 라벨을 사용하고 있어 추가 수정하지 않았다.

## 검증

- 기존 긴 상단 제목 문자열이 UI 템플릿, 정적 파일, 테스트 코드에 남아 있지 않은 것을 `rg`로 확인했다.

## 남은 리스크와 후속 작업

- 표시 텍스트만 바꾼 변경이라 별도 브라우저 회귀 테스트는 실행하지 않았다.

---

# 2026-08-11 - 검토 필요 담당 후보 내 배정 UI 간소화

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Human review, manual assignment UI, Settings routing priority |
| 관련 파일 | `app/server.py`, `app/templates/partials/mail_decision_panel.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py`, `docs/features/assignee-routing.md`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 검토 필요 직접 배정 UI에서 사유 항목을 제거하고, Settings 탭의 담당자 우선순위 배정 데이터를 기반으로 담당자를 선택할 수 있게 해달라고 요청했다.
- 이어서 별도 영역을 만들지 말고 기존 `담당 후보` 영역에서 담당자를 간단하게 배정할 수 있게 하며, 담당 영역, 소속, 직급 정보를 추가하라고 요청했다.
- UI는 padding을 줄이고 부수적인 설명 텍스트를 제외해 최대한 단순하게 구성하길 요청했다.

## 해결 방법

- 수동 배정 form에서 사유 입력과 설명 문장을 제거하고 별도 `직접 배정` 영역도 없앴다.
- 기존 `담당 후보` 목록에 Settings의 운영 담당자 카테고리 배정 기준 후보를 합쳐 표시하고, 각 후보 행에서 바로 배정할 수 있게 했다.
- 담당 후보에는 담당 영역, 소속, 직급, 이메일, 점수를 표시한다.
- API 요청 모델에서도 `reason` 필드를 제거했다.
- form padding/gap과 grid 구성을 줄여 select와 배정 버튼 중심으로 압축했다.

## 검증

- `python -m py_compile app/server.py app/repositories/postgres_routing_repository.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 48 passed.

## 남은 리스크와 후속 작업

- Settings 탭의 drag reorder는 현재 서버 저장 없이 화면 갱신만 수행하므로, 이 UI는 저장된 카테고리 배정 데이터 기준으로 우선순위를 계산한다.

---

# 2026-08-11 - 검토 필요 메일 직접 담당자 배정 구현

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Human review, assignee routing, Inbox UI, API |
| 관련 파일 | `app/repositories/postgres_routing_repository.py`, `app/server.py`, `app/templates/partials/mail_decision_panel.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py`, `docs/features/human-review-corrections.md`, `docs/features/assignee-routing.md`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 `검토필요` 상태일 때 사람이 직접 담당자를 배정할 수 있도록 UI와 백엔드를 구현해달라고 요청했다.
- 문서 기준상 사용자 확정 담당자는 AI 결과를 덮어쓰지 않고 라우팅 현재값과 이벤트/감사 이력으로 남겨야 한다.

## 해결 방법

- `review_required` 상태의 최신 Mail Decision Run 또는 라우팅 배정에 한해 활성 운영 담당자를 직접 배정할 수 있게 했다.
- 배정 시 `routing_assignments`는 `assigned`/`assignment_source=user`로 갱신하고, `routing_events`와 `audit_logs`에 before/after를 기록한다.
- 수동 배정으로 검토가 해결되면 최신 `mail_decision_runs.status`를 `completed`로 닫고 `state_json.context.human_review`에 해결 정보를 남긴다.
- 업무 판단 패널에 담당자 선택 form을 추가하고, `PATCH/POST /api/emails/{email_uid}/routing` API를 추가했다.

## 검증

- `python -m py_compile app/server.py app/repositories/postgres_routing_repository.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 47 passed.
- 전역 `pytest` 명령은 설치되어 있지 않아 실패했고, `uv run pytest`로 재실행했다.

## 남은 리스크와 후속 작업

- 이번 구현은 담당자 직접 배정에 한정한다. 업무 레이블, 요약, 긴급도, 핵심 정보 수정 API는 아직 남아 있다.
- 실제 PostgreSQL 트랜잭션 동작은 기존 schema 계약에 맞춰 구현했지만, 별도 통합 DB 테스트는 추가하지 않았다.

---

# 2026-08-11 - Docker 재시작 시 demo seed 중복키 장애 해결

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Docker dev bootstrap, PostgreSQL demo seed |
| 관련 파일 | `app/repositories/postgres_seed_writer.py`, `tests/test_demo_seed_service.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 `docker compose up --build -df` 실행 후 웹 접속이 안 된다고 보고했고, 정상 복구 뒤 같은 일이 재발하지 않도록 근본 원인 해결을 요청했다.
- 확인 결과 `web` 컨테이너가 bootstrap 중 `assignee_capabilities_unique` 중복키로 실패해 uvicorn까지 도달하지 못하고 재시작 루프에 빠져 있었다.

## 확인한 사실

- PostgreSQL/Qdrant/Ollama 컨테이너와 볼륨은 정상 유지되고 있었다.
- `PostgresSeedWriter`는 모든 seed row를 `ON CONFLICT (id)`로만 upsert했다.
- `assignee_capabilities` schema는 `(user_id, capability_type, capability_value)`를 업무 유일키로 가지며, 기존 DB에 같은 역량이 다른 id로 남아 있으면 반복 seed가 실패할 수 있었다.
- `users` 테이블은 같은 id로 이메일이 바뀐 기존 데이터가 있어, 일반 seed 테이블을 모두 자연키 upsert로 바꾸면 오히려 primary key 충돌이 발생했다.

## 해결 방법

- `assignee_capabilities` seed만 schema의 업무 유일키 `(user_id, capability_type, capability_value)` 기준으로 upsert하게 했다.
- 다른 seed 테이블은 기존처럼 `id` 기준 upsert를 유지해 기존 개발 DB의 deterministic id 갱신 흐름을 보존했다.
- seed conflict key 누락 시 명확히 실패하는 방어 로직과 regression test를 추가했다.

## 검증

- `uv run pytest tests/test_demo_seed_service.py`: 5 passed.
- `python -m py_compile app/repositories/postgres_seed_writer.py`: passed.
- `docker compose exec -e CORAMAIL_DEV_SEED_DEMO=true web python -m app.tools.bootstrap_dev_environment`: passed.
- `docker compose up --build -d web`: passed.
- `curl -sS -i http://127.0.0.1:8000/api/health`: `200 OK`.

## 남은 리스크와 후속 작업

- 이번 수정은 실제 장애를 만든 `assignee_capabilities` 반복 seed 충돌에 한정했다.
- 다른 seed 테이블에서 업무 유일키와 id가 엇갈린 운영성 데이터가 생기면 별도 reconcile 정책이 필요하다.

---

# 2026-08-10 - 수동 전달 확인 알림 중앙 모달 개선

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard tab, manual routing confirm dialog |
| 관련 파일 | `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 전달 버튼 클릭 시 뜨는 기본 팝업 알림창 디자인을 웹 디자인과 일관성 있게 개선하고, 화면 가운데에 표시되게 해달라고 요청했다.
- 이후 추가 확인을 중단하라고 요청해 더 이상의 렌더링 검증은 진행하지 않았다.

## 해결 방법

- `hx-confirm` 흐름을 유지하되 `htmx:confirm` 이벤트를 가로채 앱 스타일 중앙 모달로 표시하게 했다.
- 확인 버튼은 원래 HTMX 요청을 `issueRequest(true)`로 이어가고, 취소/ESC/backdrop은 요청 없이 모달을 닫게 했다.
- Gmail 설정 모달과 같은 backdrop/box-shadow/radius 계열을 사용하고, 전달 버튼 계열의 파란 톤과 icon을 적용했다.
- 모바일 폭에서는 모달을 1열로 바꾸고 버튼이 같은 폭으로 배치되게 했다.

## 검증

- `.venv/bin/pytest tests/test_mail_decision_ui.py -q`: 43 passed.
- `python -m py_compile app/server.py app/services/postgres_mail_service.py`: passed.
- 사용자의 확인 중단 지시 전까지 Playwright/Chromium으로 desktop 중앙 배치, mobile 중앙 배치, 취소/확인 동작, console error 없음까지 확인했다.

## 남은 리스크와 후속 작업

- 사용자가 확인 중단을 요청해 추가 브라우저 검증은 수행하지 않았다.
- 모바일 dashboard에서는 기존 CSS 정책상 manual route 컬럼이 숨겨져 있어 실제 버튼 클릭 대신 모달 함수를 직접 열어 layout만 확인했다.

---

# 2026-08-10 - Dashboard 라우팅 지표 문구 정리

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard tab, stats cards, Routing Overview |
| 관련 파일 | `app/templates/partials/stats.html`, `app/templates/partials/dashboard_routing_overview.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 dashboard 탭의 `AI Auto-Routed`, `AI Auto-Classified` 문구를 각각 `Routed`, `Classified`로 바꾸길 요청했다.
- Routing Overview에서 Assigned는 퍼센트가 큰 글씨이지만 Unassigned는 건수가 큰 글씨로 표시되어, 둘 다 퍼센트를 큰 글씨로 맞추길 요청했다.

## 확인한 사실

- 상단 통계 카드 문구는 `app/templates/partials/stats.html`에서 렌더링된다.
- Routing Overview의 Assigned/Unassigned 카드는 `app/templates/partials/dashboard_routing_overview.html`에서 렌더링된다.
- 작업 시작 전부터 `app/server.py`, `app/static/app.css`, `app/templates/shell.html`, `app/templates/views/search.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` 변경과 `node_modules/`, `package.json`, `package-lock.json` 미추적 파일이 있었고, 이번 요청과 무관한 변경은 되돌리지 않았다.

## 해결 방법

- 통계 카드 label을 `Classified`, `Routed`로 변경했다.
- Unassigned 카드의 큰 글씨를 `unassigned_percent`로 바꾸고, 건수는 Assigned와 같은 형식의 작은 보조 텍스트로 표시하게 했다.
- UI 템플릿 테스트에 새 문구와 Unassigned 퍼센트 렌더링 단언을 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py::test_dashboard_summary_excludes_unclassified_and_unassigned_rows`: passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 이번 문구/표시 위치 변경 범위에서는 수행하지 않았다.

---

# 2026-08-10 - Inbox HTML 메일 본문 렌더링 복원

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox tab, email detail, Gmail HTML body, inline images, attachments |
| 관련 파일 | `app/mail_content.py`, `app/services/postgres_mail_service.py`, `app/repositories/postgres_mail_repository.py`, `app/repositories/postgres_gmail_sync_repository.py`, `app/services/gmail_mail_service.py`, `app/server.py`, `db/postgresql/001_initial_schema.sql`, `db/postgresql/005_attachment_inline_metadata.sql`, `docs/architecture/postgresql_schema.md`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 inbox 탭의 message 영역에서 메일 본문이 원본처럼 렌더링되지 않는다고 보고했다.
- 기존 `coramail_ai`에서는 본문 HTML의 이미지, 이모티콘, 텍스트 강조를 그대로 표시했고, 본문 내 inline 이미지는 첨부파일 영역에 표시하지 않아야 한다고 설명했다.

## 확인한 사실

- `coramail_ai` 구현은 HTML 본문을 iframe `srcdoc`로 렌더링하고, attachment payload의 `content_id`와 `view_url`을 사용해 `cid:` 이미지를 실제 파일 URL로 치환했다.
- `coramail_agent` 템플릿은 이미 `email.body_html_srcdoc` iframe 표시를 지원했지만, PostgreSQL 상세 payload가 이 값을 채우지 않았다.
- 현재 PostgreSQL attachment 목록은 `is_inline IS FALSE`만 조회해 attachment 영역에서 inline 이미지를 제외하고 있었지만, 그 때문에 본문 `cid:` 치환에 필요한 inline attachment도 상세 payload에 전달되지 않았다.
- 기존 schema는 `is_inline`만 저장하고 `Content-ID`, `Content-Disposition`을 보존하지 않아, 재동기화 전 기존 메일은 일부 inline 이미지 치환 정보가 없을 수 있다.
- 작업 시작 전부터 Search UI, manual route modal, session-log 변경과 `node_modules/`, `package.json`, `package-lock.json` 미추적 파일이 있었고 이번 커밋 범위에서 제외했다.

## 해결 방법

- 공통 메일 본문 helper를 추가해 HTML 강조, 이모티콘, 표 등 원본 HTML을 iframe `srcdoc`로 감싸고 `cid:` 이미지와 CSS `url(cid:...)`를 inline attachment URL로 치환하게 했다.
- PostgreSQL 상세 조회는 전체 attachment를 한 번 조회해 inline 이미지는 본문 `srcdoc` 치환에만 사용하고, 화면 첨부 목록에는 기존처럼 non-inline 파일만 표시한다.
- inline 본문 리소스 URL은 `?inline=true`를 사용해 전체 attachment index 기준으로 파일을 찾게 하고, 일반 첨부 URL은 표시 대상 첨부 index 기준을 유지했다.
- Gmail sync 저장소와 schema에 `content_id`, `content_disposition` 컬럼을 추가해 이후 동기화부터 inline 이미지 매핑 정보를 보존한다.

## 검증

- `python -m py_compile app/mail_content.py app/repositories/postgres_mail_repository.py app/services/postgres_mail_service.py app/repositories/postgres_gmail_sync_repository.py app/services/gmail_mail_service.py app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py tests/test_gmail_persistent_mode.py -q`: 53 passed.
- `python -m app.tools.apply_postgres_schema --dry-run`: 5 files, 92 statements.
- `uv run ruff check app/mail_content.py app/repositories/postgres_mail_repository.py app/services/postgres_mail_service.py app/repositories/postgres_gmail_sync_repository.py app/services/gmail_mail_service.py app/server.py tests/test_mail_decision_ui.py tests/test_gmail_persistent_mode.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 45 passed.

## 남은 리스크와 후속 작업

- 이미 저장된 Gmail 메일은 기존 schema에 `content_id`가 없었으므로, inline 이미지가 완전히 표시되려면 migration 적용 후 Gmail 재동기화가 필요할 수 있다.
- Browser plugin은 세션에 없었다. 실제 Gmail HTML 본문 screenshot 검증은 운영 Gmail 데이터와 로컬 로그인 상태가 필요해 이번 검증 범위에서는 단위/템플릿 payload 테스트로 대체했다.

---

# 2026-08-10 - 담당자 전달 완료 후 업무 상태 표시 전환

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard tab, inbox row status, manual routing |
| 관련 파일 | `app/services/postgres_mail_service.py`, `app/templates/partials/mail_rows.html`, `app/static/app.css`, `docs/features/assignee-routing.md`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 담당자에게 메일 전달이 완료된 뒤 row의 status도 `전달 완료`처럼 함께 바뀌어야 한다고 요청했다.

## 확인한 사실

- 수동 전달 성공 시 저장소는 이미 최신 `manual_route_forward` 알림을 `sent`로 만들고 `routing_assignments.status`를 `forwarded`로 갱신한다.
- 화면용 `work_status` 계산은 확정 담당자가 있으면 `assigned`를 먼저 반환해, 전달 완료 후에도 `배정 완료`로 표시될 수 있었다.
- 작업 시작 전부터 Search UI 관련 변경, `node_modules/`, `package.json`, `package-lock.json` 미추적 파일이 있었고 이번 변경과 무관해 그대로 두었다.

## 해결 방법

- PostgreSQL 메일 row 변환에서 `routing_status='forwarded'` 또는 최신 수동 전달 알림 `sent`를 `work_status='forwarded'`로 우선 표시하게 했다.
- `forwarded` 업무 상태 라벨을 `전달 완료`로 추가하고 row icon/color 매핑을 연결했다.
- 라우팅 기능 문서에 dashboard/mailbox 업무 상태가 라우팅 상태와 최신 수동 전달 알림을 함께 반영한다는 기준을 기록했다.

## 검증

- `.venv/bin/pytest tests/test_mail_decision_ui.py -q`: 42 passed.
- `pytest tests/test_mail_decision_ui.py -q`는 기본 셸에 `pytest`가 없어 실행되지 않았다.

## 남은 리스크와 후속 작업

- 실제 Gmail API 발송 자체는 이번 변경 범위가 아니며, 기존 수동 전달 저장 흐름의 결과를 UI 상태로 반영하는 변경이다.

---

# 2026-08-10 - Dashboard 수동 전달 완료 상태 자동 갱신

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard tab, manual routing, HTMX refresh |
| 관련 파일 | `app/templates/partials/mail_rows.html`, `app/templates/shell.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 dashboard 전달 버튼 클릭 후 `전달 중`까지는 표시되지만, 백그라운드 전달이 완료되어도 새로고침 전까지 `전달 완료`로 바뀌지 않는다고 보고했다.

## 확인한 사실

- 수동 전달 시작 응답은 dashboard row fragment를 `pending` 상태로 갱신하지만, 백그라운드 Gmail 발송 완료 시점에는 브라우저로 push되는 이벤트가 없다.
- 기존 `/api/ui-state` polling digest는 row 수와 서비스 버전 중심이라 `notifications.status`가 `pending`에서 `sent`로 바뀌는 것만으로는 즉시 row refresh가 보장되지 않았다.

## 해결 방법

- 수동 전달 버튼에 `data-manual-route-button`, `data-manual-route-status`를 추가해 브라우저가 pending row를 감지할 수 있게 했다.
- dashboard row에 pending 수동 전달이 있으면 `/ui/mail-rows?view=dashboard`를 짧은 간격으로 다시 요청하고, pending이 사라지면 자동으로 polling을 멈추도록 했다.
- 전달 버튼 요청 성공, dashboard row fragment swap, dashboard 최초 로드/재진입 시 pending 감지를 시작하도록 했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py`: 40 passed.
- `uv run ruff check`를 HTML/Jinja 파일에 직접 실행하면 템플릿을 Python으로 파싱해 실패하므로 이번 검증에서 제외했다.

## 남은 리스크와 후속 작업

- Browser plugin은 세션에 없어서 실제 브라우저 screenshot 검증은 수행하지 못했다.
- 완료 반영 지연은 polling 간격인 약 1.5초와 Gmail 발송 완료 시점에 따라 달라진다.

---

# 2026-08-10 - Dashboard 수동 담당자 전달 기능 이식

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard tab, manual routing, Gmail forwarding, routing audit |
| 관련 파일 | `app/server.py`, `app/integrations/gmail/sync_client.py`, `app/services/gmail_mail_service.py`, `app/services/postgres_mail_service.py`, `app/repositories/postgres_mail_repository.py`, `app/repositories/postgres_routing_repository.py`, `tests/test_mail_decision_ui.py`, `tests/test_gmail_persistent_mode.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 dashboard 탭의 `전달` 버튼으로 담당자에게 수동 라우팅하려는 기능이 동작하지 않는다고 보고했다.
- 정상 동작하던 `coramail_ai` 구현을 가져와 `coramail_agent`에 이식해 달라고 요청했다.

## 확인한 사실

- `coramail_agent`의 `/ui/emails/{email_ref}/route-manual` 라우트는 실제 Gmail 발송 없이 dashboard row fragment만 다시 렌더링하는 stub였다.
- `coramail_ai`의 정상 구현은 수동 전달 클릭 시 먼저 delivery `pending` 상태를 저장하고, 백그라운드 thread에서 Gmail `send`를 호출한 뒤 성공/실패 상태를 기록한다.
- `coramail_agent`에는 별도 delivery log 테이블이 없고, 현재 문서와 스키마상 수동 전달 상태는 `notifications`, 최종 라우팅 상태와 감사 이력은 `routing_assignments`, `routing_events`에 기록하는 편이 맞다.
- 작업 시작 전부터 Search UI 관련 변경과 `node_modules/`, `package.json`, `package-lock.json` 미추적 파일이 있었고 이번 작업과 무관해 그대로 두었다.

## 해결 방법

- Gmail MIME 발송 helper를 추가해 담당자에게 `Fwd:` 형식의 수동 전달 메일과 저장된 첨부파일을 보낼 수 있게 했다.
- dashboard 수동 전달 라우트가 Gmail 모드에서 실제 전달 작업을 시작하도록 stub를 교체했다. 데모 모드에서는 외부 발송 없이 기존처럼 fragment만 갱신한다.
- 수동 전달 시작 시 `notifications.notification_type = manual_route_forward`, `status = pending`을 기록하고, 성공 시 `sent`와 Gmail provider message id를 저장한다.
- 전달 성공 시 `routing_assignments.status = forwarded`, `forwarded_at`을 갱신하고 `routing_events.event_type = forwarded`, `source = user` 이력을 남긴다.
- 목록 row가 최신 수동 전달 notification을 읽어 `전달 중`, `전달 완료`, `전달 실패/재전달`, `미전달`, `미할당` 버튼 상태를 표시하도록 했다.

## 검증

- `python -m py_compile app/server.py app/services/gmail_mail_service.py app/services/postgres_mail_service.py app/repositories/postgres_mail_repository.py app/repositories/postgres_routing_repository.py app/integrations/gmail/sync_client.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py tests/test_gmail_persistent_mode.py`: 46 passed.
- `uv run ruff check app/integrations/gmail/sync_client.py app/services/gmail_mail_service.py app/services/postgres_mail_service.py app/repositories/postgres_mail_repository.py app/repositories/postgres_routing_repository.py app/server.py tests/test_mail_decision_ui.py tests/test_gmail_persistent_mode.py`: passed.
- Browser plugin은 세션에 없었다. 실제 Gmail API 발송은 로컬 인증/운영 계정이 필요한 외부 동작이라 fake Gmail service 단위 테스트와 UI row 상태 테스트로 검증했다.

## 남은 리스크와 후속 작업

- 백그라운드 thread 기반 전달은 프로세스 재시작 시 진행 중 작업 복구가 되지 않는다. 운영 자동 전달까지 확장할 때는 durable worker와 재시도 정책으로 승격해야 한다.
- 현재 실패 상태는 `notifications.status = failed`에 기록하고 `routing_assignments`는 기존 배정 상태를 유지한다.

---

# 2026-08-10 - Search 시작점을 실제 메일함 데이터 기반으로 전환

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search tab, mailbox metadata, recent business refs |
| 관련 파일 | `app/server.py`, `app/templates/views/search.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Search 입력창 아래의 고정 질문 작성 UI와 테스트용 질문을 모두 제거하고, 현재 메일함의 실제 최근 메일과 업무번호를 Search 시작점으로 보여 달라고 요청했다.
- 질문 action은 자동 검색을 실행하지 않고 입력창에 자연어 질문만 작성해야 한다.
- 이번 작업 범위에서 commit과 push는 하지 말라고 명시했다.

## 확인한 사실

- 기존 고정 composer는 `app/templates/views/search.html`, `app/templates/shell.html`, `app/static/app.css`에 분산되어 있었다.
- `/ui/search`는 `search_context()`를 통해 렌더링되고, `/ui/search-results` 제출 흐름은 HTMX form으로 유지된다.
- 현재 mailbox adapter들은 `list_emails()`와 `classification.business_refs`를 제공하므로 Search 화면 진입 시 LLM이나 embedding 호출 없이 최근 메일과 최근 업무를 구성할 수 있다.
- 작업 시작 전부터 미추적 `node_modules/`, `package.json`, `package-lock.json`가 있었고 이번 변경과 무관해 그대로 두었다.

## 해결 방법

- `data-search-composer`, `data-search-context`, `data-search-topic`, `data-search-template` 기반 HTML, JS, CSS를 제거했다.
- Search placeholder를 fixture나 특정 업무번호에 의존하지 않는 문장으로 변경했다.
- `received_at DESC` 기준 최근 메일 5건을 서버에서 구성하고 subject, sender, received time, category를 표시하도록 했다.
- `business_refs`를 업무번호별로 grouping해 최근 관련 메일 시각 기준으로 정렬하고 sender, category, mail count를 표시하도록 했다.
- 최근 메일/업무 row는 semantic button으로 만들고, 선택된 row에만 action button을 보여주도록 했다.
- action click은 input value와 focus만 변경하며 `/ui/search-results`를 호출하지 않는다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 36 passed.
- `uv run pytest tests/test_mail_search_service.py -q`: 15 passed.
- `node /tmp/coramail_search_ui_check.js`: passed. Browser plugin은 세션에 없어서 Playwright를 사용했고, 설치된 Playwright가 기대하는 Chromium revision은 없었으나 기존 cache의 Chromium headless shell을 명시해 검증했다.

## 남은 리스크와 후속 작업

- attachment analysis field 기반의 `금액·수량·납기`, `품목·수량·납기` action 확장은 이번 1차 구현에서 제외했다.
- 현재 PostgreSQL demo-source 데이터의 최신 메일 일부는 `business_refs`가 비어 있어 `최근 업무`가 표시되지 않을 수 있다. Direct demo fixture에서는 업무 grouping이 표시된다.
- 사용자가 명시적으로 제외했으므로 commit과 push는 수행하지 않았다.

---

# 2026-08-10 - 담당자 샘플 이메일 도메인 다원이앤씨로 변경

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo seed, 담당자 샘플 데이터 |
| 관련 파일 | `data/demo/mail_decision_foundation.seed.json`, `tests/test_demo_seed_service.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 담당자 샘플 이메일 주소의 도메인을 `dawonict.co.kr`로 바꿔 달라고 요청했다.

## 확인한 사실

- 작업 시작 전 `app/server.py`, `app/templates/shell.html`, `app/templates/views/search.html`에 미커밋 수정이 있었고 이번 변경과 무관해 건드리지 않았다.
- 기존 담당자 seed 이메일은 `@fluemax.co.kr` 도메인을 사용하고 있었다.

## 해결 방법

- 담당자 8명의 `email` 값만 `@dawonict.co.kr` 주소로 교체했다.
- seed 테스트의 이메일 도메인 기대값만 새 도메인으로 맞췄다.
- 실행 중인 Docker PostgreSQL의 기존 담당자 8행도 `email` 컬럼만 같은 값으로 업데이트했다.

## 검증

- `docker compose exec postgres psql ... select name,email from users ...`: 담당자 8명 모두 `@dawonict.co.kr` 확인.
- `uv run pytest tests/test_demo_seed_service.py`: 2 passed.
- `uv run python -m app.tools.export_demo_seed --check`: passed.

## 남은 리스크와 후속 작업

- 없음. 미커밋 app 파일들과 Node 관련 미추적 파일은 이번 작업 범위에서 제외했다.

---

# 2026-08-10 - 담당자 샘플 이메일 주소 현실화

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo seed, 담당자 샘플 데이터 |
| 관련 파일 | `data/demo/mail_decision_foundation.seed.json`, `tests/test_demo_seed_service.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 현재 담당자들의 메일 샘플 데이터에서 메일 주소만 더 그럴싸한 값으로 바꿔 달라고 요청했다.

## 확인한 사실

- 담당자 샘플 데이터는 `data/demo/mail_decision_foundation.seed.json`의 `users` 배열에 있다.
- 기존 값은 `@example.invalid` 도메인을 사용하고 있었다.
- 작업 시작 전부터 미추적 `node_modules/`, `package.json`, `package-lock.json`가 있었고 이번 작업과 무관해 그대로 두었다.

## 해결 방법

- 담당자 8명의 `email` 값만 `@fluemax.co.kr` 형식의 주소로 교체했다.
- seed 테스트의 이메일 도메인 기대값만 새 도메인으로 맞췄다.
- 실행 중인 Docker PostgreSQL의 기존 담당자 8행도 `email` 컬럼만 같은 값으로 업데이트했다.

## 검증

- `uv run python -m app.tools.export_demo_seed --check`: passed.
- `uv run pytest tests/test_demo_seed_service.py`: 2 passed.
- `docker compose exec postgres psql ... select name,email from users ...`: 담당자 8명 모두 `@fluemax.co.kr` 확인.

## 남은 리스크와 후속 작업

- 새 주소는 데모용 합성 주소이며 실제 운영 담당자 주소로 사용하면 안 된다.

---

# 2026-08-10 - Inbox 담당 후보 UI 밀도 조정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox, Mail Decision panel, routing candidate UI |
| 관련 파일 | `app/templates/partials/mail_decision_panel.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Inbox 탭의 `업무 판단 및 담당자 추천` 영역 안에 있는 담당 후보 결과 UI를 수정해 달라고 요청했다.
- 구체적으로 후보 이메일을 이름 오른쪽으로 옮기고, 각 담당자별 영역의 높이를 줄이는 것이 목표였다.

## 확인한 사실

- 담당 후보 목록은 `app/templates/partials/mail_decision_panel.html`에서 렌더링된다.
- 기존 UI는 이름과 점수를 첫 줄에 표시하고 이메일을 별도 문단으로 아래에 표시해 후보 카드가 세로로 커졌다.
- 작업 시작 전부터 미추적 `node_modules/`, `package.json`, `package-lock.json`가 있었고 이번 작업과 무관해 그대로 두었다.

## 해결 방법

- 후보 이름과 이메일을 같은 identity row에 배치하고 이메일 전용 class를 추가했다.
- 후보 카드의 padding, gap, border radius를 줄여 담당자별 영역 높이를 낮췄다.
- 이메일이 길 때 한 줄 말줄임 처리되도록 CSS를 추가했다.
- 후보 이메일이 더 이상 별도 `<p>` 문단으로 렌더링되지 않는지 테스트를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -q`: 32 passed.
- `git diff --check -- app/templates/partials/mail_decision_panel.html app/static/app.css tests/test_mail_decision_ui.py`: passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경은 서버 렌더링과 CSS 밀도 조정에 한정된다.
- 미추적 Node 파일들은 이번 변경에 포함하지 않는다.

---

# 2026-08-10 - Receiver 검토 필요 표시를 미할당으로 통일

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Mail Streams, Inbox Receiver column, routing overview |
| 관련 파일 | `app/server.py`, `app/services/postgres_mail_service.py`, `app/static/app.css`, `tests/test_mail_decision_ui.py`, `docs/development/coramail-ai-feature-parity.md`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 status에 `검토 필요`가 있더라도 Receiver 칼럼의 `검토 필요` 표시는 모두 `미할당`으로 바꿔 달라고 요청했다.

## 확인한 사실

- 이전 구현은 `routing_status = review_required`인 경우 Receiver에 `검토 필요`를 표시했다.
- 템플릿 헬퍼도 과거 `담당자 검토 필요` 값을 `검토 필요`로 정규화하고 있었다.
- Receiver에서 검토 필요를 미할당으로 합치면 Routing Overview의 미할당 count가 늘고, 기존 workload bar 계산이 미할당 count를 기준에 포함할 수 있었다.

## 해결 방법

- PostgreSQL 메일 행과 classification payload의 미확정 routing display를 모두 `미할당`으로 통일했다.
- 템플릿 표시 헬퍼는 `검토 필요`와 `담당자 검토 필요`를 모두 `미할당`으로 정규화한다.
- Receiver review 전용 CSS를 제거했다.
- Routing Overview의 담당자 workload bar는 미할당을 제외한 담당자 count 기준으로 계산하게 수정했다.

## 검증

- `python -m py_compile app/server.py app/services/postgres_mail_service.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 31 passed.
- `git diff --check`: passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경은 서버 렌더링과 summary 계산, CSS 정리에 한정된다.
- 미추적 `node_modules/`, `package.json`, `package-lock.json`는 이번 작업과 무관해 커밋하지 않는다.

---

# 2026-08-10 - Search 질문 작성 도우미로 전환

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search tab, RAG question composer |
| 관련 파일 | `app/templates/views/search.html`, `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 앞선 Search 가이드가 단순 예시 버튼에 가까워 원하는 방향이 아니라고 설명했다.
- 목표는 사용자가 더 편리하게 질문할 수 있도록 돕는 것이며, 고정 질문을 제출하는 버튼보다 질문을 작성하고 조합하는 경험이 필요하다.

## 확인한 사실

- Search 탭은 HTMX로 `/ui/search-results`에 `q`를 제출한다.
- Search 화면은 동적 fragment로 로드되므로, 질문 도우미 동작은 shell 수준의 이벤트 위임으로 처리해야 탭 전환 후에도 유지된다.
- 현재 Browser 플러그인은 세션에 없고, 로컬 Node는 `v12.22.9`라 설치된 Playwright가 사용하는 문법을 파싱하지 못해 브라우저 자동 검증이 실패했다.

## 해결 방법

- 입력창 아래의 제출형 예시 버튼을 제거하고 `검색 질문 작성 도우미`로 교체했다.
- 사용자가 `범위`에서 최근 메일, 최근 견적, 참조번호, 첨부파일을 고르고 `확인 항목`에서 납기, 금액, 수량, 품번, 요청사항을 조합하면 입력창에 자연어 질문 초안이 생성되게 했다.
- `바로 시작` 버튼은 검색을 즉시 실행하지 않고 입력창에 질문 초안을 넣어 사용자가 수정 후 검색할 수 있게 했다.
- 선택된 칩에는 활성 상태를 표시하고, 모바일에서도 줄바꿈되도록 CSS를 정리했다.
- UI 렌더링 테스트를 새 질문 작성 도우미 구조에 맞게 갱신했다.

## 검증

- `git diff --check -- app/templates/views/search.html app/templates/shell.html app/static/app.css tests/test_mail_decision_ui.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 31 passed.
- `curl -s http://127.0.0.1:8021/ui/search | head -5`: 서버 HTML 응답 확인.
- Playwright 브라우저 검증은 실패: 로컬 `node v12.22.9`가 설치된 Playwright의 `??` 문법을 파싱하지 못했다.

## 남은 리스크와 후속 작업

- 실제 브라우저 클릭 검증과 스크린샷 검증은 Node 런타임 제약 때문에 수행하지 못했다.
- 운영 UX를 더 다듬으려면 최근 메일의 실제 메타데이터나 선택된 Inbox 메일을 Search context로 전달하는 기능을 별도 설계해야 한다.
- 미추적 `node_modules/`, `package.json`, `package-lock.json`는 이번 작업과 무관해 커밋하지 않는다.

---

# 2026-08-10 - Search RAG 질문 가이드 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search tab, RAG question guidance |
| 관련 파일 | `app/templates/views/search.html`, `app/templates/partials/search_results.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Search 탭이 RAG 챗봇처럼 보이지만 `안녕하세요` 같은 일반 대화에는 답하지 않는 점을 확인했다.
- 일반 챗봇이 아니라 메일·첨부 근거 기반 질문에 답한다는 사용 가이드를 입력 영역 근처에 더 명확히 보여 달라고 요청했다.
- 최근 메일을 context로 넣는 레이블/토큰 버튼과 적절한 질문 유형 제안을 예시로 제시했다.

## 확인한 사실

- Search 탭은 `/ui/search-results` HTMX GET 폼으로 동작하며, `q` 값을 검색 서비스에 전달한다.
- `button type="submit" name="q" value="..."`를 사용하면 별도 JavaScript 없이 제안 질문을 기존 검색 흐름에 태울 수 있다.
- 기존 테스트는 Search 화면에 가짜 prefilled query가 없어야 하고 `/ui/search-answer` 옛 endpoint를 쓰지 않아야 한다.

## 해결 방법

- 검색 입력 아래에 `최근 메일 context`와 `질문 유형` 두 줄의 제안 버튼을 추가했다.
- 제안 버튼은 가장 최신 메일, 최근 메일 납기, 최근 견적 금액·납기, 참조번호, 첨부 유형, 필드 확인 질문을 제출한다.
- 빈 상태 설명을 일반 대화가 아니라 최근 메일, 참조번호, 납기, 금액, 수량, 첨부 문서 유형처럼 메일 근거가 있는 질문에 답한다고 바꿨다.
- 제안 버튼이 줄바꿈되고 모바일에서 입력 영역을 밀어내지 않도록 CSS를 추가했다.
- UI 렌더링 테스트에 제안 가이드 존재 여부를 추가했다.

## 검증

- `git diff --check -- app/templates/views/search.html app/templates/partials/search_results.html app/static/app.css tests/test_mail_decision_ui.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 31 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경은 서버 렌더링 HTML/CSS와 단위 UI 테스트로 확인했다.
- `안녕하세요` 자체를 small-talk fallback으로 답변하는 서비스 변경은 이번 범위에 포함하지 않았다.
- 미추적 `node_modules/`, `package.json`, `package-lock.json`는 이번 작업과 무관해 커밋하지 않는다.

---

# 2026-08-10 - Receiver 칩 카테고리 테두리 복원

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Mail Streams, Inbox Receiver column styling |
| 관련 파일 | `app/static/app.css`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 `RECEIVER` 칼럼에도 원래 레이블 버튼과 같은 디자인 테두리를 넣어 달라고 요청했다.

## 확인한 사실

- `receiver-chip`은 `category-chip--order`, `category-chip--inquiry` 같은 카테고리 색상 클래스를 함께 받는다.
- 그러나 `.chip.receiver-chip`의 `border: 0.5px solid transparent` shorthand가 앞서 지정된 카테고리별 `border-color`를 투명색으로 덮고 있었다.

## 해결 방법

- `.chip.receiver-chip`에서 border shorthand를 제거하고 `border-style`과 `border-width`만 지정했다.
- 카테고리별 `border-color`는 기존 레이블 버튼 클래스에서 그대로 적용되게 했다.

## 검증

- `git diff --check -- app/static/app.css`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 31 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 변경은 CSS 우선순위 수정에 한정된다.
- 미추적 `node_modules/`, `package.json`, `package-lock.json`는 이번 작업과 무관해 커밋하지 않는다.

---

# 2026-08-10 - Receiver 칼럼 담당자 칩 스타일과 검토 문구 수정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Mail Streams, Inbox mail rows, Receiver column routing display |
| 관련 파일 | `app/server.py`, `app/services/postgres_mail_service.py`, `app/templates/partials/mail_rows.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py`, `docs/development/coramail-ai-feature-parity.md`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Mail Streams와 Inbox 메일 목록의 `RECEIVER` 칼럼에서 발주, 문의, 서비스, 기술, 기타 담당자 표시를 각각 같은 색상과 디자인으로 맞춰 달라고 요청했다.
- `담당자 검토 필요` 문구는 `검토 필요`로 줄여 표시하도록 요청했다.

## 확인한 사실

- 메일 목록은 `app/templates/partials/mail_rows.html`에서 공통 렌더링되며, Dashboard/Mail Streams와 Inbox가 같은 partial을 사용한다.
- `routing_display`는 PostgreSQL 메일 행 변환과 Mail Decision 패널에서 `담당자 검토 필요`를 기본 빈 담당자 라벨로 사용하고 있었다.
- 기존 카테고리 칩 색상 클래스가 발주, 문의, 서비스, 기술, 기타에 이미 정의되어 있었다.
- 작업 중 인덱스에는 이전 Search UI 변경의 staged CSS/세션 로그 변경이 존재했으므로 이번 커밋 범위에서 분리해야 한다.

## 해결 방법

- `RECEIVER` 셀을 텍스트 대신 `receiver-chip`으로 렌더링하고, 담당자 값은 해당 행의 업무 카테고리 색상 클래스를 재사용하게 했다.
- `검토 필요`와 `미할당`은 담당자 배정 완료로 집계하지 않도록 유지하고, 과거 `담당자 검토 필요` 값도 화면에서는 `검토 필요`로 정규화한다.
- PostgreSQL 메일 행과 Mail Decision 패널의 빈 담당자 라벨을 `검토 필요`로 바꿨다.
- 관련 UI 테스트에 카테고리별 receiver chip 클래스 검증을 추가했다.

## 검증

- `python -m py_compile app/server.py app/services/postgres_mail_service.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py -q`: 31 passed.
- `pytest tests/test_mail_decision_ui.py -q`: failed because `pytest` is not installed on PATH; `uv run pytest`로 대체했다.

## 남은 리스크와 후속 작업

- 실제 브라우저 스크린샷 검증은 수행하지 않았다. 이번 변경은 서버 렌더링 HTML/CSS와 단위 UI 테스트로 확인했다.
- 미추적 `node_modules/`, `package.json`, `package-lock.json`와 기존 staged Search 변경은 이번 작업과 무관해 수정하지 않는다.

---

# 2026-08-10 - Search 쿼리 입력 중간 테두리 제거

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search tab, RAG query input styling |
| 관련 파일 | `app/static/app.css`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Search 탭에서 쿼리 입력 영역이 이중 박스로 감싸져 보이므로 중간 박스 테두리를 제거해 달라고 요청했다.

## 확인한 사실

- Search 화면은 바깥 `panel`, 중간 `form.search-box`, 실제 입력창 `.input`이 각각 시각적 박스를 형성하고 있었다.
- 중간 박스는 `app/static/app.css`의 `.search-box`에 적용된 `border`로 표시되고 있었다.
- 작업 시작 시점에 `app/server.py`, `app/services/postgres_mail_service.py`, `node_modules/`, `package.json`, `package-lock.json`와 `app/static/app.css` 일부에는 기존 미커밋 변경이 있었다.

## 해결 방법

- `.search-box`의 border를 제거해 바깥 패널과 입력창 테두리만 남겼다.
- 기존 미커밋 변경은 이번 작업 범위에서 수정하거나 stage하지 않는다.

## 검증

- `git diff --check -- app/static/app.css`: passed.

## 남은 리스크와 후속 작업

- 시각적 변경은 CSS 한 줄이므로 별도 브라우저 스크린샷 검증은 수행하지 않았다.

---

# 2026-08-10 - Mail Streams 담당자 배정 상태 표시 정합성 수정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Mail Streams, Inbox/Dashboard mail rows, routing assignment display |
| 관련 파일 | `app/services/postgres_mail_service.py`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Mail Streams의 status 칼럼이 `대기`로 표시되는데 같은 행에 담당자 배정이 표시되는 이유를 근본 원인 분석 후 해결해 달라고 요청했다.
- 사용자는 담당자 표시가 잘못되었거나 status가 잘못된 것 중 하나라고 지적했다.

## 확인한 사실

- 목록 row의 `work_status`는 `classification_result_status`, `summary_result_status`, `processing_jobs`, `mail_decision_runs`, `routing_assignments`를 합쳐 계산한다.
- 기존 `_work_status()`는 `pending` 분석 결과를 `routing_assignments.status = assigned`보다 먼저 평가해, 이미 현재 라우팅이 배정된 행도 `대기`로 표시할 수 있었다.
- 담당자 표시도 `routing_status`와 무관하게 `assignee_name` 값만 있으면 배정처럼 보이게 해, `pending` 또는 `review_required` 라우팅에 남은 stale assignee 값이 UI 모순을 만들 수 있었다.

## 해결 방법

- `routing_assignments.status`가 `assigned`, `forwarded`, `completed`이고 담당자 값이 있을 때만 확정 담당자로 표시하도록 `PostgresMailboxService`에 기준 함수를 추가했다.
- 확정 담당자가 있으면 `pending` 분석 결과보다 `배정 완료` 상태가 우선되게 `work_status` 계산 순서를 수정했다.
- 확정되지 않은 라우팅에 남아 있는 담당자 값은 목록/분류 payload에서 표시하지 않고 `미할당` 또는 `담당자 검토 필요`로 표시한다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "postgres_mail_row"`: 3 passed, 27 deselected.
- `uv run pytest tests/test_mail_decision_ui.py`: 30 passed.
- `python -m py_compile app/services/postgres_mail_service.py`: passed.

## 남은 리스크와 후속 작업

- 작업 시작 시점의 미추적 `node_modules/`, `package.json`, `package-lock.json`은 이번 수정과 무관해 커밋하지 않는다.
- 실제 DB에 `routing_status = pending/review_required`이면서 `assignee_user_id`가 남은 기존 데이터가 있다면 화면에서는 숨겨지지만, 데이터 정리 마이그레이션은 별도 작업으로 검토할 수 있다.

---

# 2026-08-10 - Search 질문 텍스트 표시 제거

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search tab, RAG query input, evidence panel header |
| 관련 파일 | `app/templates/views/search.html`, `app/templates/partials/search_results.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Search 탭에서 쿼리 입력 영역 위의 `메일·첨부 RAG 질문` 가시 텍스트를 제거해 달라고 요청했다.
- 사용자는 근거 영역 박스 상단 우측에 표시되는 질문 쿼리 텍스트도 제거해 달라고 요청했다.

## 확인한 사실

- 입력 라벨은 `app/templates/views/search.html`에서 `<label class="search-box-label">`로 렌더링되고 있었다.
- 근거 패널 우측의 질문 텍스트는 `app/templates/partials/search_results.html`의 `search-query-label` 배지로 렌더링되고 있었다.

## 해결 방법

- 입력 영역의 가시 라벨을 제거하고, 접근성을 위해 동일 문구를 `aria-label`로만 유지했다.
- 근거 패널 헤더의 `search-query-label` 배지 렌더링을 제거했다.
- Search UI 테스트에 라벨과 질문 배지가 렌더링되지 않는다는 단언을 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "search_ui_and_api_share_search_service or search_view_has_no_fake_prefilled_query"`: 2 passed, 26 deselected.
- `uv run pytest tests/test_mail_decision_ui.py`: 28 passed.

## 남은 리스크와 후속 작업

- 작업 시작 전부터 있던 Inbox 패널 분리 관련 변경과 미추적 `node_modules/`, `package.json`, `package-lock.json`은 이번 변경과 무관하다.

---

# 2026-08-10 - Inbox Mail Overview와 업무 판단 패널 분리

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox detail UI, Mail Overview panel, Mail Decision panel |
| 관련 파일 | `app/templates/partials/email_detail.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Inbox에서 `Mail Overview`와 `업무 판단 및 담당자 추천` 영역 박스가 구분되지 않고 이어져 보이므로 `Summary` 영역처럼 개별 영역으로 구분해 달라고 요청했다.

## 확인한 사실

- `Mail Overview` 패널 하단의 라우팅 근거 블록이 HTML 주석 처리되어 있었고, 그 과정에서 `Mail Overview` 패널을 닫는 `</div>`까지 주석 안에 들어가 있었다.
- 이 때문에 렌더링된 DOM에서 `업무 판단 및 담당자 추천` 패널이 `Mail Overview` 패널 안에 중첩되어 두 영역이 시각적으로 이어져 보일 수 있었다.

## 해결 방법

- `Mail Overview` 패널에 `mail-overview-panel` 식별 클래스를 추가했다.
- 주석 처리된 라우팅 근거 블록 밖에서 `Mail Overview` 패널을 닫도록 템플릿 구조를 수정해 `업무 판단 및 담당자 추천` 패널이 형제 패널로 렌더링되게 했다.
- 회귀 방지를 위해 렌더링된 HTML에서 `mail-decision-inspector`가 `mail-overview-panel` 안에 중첩되지 않는지 확인하는 테스트를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k "email_detail_renders_mail_decision_latest_lazy_load or email_detail_keeps_mail_overview_and_decision_panels_separate"`: 2 passed, 26 deselected.
- `uv run pytest tests/test_mail_decision_ui.py`: 28 passed.

## 남은 리스크와 후속 작업

- 작업 시작 전부터 있던 미추적 `node_modules/`, `package.json`, `package-lock.json`은 이번 변경과 무관해 커밋에 포함하지 않는다.

---

# 2026-08-10 - Dashboard 카테고리 색상 통일

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard Mail Streams filter, Category Distribution chart palette |
| 관련 파일 | `app/server.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Dashboard 탭의 `Mail Streams` 상단 우측 카테고리 필터 버튼 색상을 기존 분류 레이블 표시 색상과 통일해 달라고 요청했다.
- `Category Distribution`의 `미분류` 색상도 기존 레이블 색상과 통일하고, `Mail Streams`의 `전체` 버튼 색상은 회색에서 검정색으로 바꿔 달라고 요청했다.

## 확인한 사실

- 기존 분류 레이블 chip 색상은 `app/static/app.css`의 `category-chip--*` 클래스에 정의되어 있었다.
- `Mail Streams` 필터 버튼과 `Category Distribution` 차트 팔레트는 `app/server.py`의 `category_filter_visual()`과 `category_chart_palette()`에서 별도 색상 값을 사용하고 있었다.
- Daily Inflow 범례는 이미 레이블 chip 색상과 같은 계열을 사용하고 있었다.

## 해결 방법

- `category_filter_visual()`의 각 카테고리 색상을 기존 레이블 chip 색상과 같은 background, text, border, dot 값으로 맞췄다.
- `전체` 필터 버튼은 배경을 유지하되 글자, 테두리, dot을 검정 계열로 변경했다.
- `category_chart_palette()`의 `미분류`를 포함한 카테고리 팔레트를 레이블 chip 색상과 같은 기준으로 변경했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py`: 27 passed.

## 남은 리스크와 후속 작업

- 작업 시작 전부터 있던 미추적 `node_modules/`, `package.json`, `package-lock.json`은 이번 변경과 무관해 커밋에 포함하지 않는다.

---

# 2026-08-10 - Inbox 업무 판단 클릭 중 임시 텍스트 제거

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox detail UI, Mail Decision panel, HTMX loading indicator |
| 관련 파일 | `app/templates/partials/mail_decision_panel.html`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Inbox에서 `업무 판단` 버튼을 눌렀을 때 왼쪽에 텍스트가 잠깐 뜨지만 박스 영역을 벗어나 보이지 않는 부분을 제거해 달라고 요청했다.

## 확인한 사실

- Mail Decision panel의 액션 row에는 HTMX 요청 중 `분석 중...` 텍스트를 표시하는 `.mail-decision-loading` indicator가 있었다.
- 버튼은 같은 indicator를 `hx-indicator`로 지정해 클릭 중 해당 텍스트가 표시되도록 되어 있었다.

## 해결 방법

- 업무 판단 버튼 클릭 중 표시되는 `분석 중...` indicator span을 제거했다.
- 버튼의 `hx-indicator` 참조도 함께 제거해 보이지 않는 임시 텍스트가 다시 렌더링되지 않게 했다.
- 관련 렌더링 테스트에 해당 텍스트와 class가 없는지 확인하는 assertion을 추가했다.

## 검증

- `.venv/bin/python -m pytest tests/test_mail_decision_ui.py -k mail_decision_panel`: 4 passed, 23 deselected.
- 시스템 Python의 `python -m pytest ...`는 `pytest` 모듈이 없어 실행되지 않았고, 저장소 가상환경으로 재실행했다.

## 남은 리스크와 후속 작업

- 작업 시작 전부터 있던 미추적 `node_modules/`, `package.json`, `package-lock.json`은 이번 변경과 무관해 커밋에 포함하지 않는다.

---

# 2026-08-10 - Search 근거 본문 노출 제거

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search UI, RAG answer evidence, mail detail navigation |
| 관련 파일 | `app/templates/partials/search_results.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Search 탭에서 답변이 나온 뒤 근거 영역에 메일 본문이 plain text로 표시되는 영역을 제거하고, `원본 메일 보기` 버튼을 적절한 위치와 크기로 옮기라고 요청했다.

## 확인한 사실

- Search 결과 partial은 각 근거 카드에서 `item.preview`를 일반 문단으로 렌더링해 메일 본문 또는 첨부 미리보기 텍스트를 그대로 노출했다.
- `원본 메일 보기` 링크는 카드 본문 하단에 있었고 `btn-secondary`, `btn-sm` 클래스는 현재 CSS에서 정의되지 않아 버튼 크기 의도가 명확히 적용되지 않았다.

## 해결 방법

- 근거 카드에서 `item.preview` 문단 렌더링을 제거해 Search 탭 HTML에 원문 미리보기 텍스트가 표시되지 않게 했다.
- `원본 메일 보기` 버튼을 근거 카드 헤더 오른쪽 액션 영역으로 옮기고, 검색 결과 카드 전용 작은 보조 버튼 스타일과 아이콘을 적용했다.
- UI 테스트가 preview 텍스트 미노출과 기존 API 응답 유지 경로를 검증하도록 갱신했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py`: 27 passed.

## 남은 리스크와 후속 작업

- API 검색 응답의 `preview` 필드는 유지했다. 이번 요청은 Search 탭의 plain text 표시 제거에 한정했고, 검색 서비스 계약 자체는 변경하지 않았다.
- 작업 시작 전부터 있던 미추적 `node_modules/`, `package.json`, `package-lock.json`은 이번 변경과 무관해 커밋에 포함하지 않는다.

---

# 2026-08-10 - Inbox bulk 재분류/재요약 버튼 제거

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox UI, classification regeneration, summary regeneration, Mail Decision Run alignment |
| 관련 파일 | `app/templates/views/inbox.html`, `app/server.py`, `app/static/app.css`, `docs/features/email-classification.md`, `docs/features/email-summary.md`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Inbox 탭의 `전체 재분류`, `전체 재요약` 버튼 동작 현황 확인과 불필요시 삭제 판단 근거 정리를 요청했다.
- 확인 결과를 바탕으로 삭제 진행을 요청했다.

## 확인한 사실

- Inbox 상단 bulk 버튼은 각각 `/ui/classifications/regenerate-all`, `/ui/summaries/regenerate-all`에 연결되어 있었다.
- 해당 서버 엔드포인트는 작업 등록, 워커 실행, 진행 상태 저장 없이 상태 partial만 다시 렌더링했다.
- `inbox_context()`는 bulk 상태를 항상 idle/empty 값으로 반환해 버튼을 눌러도 전체 재처리가 시작되지 않았다.
- 단건 재분류/재요약은 별도 경로에서 `processing_jobs`를 만들고 worker를 실행하므로 실제 동작 경로가 남아 있다.
- 목표 아키텍처는 독립 `classification`/`executive_summary` job 흐름을 임시 데모로 분류하고, 메일 단위 `Mail Decision Run` 통합 실행을 기준으로 삼는다.

## 해결 방법

- Inbox 툴바에서 bulk 재분류/재요약 버튼 partial include를 제거했다.
- 무동작 bulk UI/status 엔드포인트와 idle context 값을 제거했다.
- 더 이상 사용되지 않는 bulk partial 파일과 CSS 규칙을 삭제했다.
- 기능 문서의 현재 구현 계약에서 bulk UI 엔드포인트 항목을 제거했다.

## 검증

- `rg -n "bulk-summary-regeneration|classification_bulk_regeneration|summary_bulk_regeneration|regenerate-all|inbox_bulk|전체 재분류|전체 재생성" app docs tests`: no matches.
- `uv run pytest tests/test_mail_decision_ui.py`: 27 passed.

## 남은 리스크와 후속 작업

- 향후 대량 재실행이 필요하면 독립 summary/classification bulk 버튼이 아니라 필터 조건 기반 `Mail Decision Run` 재실행 기능으로 새로 설계해야 한다.
- 작업 시작 전부터 있던 미추적 `node_modules/`, `package.json`, `package-lock.json`은 이번 변경과 무관해 커밋에 포함하지 않았다.

---

# 2026-08-10 - Gmail connected 계정 라벨 식별 보강

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gmail connected status, account identity, topbar label |
| 관련 파일 | `app/repositories/gmail_account_repository.py`, `app/services/gmail_mail_service.py`, `tests/test_gmail_oauth_service.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Gmail이 connected 상태로 보이는데 상단 Gmail 버튼 텍스트가 메일 주소가 아니라 `Gmail 계정 미확인`으로 표시되는 이유를 물었고, 근본 원인 분석 후 해결을 요청했다.

## 확인한 사실

- 상단 버튼 텍스트는 설정 모달의 `gmail_sync.connected`가 아니라 `GmailMailboxService.status()["account"]` 값을 사용한다.
- `GOOGLE_TOKEN_JSON`은 OAuth access/refresh token 중심 데이터라서 이메일 주소를 포함하지 않는 경우가 정상적으로 있다.
- 기존 코드는 token 존재만으로 connected 상태를 true로 보면서도, token 안에 `account`, `email`, `email_address`가 없고 `gmail_account.json` 메타데이터도 없으면 계정명을 확인할 방법이 없어 `Gmail 계정 미확인`으로 fallback했다.
- 즉 문제의 근본 원인은 connected 여부와 계정 identity 보장이 서로 다른 상태인데, token-only connected 상태에서 Gmail profile 조회·저장 경로가 없었던 것이다.

## 해결 방법

- connected token은 있는데 저장된 이메일 주소가 없을 때 `GmailMailboxService.status()`가 non-interactive Gmail service로 profile email을 한 번 조회하도록 했다.
- 조회된 이메일은 `GmailAccountRepository.save_account_identity()`로 `gmail_account.json`에 저장해 이후 상단바와 설정 모달이 동일한 계정 identity를 재사용하게 했다.
- 이미 열린 브라우저 화면에서도 설정 모달 refresh 응답의 이메일 주소를 상단 Gmail 버튼 텍스트에 즉시 반영하도록 했다.
- profile 조회 실패는 connected 상태 자체를 깨지 않도록 debug 로그만 남기고 기존 fallback을 유지한다.
- token에 이메일이 없는 connected 상태에서도 status account가 Gmail profile 이메일로 채워지는 회귀 테스트를 추가했다.

## 검증

- `uv run pytest tests/test_gmail_oauth_service.py tests/test_gmail_persistent_mode.py tests/test_mail_decision_ui.py`: 39 passed.

## 남은 리스크와 후속 작업

- Gmail profile 조회는 유효한 token과 Gmail API 접근이 필요하다. 네트워크/API 실패 시에는 기존처럼 `Gmail 계정 미확인` fallback을 유지하지만, 성공한 뒤에는 runtime 계정 메타데이터에 저장된다.
- 작업 시작 전에 이미 수정돼 있던 Gmail pagination 관련 파일 변경은 되돌리지 않았고, 이번 수정과 겹치는 `app/services/gmail_mail_service.py`에서는 계정 identity 관련 hunk만 커밋 범위로 분리한다.

---

# 2026-08-10 - Gmail 전체 INBOX 동기화 제한 해제

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gmail synchronization, Gmail API pagination, dashboard mailbox data |
| 관련 파일 | `app/integrations/gmail/sync_client.py`, `app/services/gmail_mail_service.py`, `tests/test_gmail_persistent_mode.py`, `docs/features/gmail-web-sync-settings.md`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Gmail 연동 완료 후 대시보드에 최대 50건만 들어오고 있으며, 실제 Gmail 메일함처럼 전체 메일이 들어와야 한다고 요청했다.

## 확인한 사실

- 대시보드 표시 계층이 아니라 Gmail 수집 계층에서 제한이 걸려 있었다.
- `fetch_inbox_messages()`는 `max_results=50`을 기본값으로 Gmail `messages.list` 첫 페이지만 요청했고, `nextPageToken`을 따라가지 않았다.
- `GmailMailboxService._max_results()`도 `CORAMAIL_GMAIL_MAX_RESULTS` 기본값을 50으로 전달해 기본 동기화가 항상 50건에 머물렀다.

## 해결 방법

- Gmail `messages.list` 응답의 `nextPageToken`을 끝까지 따라가도록 페이지네이션을 구현했다.
- 기본 동기화는 전체 matching INBOX를 가져오도록 `CORAMAIL_GMAIL_MAX_RESULTS` 기본값을 제한 없음으로 변경했다.
- 운영자가 개발·복구 목적으로만 `CORAMAIL_GMAIL_MAX_RESULTS`를 명시하면 해당 상한을 적용하도록 유지했다.
- 페이지네이션과 명시 상한 동작을 검증하는 단위 테스트를 추가하고 Gmail 설정 문서의 정상 흐름과 테스트 기준을 갱신했다.

## 검증

- `python -m py_compile app/integrations/gmail/sync_client.py app/services/gmail_mail_service.py`: passed.
- `pytest tests/test_gmail_persistent_mode.py`: failed, 전역 `pytest` 명령 없음.
- `uv run pytest tests/test_gmail_persistent_mode.py`: 7 passed.

## 남은 리스크와 후속 작업

- 실제 Gmail 전체 동기화는 유효한 OAuth token과 외부 Gmail API 접근이 필요하므로 로컬 검증은 가짜 페이지 응답 기반 단위 테스트에 한정했다.
- 전체 INBOX 최초 동기화는 메일 수와 첨부파일 수에 따라 시간이 오래 걸릴 수 있다. 필요한 경우 운영자가 `CORAMAIL_GMAIL_MAX_RESULTS`를 일시적으로 설정해 단계적 동기화를 실행할 수 있다.
- 기존 미추적 `node_modules/`, `package.json`, `package-lock.json` 및 작업 전부터 수정돼 있던 Gmail 설정 관련 파일들은 이번 커밋 범위에 포함하지 않는다.

---

# 2026-08-10 - Gmail 권한 설정 모달 연결 상태 갱신

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gmail settings UI, Gmail runtime token status |
| 관련 파일 | `app/templates/shell.html`, `app/repositories/gmail_account_repository.py`, `tests/test_mail_decision_ui.py`, `tests/test_gmail_oauth_service.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Gmail 연동이 성공한 뒤 Gmail 계정 권한 설정 창을 다시 열면 초기 상태처럼 표시된다고 설명했다.
- 원하는 동작은 저장된 token 또는 현재 connected 상태가 있으면 모달이 열릴 때 그 상태를 그대로 반영하는 것이다.

## 확인한 사실

- Gmail 설정 partial은 페이지 최초 렌더링 시 shell HTML 안에 포함되고, 설정 버튼 클릭은 기존 DOM을 `hidden=false`로 여는 동작만 수행했다.
- 따라서 OAuth callback, token 저장, `.env`/runtime token 변경 이후에도 모달을 다시 열 때 최신 `/ui/settings/gmail-sync` 상태를 재조회하지 않았다.
- `GmailAccountRepository`도 생성 시점의 환경변수 문자열을 필드에 보관하고 있어 프로세스 실행 중 활성 `.env` token이 바뀐 경우 상태 계산이 뒤처질 수 있었다.

## 해결 방법

- Gmail 설정 모달을 열기 직전에 `/ui/settings/gmail-sync`를 `cache: "no-store"`로 다시 가져와 `.gmail-settings-dialog-body`를 교체하도록 했다.
- 교체된 HTML 안의 htmx 폼과 버튼이 계속 동작하도록 `htmx.process()`를 호출한다.
- Gmail account repository의 public status와 token 조회가 활성 `.env` 및 런타임 파일 상태를 매번 다시 반영하도록 보강했다.
- 저장소 생성 후 `.env`에 token이 추가되어도 `connected`, 계정 이메일, token source가 최신 상태로 계산되는 회귀 테스트를 추가했다.

## 검증

- `pytest tests/test_gmail_oauth_service.py tests/test_mail_decision_ui.py`: failed, 전역 `pytest` 명령 없음.
- `uv run pytest tests/test_gmail_oauth_service.py tests/test_mail_decision_ui.py`: 31 passed.

## 남은 리스크와 후속 작업

- 실제 Google OAuth 승인 화면과 Gmail API 호출은 외부 네트워크와 유효한 Google client가 필요하므로 이번 검증은 UI refresh와 저장 상태 반영 단위 테스트에 한정했다.
- 기존 미추적 `node_modules/`, `package.json`, `package-lock.json`은 이번 작업과 무관해 커밋하지 않았다.

---

# 2026-08-10 - Gmail OAuth token 자동 갱신 흐름 보정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gmail OAuth callback, token persistence, Gmail settings UI |
| 관련 파일 | `app/repositories/gmail_account_repository.py`, `app/templates/partials/gmail_sync_settings.html`, `docs/features/gmail-web-sync-settings.md`, `tests/test_gmail_oauth_service.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 `coramail_ai`에서 token JSON 파일을 직접 업로드한 것이 아니라 프로젝트 내부 코드가 자동으로 token을 생성·갱신했던 것으로 기억한다고 설명했다.
- 원하는 동작은 token을 수동 업로드하는 흐름이 아니라 자동 업데이트되는 흐름이다.

## 확인한 사실

- 직전 변경은 Gmail API client가 token refresh 후 `.env`의 `GOOGLE_TOKEN_JSON`을 갱신하도록 만들었지만, 웹 OAuth callback에서 새로 발급된 token은 런타임 파일에만 저장했다.
- 따라서 Google 권한 요청으로 새 token을 만든 경우에는 `.env` 자동 갱신까지 완전히 이어지지 않았다.

## 해결 방법

- `GmailAccountRepository.save_connected_account()`가 OAuth callback에서 받은 token을 런타임 token 파일뿐 아니라 활성 `.env`의 `GOOGLE_TOKEN_JSON`에도 저장하도록 했다.
- 수동 fallback token 등록도 활성 `.env`의 `GOOGLE_TOKEN_JSON`과 `GOOGLE_SEND_TOKEN_JSON`을 갱신하도록 맞췄다.
- Gmail 설정 UI에서 Google 권한 요청을 기본 token 생성 경로로 올리고, 기존 token 붙여넣기는 보조 fallback 섹션으로 내렸다.
- Gmail 설정 문서의 정상 흐름을 `GOOGLE_CREDENTIALS_JSON` 기반 OAuth 발급과 자동 `.env` 갱신 기준으로 수정했다.

## 검증

- `python -m py_compile app/repositories/gmail_account_repository.py app/integrations/gmail/sync_client.py app/services/gmail_mail_service.py`: passed.
- `uv run pytest tests/test_gmail_oauth_service.py tests/test_gmail_persistent_mode.py tests/test_mail_decision_ui.py -q`: 34 passed.
- `uv run pytest tests/test_gmail_persistent_mode.py tests/test_gmail_oauth_service.py tests/test_hosting_defaults.py tests/test_mail_decision_ui.py -q`: 39 passed.
- `git diff --check`: passed.

## 남은 리스크와 후속 작업

- 실제 Google OAuth 승인과 Gmail API 동기화는 유효한 Google client 설정, 브라우저 승인, 외부 네트워크가 필요하므로 로컬 단위 테스트에서는 token 저장·갱신 경로까지만 검증했다.
- `.env`에 저장되는 OAuth token은 비밀값이며 커밋하지 않는다.

---

# 2026-08-10 - coramail_ai 방식 Gmail 환경변수 동기화 이식

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gmail sync client, OAuth env JSON, local `.env`, settings documentation |
| 관련 파일 | `app/integrations/gmail/sync_client.py`, `app/services/gmail_mail_service.py`, `tests/test_gmail_persistent_mode.py`, `.env.example`, `docs/features/gmail-web-sync-settings.md`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 `coramail_ai`에서 Gmail token을 직접 가져오지 않았던 동기화 방식을 `coramail_agent`에 이식해 달라고 요청했다.
- 사용자는 기존 `.env`도 참고하라고 했다.

## 확인한 사실

- `coramail_ai`는 `GOOGLE_CREDENTIALS_JSON`을 OAuth client source로 읽고, 발급 또는 갱신된 Gmail token을 `GOOGLE_TOKEN_JSON`으로 활성 `.env`에 저장한다.
- `coramail_agent`는 `GOOGLE_TOKEN_JSON`과 런타임 token 파일은 이미 인식했지만, `build_gmail_service()`의 interactive OAuth 경로는 file path client secret만 지원했다.
- `coramail_agent/.env`에는 Gmail 관련 키가 없었고, `coramail_ai/.env`에는 `GOOGLE_CREDENTIALS_JSON`, `GOOGLE_TOKEN_JSON`, `GOOGLE_SEND_TOKEN_JSON`이 있었다. 값은 출력하거나 커밋하지 않았다.

## 해결 방법

- Gmail sync client가 활성 `.env` 또는 `CORAMAIL_ENV_FILE`에서 `GOOGLE_CREDENTIALS_JSON`과 `GOOGLE_TOKEN_JSON`을 직접 읽도록 했다.
- interactive OAuth가 `GOOGLE_CREDENTIALS_JSON`의 client config로도 시작될 수 있게 하고, 토큰 refresh 또는 interactive OAuth 후 갱신된 `GOOGLE_TOKEN_JSON`을 활성 `.env`와 런타임 token file에 저장하도록 했다.
- `GmailMailboxService`가 프로젝트 `.env`를 `GmailSyncConfig.env_path`로 넘기도록 연결했다.
- `.env.example`과 Gmail sync 설정 문서에 `coramail_ai` 호환 로컬 흐름을 기록했다.
- 로컬 작업 편의를 위해 `coramail_ai/.env`의 Gmail 관련 세 키를 `coramail_agent/.env`에 병합했다. `.env`는 비밀값을 포함하므로 커밋하지 않는다.

## 검증

- `python -m py_compile app/integrations/gmail/sync_client.py app/services/gmail_mail_service.py tests/test_gmail_persistent_mode.py`: passed.
- `uv run pytest tests/test_gmail_persistent_mode.py tests/test_gmail_oauth_service.py -q`: 7 passed.
- `uv run pytest tests/test_gmail_persistent_mode.py tests/test_gmail_oauth_service.py tests/test_hosting_defaults.py tests/test_mail_decision_ui.py -q`: 38 passed.
- `git diff --check`: passed.

## 남은 리스크와 후속 작업

- 실제 Gmail API sync는 유효한 Google OAuth token과 외부 네트워크 접근이 필요하므로 이번 변경에서는 단위/회귀 테스트로 검증했다.
- `.env` 병합 값은 로컬 실행용 비밀값이며 원격 저장소에는 push하지 않는다.

---

# 2026-08-10 - Gmail OAuth 권한 승인 후 token 미적용 원인 수정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gmail OAuth callback, scope reissue, token persistence |
| 관련 파일 | `app/services/gmail_oauth_service.py`, `app/repositories/gmail_account_repository.py`, `app/server.py`, `tests/test_gmail_oauth_service.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Google 로그인과 권한 부여는 성공하는데 Gmail 권한이 앱에 적용되지 않고 token을 어디서 얻는지 모르겠다고 보고했다.
- 사용자는 scope를 바꿔 재발급하고 싶어 했고, OAuth client redirect URI는 `http://127.0.0.1:8000/auth/gmail/callback`로 맞춘 상태였다.

## 확인한 사실

- `data/runtime/gmail_oauth_client.json`은 `installed` client이고 redirect URI가 `http://127.0.0.1:8000/auth/gmail/callback`로 맞았다.
- Docker web 로그에는 `/auth/gmail/callback?...code=...&scope=https://mail.google.com/%20...gmail.readonly...gmail.send...gmail.modify` 요청이 303으로 들어온 기록이 있었다.
- callback 이후에도 `data/runtime/gmail_token.json`이 없었고, 계정 상태는 `Gmail token is unavailable or invalid.`였다.
- OAuth 요청은 `https://mail.google.com/` 하나만 기대했지만 `include_granted_scopes=true` 때문에 과거 승인 scope들이 응답에 섞였다. oauthlib는 scope 변경을 기본적으로 `Warning` 예외로 처리해 token 저장 전에 callback을 중단할 수 있다.
- 기존 callback은 token 교환 뒤 Gmail profile 조회까지 성공해야 token을 저장했기 때문에, profile 조회 단계 실패도 token 미적용으로 이어질 수 있었다.

## 해결 방법

- 새 권한 요청 URL에서 `include_granted_scopes`를 제거해 과거 승인 scope가 불필요하게 섞이지 않도록 했다.
- token 교환 중 oauthlib scope 변경 검증은 `OAUTHLIB_RELAX_TOKEN_SCOPE=1`을 일시적으로 설정해 허용하고, 환경변수는 즉시 원복한다.
- Gmail profile 조회가 실패하더라도 이미 발급된 OAuth token은 `data/runtime/gmail_token.json`에 저장하도록 바꿨다.
- callback 예외는 서버 로그와 `gmail_account.json`의 OAuth error 상태에 기록하도록 복원했다.
- 실제 `/ui/settings/gmail/connect` 응답의 Location header가 `redirect_uri=http://127.0.0.1:8000/auth/gmail/callback`, `scope=https://mail.google.com/`, `include_granted_scopes` 없음으로 생성되는 것을 확인했다.

## 검증

- `python -m py_compile app/server.py app/services/gmail_oauth_service.py app/repositories/gmail_account_repository.py`: passed.
- `uv run pytest tests/test_gmail_oauth_service.py tests/test_gmail_persistent_mode.py tests/test_mail_decision_ui.py::test_gmail_sync_paths_keep_august_7_unauthenticated_behavior -q`: 6 passed.
- `uv run pytest tests/test_gmail_oauth_service.py tests/test_gmail_persistent_mode.py tests/test_hosting_defaults.py tests/test_mail_decision_ui.py -q`: 36 passed.

## 남은 리스크와 후속 작업

- 실제 계정 연동 완료는 사용자가 브라우저에서 다시 `Google 권한 요청`을 눌러 새 callback을 완료해야 `data/runtime/gmail_token.json` 생성으로 확인할 수 있다.

---

# 2026-08-10 - Gmail 동기화 endpoint 인증 예외 복원

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gmail sync execution, UI auth middleware, August 7 sync behavior |
| 관련 파일 | `app/server.py`, `tests/test_mail_decision_ui.py`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Gmail 동기화 자체가 성공했던 2026-08-07 시점 기준으로 동기화 부분을 다시 맞춰 달라고 요청했다.
- 직전 롤백으로 Gmail token/client/service 파일은 2026-08-07 기준과 일치했지만, 이후 추가된 UI 로그인 인증이 `/ui/settings/gmail/sync`와 `/ui/auto-sync/run` 같은 동기화 실행 경로를 가로막을 수 있었다.

## 확인한 사실

- `app/integrations/gmail/`, `GmailMailboxService`, `GmailOAuthService`, `GmailAccountRepository`, `gmail_sync_settings.html`, Gmail sync 문서는 2026-08-07 기준 커밋 `5341d6c`와 diff가 없었다.
- 남은 동기화 영향 차이는 `path_requires_auth()`가 `/ui/*` 전체를 보호하면서 Gmail 설정·동기화 POST도 인증 대상으로 만든 점이었다.

## 해결 방법

- Gmail 동기화 설정·토큰 등록·OAuth 시작·연결 해제·수동 sync·topbar auto-sync 실행 endpoint를 인증 예외로 추가했다.
- 일반 UI 루트와 대시보드 인증은 유지해 이번 변경을 동기화 경로에 한정했다.
- 회귀 테스트로 Gmail sync endpoint는 인증을 요구하지 않고 일반 UI는 계속 인증을 요구함을 고정했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py::test_gmail_sync_paths_keep_august_7_unauthenticated_behavior tests/test_mail_decision_ui.py::test_ui_auth_redirects_login_and_logout tests/test_gmail_persistent_mode.py -q`: 5 passed.
- `uv run pytest tests/test_gmail_persistent_mode.py tests/test_hosting_defaults.py tests/test_mail_decision_ui.py -q`: 34 passed.

## 남은 리스크와 후속 작업

- 실제 Gmail API 동기화 성공은 2026-08-07에 사용하던 유효한 `GOOGLE_TOKEN_JSON` 또는 `data/runtime/gmail_token.json`이 있어야 확인할 수 있다.

---

# 2026-08-10 - Dashboard Daily Inflow 최근 7일 고정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard Daily Inflow, category timeline aggregation |
| 관련 파일 | `app/server.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Dashboard 탭의 `Daily Inflow` 날짜 범위가 잘못 설정되어 있으며, 항상 오늘 날짜 기준 최근 7일 데이터를 볼 수 있게 해 달라고 요청했다.

## 확인한 사실

- `Daily Inflow` 차트는 서버의 `category_timeline()` 결과를 `dashboard_category_timeline.html`과 Chart.js 초기화 코드가 그대로 렌더링한다.
- 기존 구현은 메일이 존재하는 날짜만 `MM-DD` label로 모아 정렬했기 때문에, 오래된 샘플이나 미래 날짜가 섞이면 오늘 기준 최근 7일이 아닌 데이터 전체 날짜 범위가 표시될 수 있었다.
- 작업 시작 전부터 `app/static/app.css`, `app/templates/shell.html`, `tests/test_mail_decision_ui.py`, 세션 로그, untracked Node 패키지 파일 변경이 존재했으며 이번 요청과 무관한 변경은 되돌리지 않았다.

## 해결 방법

- `category_timeline()`이 표시 기준 시간대의 오늘 날짜를 기준으로 6일 전부터 오늘까지 7개 label을 항상 생성하도록 변경했다.
- 차트 집계는 해당 7일 범위 안의 메일만 포함하고, 날짜가 없거나 범위 밖인 행은 제외하도록 했다.
- 테스트에서 고정된 오늘 날짜를 주입해 오래된 날짜, 미래 날짜, 날짜 없는 행이 최근 7일 집계에 들어가지 않는 것을 확인했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py::test_category_timeline_is_fixed_to_recent_seven_days_from_today tests/test_mail_decision_ui.py::test_dashboard_summary_excludes_unclassified_and_unassigned_rows`: passed.

## 남은 리스크와 후속 작업

- `MM-DD` label은 연도를 표시하지 않으므로 연말을 지나는 7일 범위에서는 화면 label만으로 연도 구분이 어렵다. 집계 자체는 날짜 객체 기준 최근 7일로 제한된다.

---

# 2026-08-10 - coramail_ai 로그인/로그아웃 인증 이식

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | UI authentication, login/logout, topbar current user |
| 관련 파일 | `app/server.py`, `app/templates/login.html`, `.env.example`, `README.md`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 `coramail_ai`에 있는 login, logout, 계정 관련 구현을 `coramail_agent`로 가져와 이식해 달라고 요청했다.
- 직전 확인에서 로그아웃 버튼 왼쪽의 `demo` 표시가 실제 로그인 사용자값이 아니라 `ui_globals()`의 하드코딩 값임을 확인했다.

## 확인한 사실

- `coramail_ai/app.py`는 별도 session middleware 없이 HMAC 서명 쿠키(`coramail_session`)로 `/`와 `/ui/*`를 보호한다.
- 기본 계정 계약은 `CORAMAIL_AUTH_USERNAME=admin`, `CORAMAIL_AUTH_PASSWORD=coramail`, `CORAMAIL_AUTH_SECRET`, `CORAMAIL_AUTH_SESSION_SECONDS`이다.
- `coramail_agent`에는 `app/templates/login.html`과 shell의 logout form은 있었지만 `/login`, `/logout`, 인증 쿠키 helper, UI 보호 middleware가 없었다.

## 해결 방법

- `coramail_ai`의 서명 쿠키 방식 인증 helper를 `app/server.py`에 이식했다.
- `/login` GET/POST와 `/logout` POST route를 추가했다.
- 인증이 켜져 있으면 `/`와 `/ui/*`만 보호하고, htmx 요청은 `HX-Redirect`로 로그인 화면을 안내하도록 했다.
- `ui_globals()`의 `current_user`를 더 이상 `demo`로 고정하지 않고 인증 쿠키 사용자 또는 `AUTH_USERNAME`을 표시하게 했다.
- `.env.example`과 README에 인증 환경변수와 기본 개발 계정, 운영 변경 주의사항을 기록했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py tests/test_hosting_defaults.py -q`: 30 passed.
- `uv run pytest tests/test_dev_environment.py -q`: 7 passed.
- `uv run pytest -q`: 154 passed, 1 known collection warning.

## 남은 리스크와 후속 작업

- 기본 개발 비밀번호 `coramail`은 공유/운영 환경에서 반드시 변경해야 한다.
- 이번 이식은 `coramail_ai`와 같은 단일 관리자 계정 쿠키 인증이며, PostgreSQL `users` 테이블 기반 다중 사용자/권한 관리는 아직 연결하지 않았다.

---

# 2026-08-10 - 표시 모드 버튼 복구와 사용자명 demo 원인 확인

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Topbar UI, user display context |
| 관련 파일 | `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 이전 작업에서 제거한 상단 표시 모드 전환 버튼은 잘못 제거된 대상이므로 복구해 달라고 요청했다.
- 실제로 확인하려던 대상은 로그아웃 버튼 바로 왼쪽에 표시되는 사용자명 `demo`였고, 왜 `admin`이 아닌지 분석해 달라고 요청했다.

## 확인한 사실

- 표시 모드 전환 버튼은 `shell.html`의 `mode-switch` 버튼이며, 이번에 원래 마크업과 CSS를 복구했다.
- 로그아웃 버튼 바로 왼쪽의 `demo`는 `shell.html`의 `<span class="current-user">{{ current_user }}</span>`에서 표시된다.
- `current_user` 값은 `app/server.py`의 `ui_globals()`에서 `"demo"`로 하드코딩되어 있으며, 현재 서버 코드에서 로그인 세션이나 `admin` 사용자 정보를 읽어 이 값에 넣는 경로는 확인되지 않았다.
- `app/templates/login.html`에는 로그인 폼이 있지만, 현재 검색 기준으로 `app/server.py`에는 `/login` 또는 `/logout` 처리 라우트가 연결되어 있지 않다.

## 해결 방법

- 표시 모드 전환 버튼 마크업과 `mode-switch`/`mode-badge` CSS를 복구했다.
- 잘못 추가했던 “표시 모드 배지가 없어야 한다” 테스트를 “표시 모드 전환 버튼이 렌더링되어야 한다” 테스트로 정정했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -q`: 24 passed.

## 남은 리스크와 후속 작업

- `current_user`를 실제 `admin`으로 표시하려면 인증/세션 소스 또는 설정값을 정해 `ui_globals()`가 그 값을 사용하도록 별도 수정해야 한다.

---

# 2026-08-10 - 상단 Demo 표시 모드 배지 제거

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Topbar UI, display mode presentation |
| 관련 파일 | `app/templates/shell.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 상단 탭 우측에 `Demo`라고 표시되는 영역을 제거해 달라고 요청했다.

## 확인한 사실

- 상단 우측의 `Demo` 텍스트는 `shell.html`의 표시 모드 전환 버튼에서 렌더링되고 있었다.
- `/ui/display-mode/toggle` 서버 라우트와 표시 모드 쿠키 처리 자체는 이번 요청의 대상이 아니므로 유지했다.
- 작업 시작 전부터 Gmail 동기화 관련 여러 파일과 `node_modules/`, `package.json`, `package-lock.json` 변경이 존재했으며 이번 변경에서는 되돌리지 않았다.

## 해결 방법

- topbar actions에서 표시 모드 전환 버튼 마크업을 제거했다.
- 더 이상 사용하지 않는 `mode-switch`/`mode-badge` 전용 CSS를 제거했다.
- shell 렌더링 결과에 `mode-switch`와 `mode-switch-text`가 남지 않는 회귀 테스트를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -q`: 23 passed.

## 남은 리스크와 후속 작업

- 상단 UI에서 표시 모드를 직접 전환하는 컨트롤은 숨겨졌지만, 서버의 표시 모드 전환 endpoint는 남아 있다. 이후 표시 모드 전환 진입점이 필요하면 별도 설정 화면으로 옮기는 결정을 해야 한다.

---

# 2026-08-10 - Gmail 동기화 방식을 8월 7일 버전으로 롤백

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gmail sync settings, OAuth token loading, Gmail API client construction |
| 관련 파일 | `.env.example`, `app/integrations/gmail/sync_client.py`, `app/repositories/gmail_account_repository.py`, `app/server.py`, `app/services/gmail_mail_service.py`, `app/services/gmail_oauth_service.py`, `app/templates/partials/gmail_sync_settings.html`, `app/static/app.css`, `docs/features/gmail-web-sync-settings.md`, `tests/test_gmail_persistent_mode.py`, `tests/test_hosting_defaults.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Gmail 동기화가 마지막으로 성공한 날짜가 2026-08-07이라고 설명했고, 현재 방식과 당시 방식의 차이를 확인한 뒤 당시 버전의 동기화 방식으로 롤백해 달라고 요청했다.

## 확인한 사실

- 2026-08-07 기준 커밋 `5341d6c`와 현재 구현을 비교했을 때 Gmail 메시지 fetch, 첨부 다운로드, PostgreSQL upsert 흐름 자체는 큰 차이가 없었다.
- 2026-08-10 이후 변경은 API key 입력, OAuth client 파일 업로드, token 저장 순서, stale 상태 표시 같은 Gmail 설정·인증 흐름에 집중되어 있었다.
- 현재 런타임에는 `data/runtime/gmail_token.json`이 없고, `gmail_account.json`에는 `Gmail token is unavailable or invalid.`가 남아 있었다.

## 해결 방법

- 2026-08-10 이후 Gmail 설정·인증 방식을 바꾼 커밋들의 효과를 되돌려 2026-08-07 방식의 token 기반 동기화 경로로 복원했다.
- API key 기반 설정, OAuth client 파일 업로드 메타데이터 표시, profile 조회 실패 시 token 선저장 보강, 관련 UI 문구와 테스트를 제거했다.
- 기존 `GOOGLE_TOKEN_JSON` 직접 등록, OAuth client JSON 붙여넣기, token 파일 기반 sync 흐름을 다시 기준으로 삼았다.

## 검증

- `git diff --cached --stat`로 롤백 대상 파일 범위를 확인했다.
- `git diff --stat 5341d6c -- app/integrations/gmail/sync_client.py app/services/gmail_mail_service.py app/repositories/gmail_account_repository.py app/services/gmail_oauth_service.py app/templates/partials/gmail_sync_settings.html docs/features/gmail-web-sync-settings.md .env.example tests/test_gmail_persistent_mode.py`가 빈 결과를 반환해 핵심 Gmail 동기화 파일이 2026-08-07 기준과 일치함을 확인했다.
- `python -m py_compile app/server.py app/repositories/gmail_account_repository.py app/services/gmail_mail_service.py app/services/gmail_oauth_service.py app/integrations/gmail/sync_client.py`: passed.
- `uv run pytest tests/test_gmail_persistent_mode.py tests/test_hosting_defaults.py tests/test_mail_decision_ui.py`: 30 passed.

## 남은 리스크와 후속 작업

- 실제 Gmail 동기화 성공은 2026-08-07에 사용하던 유효한 `GOOGLE_TOKEN_JSON` 또는 `data/runtime/gmail_token.json`이 복원되어야 확인할 수 있다.
- 현재 작업 전부터 존재하던 untracked `node_modules/`, `package.json`, `package-lock.json`은 이번 롤백과 무관하여 그대로 둔다.

---

# 2026-08-10 - Gmail API key 입력 중심 동기화 설정 UI

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gmail sync settings, API key storage, OAuth sync readiness |
| 관련 파일 | `.env.example`, `app/integrations/gmail/sync_client.py`, `app/repositories/gmail_account_repository.py`, `app/server.py`, `app/services/gmail_mail_service.py`, `app/templates/partials/gmail_sync_settings.html`, `app/static/app.css`, `docs/features/gmail-web-sync-settings.md`, `tests/test_gmail_oauth_service.py`, `tests/test_gmail_persistent_mode.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Gmail API key를 발급받았고, 이 값을 UI에 복사해 붙여넣으면 기존 Gmail 동기화가 문제없이 동작하도록 설정 화면을 재구성하길 원했다.
- Google 안내의 `key=API_KEY` 파라미터 문구를 참고로 전달했다.

## 확인한 사실

- 현재 Gmail 동기화는 `users.messages.*`, profile 조회, 첨부 다운로드, 휴지통 이동을 호출하며 OAuth credential을 사용한다.
- Google API key는 Google API client의 `developerKey`로 전달할 수 있지만, 개인 Gmail 메일함 접근 권한을 OAuth token 대신 제공하지 않는다.
- 따라서 UI는 API key 저장을 1차 입력 흐름으로 제공하되, 실제 메일함 동기화 준비 여부는 OAuth token 또는 Google 권한 승인 상태를 함께 확인해야 한다.

## 해결 방법

- `GOOGLE_API_KEY` 환경변수와 `data/runtime/gmail_api_key.txt` runtime 저장소를 추가했다.
- Gmail 설정 모달에 API key 붙여넣기 form을 최상단 주요 설정으로 배치하고, 저장된 key는 끝자리만 표시하도록 했다.
- 저장된 API key를 `GmailSyncConfig.api_key`로 전달하고 Google API client 생성 시 `developerKey`로 넘기도록 했다.
- OAuth token이 없으면 동기화 버튼을 비활성화하고, API key만으로는 개인 Gmail 메일 목록·본문·첨부를 읽을 수 없다는 안내를 표시한다.
- 기존 `GOOGLE_TOKEN_JSON` 직접 등록과 OAuth client JSON 등록은 고급/보조 흐름으로 유지했다.
- 기능 문서와 `.env.example`에 API key 입력 계약과 OAuth 필요 조건을 반영했다.

## 검증

- `python -m py_compile app/server.py app/repositories/gmail_account_repository.py app/services/gmail_mail_service.py app/integrations/gmail/sync_client.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py tests/test_gmail_oauth_service.py tests/test_gmail_persistent_mode.py`: 30 passed.

## 남은 리스크와 후속 작업

- 실제 Gmail 동기화 성공은 유효한 OAuth token 또는 Google 권한 승인까지 완료한 환경에서 확인해야 한다.
- Google API key 값 자체는 런타임 파일 또는 환경변수에 보관되므로 운영 배포 전 secrets store로 이동해야 한다.

---

# 2026-08-10 - Gmail OAuth token 저장 실패 원인 추적과 client 파일 표시 개선

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gmail OAuth callback, sync settings UX, credential diagnostics |
| 관련 파일 | `app/repositories/gmail_account_repository.py`, `app/services/gmail_oauth_service.py`, `app/server.py`, `app/templates/partials/gmail_sync_settings.html`, `app/static/app.css`, `docs/features/gmail-web-sync-settings.md`, `tests/test_gmail_oauth_service.py`, `tests/test_hosting_defaults.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 OAuth client JSON을 이미 업로드했는데도 파일 선택 영역에서 무엇이 등록됐는지 확인할 수 없는 점을 지적했다.
- Google 권한 요청을 통해 로그인했는데도 token이 없다고 동기화가 안 되는 근본 원인 확인과 수정을 요청했다.

## 확인한 사실

- 서버 로그에서 `/auth/gmail/callback?...code=...`가 실제로 들어왔고 303 redirect로 처리됐다.
- callback 이후에도 `data/runtime/gmail_token.json`이 없었고, 자동 동기화는 `Gmail token is unavailable or invalid.`로 실패했다.
- 기존 callback 구현은 token 교환 뒤 Gmail profile 조회까지 성공해야만 token을 저장했다. 따라서 profile 조회 단계가 실패하면 이미 발급받은 token도 저장되지 않는 구조였다.
- 기존 업로드 시점에는 원본 파일명을 저장하지 않아 과거 업로드 파일명은 복원할 수 없지만, 저장된 client JSON의 안전한 메타데이터는 표시할 수 있다.

## 해결 방법

- OAuth callback에서 token 교환이 성공하면 Gmail profile 조회 전에 token을 먼저 저장하도록 순서를 바꿨다.
- Gmail profile 조회 실패는 token 저장을 막지 않고 서버 로그에 남기며, 계정 이메일은 후속 sync/진단에서 보강할 수 있게 했다.
- callback 예외는 서버 로그와 Gmail account status에 기록하도록 바꿨다.
- OAuth client JSON 업로드 시 원본 파일명, client type, client id suffix, redirect URI, 등록 시각을 `data/runtime/gmail_oauth_client_meta.json`에 저장한다.
- 설정 모달에 OAuth client 파일 카드 UI를 추가해 등록된 파일과 메타데이터를 확인할 수 있게 했다.
- 기존 token 직접 등록은 일반 경로에서 고급 접힘 섹션으로 낮췄다.

## 검증

- `python -m py_compile app/repositories/gmail_account_repository.py app/services/gmail_oauth_service.py app/server.py`: passed.
- `uv run pytest tests/test_gmail_oauth_service.py tests/test_hosting_defaults.py tests/test_mail_decision_ui.py`: 34 passed.
- 실행 중인 Docker web 서버에서 `/ui/settings/gmail-sync`가 저장된 OAuth client 카드(`gmail_oauth_client.json`, `installed`, client id suffix, redirect URI)를 렌더링하고 stale token 오류를 표시하지 않는 것을 확인했다.
- `/api/auto-sync`가 token이 없는 현재 상태에서 `last_exit_code=0`, `last_error=""`를 반환하는 것을 확인했다.

## 남은 리스크와 후속 작업

- 기존 업로드 파일은 과거에 파일명을 저장하지 않아 UI에 `gmail_oauth_client.json` fallback 이름으로 표시된다. 다음 업로드부터 원본 파일명을 표시한다.
- 사용자가 다시 `Google 권한 요청`을 완료해야 새 callback 코드 경로로 `gmail_token.json` 생성 여부를 확인할 수 있다.

---

# 2026-08-10 - Gmail OAuth client 등록 후 재업로드 없는 권한 요청 UX

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gmail sync settings, OAuth reconnect UX |
| 관련 파일 | `app/repositories/gmail_account_repository.py`, `app/templates/partials/gmail_sync_settings.html`, `docs/features/gmail-web-sync-settings.md`, `tests/test_mail_decision_ui.py`, `tests/test_hosting_defaults.py` |

## 요청 또는 배경

- 사용자는 OAuth client JSON을 이미 업로드했는데도 매번 다시 업로드해야 하는 것처럼 보이는 UI와 설명이 잘못됐다고 지적했다.
- 기대 동작은 client JSON 등록 후에는 재업로드 없이 `Google 권한 요청`만 눌러 Gmail token을 발급하는 것이다.

## 확인한 사실

- 기존 모달은 `has_client_config=true`일 때 Google 권한 요청 링크를 활성화했지만, 고급 영역 제목과 안내문이 계속 새 token 생성/JSON 등록 중심으로 보여 혼동을 만들었다.
- 깨진 token 제거 후에도 과거 sync error가 account JSON에 남아 있으면, token이 없는 상태가 오류처럼 표시될 수 있었다.

## 해결 방법

- client JSON 등록 상태에서는 hero 제목을 `OAuth 설정 완료`로 표시하고, 다시 업로드하지 말고 Google 권한 요청으로 token을 발급하라고 안내한다.
- 등록된 상태의 JSON upload form은 `OAuth client JSON 교체` 섹션으로 낮춰 표시한다.
- client JSON 미등록 상태에서는 먼저 OAuth client JSON을 등록해야 한다고 안내한다.
- token 파일이 없으면 stale sync error와 이전 scope를 public status에서 숨겨 `권한 요청 필요` 상태로 보이게 했다.
- 기능 문서의 alternate permission flow와 테스트 기준을 재업로드 없는 흐름으로 갱신했다.

## 검증

- `python -m py_compile app/repositories/gmail_account_repository.py app/server.py`: passed.
- `uv run pytest tests/test_mail_decision_ui.py tests/test_hosting_defaults.py`: 32 passed.
- 실행 중인 Docker web 서버에서 `/ui/settings/gmail-sync`가 `OAuth 설정 완료`, `다시 업로드하지 말고 Google 권한 요청`, `OAuth client JSON 교체`를 렌더링하고 stale token 오류를 표시하지 않는 것을 확인했다.

## 남은 리스크와 후속 작업

- 실제 Google OAuth 승인 callback 이후 새 `gmail_token.json`이 생성되고 sync가 성공하는지는 사용자 브라우저의 Google 로그인 완료 후 확인해야 한다.

---

# 2026-08-10 - Gmail OAuth client JSON 파일 업로드 지원

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gmail sync settings, OAuth client configuration |
| 관련 파일 | `app/server.py`, `app/templates/partials/gmail_sync_settings.html`, `docs/features/gmail-web-sync-settings.md`, `tests/test_hosting_defaults.py` |

## 요청 또는 배경

- 사용자는 Gmail 계정 동기화 설정에서 Google OAuth client JSON을 textarea에 복사해 붙여넣는 것보다 파일 업로드 방식이 더 간단하다고 제안했다.

## 확인한 사실

- 기존 설정 모달은 `POST /ui/settings/gmail/client-config`에 `client_config_json` textarea 값을 보내 저장했다.
- 프로젝트에는 `python-multipart` 의존성이 없어 FastAPI `request.form()` 기반 multipart 처리로 바꾸면 새 의존성이 필요하다.
- OAuth client JSON 파일명은 저장에 사용할 필요가 없고, 내용만 기존 `data/runtime/gmail_oauth_client.json` 저장 계약에 맞춰 검증하면 된다.

## 해결 방법

- Gmail 설정 모달의 OAuth client 설정 form에 `multipart/form-data`와 `.json` 파일 input을 추가했다.
- 서버는 multipart 요청에서 `client_config_file` 내용을 우선 사용하고, 파일이 없으면 기존 `client_config_json` textarea 값을 fallback으로 사용한다.
- 추가 의존성 없이 표준 라이브러리 `email` MIME 파서로 multipart body를 읽도록 구현했다.
- Gmail Web Sync Settings 문서의 입력 계약, 대체 권한 요청 흐름, 테스트 기준을 업로드 또는 붙여넣기 방식으로 갱신했다.

## 검증

- `python -m py_compile app/server.py`: passed.
- `uv run pytest tests/test_hosting_defaults.py`: 7 passed.

## 남은 리스크와 후속 작업

- 실제 브라우저에서 Google Cloud Console이 내려주는 OAuth client JSON 파일을 업로드한 뒤 Google redirect까지 이어지는 수동 확인은 별도로 필요하다.

---

# 2026-08-10 - Dashboard 상단 높이 압축과 Mail Streams 공간 확대

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard layout, Mail Streams UI |
| 관련 파일 | `app/static/app.css` |

## 요청 또는 배경

- 사용자는 Dashboard 탭에서 가로 2단 상단 영역의 세로 비율을 조금 줄이고 `Mail Streams`의 세로 비율을 조금 늘려달라고 요청했다.
- 높이 조정 중 내부 내용 구성과 배치가 바뀌면 안 되며, 가능한 한 padding을 줄이는 방식으로 진행해달라고 했다.

## 확인한 사실

- Dashboard 화면은 `stats`, `dashboard-summary-grid`, `dashboard-mail-grid` 순서의 3행 구조이며, `Mail Streams`는 남은 세로 공간을 차지한다.
- `Mail Streams` 행 높이와 수동 라우팅 버튼 높이는 이미 inbox 기준으로 조밀하게 조정되어 있어 추가 압축보다 상단 영역의 padding과 gap을 줄이는 편이 요청에 더 맞다.

## 해결 방법

- Dashboard 전용 최종 cascade 구간에서 전체 row gap, stat 카드 padding/min-height, 상단 panel head/body padding을 줄였다.
- Category Distribution, Daily Inflow, Routing Overview 내부 gap과 padding을 소폭 줄여 구성 순서나 컬럼 구조를 바꾸지 않고 상단 높이를 압축했다.
- `Mail Streams` 테이블 내부 행 구성과 템플릿은 변경하지 않았다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py`: 25 passed.
- `python -m py_compile app/server.py`: passed.
- 로컬 실행 중인 `http://127.0.0.1:8000/ui/dashboard`가 200 HTML을 반환하는 것을 확인했다.
- 로컬 앱이 제공하는 `/static/app.css`에 Dashboard padding override가 포함된 것을 확인했다.

## 남은 리스크와 후속 작업

- Browser 플러그인과 Playwright 패키지가 없어 자동 스크린샷 검증은 수행하지 못했다.
- 실제 브라우저에서 세부 시각 비율을 더 미세 조정해야 하면 같은 CSS override 범위에서 수치를 조정하면 된다.

---

# 2026-08-10 - Inbox Status 종합 업무 상태 표시

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox list UI, Mail Decision Run status, routing status |
| 관련 파일 | `docs/features/inbox-list-detail.md`, `app/repositories/postgres_mail_repository.py`, `app/services/postgres_mail_service.py`, `app/templates/partials/mail_rows.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 메일 목록 컬럼 `Status`의 현황 진단 결과를 바탕으로 개발 계획 방안을 세우고 진행해달라고 요청했다.
- 이전 기준점으로 `149 passed`, clean worktree, `main`, `5341d6c feat: make routing policy configurable`가 주어졌지만, 작업 시작 시점에는 최신 커밋이 `fee3462 fix: simplify summary label`였고 작업트리는 clean이었다.

## 확인한 사실

- 기존 Inbox `Status` 컬럼은 `classification_state`와 `classification_state_label`만 표시했다.
- PostgreSQL-backed 목록 행은 분류 source가 있으면 라우팅이 사람 검토 상태여도 `completed`/`DB`로 보일 수 있었다.
- 목표 아키텍처와 Inbox 기능 문서는 Mail Decision Run, 분석 작업, 라우팅, 사람 검토 상태를 사용자가 목록에서 알아볼 수 있어야 한다고 요구한다.

## 해결 방법

- Inbox 기능 문서에 목록 표시용 `work_status`, `work_status_label` 계약과 상태 우선순위를 추가했다.
- PostgreSQL 메일 목록 조회에 최신 `mail_decision_runs.status`를 포함했다.
- `PostgresMailboxService`에서 분류 상태는 보존하면서 최신 Mail Decision Run, 분석 작업, 분류 결과, 라우팅 상태를 합성한 `work_status`를 계산하게 했다.
- 목록 템플릿은 `work_status`를 우선 표시하고, 데모/Gmail 행처럼 값이 없는 경우 기존 `classification_state`로 fallback한다.
- `review_required`, `auto_assigned`, `assigned` 상태 스타일과 회귀 테스트를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py tests/test_attachment_analysis_presentation.py`: 36 passed.
- `uv run pytest tests/test_postgres_mail_decision_repository.py tests/test_mail_decision_ui.py`: 29 passed.
- `uv run pytest`: 151 passed, 1 existing collection warning.

## 남은 리스크와 후속 작업

- `work_status`는 현재 목록 표시 계약이며, 운영 API의 status 필터와 work-status 집계 API에는 아직 별도 필터 계약으로 확장하지 않았다.
- 첨부파일 단위 실패를 목록 `work_status`에 반영하려면 목록 조회에 첨부 분석 집계 상태를 추가해야 한다.

---

# 2026-08-10 - Summary 라벨 단순화

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Mail detail UI, analysis schema documentation |
| 관련 파일 | `app/templates/partials/email_detail.html`, `docs/architecture/postgresql_schema.md`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 coramail agent에서 기존의 긴 영문 요약 라벨로 표시되는 부분을 모두 `Summary`로 바꿔달라고 요청했다.

## 확인한 사실

- 실제 메일 상세 화면의 패널 제목은 `app/templates/partials/email_detail.html`에 있었다.
- 같은 라벨 문구가 PostgreSQL 스키마 설명과 과거 세션 로그에도 남아 있었다.

## 해결 방법

- 메일 상세 화면의 패널 제목을 `Summary`로 변경했다.
- 현재 문서와 기록에서 사용자-facing 요약 라벨 표현을 `Summary`로 정리했다.

## 검증

- 저장소 전체 문자열 검색 결과 기존 긴 영문 요약 라벨이 남아 있지 않음을 확인했다.
- 정적 텍스트 변경이므로 별도 테스트 실행은 생략했다.

## 남은 리스크와 후속 작업

- 없음.

---

# 2026-08-07 - Settings 자동 배정 기준 설정 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Settings UI, assignee routing, Mail Decision policy |
| 관련 파일 | `app/server.py`, `app/services/mail_decision_routing_service.py`, `app/repositories/postgres_routing_policy_settings_repository.py`, `app/templates/views/settings.html`, `app/templates/partials/auto_assignment_policy.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py`, `tests/test_mail_decision_routing_service.py`, `docs/features/assignee-routing.md` |

## 요청 또는 배경

- 사용자는 `FB24291770 / 납품일정문의` 메일이 자동 배정되지 않은 이유를 확인한 뒤, 그 자동 배정 기준을 Settings 탭에서 설정할 수 있게 해달라고 요청했다.
- 직전 확인 결과 해당 메일은 업무유형 판단은 `delivery_confirmation` 신뢰도 `0.99`로 성공했지만, 1순위 후보 점수 `0.345`가 자동 배정 기준 `0.82`보다 낮아 `top_score_below_threshold`로 사람 검토 대상이 됐다.

## 확인한 사실

- 자동 배정 정책은 `RoutingPolicyConfig`의 `auto_assign_threshold`, `minimum_margin`, `minimum_classification_confidence`를 사용한다.
- PostgreSQL에는 이미 `organization_settings.system_settings` JSONB 컬럼이 있어 운영 설정 저장 위치로 사용할 수 있다.
- Mail Decision API 서비스는 인스턴스를 재사용하므로, Settings 변경이 다음 실행부터 반영되려면 후보 생성 시점에 저장된 설정을 다시 읽어야 한다.

## 해결 방법

- `PostgresRoutingPolicySettingsRepository`를 추가해 `organization_settings.system_settings.routing_policy`에 자동 배정 기준을 저장하고 조회하게 했다.
- Settings 탭에 `자동 배정 기준` 패널을 추가하고, 자동 배정 최소 점수, 1·2순위 최소 점수 차이, 업무유형 최소 신뢰도를 HTMX partial로 저장할 수 있게 했다.
- 라우팅 후보 생성 단계가 DB 저장 설정을 읽어 `RoutingPolicy`를 구성하도록 변경했다. 저장값이 없으면 기존 환경변수와 코드 기본값을 사용한다.
- `docs/features/assignee-routing.md`에 설정 항목, 기본값, 저장 위치, 적용 시점을 문서화했다.

## 검증

- `python -m py_compile app/repositories/postgres_routing_policy_settings_repository.py app/services/mail_decision_routing_service.py app/server.py`
- `uv run pytest tests/test_mail_decision_ui.py tests/test_mail_decision_routing_service.py tests/test_routing_policy.py`: 27 passed.
- 실행 중인 개발 서버에서 `GET /ui/settings/auto-assignment-policy`가 200 OK와 기본값 `0.82`, `0.15`, `0.78`을 반환함을 확인했다.
- 같은 값으로 `POST /ui/settings/auto-assignment-policy`를 호출해 성공 메시지와 partial HTML을 확인했다.
- Docker PostgreSQL의 `organization_settings.system_settings.routing_policy`에 저장값이 기록된 것을 확인했다.

## 남은 리스크와 후속 작업

- 현재 Settings는 threshold 조정만 제공한다. `딘텍` 고객 담당자, 제품/프로젝트 담당자 같은 조직 근거 자체는 별도 담당자 capability 또는 routing rule 관리 UI 확장이 필요하다.
- 기준을 너무 낮추면 자동 배정 precision이 떨어질 수 있으므로 운영 전에는 평가 리포트와 함께 조정해야 한다.

---

# 2026-08-07 - 기타 카테고리 담당자 seed 배정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo seed, assignee routing, Settings UI data source |
| 관련 파일 | `data/demo/mail_decision_foundation.seed.json`, `tests/test_demo_seed_service.py`, `data/demo/README.md`, `docs/development/demo-data-standard.md` |

## 요청 또는 배경

- 사용자는 Settings와 담당자 배정 테스트에서 기타 카테고리도 담당자가 배정되어야 한다고 요청했다.
- 직전 seed는 fallback rule을 만들 수 있었지만 Settings의 `mail_categories` 표시는 `business_type` capability 기준이라 fallback capability만으로는 기타 담당자로 보이지 않았다.

## 확인한 사실

- Settings repository는 `invoice`, `payment_inquiry`, `spam` business type 중 하나 이상을 가진 담당자를 `기타` 카테고리 담당자로 표시한다.
- 따라서 기타 담당자는 routing rule만 추가하는 것이 아니라 Settings 표시 기준인 business-type capability에도 명시되어야 한다.

## 해결 방법

- `강태훈`에게 `invoice`, `payment_inquiry`, `spam` business-type capability를 추가해 `업무관리팀 팀장`이 기타 담당자로 표시되도록 했다.
- demo seed 테스트에서 기타 카테고리 표시와 `강태훈`의 `mail_categories == ["기타"]`를 검증한다.
- demo data 문서에 development organization seed가 general-category assignee를 포함해야 한다는 기준을 추가했다.

## 검증

- `uv run python -m app.tools.export_demo_seed --check`: assignee_capabilities 21, routing_rules 7 확인.
- `uv run pytest tests/test_demo_seed_service.py`: 2 passed.
- `uv run pytest`: 147 passed, 1 existing collection warning.
- 현재 Docker DB에 `python -m app.tools.load_demo_seed_postgres`를 실행했고, `settings_context()`에서 `강태훈 업무관리팀 팀장 기타` 표시를 확인했다.

## 남은 리스크와 후속 작업

- 현재 기타는 `invoice`, `payment_inquiry`, `spam` 중심이다. 운영에서 기타에 포함할 실제 업무 유형이 늘어나면 `CATEGORY_BUSINESS_TYPES`와 routing policy의 분류 타입 계약을 함께 확장해야 한다.

---

# 2026-08-07 - 담당자 테스트용 현실형 부서/직급 seed 보강

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo seed, assignee routing, Settings UI data source |
| 관련 파일 | `app/services/demo_seed_service.py`, `tests/test_demo_seed_service.py`, `data/demo/README.md`, `docs/development/demo-data-standard.md` |

## 요청 또는 배경

- 사용자는 담당자 배정 기능을 테스트하려면 fake 담당자라도 부서와 직급이 실제 데이터처럼 구성되어야 한다고 요청했다.
- 직전 seed는 Settings 탭에는 표시됐지만 모든 담당자의 부서가 `개발 Seed`, 직급이 `가짜 담당자`라 실제 조직 기준 routing 검증에는 부족했다.

## 확인한 사실

- Settings 담당자 관리는 `users.notification_preferences.department`와 `position`을 그대로 표시한다.
- 따라서 별도 UI 수정 없이 demo seed의 사용자 metadata를 현실적인 synthetic 조직 프로필로 바꾸면 Settings 화면과 routing 후보 표시가 같이 개선된다.
- 기존 seed의 사람, 이메일, capability, routing rule은 모두 synthetic이며 운영 데이터로 오인되지 않도록 `synthetic`과 `seed_source` 표시는 유지해야 한다.

## 해결 방법

- foundation seed 사용자 8명에 업무 성격별 부서/직급을 매핑했다.
- 예: 발주/문의 담당자는 `국내영업1팀 대리`, 기술 검토 담당자는 `기술지원팀 과장`, 납기/물류 담당자는 `구매물류팀 주임`, fallback 담당자는 `업무관리팀 팀장`으로 표시된다.
- Settings view 단위 테스트를 수정해 부서/직급 다양성과 주요 담당자의 표시값을 검증한다.
- demo data 문서에 realistic synthetic departments/positions가 Settings와 routing UI 테스트 목적임을 명시했다.

## 검증

- `uv run python -m app.tools.export_demo_seed --check`: users 8, assignee_capabilities 18, routing_rules 7 확인.
- `uv run pytest tests/test_demo_seed_service.py`: 2 passed.
- `uv run pytest`: 147 passed, 1 existing collection warning.
- 현재 Docker DB에 `python -m app.tools.load_demo_seed_postgres`를 실행해 seed를 재적재했고, `settings_context()`에서 8명 모두 현실형 부서/직급으로 표시되는 것을 확인했다.

## 남은 리스크와 후속 작업

- 이번 부서/직급은 테스트용 synthetic 조직 프로필이다. 실제 배정 정책 검증 전에는 고객사의 승인된 부서, 직급, 담당 범위, 부재/업무량 데이터로 교체해야 한다.
- 현재 routing rule은 여전히 category 중심이다. 부서/직급 자체가 배정 근거가 되려면 routing policy와 evidence model에 조직 계층/권한 조건을 별도 계약으로 추가해야 한다.

---

# 2026-08-07 - 첨부 분석 고정 필드 스키마 강제 보정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Attachment analysis, document field extraction, attachment Details presentation |
| 관련 파일 | `app/document_processing/parsers.py`, `app/document_processing/text_analyzer.py`, `app/document_processing/vision_analyzer.py`, `app/presentation/attachment_analysis.py`, `app/repositories/postgres_attachment_analysis_repository.py`, `docs/features/attachment-analysis.md`, `tests/test_attachment_analysis_presentation.py`, `tests/test_attachment_parsers.py`, `tests/test_postgres_attachment_analysis_repository.py` |

## 요청 또는 배경

- 사용자는 첨부파일 분석 결과가 문서 유형별 고정 필드만 추출되어야 하는데, 실제 결과에서 고정 필드 누락과 `Contact Person`, `Fluemax Ref No`, `Jinhan Line Ref No` 같은 비고정 필드가 생성되어 표시된다고 지적했다.
- 요구사항은 고정 필드와, 견적서/견적의뢰서의 경우 표 데이터만 정보 추출 결과로 남기는지 재검토하는 것이었다.

## 확인한 사실

- 기존 구현은 고정 필드 목록을 화면 표시 순서로만 사용했고, LLM이 반환한 `fields`를 저장 전에 제한하지 않았다.
- 화면 표시 정규화도 고정 문서 유형에서 표시 순서 밖의 필드를 추가로 출력해 비고정 필드가 사용자에게 노출될 수 있었다.
- 최초 수정에서 비고정 라벨을 고정 필드명으로 매핑해 살렸으나, 사용자는 애초에 고정 필드명만 필드로 허용되어야 한다고 재지적했다.
- 재분석 결과가 비어 있을 때 기존 current result의 fields를 보존하는 경로도 과거 비고정 필드를 되살릴 수 있었다.

## 해결 방법

- 문서 유형별 고정 필드 목록을 `PREDEFINED_DOCUMENT_FIELD_ORDER`로 승격하고, `filter_predefined_document_fields()`로 저장 전과 표시 전 모두 같은 허용 스키마를 적용하게 했다.
- LLM 구조화 출력의 `fields` 키 타입을 고정 필드명 `Literal`로 제한해 `Contact Person`, `Fluemax Ref No`, `Jinhan Line Ref No` 같은 비고정 키가 schema validation에서 거부되게 했다.
- 비고정 라벨은 `Attn`, `Our Ref No`, `Your Ref No` 등으로 변환하지 않고 제외한다.
- `line_items`는 견적서(`quote`)와 견적의뢰서(`rfq`)에서만 유지하며, 행 내부도 `Description`, `Code`, `Qty`, `Unit`, `U/Price`, `Amount`만 남긴다.
- 텍스트 LLM 분석, Vision 분석, 규칙 파서 결과, Postgres 기존 필드 보존 경로, Details 표시 경로에 모두 같은 필터를 적용했다. Postgres payload 생성 시 표시 전 선행 정규화를 제거해 고정 문서 유형에서 비고정 키가 살아나지 않게 했다.
- 기능 문서에 고정 필드 외 임의 필드 금지와 견적서/견적의뢰서 표 추출 정책을 명시했다.

## 검증

- `uv run pytest tests/test_attachment_analysis_presentation.py tests/test_attachment_parsers.py tests/test_postgres_attachment_analysis_repository.py`: 28 passed.
- `uv run pytest`: 145 passed, 1 existing collection warning.

## 남은 리스크와 후속 작업

- 이미 DB에 저장된 과거 current result는 새 재분석 또는 보존 경로를 거치면 비고정 필드가 제외되지만, 별도 마이그레이션으로 즉시 일괄 정리하지는 않았다.
- 실제 운영 양식에서 더 많은 필드가 필요하면 alias를 추가해 흡수하지 말고 고정 필드 스키마 변경 여부를 먼저 결정해야 한다.

---

# 2026-08-07 - 개발용 가짜 담당자 seed와 Settings 표시 연결

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo seed, assignee routing, Settings UI data source |
| 관련 파일 | `app/services/demo_seed_service.py`, `app/repositories/postgres_seed_writer.py`, `tests/test_demo_seed_service.py`, `data/demo/README.md`, `docs/development/demo-data-standard.md` |

## 요청 또는 배경

- 사용자는 담당자 배정 파이프라인 검증을 위해 가짜 담당자 데이터가 필요하며, 담당자 데이터 추가 시 Settings 탭에 자동 표시되어야 한다고 요청했다.
- 직전 작업으로 분류/요약은 retrieval 부족 상태에서도 저장되도록 바뀌었지만, active user, assignee capability, routing rule 데이터가 없어 담당자 후보 생성과 Settings 배정 상태 검증은 여전히 막혀 있었다.

## 확인한 사실

- `data/demo/mail_decision_foundation.seed.json`에는 이미 8명의 가짜 담당자와 capability 정의가 있었다.
- 기존 demo PostgreSQL seed writer는 이메일 fixture 테이블만 쓰고 `users`, `assignee_capabilities`, `routing_rules`, `categories`는 쓰지 않았다.
- Settings 탭은 DB의 `users`와 `assignee_capabilities`를 직접 읽으므로, seed writer가 해당 테이블에 row를 쓰면 별도 UI 수정 없이 자동 표시된다.
- `@coramail.invalid` synthetic evaluation 담당자는 Gmail 후보에서 제외되는 정책이 있으므로, 이번 foundation seed는 개발용 운영 담당자처럼 `@example.invalid` 주소를 사용하고 metadata에 synthetic seed임을 남기는 경로가 적합하다.

## 해결 방법

- demo seed bundle에 기본 category 6개, foundation user 8명, assignee capability 18개, category routing rule 7개를 포함하도록 `DemoSeedService`를 확장했다.
- `product_group` capability는 routing policy가 사용하는 `product` capability로 정규화해 저장한다.
- `PostgresSeedWriter`가 `categories`, `users`, `assignee_capabilities`, `routing_rules`를 이메일 seed보다 먼저 upsert하도록 확장했다.
- 가짜 담당자 row의 `notification_preferences`에는 `department = 개발 Seed`, `position = 가짜 담당자`, `synthetic = true`, `seed_source = mail_decision_foundation.seed.json`을 기록한다.
- demo data 문서에 development routing organization seed와 synthetic evaluation seed의 차이를 명시했다.

## 검증

- `uv run python -m app.tools.export_demo_seed --check`: users 8, assignee_capabilities 18, routing_rules 7 확인.
- `uv run pytest`: 147 passed, 1 existing collection warning.
- 현재 Docker DB에서 `python -m app.tools.load_demo_seed_postgres`를 실행해 written counts 78 rows를 확인했다.
- `settings_context()` 직접 호출에서 operating assignee 8명, synthetic 0명, 발주/문의/서비스/기술 route assignment가 자동 표시되는 것을 확인했다.

## 남은 리스크와 후속 작업

- 이 가짜 담당자는 Gmail-mode routing 후보에도 포함되는 개발용 seed다. 운영 배포 전 실제 조직 데이터로 교체해야 한다.
- 현재 fake routing rule은 category 단위 rule이며, request type별 rule 검색 정밀도와 workload/availability는 아직 단순화되어 있다.
- 다음 단계는 실제 Mail Decision Run에서 routing candidate가 생성되는지 한두 건 end-to-end로 확인하고, fact extraction의 고객명 오인 문제를 줄이는 것이다.

---

# 2026-08-07 - Retrieval 부족 시 분류/요약 생성 차단 해제

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Mail Decision Runtime, email classification, email summary, routing review policy |
| 관련 파일 | `app/services/mail_decision_runtime_service.py`, `tests/test_mail_decision_runtime.py`, `docs/architecture/agentic_rag_mail_decision_system.md`, `docs/features/email-classification.md`, `docs/features/email-summary.md` |

## 요청 또는 배경

- 사용자는 현재 시스템 아키텍처 리뷰 과정에서 이메일 유형 분류와 요약이 보이지 않는 근본 원인을 확인했고, 우선순위가 높은 개선을 먼저 진행해 달라고 요청했다.
- 직전 진단에서는 운영 DB의 active user, assignee capability, routing rule 부재와 별개로, `retrieval_context_insufficient`가 Decision Agent 실행 전 전체 run을 중단해 분류/요약 생성까지 막는 점을 핵심 병목으로 판단했다.

## 확인한 사실

- 현재 로컬 DB에는 classification pending 결과가 다수 있고, 기존 Mail Decision Run에는 `decision_output`이 없었다.
- `active users`, `assignee_capabilities`, `routing_rules`는 0건이어서 담당자 자동 배정은 아직 검증할 수 없다.
- 검색 문맥 부족은 담당자 자동 배정 차단 조건으로 유지해야 하지만, 본문과 첨부 근거 기반의 제한적 분류/요약 생성을 항상 막을 필요는 없다.

## 해결 방법

- `_evaluate_context()`가 검색 문맥 부족 시 즉시 `REVIEW_REQUIRED`로 종료하지 않고 `non_blocking_warnings`, `routing_blockers`, `retrieval_missing_context`에 기록한 뒤 다음 단계로 진행하게 했다.
- `_generate_decision()`은 `routing_blockers`에 `retrieval_context_insufficient`가 있으면 생성된 decision과 classification에 `review_required = true` 및 review reason을 보강한 뒤 저장한다.
- 기능/아키텍처 문서에 검색 문맥 부족은 자동 배정 차단 조건이며, 분류/요약은 제한 결과로 저장 가능하다는 정책을 반영했다.

## 검증

- `uv run pytest tests/test_mail_decision_runtime.py tests/test_mail_decision_routing_service.py tests/test_decision_agent.py`: 10 passed.
- `uv run pytest`: 140 passed, 1 existing collection warning.
- 실제 로컬 API에서 `POST /api/emails/889e6fa9-5052-5a38-b056-1b798ce84304/classification/regenerate`를 실행해 classification job `success`, category `발주`, confidence `0.99`를 확인했다.
- 같은 메일의 상세 API에서 `classification_state = completed`, `mail_category = 발주`, summary section 표시를 확인했다. 결과는 `review_required = true`, reason `retrieval_context_insufficient`로 저장됐다.

## 남은 리스크와 후속 작업

- 담당자 자동 배정은 여전히 운영 조직 데이터가 없어 불가능하다. 다음 우선순위는 최소 active user, assignee capability, routing rule seed를 추가해 routing candidate 생성까지 검증하는 것이다.
- Fact extraction이 문서 유형이나 자사명을 customer로 오인하는 문제가 남아 있어, 다음 단계에서 고객 후보 필터링과 한국어 업무 신호 보강이 필요하다.
- 이번 실제 API 검증은 로컬 개발 DB 상태를 변경했으며 운영 성능 주장으로 사용하지 않는다.

---

# 2026-08-07 - Docker Ollama GPU 사용 복구

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Docker Compose, Ollama, Local AI runtime performance |
| 관련 파일 | `docker-compose.yml` |

## 요청 또는 배경

- 사용자가 Docker 전환 후 LLM 답변이 더 오래 걸리는 느낌이 든다고 문의했다.
- 컨테이너 내부 `nvidia-smi` 실행은 `executable file not found`로 실패했다.

## 확인한 사실

- 호스트 `nvidia-smi`에서는 RTX 5060 Ti가 정상 인식됐다.
- `docker compose exec ollama ollama ps`에서 `llama3.2:latest`, `nomic-embed-text:latest`가 `100% CPU`로 표시되어 Ollama 컨테이너가 GPU를 사용하지 않고 있었다.
- 컨테이너 내부에 `nvidia-smi` 바이너리가 없는 것은 별도 문제이며, 실제 판단 기준은 Ollama의 `PROCESSOR` 상태였다.

## 해결 방법

- `docker-compose.yml`의 `ollama` 서비스에 `gpus: all`을 추가했다.
- 모델 재로드 체감 지연을 줄이기 위해 `OLLAMA_KEEP_ALIVE` 기본값을 `10m`으로 설정했다.
- `docker compose up -d ollama`로 Ollama 컨테이너를 재생성했다.

## 검증

- `docker compose config --services`: compose 설정 파싱 통과.
- `curl http://127.0.0.1:11435/api/generate`: `llama3.2:latest` 호출 성공.
- `docker compose exec ollama ollama ps`: `llama3.2:latest`가 `100% GPU`로 표시됨.
- Ollama 로그에서 후속 `/api/chat` 호출이 GPU에서 약 139 tokens/s로 처리됨을 확인했다.

## 남은 리스크와 후속 작업

- 첫 호출은 모델 로드 시간 때문에 여전히 느릴 수 있다. `OLLAMA_KEEP_ALIVE` 시간 이후 모델이 언로드되면 다음 호출에서 다시 로드 시간이 발생한다.
- Docker/WSL NVIDIA runtime이 깨진 환경에서는 `gpus: all`만으로는 동작하지 않을 수 있으며, 이 경우 NVIDIA Container Toolkit/WSL GPU 설정 점검이 필요하다.

---

# 2026-08-07 - 첨부 Details 모델 출력 필드 정규화 복구

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Attachment analysis, Local AI models, predefined document Details |
| 관련 파일 | `app/presentation/attachment_analysis.py`, `tests/test_attachment_analysis_presentation.py` |

## 요청 또는 배경

- 사용자가 첨부 분석 Details가 “표시할 정보 추출 결과가 없습니다.”로 표시되는 근본 원인을 요청했다.
- 사용자는 모델 관련 이슈를 의심했고, 이전에는 견적서 첨부가 필드별로 표시되는 것을 확인했다고 설명했다.

## 확인한 사실

- `web` 로그에 `model 'llama3.2:latest' not found` 404가 남아 있었고, `/api/health`에서 local AI LLM이 degraded 상태였다.
- Ollama 볼륨에 모델이 하나도 설치되어 있지 않아 텍스트, 임베딩, 비전 모델 호출이 실패하고 있었다.
- 모델 설치 후 재분석한 견적서 PDF는 DB에 `document_type=quote`와 `fields`를 정상 저장했다.
- 남은 UI 문제는 LLM이 반환한 `total_price`, `delivery_time`, `vessel/project`, 소문자 line item 키 같은 모델 출력 필드명이 화면의 사전정의 칼럼명과 매핑되지 않아 발생했다.

## 해결 방법

- 로컬 Ollama에 `llama3.2:latest`, `nomic-embed-text:latest`, `qwen3-vl:2b`를 설치해 `/api/health`의 `local_ai.ready=true`를 복구했다.
- 첨부 Details 정규화에서 모델 출력 키를 사전정의 칼럼명으로 변환하도록 보강했다.
- `dates`, `reference_numbers`, `line_items` 배열도 `Date`, `Our Ref No`, `Your Ref No`, `Description`, `Qty`, `U/Price`, `Amount` 등 화면 칼럼명으로 변환하도록 했다.
- 사전정의 문서 유형에서는 저장된 fields와 원문 기반 규칙 추출 결과를 병합해 빈 Details로 떨어질 가능성을 낮췄다.

## 검증

- `curl http://127.0.0.1:8000/api/health`: `local_ai.ready=true`, required model missing 없음.
- `curl -X POST /api/emails/6fa8fa6b-deeb-55bf-bdc0-dd18b11d0c8c/attachments/reanalyze`: 견적서 PDF 재분석 완료.
- `curl /api/emails/6fa8fa6b-deeb-55bf-bdc0-dd18b11d0c8c`: Details가 `To`, `Your Ref No`, `Vessel`, `Date`, `Our Ref No`, `Total Price`, `Terms & Conditions - Delivery time` 등으로 표시됨을 확인했다.
- `uv run pytest`: 140 passed, 1 existing collection warning.

## 남은 리스크와 후속 작업

- 모델 설치는 로컬 Docker 볼륨 상태에 의존하므로 볼륨을 삭제하면 `scripts/dev_pull_models.sh` 또는 동일한 pull 절차가 다시 필요하다.
- 향후 LLM 프롬프트가 새로운 필드 키를 만들면 정규화 alias를 추가해야 한다.

---

# 2026-08-07 - Mail Streams 행 높이 inbox 기준 정렬

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Dashboard Mail Streams UI, Inbox mail row UI |
| 관련 파일 | `app/static/app.css` |

## 요청 또는 배경

- 사용자가 inbox의 메일별 행 높이를 dashboard의 `Mail Streams` 각 메일 행에도 적용해 달라고 요청했다.
- 버튼이나 레이블이 겹치거나 밀려나지 않도록 내부 padding 조정도 함께 요청했다.

## 확인한 사실

- inbox와 dashboard `Mail Streams`는 `app/templates/partials/mail_rows.html` partial을 공유하지만, CSS에서 dashboard 전용 셀 padding과 수동 라우팅 버튼 높이가 별도로 적용되고 있었다.
- dashboard 수동 라우팅 버튼의 `min-height`가 행 높이를 키울 수 있어, inbox와 같은 조밀한 행 높이를 맞추려면 dashboard table 내부에서만 버튼 높이와 padding을 줄이는 것이 가장 좁은 수정이었다.

## 해결 방법

- `dashboard-mail-table` 본문 셀의 세로 padding을 inbox와 같은 `4px`로 맞췄다.
- `Mail Streams` 본문 행 높이를 `34px`로 지정했다.
- dashboard 내부의 수동 전달 버튼 높이, 좌우 padding, icon gap을 줄여 같은 행 높이 안에서 버튼과 레이블이 중앙 정렬되도록 했다.
- route cell 좌우 padding을 줄여 버튼이 밀려나지 않게 했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py tests/test_hosting_defaults.py`: 24 passed.

## 남은 리스크와 후속 작업

- CSS 단위 변경이며 브라우저 스크린샷 기반 픽셀 검증은 수행하지 않았다. 실제 데이터의 긴 버튼 라벨은 기존처럼 한 줄 유지와 overflow clipping에 의존한다.

---

# 2026-08-07 - 사전 정의 문서 유형 Details 내용 fallback 제거

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Attachment Details, predefined document fields, presentation fallback |
| 관련 파일 | `app/presentation/attachment_analysis.py`, `tests/test_attachment_analysis_presentation.py` |

## 요청 또는 배경

- 사용자가 Details의 칼럼명이 `내용`이면 안 되며, 사전 정의 문서 유형에서는 문서 유형별로 사전에 정의한 필드명이 칼럼명이어야 한다고 재차 지적했다.

## 확인한 사실

- 직전 수정은 `견적서 유형으로 추정됩니다.` summary가 `내용`으로 표시되는 경로는 막았지만, 그 다음 fallback인 `extracted_text` preview가 여전히 `내용` 라벨을 만들 수 있었다.
- 이 fallback은 비정형/unknown 문서에는 유용하지만, `quote`, `rfq`, `payment_request`, `transaction_statement` 같은 사전 정의 문서 유형에는 제품 요구사항과 맞지 않는다.

## 해결 방법

- `business_analysis_rows()`에서 사전 정의 문서 유형이면 필드 추출/복구 결과가 있을 때만 rows를 반환하고, rows가 없으면 `analysis_summary`와 `extracted_text` preview fallback을 모두 차단했다.
- 따라서 사전 정의 문서 유형의 Details에는 `To`, `Vessel`, `Our Ref No`, `Total Price` 같은 사전 필드명만 표시된다.
- 필드 추출 근거가 없으면 `내용` 행 대신 “표시할 정보 추출 결과가 없습니다.”로 표시된다.

## 검증

- `uv run pytest tests/test_attachment_analysis_presentation.py tests/test_attachment_parsers.py tests/test_mail_decision_ui.py`: 38 passed.
- `uv run pytest`: 139 passed, 1 existing collection warning.
- `python -m py_compile app/presentation/attachment_analysis.py`: passed.

---

# 2026-08-07 - 첨부 재분석 current 결과 다운그레이드 방지

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Attachment reanalysis, attachment_analysis_results current row, field preservation |
| 관련 파일 | `app/repositories/postgres_attachment_analysis_repository.py`, `tests/test_postgres_attachment_analysis_repository.py` |

## 요청 또는 배경

- 사용자가 로그에서 `POST /ui/emails/{email_uid}/attachments/reanalyze HTTP/1.1" 204 No Content`를 확인했고, 이것이 어제 보이던 첨부 분석 필드가 오늘 사라진 원인 같다고 지적했다.

## 확인한 사실

- `204 No Content` 자체는 HTMX가 `HX-Trigger` 이벤트만 받도록 설계된 정상 응답이다.
- 하지만 해당 POST 내부에서 `_reanalyze_email_attachments_by_ref()`가 실행되고, 각 첨부 결과를 `_postgres_attachment_analysis_repository.save(result)`로 저장한다.
- 기존 저장 로직은 current `document_understanding` 결과를 무조건 `is_current=false`로 내리고 새 결과를 current로 저장했다.
- 따라서 재분석 중 LLM document understanding이 실패해 새 결과가 `fields={}`와 유형 추정 summary만 가진 경우, 어제 current였던 필드 추출 결과를 실제로 덮어쓸 수 있었다.

## 해결 방법

- `PostgresAttachmentAnalysisRepository.save()`가 기존 current `result_json`을 먼저 읽도록 했다.
- 새 payload에 업무 필드가 없고 기존 current payload에는 업무 필드가 있으며 문서 유형이 같으면 기존 필드를 새 payload의 `fields`로 보존한다.
- 이월된 경우 `preserved_previous_business_fields` warning을 남겨 재분석 결과가 과거 필드를 보존했음을 추적할 수 있게 했다.
- 문서 유형이 다르거나 새 결과에 이미 업무 필드가 있으면 새 결과를 그대로 저장한다.

## 검증

- `uv run pytest tests/test_postgres_attachment_analysis_repository.py tests/test_attachment_analysis_presentation.py tests/test_attachment_parsers.py tests/test_mail_decision_ui.py`: 40 passed.
- `uv run pytest`: 138 passed, 1 existing collection warning.
- `python -m py_compile app/repositories/postgres_attachment_analysis_repository.py`: passed.

## 남은 리스크와 후속 작업

- 이미 summary-only current 결과가 저장되고 이전 current 결과가 내려간 경우에는 이번 보호 로직이 과거 row를 자동 복구하지 않는다. UI 표시 계층의 `extracted_text` 기반 복구가 먼저 적용되며, `extracted_text`도 없으면 원본 파일 재분석이 필요하다.

---

# 2026-08-07 - 저장된 첨부 분석 summary-only 결과의 Details 복구

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Attachment analysis presentation, stored analysis recovery, predefined document fields |
| 관련 파일 | `app/presentation/attachment_analysis.py`, `tests/test_attachment_analysis_presentation.py` |

## 요청 또는 배경

- 사용자가 전날에는 첨부파일 분석 결과가 필드별로 나오는 것을 확인했는데, 오늘은 Details에 `내용` 필드와 `견적서 유형으로 추정됩니다.`만 표시되는 이유를 재차 지적했다.

## 확인한 사실

- 전날 정상으로 보였던 결과는 LLM document understanding 또는 기존 필드 추출 결과가 `fields`/`extracted_fields`에 저장되어 있었기 때문에 UI가 필드 표를 표시한 것이다.
- 오늘 재분석에서 LLM 모델 호출이 실패하거나 보강 결과가 비어 있으면 parser fallback이 `document_type=quote`와 `analysis_summary=견적서 유형으로 추정됩니다.`만 저장했다.
- `PostgresAttachmentAnalysisRepository.save()`는 같은 attachment의 기존 current 분석을 `is_current=false`로 내리고 새 결과를 current로 저장한다. 따라서 어제 필드가 있던 current 결과가 오늘 summary-only current 결과로 교체될 수 있었다.
- 직전 수정으로 앞으로 생성되는 parser 결과는 사전 필드를 채우지만, 이미 DB에 저장된 summary-only current 결과는 UI가 그대로 읽으므로 여전히 Details에 `내용: 견적서 유형으로 추정됩니다.`가 표시될 수 있었다.

## 해결 방법

- Details 표시 계층에서 `fields`가 비어 있고 문서 유형이 `quote`/`rfq`/`payment_request`/`transaction_statement`이며 `extracted_text`가 있으면 사전 필드 extractor를 다시 적용해 필드 표를 복구하게 했다.
- 사전 정의 문서 유형에서 필드를 복구할 수 없는 경우 `견적서 유형으로 추정됩니다.` 같은 문서 유형 추정 summary를 사용자용 Details의 `내용`으로 표시하지 않도록 했다.
- 저장된 JSON이 `fields={}`, `analysis_summary=견적서 유형으로 추정됩니다.`, `extracted_text`에 견적서 라벨이 있는 회귀 케이스를 테스트로 고정했다.

## 검증

- `uv run pytest tests/test_attachment_analysis_presentation.py tests/test_attachment_parsers.py tests/test_mail_decision_ui.py`: 37 passed.
- `uv run pytest`: 135 passed, 1 existing collection warning.
- `python -m py_compile app/presentation/attachment_analysis.py`: passed.

## 남은 리스크와 후속 작업

- 저장된 summary-only 결과에 `extracted_text` 자체가 없으면 UI에서 필드를 복구할 근거가 없다. 그런 첨부는 재분석 또는 원본 파일 기반 재파싱이 필요하다.

---

# 2026-08-07 - Mail Decision 모델 호출 실패 fallback 처리

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Mail Decision Runtime, fact extraction, decision generation, retrieval degradation |
| 관련 파일 | `app/agents/fact_extraction_agent.py`, `app/agents/decision_agent.py`, `app/services/mail_decision_runtime_service.py`, `app/retrieval/service.py`, 관련 테스트 |

## 요청 또는 배경

- 사용자가 업무 판단 실행 후 `메일 정보 추출 과정에서 모델 호출에 실패했습니다.` 메시지가 표시되는 문제를 보고했다.

## 확인한 사실

- 해당 메시지는 `fact_extraction_gateway_failed` review reason의 사용자 표시 문구였다.
- 기존 Runtime은 `FactExtractionAgent.extract()`의 LLM 호출이 실패하면 즉시 `REVIEW_REQUIRED`로 멈추고, 본문·제목·첨부 분석 결과에서 이미 얻을 수 있는 근거 기반 사실도 저장하지 않았다.
- Fact extraction fallback을 만든 뒤에도 retrieval의 similar-case 검색이 embedding 모델을 호출하므로, 같은 LLM 장애가 검색 단계 실패로 번질 수 있었다.
- Decision Agent의 LLM 호출도 실패하면 결과 저장 없이 review reason만 남기도록 되어 있었다.

## 해결 방법

- `FactExtractionAgent.extract_grounded()`를 추가해 LLM이 실패해도 제목, 본문 라벨, 업무번호, 납품/긴급 신호, 첨부 분석 fields에서 제한적 `MailFacts`를 생성하도록 했다.
- Runtime은 fact extraction 모델 호출 실패를 terminal review reason이 아니라 `non_blocking_warnings`에 남기고, grounded facts를 저장한 뒤 검색 단계로 진행하게 했다.
- Decision Agent에는 `fallback_decision()`을 추가해 LLM 결정 생성이 실패해도 낮은 confidence, `generation_mode=fallback_llm_unavailable`, `review_required=True`인 제한적 판단 결과를 저장하게 했다.
- decision output이 review required이면 라우팅 미연결 단계까지 진행하지 않고 `decision_review_required`에서 멈추도록 했다.
- Retrieval service는 Qdrant/embedding 모델 호출 실패를 run 실패가 아니라 해당 query의 reason으로 기록하고 남은 검색 근거로 충분성을 평가하게 했다.

## 검증

- `uv run pytest`: 133 passed, 1 existing collection warning.
- `git diff --check`: passed.
- `python -m py_compile app/agents/fact_extraction_agent.py app/agents/decision_agent.py app/services/mail_decision_runtime_service.py`: passed.

## 남은 리스크와 후속 작업

- fallback 판단은 모델 기반 업무 판단이 아니며 자동 배정 근거로 쓰지 않는다. 운영 품질을 위해서는 Compose Ollama 모델 pull 및 health readiness가 정상인지 별도로 확인해야 한다.

---

# 2026-08-07 - 첨부파일 사전 문서 유형 필드 추출 fallback 복구

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Attachment analysis, predefined document fields, reanalysis, mail detail UI |
| 관련 파일 | `app/document_processing/parsers.py`, `tests/test_attachment_parsers.py` |

## 요청 또는 배경

- 사용자가 전날 구현한 첨부파일 분석이 견적서 유형을 분류했지만 Details에 `견적서 유형으로 추정됩니다.`만 표시되고, 사전 정의된 문서 유형별 필드값 추출 결과가 나오지 않는 문제를 보고했다.
- 사용자는 근본 원인을 찾아 해결해 달라고 요청했다.

## 확인한 사실

- UI 표시 계층은 `fields` 또는 `extracted_fields`가 있으면 업무 필드 표를 우선 표시하도록 이미 구현되어 있었다.
- 재분석 경로는 parser 결과 생성 후 LLM 기반 `TextAttachmentAnalyzer.enrich()`를 호출하지만, LLM Gateway 실패 또는 비활성 상태에서는 parser 결과를 그대로 저장한다.
- 기존 parser 결과는 PDF 텍스트 규칙으로 `quote` 같은 문서 유형과 `analysis_summary`만 채우고, 사전 정의 문서 유형의 `fields`는 채우지 않았다.
- 따라서 LLM enrichment가 실패하거나 필드를 반환하지 않으면 저장된 결과가 문서 유형 추정 summary뿐이고, Details가 그 summary로 fallback되는 것이 직접 원인이었다.

## 해결 방법

- PDF/XLSX/DOCX/TXT에서 파싱 텍스트가 있으면 `_result()` 단계에서 문서 유형을 규칙으로 추론하도록 통합했다.
- `quote`, `rfq`, `payment_request`, `transaction_statement`에 대해 사전 필드명 기반 deterministic extractor를 추가해 LLM enrichment 전에도 `fields`를 채우게 했다.
- 견적서의 `To`, `Vessel`, `Our Ref No`, `Total Price`, `Terms & Conditions - Delivery time`, 간단한 `line_items` 표 추출을 회귀 테스트로 고정했다.
- XLSX처럼 셀 텍스트가 `label | value` 형태로 펼쳐지는 경우도 같은 필드 extractor가 처리하도록 검증했다.

## 검증

- `uv run pytest tests/test_attachment_parsers.py tests/test_attachment_analysis_presentation.py`: 16 passed.
- `uv run pytest tests/test_mail_decision_ui.py tests/test_gmail_persistent_mode.py tests/test_mail_decision_runtime.py`: 24 passed.
- `python -m py_compile app/document_processing/parsers.py`: passed.

## 남은 리스크와 후속 작업

- deterministic extractor는 사전 필드명과 단순 표 형태를 기준으로 하는 fallback이다. 스캔 PDF/이미지, 복잡한 병합 셀, 라벨과 값이 멀리 떨어진 양식은 Vision/LLM 또는 레이아웃 parser 보강이 계속 필요하다.

---

# 2026-08-07 - Compose-first 개발 환경 재구축과 결정 정정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Docker Compose 개발 환경, web container, bootstrap, Ollama, health readiness |
| 관련 파일 | `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.env.example`, `app/tools/bootstrap_dev_environment.py`, `app/server.py`, `scripts/dev_up.sh`, `scripts/dev_pull_models.sh`, `docs/development/docker-dev-environment.md`, 관련 테스트 |

## 요청 또는 배경

- 사용자가 이전 개발 환경 구축이 “현재 오류만 피하는 infra-only 구성”에 가까우며, 처음 요청한 “확장성과 잠재 리스크까지 고려한 완전한 개발 환경”과 맞지 않으면 재구축하라고 지적했다.
- 사용자는 `coramail_ai`에서는 `docker compose up`으로 웹 서버까지 같이 시작됐다고 비교했다.

## 확인한 사실

- 이전 구성은 PostgreSQL/Qdrant 안정화에는 유효했지만 Compose 기본 서비스에 web이 없어 `docker compose up`만으로 앱이 시작되지 않았다.
- `coramail_ai`는 Compose에 `api` 서비스를 포함해 `docker compose up`으로 웹까지 실행하는 선례가 있었다.
- Compose one-shot bootstrap 서비스만 두면 최초 성공 후 schema 변경 시 자동 재실행되지 않을 수 있으므로, web 컨테이너 시작 시 bootstrap을 먼저 실행하는 방식이 더 안전했다.
- host Ollama를 `host.docker.internal`로 쓰는 방식은 host Ollama가 127.0.0.1에만 bind된 경우 컨테이너에서 접근할 수 없어 degraded가 될 수 있었다.
- 빈 Ollama 또는 호환 API가 예기치 않은 `/v1/models` payload를 반환하면 기존 health parser가 500을 낼 수 있었다.

## 해결 방법

- `Dockerfile`과 `.dockerignore`를 추가해 앱 컨테이너 이미지를 만들었다.
- `docker-compose.yml`에 기본 `web` 서비스를 추가해 `docker compose up --build`만으로 FastAPI 개발 서버가 시작되게 했다.
- `web` 시작 command가 `python -m app.tools.bootstrap_dev_environment`를 먼저 실행하고, 성공하면 uvicorn reload 서버를 실행하도록 했다.
- `bootstrap_dev_environment` 도구를 추가해 PostgreSQL readiness, Qdrant readiness, Qdrant collection 생성, PostgreSQL schema 적용, demo seed 적재를 컨테이너 내부 service URL 기준으로 수행하게 했다.
- Ollama를 기본 Compose 서비스로 전환하고 host port는 기존 로컬 Ollama와 충돌하지 않도록 `11435`로 열었다.
- Compose web의 LLM endpoint 기본값을 `http://ollama:11434/v1`로 바꿨다.
- `scripts/dev_up.sh`는 `docker compose up --build` 래퍼로 단순화했다.
- `scripts/dev_pull_models.sh`를 추가해 Compose Ollama에 text, vision, embedding 모델을 pull할 수 있게 했다.
- `/api/health`의 LLM readiness parser가 `data: null` 같은 예상 밖 payload에서도 500을 내지 않고 degraded로 내려가도록 수정했다.
- 문서와 테스트를 Compose-first 기준으로 갱신했다.

## 검증

- `docker compose up --build -d`: web, postgres, qdrant, ollama 기동 성공.
- `docker compose logs web`: bootstrap 실행, schema 4개 적용, demo seed 39 rows 적재, uvicorn 시작 확인.
- `curl http://127.0.0.1:8000/`: 200.
- `curl http://127.0.0.1:8000/api/health`: 200. Compose Ollama에 모델이 아직 없어 LLM은 degraded로 표시되지만 500은 발생하지 않음.
- `uv run pytest`: 130 passed, 1 existing collection warning.
- `docker compose config`: passed.
- `git diff --check`: passed.

## 남은 리스크와 후속 작업

- Compose Ollama volume에는 기본 모델이 자동 포함되지 않는다. 첫 실행 후 `scripts/dev_pull_models.sh`를 실행해야 `/api/health`의 LLM 항목이 ready가 된다.
- 실제 모델 자동 pull을 `docker compose up`에 포함하면 최초 실행 시간이 길어지고 네트워크 실패가 web startup을 막을 수 있어 별도 스크립트로 분리했다.
- Gmail OAuth redirect/callback은 컨테이너 환경에서 추가 검증이 필요하다.

---

# 2026-08-07 - Docker Compose 기반 로컬 개발 환경 구축

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Docker development environment, PostgreSQL, Qdrant, local bootstrap |
| 관련 파일 | `docker-compose.yml`, `.env.example`, `scripts/dev_*.sh`, `docs/development/docker-dev-environment.md`, `README.md`, `tests/test_dev_environment.py` |

## 요청 또는 배경

- 사용자가 현재 재부팅 후 DB 미기동 문제뿐 아니라 추후 잠재 리스크와 확장성을 고려해 개발용 Docker 환경을 구축해 달라고 요청했다.
- 사용자는 먼저 계획을 세운 후 진행하라고 요청했다.

## 확인한 사실

- 저장소에는 기존 `Dockerfile`, `docker-compose.yml`, `.dockerignore`가 없었다.
- PostgreSQL schema 적용 CLI와 demo seed CLI는 이미 있어 Compose bootstrap에 재사용할 수 있었다.
- 기존 문제의 직접 원인은 `.env`가 Gmail/PostgreSQL 모드를 가리키는데 재부팅 후 PostgreSQL/Qdrant가 자동 기동되지 않는 구조였다.
- Qdrant 서버가 떠 있어도 기본 collection `coramail_cases_clean_v2`가 없으면 `/api/health`가 degraded가 된다.
- 고정 `container_name`은 과거 실험 컨테이너와 충돌할 수 있어 Compose project name 기반 자동 이름을 쓰는 편이 더 안전했다.

## 해결 방법

- `docker-compose.yml`을 추가해 PostgreSQL 17과 Qdrant를 기본 개발 인프라로 구성했다.
- Ollama는 optional Compose profile로 두어 로컬 Ollama 또는 GPU/runtime 선택을 막지 않게 했다.
- `.env.example`에 host 실행 기준 DB, Qdrant, LLM, dev script 기본값을 추가했다.
- `scripts/dev_up.sh`를 추가해 Docker Compose 기동, PostgreSQL readiness wait, Qdrant readiness wait, 기본 Qdrant collection 생성, schema 적용, demo seed 적재를 한 번에 수행하게 했다.
- `scripts/dev_app.sh`, `scripts/dev_down.sh`, `scripts/dev_reset.sh`, `scripts/dev_env.sh`를 추가했다.
- `dev_reset.sh`는 volume 삭제 전 `CORAMAIL_DEV_RESET_CONFIRM=delete-dev-volumes` 확인값을 요구하도록 했다.
- `docs/development/docker-dev-environment.md`와 README에 빠른 시작, 포트 충돌, host/container URL 차이, volume 초기화, 운영과의 차이, 향후 앱 컨테이너화 기준을 기록했다.
- 개발 환경 계약 테스트를 추가했다.

## 검증

- `docker compose config`: passed.
- `scripts/dev_up.sh`: PostgreSQL/Qdrant 기동, schema 4개 적용, demo seed 39 rows 적재 성공.
- `scripts/dev_up.sh` 반복 실행: passed.
- `scripts/dev_app.sh`: uvicorn 개발 서버 기동 확인.
- `curl http://127.0.0.1:8000/api/health`: `status=ok`, database/llm/qdrant ready 확인.
- `uv run pytest`: 127 passed, 1 existing collection warning.
- `git diff --check`: passed.

## 남은 리스크와 후속 작업

- 앱은 아직 컨테이너화하지 않았다. Gmail OAuth, 첨부파일 저장 경로, reload, local LLM/GPU 연결을 확정한 뒤 앱 컨테이너화를 별도 단계로 진행하는 것이 안전하다.
- Qdrant 기본 collection은 빈 collection으로 생성한다. 실제 유사 사례 검색 데이터를 넣으려면 synthetic evaluation seed 또는 별도 indexing pipeline을 실행해야 한다.
- Compose 기본 비밀번호는 로컬 개발용이다. 운영이나 고객 환경에는 그대로 사용하면 안 된다.

---

# 2026-08-07 - 재부팅 후 웹 500 오류 원인 확인과 fallback 처리

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | FastAPI UI, Gmail/PostgreSQL display mode, hosting defaults |
| 관련 파일 | `app/server.py`, `tests/test_hosting_defaults.py` |

## 요청 또는 배경

- 사용자가 재부팅 후 웹을 실행하면 다시 Internal Server Error가 뜬다며 근본 원인 확인을 요청했다.

## 확인한 사실

- `.env`에 `CORAMAIL_DATABASE_URL`, `CORAMAIL_LOCAL_DEV_DEFAULTS`, `CORAMAIL_DEMO_MODE`가 설정되어 앱이 기본 Gmail/PostgreSQL 경로를 선택했다.
- 재부팅 후 로컬 PostgreSQL은 `127.0.0.1:5432`에서 리스닝하지 않았다.
- `/`와 `/api/health` 모두 `GmailMailboxService.list_emails -> PostgresMailboxService -> psycopg.connect`에서 `Connection refused`가 발생해 500으로 실패했다.
- 즉 원인은 화면 템플릿이 아니라, 영구 설정은 DB/Gmail 모드를 가리키는데 재부팅 후 DB 의존성이 준비되지 않는 실행 환경과, 그 실패를 UI/health가 degrade로 처리하지 못한 구조였다.

## 해결 방법

- 메일 목록 조회를 `mail_rows()` helper로 감싸고, 연결 계열 오류가 발생하면 demo fixture로 fallback하도록 했다.
- 루트, 대시보드, 인박스, mail rows, UI state, health, `/api/emails`, 관련 메일 조회가 같은 fallback 경로를 사용하도록 교체했다.
- 메일 상세 조회도 persistent DB 조회 실패 시 demo fixture 상세 조회로 fallback하도록 보강했다.
- fallback 상황에서도 `/api/health`는 200을 반환하고 상태를 `degraded`로 보고하며 DB 연결 실패 원인을 readiness에 남긴다.

## 검증

- `uv run pytest tests/test_hosting_defaults.py tests/test_mail_decision_ui.py::test_dashboard_summary_excludes_unclassified_and_unassigned_rows`: passed.
- `uv run python -m py_compile app/server.py tests/test_hosting_defaults.py`: passed.
- `curl http://127.0.0.1:8002/`: 200 OK.
- `curl http://127.0.0.1:8002/api/health`: 200 OK, `status=degraded`, database `Connection refused`.
- 기존 `127.0.0.1:8000` 서버에서도 `/`와 `/api/health`가 200으로 복구됨을 확인했다.
- `uv run pytest`: 122 passed, 1 existing collection warning.

## 남은 리스크와 후속 작업

- 이 수정은 웹 500을 막는 fallback이며 PostgreSQL을 자동 기동하지는 않는다.
- 실제 Gmail/PostgreSQL 운영 데이터를 보려면 PostgreSQL 서비스 자동 시작 또는 앱 실행 전 DB bootstrap을 별도로 정리해야 한다.
- 현재 Qdrant도 `127.0.0.1:6333 Connection refused`라 health는 계속 `degraded`로 표시된다.

---

# 2026-08-06 - Search intent/tool 설계 근거 재검토와 개선

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search 탭, Agentic RAG, intent taxonomy, tool registry |
| 관련 파일 | `docs/features/context-search-qdrant-indexing.md` |

## 요청 또는 배경

- 사용자가 intent 설계를 어떻게 했고 tool을 어떻게 구성했는지 근거를 들어 설명하라고 요청했다.
- 또한 기존 설계를 객관적으로 재검토하고 개선해 달라고 요청했다.

## 확인한 사실

- 기존 문서의 방향은 맞지만 intent taxonomy의 근거가 충분히 드러나지 않았고, tool도 이름 수준이라 구현 계약으로 쓰기에는 부족했다.
- `document_qa`와 `mailbox_lookup`만으로는 필드 추출형 질문, 요약형 질문, thread 조회, 라우팅 지식 조회의 서로 다른 실패 양상과 검증 기준을 분리하기 어렵다.
- LLM planner가 누락하거나 생성한 값을 그대로 필수 tool argument로 쓰면 RAG 품질과 보안 경계가 약해진다.

## 해결 방법

- 각 intent를 왜 분리했는지 신뢰 소스와 실패 양상 기준으로 근거를 문서화했다.
- `unsupported_or_ambiguous`를 `clarification_needed`와 `unsupported`로 분리했다.
- 복합 질문을 위해 primary intent와 secondary actions를 허용하는 방향을 추가했다.
- `metadata_mail_lookup`, `business_ref_exact_lookup`, `attachment_field_retriever`, `document_hybrid_retriever`, `email_detail_fetcher`, `thread_lookup`, `routing_context_lookup`의 tool registry를 신뢰 소스, 입력, 출력, 실패 조건, LLM 역할로 정리했다.
- tool selection policy와 intent/tool 검증 기준을 추가했다.

## 검증

- 문서 변경만 수행했다.
- `git diff --check docs/features/context-search-qdrant-indexing.md docs/development/codex-history/session-log.md`: passed.

## 남은 리스크와 후속 작업

- 다음 구현에서는 이 문서 계약을 `SearchIntent`, tool plan schema, evidence evaluator schema, API trace로 승격해야 한다.
- 현재 작업트리에 별도 첨부 Details 관련 미커밋 변경이 있어 이번 커밋에는 포함하지 않는다.

---

# 2026-08-06 - Agentic Search RAG 전문가 피드백과 해결안 정리

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search 탭, Agentic RAG, query intent, tool planning |
| 관련 파일 | `docs/features/context-search-qdrant-indexing.md` |

## 요청 또는 배경

- 사용자가 질문의도분석 후 질문의도에 맞게 tool을 호출하거나 LLM으로 답변을 생성하는 방식이 적절해 보인다고 제안했고, Agent 및 RAG 전문가 관점의 객관적인 피드백과 해결방안을 요청했다.

## 확인한 사실

- 현재 Search 탭은 planner, hybrid retrieval, grounded answer를 갖고 있지만, 질문 의도별 tool 선택과 재검색 loop가 명시적인 계약으로 분리되어 있지 않다.
- 견적서 납기·총액 사례는 단순한 특정 문자열 검색 문제가 아니라, 의도 분석, 필수 제약 보존, 필드 단위 evidence retrieval, 답변 충분성 평가가 분리되지 않은 데서 생긴 문제다.

## 해결 방법

- `context-search-qdrant-indexing.md`에 Agentic Search RAG 목표 구조를 추가했다.
- 초기 intent taxonomy를 `mailbox_lookup`, `document_field_qa`, `document_summary_qa`, `thread_lookup`, `routing_context_qa`, `unsupported_or_ambiguous`로 정리했다.
- 의도별 우선 tool, LLM 신뢰 경계, Evidence Evaluator의 책임, 답변 생성 규칙, 단계별 M5 구현안을 문서화했다.

## 검증

- 문서 변경만 수행했다.
- `git diff --check docs/features/context-search-qdrant-indexing.md docs/development/codex-history/session-log.md`: passed.

## 남은 리스크와 후속 작업

- 다음 구현 단계에서는 문서화한 intent/tool/evidence schema를 실제 API trace와 `MailSearchService` Agent loop로 옮겨야 한다.
- 현재 작업트리에는 별도 첨부 Details 관련 미커밋 변경이 남아 있어 이번 문서 커밋에는 포함하지 않는다.

---

# 2026-08-06 - 첨부 Details 그룹형 필드 표시 오류 수정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox attachment Details, attachment analysis presentation |
| 관련 파일 | `app/presentation/attachment_analysis.py`, `tests/test_attachment_analysis_presentation.py` |

## 요청 또는 배경

- 첨부 분석 Details가 `dates name Date / value 2025-02-21`, `customer name Company Name / value ...`처럼 그룹명과 내부 JSON 키를 그대로 표시했다.
- 사용자는 필드값과 추출한 정보만 표시되도록 근본 원인을 찾아 수정해 달라고 요청했다.

## 확인한 사실

- 분석 결과의 `fields`는 `dates`, `totals`, `customer`, `delivery_terms`, `reference_numbers` 같은 그룹 아래에 `{name, value}` 또는 `{field_name, value}` 항목을 담을 수 있다.
- 기존 presentation 변환은 dict를 표시할 때 모든 key/value를 문자열로 이어 붙여 `name ... / value ...`를 만들었다.
- 문제는 분석 결과 생성이 아니라 UI 표시용 정규화 계층에서 그룹형 필드를 펼치지 못한 것이다.

## 해결 방법

- attachment field 정규화가 그룹명 대신 내부 `name`/`field_name`을 실제 표시 label로 사용하고 `value`만 표시값으로 쓰도록 수정했다.
- 리스트 형태의 그룹 필드도 각 항목으로 펼치고, 빈 값과 내부 메타데이터는 계속 제외하도록 했다.
- `Vessel Name`은 사전 양식 표시 필드 `Vessel`로, `total price`는 `Total Price`로 정규화했다.

## 검증

- `uv run pytest tests/test_attachment_analysis_presentation.py -q`: 9 passed.
- `uv run pytest -q`: 120 passed, 1 existing collection warning.
- `python -m py_compile app/presentation/attachment_analysis.py tests/test_attachment_analysis_presentation.py`: passed.

## 남은 리스크와 후속 작업

- 이미 브라우저에 열린 상세 패널은 새 HTML을 받기 전까지 이전 표시를 유지할 수 있다. 서버 reload 후 메일 상세를 새로 열거나 첨부 재분석/상세 refresh를 실행해야 한다.

---

# 2026-08-06 - Search RAG 답변 trace 표시 위치 정리

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search tab, RAG answer UI, evidence metadata |
| 관련 파일 | `app/templates/partials/search_results.html`, `app/static/app.css`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- Search 탭의 RAG 답변칸 마지막에 모델명과 후보/근거 개수 trace가 문장처럼 붙어 표시되는 부분을 제거해 달라는 요청을 받았다.
- 같은 정보는 답변 본문이 아니라 근거 영역에 표시하되, 기존 문자열을 그대로 노출하지 않고 UI에 맞게 정리해야 했다.

## 확인한 사실

- `partials/search_results.html`에서 `result.trace.answer_model`, `candidate_count`, `selected_count`를 RAG 답변 패널 본문 하단에 직접 렌더링하고 있었다.
- 관련 UI 테스트도 기존 문장형 trace 문자열을 기대하고 있었다.
- 작업 시작 전 `app/services/mail_search_service.py`, `docs/features/context-search-qdrant-indexing.md`, `tests/test_mail_search_service.py`에 별도 미커밋 변경이 있었으므로 이번 작업 범위에서 제외했다.

## 해결 방법

- RAG 답변 패널에서는 trace 문구를 제거했다.
- 근거 패널 헤더에 모델과 채택/검토 수치를 작은 메타 배지로 표시하도록 옮겼다.
- 좁은 화면에서도 헤더 메타와 검색어 라벨이 줄바꿈될 수 있도록 전용 CSS를 추가했다.
- UI 테스트는 기존 문장형 trace가 사라지고 새 근거 메타가 표시되는지 검증하도록 갱신했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py -k search`: 2 passed.
- `pytest tests/test_mail_decision_ui.py -k search`: 로컬 PATH에 `pytest` 실행 파일이 없어 실행되지 않았다.

## 남은 리스크와 후속 작업

- 실제 브라우저 렌더링 스크린샷 검증은 수행하지 않았다. 필요 시 search 화면을 띄워 모바일/데스크톱 헤더 줄바꿈을 확인하면 된다.

---

# 2026-08-06 - Search RAG QuerySignals 일반화

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search 탭, MailSearchService, hybrid retrieval, grounded RAG answer |
| 관련 파일 | `app/services/mail_search_service.py`, `tests/test_mail_search_service.py`, `docs/features/context-search-qdrant-indexing.md` |

## 요청 또는 배경

- 직전 수정이 `FM250016318 견적서의 납기와 총액` 질문에만 좁게 맞춰진 방식이 아니라, 이 사례를 바탕으로 더 강건한 RAG가 되도록 일반화해 달라는 요청을 받았다.

## 확인한 사실

- 기존 보강은 원 질문의 식별자 보존과 다중 excerpt를 추가했지만, “업무 식별자 + 확인할 필드”를 명시적 검색 신호로 모델링하지는 않았다.
- planner가 식별자를 누락하는 경우뿐 아니라, 반대로 질문에 없는 식별자를 만들어내는 경우도 방어해야 한다.
- 실제 첨부 분석 결과는 한글 질문(`납기`, `총액`, `수량`)과 영어 필드명(`Delivery date`, `Grand total`, `Amount`, `Qty`)이 섞일 수 있다.

## 해결 방법

- `SearchQuerySignals`를 추가해 원 질문, planner 결과, 업무 식별자, 요청 필드명, 한/영 필드 alias를 하나의 검색 신호로 병합했다.
- 후보 필수 필터는 원 질문에 실제로 포함된 업무 식별자만 사용하도록 했다. planner가 질문에 없는 식별자를 만들면 retrieval query에는 남을 수 있지만 필수 필터로 승격하지 않는다.
- `납기`, `총액`, `수량`, `품번`, `제품`, `선박` 계열 필드 alias를 lexical retrieval과 excerpt 위치 선정에 반영했다.
- 회귀 테스트를 FM 번호 전용에서 비-FM 참조번호, 영어 첨부 필드명, planner invented identifier 방어까지 확장했다.

## 검증

- `uv run pytest tests/test_mail_search_service.py -q`: 15 passed.
- `uv run pytest tests/test_mail_search_service.py tests/test_mail_decision_ui.py -q`: 34 passed.
- `python -m py_compile app/services/mail_search_service.py`: passed.
- `uv run ruff check app/services/mail_search_service.py tests/test_mail_search_service.py`: passed.
- `uv run pytest -q`: 119 passed, 1 failed, 1 warning. 실패는 `tests/test_attachment_analysis_presentation.py::test_attachment_rows_flatten_grouped_name_value_fields`의 첨부 Details 필드 정렬 기대값 문제로, 이번 Search RAG 변경 파일과 독립적이다.

## 남은 리스크와 후속 작업

- 필드 alias 목록은 초기 업무 필드 중심이다. 운영 첨부에서 반복되는 새로운 필드명은 사용자 수정 이력과 검색 trace를 보고 확장해야 한다.
- 검색 trace에는 아직 `QuerySignals` 원문이 별도 구조로 노출되지 않는다. 운영 관찰성을 높이려면 trace에 required identifiers와 alias-expanded terms를 추가할 수 있다.

---

# 2026-08-06 - Search 탭 견적서 납기·총액 Retrieval 보강

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search 탭, MailSearchService, hybrid retrieval, grounded RAG answer |
| 관련 파일 | `app/services/mail_search_service.py`, `tests/test_mail_search_service.py`, `docs/features/context-search-qdrant-indexing.md` |

## 요청 또는 배경

- Search 탭에서 `FM250016318 견적서의 납기와 총액` 질문이 `제공된 메일과 첨부 분석 근거만으로는 질문에 답할 수 없습니다.`로 반환되는 문제의 근본 원인을 찾아 Retrieval 기법으로 해결해 달라는 요청을 받았다.

## 확인한 사실

- 검색 서비스는 업무 식별자가 포함된 질문에서 동일 식별자가 없는 문서를 제외하는 정책을 갖고 있었지만, LLM planner가 `semantic_query`를 만들며 원 질문의 FM 번호를 누락하면 identifier 기반 후보 필터가 약해질 수 있었다.
- 긴 첨부 분석 결과에서는 기존 excerpt가 첫 매칭 위치 하나 주변만 잘라 LLM prompt에 넣었다. 이 경우 FM 번호는 포함되지만 뒤쪽의 `납기`, `총액` 근거가 prompt에서 사라져 LLM이 근거 부족으로 판정할 수 있었다.
- 현재 `data/demo/received_quotations.fixture.json`의 데모 fixture에는 `FM250016318` 자체가 없고 `FM250016038`, `FM250016378`, `FM250016030`만 있다. 운영 Gmail/PostgreSQL 모드에서는 실제 DB의 첨부 분석 결과가 검색 대상이다.

## 해결 방법

- `document_qa` 검색어를 planner 결과만 사용하지 않고 원 질문의 업무 식별자와 요청 필드명을 보존하도록 했다.
- 긴 메일·첨부 근거 preview를 첫 매칭 하나가 아니라 업무 식별자와 요청 필드 주변의 여러 조각으로 구성하도록 바꿨다.
- planner가 FM 번호를 누락하는 회귀와, 긴 첨부 분석문에서 FM 번호·납기·총액이 멀리 떨어진 회귀를 테스트로 추가했다.
- 검색 기능 문서에 원 질문 식별자 보존과 다중 excerpt 기준을 반영했다.

## 검증

- `uv run pytest tests/test_mail_search_service.py -q`: 13 passed.
- `uv run pytest tests/test_mail_search_service.py tests/test_mail_decision_ui.py -q`: 31 passed.
- `python -m py_compile app/services/mail_search_service.py`: passed.
- `uv run ruff check app/services/mail_search_service.py tests/test_mail_search_service.py`: passed.

## 남은 리스크와 후속 작업

- 실제 `FM250016318` 답변 품질은 운영 PostgreSQL/Gmail 모드의 첨부 분석 결과에 해당 번호, 납기, 총액이 저장되어 있어야 검증할 수 있다.
- 현재 작업트리에 기존 UI/CSS 및 첨부 분석 관련 미커밋 변경이 있어 이번 수정 커밋에는 검색 로직과 관련 문서·테스트만 분리해야 한다.

---

# 2026-08-06 - Gmail 첨부 재분석 provider 조회 오류 수정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox attachment reanalysis, Gmail/PostgreSQL mailbox adapter |
| 관련 파일 | `app/server.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 첨부 레이블이 여전히 표시되지 않아 처리 시간이 오래 걸리는 문제인지, 코드 문제인지 확인 요청을 받았다.

## 확인한 사실

- 서버는 `uvicorn --reload`로 실행 중이라 코드 변경 자체는 reload될 수 있는 상태였다.
- 첨부 재분석 함수 `_reanalyze_email_attachments_by_ref`가 메일 상세 조회는 Gmail/Synthetic persistent service에서 찾으면서, 첨부 목록 조회는 항상 synthetic `_postgres_service.repository`에 고정해 호출했다.
- Gmail provider 메일에서는 이 경로가 실제 Gmail 첨부를 조회하지 못해 재분석 결과가 저장되지 않거나 `attachment_count=0`으로 조용히 끝날 수 있었다.

## 해결 방법

- 이메일 UUID를 해석할 때 실제로 매칭된 persistent mailbox service를 함께 반환하는 helper를 추가했다.
- 첨부 재분석이 매칭된 service의 repository에서 첨부를 조회하도록 변경했다.
- Gmail persistent service에만 첨부가 있는 경우 synthetic service를 호출하지 않고 Gmail service 첨부를 저장하는 회귀 테스트를 추가했다.

## 검증

- `uv run pytest tests/test_mail_decision_ui.py tests/test_attachment_parsers.py -q`: 25 passed.
- `uv run pytest -q`: 117 passed, 1 existing collection warning.
- `python -m py_compile app/server.py tests/test_mail_decision_ui.py`: passed.

## 남은 리스크와 후속 작업

- 이미 저장된 과거 첨부 분석 결과는 자동 갱신되지 않는다. 서버 reload 이후 해당 메일에서 첨부 재분석을 다시 실행해야 새 레이블이 저장된다.

---

# 2026-08-06 - coramail_ai 첨부 문서/이미지 레이블 기준 이식

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Attachment parser, attachment understanding, Inbox attachment labels |
| 관련 파일 | `app/document_processing/attachment_classifier.py`, `app/document_processing/parsers.py`, `app/document_processing/text_analyzer.py`, `app/document_processing/vision_analyzer.py`, `app/presentation/attachment_analysis.py`, 관련 문서와 테스트 |

## 요청 또는 배경

- 양식이 있는 PDF는 견적서, 견적의뢰서 같은 문서 유형을 사전 기준으로 분류해야 하는데 일부 파일에는 레이블이 없었다.
- 이미지 첨부도 어떤 이미지 파일인지 레이블이 붙어야 하는데 비어 있었다.
- 기준과 내부 구현은 기존 `coramail_ai` 코드를 참고해 이식해 달라는 요청을 받았다.

## 확인한 사실

- `coramail_ai`는 `quote`, `rfq`, `payment_request`, `transaction_statement`, `drawing_scan`, `manual_scan`, `field_photo`, `part_photo`, `document_scan`, `unknown`을 허용 문서 카테고리로 사용했다.
- PDF 텍스트의 `QUOTATION`, `INQUIRY`, `견적서`, `견적의뢰서`, `입금요청서`, `거래명세서`는 규칙으로 먼저 문서 유형을 추정했다.
- 현재 구현은 이미지 파서가 width/height metadata와 `vision_analysis_required`만 남기고 `document_type`을 비워, Vision/LLM이 없거나 실패하면 UI 레이블이 비는 구조였다.
- 텍스트 분석 LLM이 일반 문서나 unknown을 반환하면 파서 단계의 더 구체적인 규칙 기반 레이블을 덮어쓸 수 있었다.

## 해결 방법

- `coramail_ai` 기준의 첨부 카테고리, 한글 레이블, PDF 텍스트 규칙, 이미지/PDF 파일명 fallback 규칙을 `attachment_classifier`로 이식했다.
- PDF 파서가 텍스트 추출 직후 사전 규칙으로 `quote`, `rfq`, `payment_request`, `transaction_statement`를 부여하도록 연결했다.
- 이미지 파서와 Vision 분석 fallback이 파일명/MIME 기준으로 `drawing_scan`, `manual_scan`, `field_photo`, `part_photo`, `document_scan` 중 하나를 남기도록 수정했다.
- 텍스트 분석 LLM이 `unknown` 또는 `general_document`를 반환할 때는 파서 단계의 구체적인 규칙 레이블을 보존하도록 했다.
- presentation 레이블도 `coramail_ai`와 맞춰 `document_scan`을 `JPG 스캔본`으로 표시하도록 정리했다.

## 검증

- `uv run pytest tests/test_attachment_parsers.py tests/test_attachment_analysis_presentation.py -q`: 14 passed.
- `uv run pytest -q`: 114 passed, 1 existing collection warning.
- `python -m py_compile app/document_processing/attachment_classifier.py app/document_processing/parsers.py app/document_processing/text_analyzer.py app/document_processing/vision_analyzer.py app/presentation/attachment_analysis.py`: passed.
- `uv run ruff check app/document_processing/attachment_classifier.py app/document_processing/parsers.py app/document_processing/text_analyzer.py app/document_processing/vision_analyzer.py app/presentation/attachment_analysis.py tests/test_attachment_parsers.py`: passed.

## 남은 리스크와 후속 작업

- 이미지 세부 분류는 Vision 결과가 없을 때 파일명 fallback을 사용하므로 실제 이미지 내용과 다를 수 있다. 운영 정확도를 높이려면 Vision 분석 결과와 사용자 수정 이력을 평가 데이터로 누적해야 한다.

---

# 2026-08-06 - 첨부 Details 표시와 대시보드 완료율 집계 오류 수정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox attachment Details, dashboard classification/routing stats |
| 관련 파일 | `app/presentation/attachment_analysis.py`, `app/services/postgres_mail_service.py`, `app/server.py`, 관련 테스트 |

## 요청 또는 배경

- Inbox 탭에서 사전 양식이 정해진 첨부 문서(견적의뢰서, 견적서 등)는 정의된 필드와 추출 정보를 Details에 표시해야 했다.
- 메일 분류 레이블이 `미분류`인데 대시보드 `AI Auto-Classified`가 100%로 표시되고, 배정이 `미할당`인데 `AI Auto-Routed`가 100%로 표시되는 오류의 근본 원인 확인과 수정을 요청받았다.

## 확인한 사실

- Details 템플릿은 이미 `analysis_rows`를 표시하고 있었지만, PostgreSQL payload와 presentation 계층에서 `quotation`, `견적서`, `견적의뢰서` 같은 legacy/coramail_ai 문서 유형 alias가 표준 `quote`/`rfq` 필드 순서로 안정적으로 정규화되지 않았다.
- 사전 필드 순서가 있는 문서에서 순서표에 없는 legacy 추출 필드(`Reference No.` 등)가 누락될 수 있었다.
- 대시보드 `classified_count`는 `len(rows)`를 그대로 사용했고, `routed_count`는 truthy 문자열이면 완료로 세서 `"미할당"`도 배정 완료에 포함했다.
- Routing Overview도 `"담당자 검토 필요"`를 업무량/배정 완료처럼 집계할 수 있었다.

## 해결 방법

- 첨부 문서 유형 alias를 canonical `quote`/`rfq`/`payment_request`/`transaction_statement`로 정규화하고, PostgreSQL 첨부 payload에도 같은 정규화를 적용했다.
- 사전 양식 문서는 정의된 필드 순서를 먼저 표시하되, 내부 메타데이터가 아닌 추가 추출 업무 필드도 Details에 이어서 표시하도록 수정했다.
- 대시보드 집계를 `mail_category != 미분류`와 실제 라우팅 완료 조건으로 계산하도록 분리했다.
- `미할당`과 `담당자 검토 필요`는 자동 배정 완료 및 담당자 workload에서 제외했다.

## 검증

- `uv run pytest tests/test_attachment_analysis_presentation.py tests/test_mail_decision_ui.py -q`: 26 passed.
- `uv run pytest -q`: 112 passed, 1 existing collection warning.

## 남은 리스크와 후속 작업

- 현재 Details는 정규화 가능한 legacy/Mail Decision 필드 계약을 표시한다. 운영에서 새 문서 유형이 추가되면 alias와 필드 순서 표를 함께 확장해야 한다.

---

# 2026-08-06 - Mail Decision DB URL import-time 고정 오류 수정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Mail Decision Runtime API, UI startup environment loading, retrieval review transition |
| 관련 파일 | `app/api/mail_decision.py`, `app/server.py`, `app/services/mail_decision_runtime_service.py`, `app/services/mail_decision_routing_service.py`, 관련 테스트 |

## 요청 또는 배경

- Inbox 탭에서 `업무판단실행` 버튼 클릭 시 `POST /api/emails/{id}/mail-decision-runs`가 `503`을 반환했다.
- 터미널에는 `MailDecisionRuntimeServerError: {"detail":"CORAMAIL_DATABASE_URL is not configured"}`가 반복 출력됐다.
- 화면에는 `Mail Decision Runtime에 CORAMAIL_DATABASE_URL이 설정되지 않았습니다` 안내가 표시됐다.

## 확인한 사실

- UI 서버는 `app.api.mail_decision` router를 import한 뒤 프로젝트 `.env`를 읽고 있었다.
- `app.api.mail_decision`은 import 시점에 `_repository = PostgresMailDecisionRepository(database_url())`를 생성하므로, `.env` 로딩 전 빈 DB URL이 repository에 고정될 수 있었다.
- 이후 같은 프로세스에서 `.env`가 로딩되어도 이미 생성된 Mail Decision repository/service는 갱신되지 않았다.
- 추가로 검색 문맥이 부족한 경우 `_evaluate_context`가 `review_reason`만 기록하고 `REVIEW_REQUIRED` 상태로 멈추지 않아 다음 단계로 진행할 수 있었다.

## 해결 방법

- Mail Decision API repository/service를 요청 시점의 현재 `database_url()` 기준으로 lazy refresh하도록 변경했다.
- UI 서버가 프로젝트 `.env`를 읽은 뒤 Mail Decision router를 import하도록 순서를 조정했다.
- Runtime, routing 하위 repository가 각자 환경변수를 다시 읽지 않고 상위 Mail Decision repository의 DB URL을 공유하도록 맞췄다.
- 검색 문맥 부족 시 즉시 `REVIEW_REQUIRED`로 전환하도록 수정했다.
- import-time DB URL 고정 회귀 테스트와 외부 `.env`/LLM 상태에 흔들리지 않는 runtime 테스트 fake를 추가했다.

## 검증

- `uv run pytest`: 110 passed, 1 existing collection warning.
- `uv run ruff check app/api/mail_decision.py app/server.py app/services/mail_decision_runtime_service.py app/services/mail_decision_routing_service.py tests/test_mail_decision_api.py tests/test_mail_decision_runtime.py tests/test_hosting_defaults.py`: passed.
- `python -m py_compile` 대상 변경 파일: passed.
- `git diff --check`: passed.

## 남은 리스크와 후속 작업

- 이미 실행 중인 UI/Runtime 프로세스는 코드와 환경을 다시 읽어야 하므로 재시작이 필요하다.
- 실제 Mail Decision 실행 완료에는 PostgreSQL뿐 아니라 로컬 LLM/Ollama 모델과 Qdrant 설정도 준비되어 있어야 한다.

---

# 2026-08-06 - UI가 중지된 별도 Runtime을 강제 호출하는 연결 오류 수정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | UI/Runtime process topology, local environment configuration |
| 관련 파일 | `.env` (Git ignored), Gmail 실행 문서, 세션 로그 |

## 요청 또는 배경

- Mail Decision 실행 시 UI는 HTTP 200을 반환했지만 `127.0.0.1:8001` 연결 거부로 실행이 실패했다.

## 확인한 사실

- `app.server`에는 Mail Decision API router가 이미 mount되어 있어 UI 프로세스 자체가 `/api` 실행을 처리할 수 있다.
- 로컬 `.env`가 `CORAMAIL_MAIL_DECISION_RUNTIME_URL=http://127.0.0.1:8001`을 강제했지만 해당 standalone Runtime 프로세스는 실행 중이지 않았다.

## 해결 방법

- 로컬 `.env`에서 Runtime URL override를 제거해 UI client가 현재 요청의 host인 자기 `/api`를 사용하도록 했다.
- 별도 Runtime을 운영할 때만 해당 환경변수를 설정하도록 문서화했다.

## 검증

- UI와 Runtime의 process topology 및 router mount를 확인했다.
- DB 설정은 기존 로컬 PostgreSQL과 `.env`를 그대로 사용한다.

## 남은 리스크와 후속 작업

- 이미 실행 중인 UI 프로세스는 import 시 환경변수를 읽으므로 반드시 재시작해야 한다.

---

# 2026-08-06 - 로컬 PostgreSQL 및 Gmail Mail Decision 실행 환경 복구

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Local PostgreSQL, Gmail persistence, Mail Decision Runtime startup |
| 관련 파일 | `.env` (Git ignored), `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- Runtime이 `CORAMAIL_DATABASE_URL is not configured`를 반환해 업무 판단 실행이 계속 실패했다.

## 확인한 사실

- 실행 중인 PostgreSQL이 없었고 저장소에도 `.env`가 없었다.
- 기존 개발용 Compose의 PostgreSQL 서비스는 사용할 수 있었다.
- 문제 Gmail provider ID `19f20a3f97e4a995`는 동기화 후 canonical UUID `1c097c33-606b-56b4-b6ac-5fefda89110f`로 저장됐다.

## 해결 방법

- 기존 개발용 PostgreSQL 컨테이너를 기동하고 CoRA PostgreSQL schema 4개를 적용했다.
- 저장된 Gmail token으로 50건을 PostgreSQL에 동기화했다.
- 로컬 전용 ignored `.env`에 UI와 Runtime이 공유할 DB URL 및 Runtime URL을 설정했다.

## 검증

- Runtime health: `status=ok`, `database_configured=true`.
- 문제 provider ID의 DB canonical UUID 매핑 확인.
- DB 설정된 Runtime의 POST는 더 이상 503 설정 오류가 아니며, LLM 처리 단계까지 진행됐다.

## 남은 리스크와 후속 작업

- Runtime POST는 현재 로컬 LLM 응답을 기다리다 테스트 timeout이 발생했으므로 Ollama가 실행 중이고 필요한 모델이 설치되어 있어야 최종 결과가 반환된다.

---

# 2026-08-06 - Mail Decision Runtime DB 환경 설정 누락 수정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Standalone Runtime startup, environment loading, UI error handling |
| 관련 파일 | `app/runtime.py`, `app/server.py`, Gmail 실행 문서, Mail Decision UI 테스트 |

## 요청 또는 배경

- UUID 오류 수정 후에도 버튼 실행 시 Runtime이 `503`과 `CORAMAIL_DATABASE_URL is not configured`를 반환했다.

## 확인한 사실

- UI와 Mail Decision Runtime은 별도 프로세스다.
- UI entrypoint는 프로젝트 `.env`를 읽지만 `app.runtime:app`은 읽지 않았다.
- Runtime repository는 import 시점에 `database_url()`을 평가하므로, 실행 후 환경변수를 바꿔도 현재 프로세스에는 반영되지 않는다.

## 해결 방법

- standalone Runtime이 Mail Decision router를 import하기 전에 프로젝트 `.env` 또는 `CORAMAIL_ENV_FILE`을 읽도록 했다.
- Runtime health 응답에 `database_configured`를 추가하고 미설정 시 `degraded`를 반환하도록 했다.
- UI는 해당 503을 일반 서버 오류가 아니라 DB 환경 설정 누락으로 안내한다.

## 검증

- Mail Decision UI/API 테스트: `24 passed`.
- Ruff, compileall, diff check 통과.

## 남은 리스크와 후속 작업

- `.env`가 없고 shell에도 `CORAMAIL_DATABASE_URL`이 없으면 실제 PostgreSQL URL을 운영 환경에 주입해야 한다. 환경 설정만으로 PostgreSQL 서버가 설치·기동되지는 않는다.

---

# 2026-08-06 - Mail Decision 실행 시 Gmail provider ID UUID 오류 수정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Mail Decision API, Gmail mailbox identifier boundary, UI execution |
| 관련 파일 | `app/api/mail_decision.py`, `app/repositories/postgres_mail_decision_repository.py`, Gmail 문서, 관련 테스트 |

## 요청 또는 배경

- 사용자가 업무 판단 실행 버튼을 클릭하면 `422 Unprocessable Entity`와 함께 `Mail Decision 요청 형식이 올바르지 않습니다.`가 표시되었다.
- 로그에는 `19bef463b6aee06d`를 UUID로 파싱하지 못했다는 오류가 남았다.

## 확인한 사실

- Gmail fallback UI는 `email_uid`에 Gmail provider message ID를 사용한다.
- Mail Decision Runtime의 경로 타입은 PostgreSQL `email_messages.id` UUID만 허용했다.
- 따라서 UI와 Runtime 사이에서 provider 식별자와 canonical 식별자의 계약이 깨졌다.

## 해결 방법

- Mail Decision create/latest API 경계의 참조 타입을 문자열로 받고, canonical UUID는 그대로 사용하며 Gmail provider message ID는 `email_messages`와 `email_accounts(provider='gmail')` 조회로 canonical UUID에 매핑한다.
- 내부 workflow와 저장소에는 계속 UUID만 전달한다. 매핑되지 않는 provider ID는 404로 반환한다.
- provider ID 매핑, create 경로, latest 경로, UUID passthrough 회귀 테스트를 추가하고 Gmail 문서에 경계 동작을 기록했다.

## 검증

- 변경 관련 테스트: 통과.
- 전체 pytest: `106 passed, 1 failed`; 실패는 기존 `test_runtime_records_attachment_review_and_continues_to_fact_extraction`가 DB URL 없이 PostgreSQL facts repository를 호출하는 환경 격리 문제이며 이번 변경 파일과 무관하다.
- `UV_CACHE_DIR=/tmp/coramail-agent-uv-cache uv run ruff check app tests`, `python -m compileall -q app`, `git diff --check`: 통과.

## 남은 리스크와 후속 작업

- Gmail Mail Decision 실행은 Runtime DB에 해당 provider message가 동기화되어 있어야 한다. 동기화 전 provider ID는 404가 되며 UI에서 별도 동기화 안내를 추가할 수 있다.

---

# 2026-08-06 - 호스팅 초기 화면 500 오류 수정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Hosting defaults, demo mailbox fallback, startup configuration |
| 관련 파일 | `app/config.py`, `README.md`, `tests/test_hosting_defaults.py` |

## 요청 또는 배경

- 사용자는 웹 호스팅에서 `500 Internal Server Error`가 발생해 서비스가 열리지 않는 문제의 근본 원인 파악과 해결을 요청했다.

## 확인한 사실

- `CORAMAIL_DATABASE_URL`과 `CORAMAIL_LOCAL_DEV_DEFAULTS`가 없는 깨끗한 실행 환경에서도 `database_url()`이 로컬 PostgreSQL 주소 `127.0.0.1:5432`를 반환했다.
- 기본 Demo 모드가 `postgres_demo_source_enabled()`에서 해당 URL을 근거로 PostgreSQL 메일 저장소를 선택했다.
- 호스팅 환경에는 로컬 PostgreSQL이 없으므로 첫 `/` 요청에서 DB 연결 예외가 화면까지 전파되어 500이 될 수 있는 구조였다.
- 앱 import와 전체 테스트 자체는 통과했으며, 문제는 호스팅 의존성 기본값과 화면 요청 경로의 결합이었다.

## 해결 방법

- `CORAMAIL_LOCAL_DEV_DEFAULTS`의 기본값을 `false`로 변경해 호스팅에서는 DB URL을 자동 생성하지 않도록 했다.
- PostgreSQL 사용이 필요한 로컬 개발은 `CORAMAIL_LOCAL_DEV_DEFAULTS=true` 또는 명시적인 `CORAMAIL_DATABASE_URL`로 opt-in하도록 README에 기록했다.
- DB URL이 없는 경우 기존 `data/demo/` fixture 경로가 선택되어 UI를 제공하고, 의존성 상태는 `/api/health`의 `degraded`로 표현되도록 유지했다.
- 깨끗한 호스팅 환경의 DB 미설정 및 Demo service 선택을 회귀 테스트로 추가했다.

## 검증

- 전체 pytest: `103 passed`, 기존 collection warning 1건.
- `ruff check app tests`, `compileall`, `git diff --check` 통과.
- DB 관련 환경변수를 제거한 실제 root handler가 `TemplateResponse`를 생성하고 Demo fixture 기반 HTML을 렌더링함을 확인.

## 남은 리스크와 후속 작업

- 호스팅에서 실제 Gmail·PostgreSQL·LLM·Qdrant 기능을 사용하려면 해당 서비스의 외부 URL과 인증 설정을 배포 환경에 별도로 주입해야 한다.
- 이미 실행 중인 프로세스는 새 기본값을 읽도록 재배포 또는 재시작해야 한다.

---

# 2026-07-31 - Search 무응답 진단과 이전 예시 문구 복구

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search runtime, uvicorn restart, Search example copy |
| 관련 파일 | Search templates, UI test |

## 요청 또는 배경

- 사용자는 Search에서 답변이 나오지 않는다고 보고하고, 변경한 예시 답변·입력 안내를 이전 버전으로 복구해 달라고 요청했다.

## 확인한 사실

- 8000 포트의 uvicorn은 최신 Search 챗봇 커밋 이전인 16:02에 시작됐고 `--reload` 없이 실행되어 새 코드를 반영하지 않았다.
- 실제 `가장 최신 메일이 뭐야?` 요청은 0.05초 만에 이전 토큰 검색의 `일치하는 메일 본문이나 첨부 분석 근거를 찾지 못했습니다.`를 반환했다.
- 최신 코드 자체의 단위·실제 Ollama 검증과 실행 웹의 동작이 달랐던 직접 원인은 stale server process였다.

## 해결 방법

- 이전 uvicorn 프로세스를 종료하고 현재 main 작업 트리의 `app.server:app`을 127.0.0.1:8000에서 재시작했다.
- 입력 label과 placeholder를 `메일·첨부 RAG 질문`, `FM250016318 견적서의 납기와 총액`으로 복구했다.
- 빈 Search 안내도 참조번호, 납기, 견적 총액, 첨부 문서 유형을 예로 들던 이전 문구로 복구했다.

## 검증

- 재시작한 실제 `/ui/search-results`에 `가장 최신 메일이 뭐야?`를 요청해 HTTP 200, 약 3.20초, 최신 메일 답변과 원본 근거 1개를 확인했다.
- 실제 `/ui/search` HTML에서 이전 label과 placeholder가 렌더링되고 최신 메일 예시 placeholder는 제거된 것을 확인했다.
- Search 관련 테스트 `27 passed`, Ruff와 `git diff --check`가 통과했다.

## 남은 리스크와 후속 작업

- 배포 후 uvicorn을 재시작하지 않으면 같은 문제가 반복된다. 현재 개발 실행은 hot reload가 아니므로 코드 반영 시 명시적인 프로세스 재시작이 필요하다.

# 2026-07-31 - Search를 메일함 질의가 가능한 AI 챗봇으로 확장

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search chatbot, query planning, mailbox metadata retrieval, latest/oldest mail |
| 관련 파일 | `app/services/mail_search_service.py`, Search templates, 검색 기능 문서와 테스트 |

## 요청 또는 배경

- 사용자는 Search에 검색 문서 QA뿐 아니라 `가장 최신 메일이 뭐야` 같은 자연어 메일함 질문에도 답하는 챗봇 역할을 기대한다고 설명했다.

## 확인한 사실

- 직전 RAG 구현은 질문과 문서 내용의 의미·단어 관련성만 평가해 최신/오래된 순서, 기간, 발신자, 업무유형 같은 메일함 메타데이터 질의를 표현할 수 없었다.
- 메일과 첨부가 각각 검색 문서이므로 단순 최신순 정렬 시 같은 메일의 첨부가 중복 결과로 섞일 수 있었다.
- 첫 실제 Ollama 검증은 최신 원본 메일을 정확히 선택했지만 LLM 답변이 수신 timestamp만 반환해 챗봇 응답으로 충분하지 않았다.

## 해결 방법

- LLM query planner가 질문을 `document_qa`와 `mailbox_lookup`으로 구분하고 semantic query, 발신자·업무유형·기간 필터, 최신/오래된 정렬, 결과 개수를 구조화 출력하도록 했다.
- 최신/최근/마지막 메일과 오래된/처음 온 메일 표현은 작은 모델의 분류 오류를 막는 결정적 검증으로 정렬과 단일 결과 정책을 보정하되, `최근 메일의 납기`처럼 본문 사실을 묻는 질문은 `document_qa`로 유지했다.
- 메일함 조회는 첨부를 제외한 원본 메일만 대상으로 `received_at`을 timezone-aware datetime으로 비교하고, 의미 유사도 없이 정확한 필터와 정렬을 적용한다.
- 단일 메일함 결과는 LLM의 짧거나 불완전한 문장에 의존하지 않고 수신일시·발신자·제목을 항상 포함하는 근거 기반 챗봇 답변 계약으로 렌더링한다.
- Search 화면을 `메일함 AI 챗봇`으로 명명하고 최신 메일, 오늘 온 발주, 특정 업체 요청, 참조번호의 납기·금액 질문 예시를 안내한다.

## 검증

- 전체 테스트 `101 passed`, 기존 pytest collection warning 1건이며 Ruff, compileall, `git diff --check`가 통과했다.
- 실제 `llama3.2` query planner/answer와 Demo 메일함으로 `가장 최신 메일이 뭐야?`를 실행해 2025-02-21 18:57 진산선무 발신 견적 메일 제목을 포함한 답변을 확인했다.
- 실제 결과는 `mailbox_lookup`, `received_at_desc`, candidate/selected 1건이며 첨부 중복과 embedding 호출 없이 최신 원본 메일로 연결됐다.

## 남은 리스크와 후속 작업

- 현재 질문은 요청마다 독립적으로 처리한다. `그 메일의 첨부는?` 같은 대명사 기반 후속 질문을 지원하려면 사용자 세션별 대화 이력과 이전 evidence ID를 전달하는 별도 계약이 필요하다.
- 기간과 업무유형 조합 등 query planner의 복합 질의 정확도는 고정 평가 질문 세트로 확장해야 한다.

# 2026-07-31 - Search를 근거 제한 LLM RAG 답변으로 전환

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search UI/API, semantic retrieval, grounded LLM answer, evidence filtering |
| 관련 파일 | `app/services/mail_search_service.py`, `app/server.py`, Search template/CSS, 검색 기능 문서와 테스트 |

## 요청 또는 배경

- 사용자는 Search를 LLM 기반 RAG 챗봇으로 기획했지만 결과가 즉시 나오고 질문과 맞지 않는 근거가 표시되어, 실제 검색 흐름을 검토하고 수정해 달라고 요청했다.

## 확인한 사실

- 기존 `MailSearchService`는 LLM이나 임베딩 모델을 호출하지 않고 검색어 토큰 포함 여부만 계산해 즉시 결과와 원문 미리보기를 반환했다.
- 일부 단어만 일치해도 결과가 남아 질문 의도와 다른 메일이 섞일 수 있었고, deterministic preview를 RAG 답변처럼 표시했다.
- Search 결과 요청 후 별도 answer endpoint가 같은 deterministic 검색을 다시 실행해 실제 LLM 생성 단계가 있는 것처럼 보였다.
- 운영 Gmail과 합성 Qdrant 사례를 격리해야 하므로 기존 유사 사례 collection을 대화형 메일 검색에 직접 혼합하는 것은 거부했다.

## 해결 방법

- 현재 표시 모드의 신뢰 가능한 메일·첨부 문서만 대상으로 로컬 임베딩 의미 점수와 단어 일치 점수를 결합하는 hybrid candidate retrieval을 구현했다.
- 질문의 업무 식별자는 hard filter로 적용해 다른 참조번호 문서가 의미 유사도만으로 반환되지 않게 했다.
- 최대 12개 후보를 로컬 텍스트 LLM에 전달하고 구조화 출력으로 답변 충분성, 근거 ID, 관련성 점수와 이유를 받도록 했다.
- 관련성 0.55 미만, 존재하지 않는 ID, 중복 ID, LLM이 선택하지 않은 후보는 결과에서 제외하고, 근거가 부족하면 답변과 근거를 명시적인 불충분 상태로 전환했다.
- embedding/answer model과 prompt name/version, 후보·선택 개수를 API trace에 포함하고 문서 임베딩을 모델·content hash 기준 최대 10,000개 메모리 캐시로 재사용한다.
- 중복 answer endpoint와 지연을 위장하던 loading partial을 제거하고 실제 단일 RAG 요청 동안 HTMX 검색 상태를 표시하도록 정리했다.

## 발생한 오류와 검증

- 기본 `python` 환경에는 pytest가 없어 프로젝트 실행기인 `uv run pytest`로 전환했다.
- sandbox 안의 uv cache와 로컬 socket 접근이 차단되어 `/tmp` cache를 사용하고 승인된 로컬 Ollama 연결로 실제 모델 검증을 수행했다.
- 전체 테스트 `98 passed`, 기존 pytest collection warning 1건이며 compileall과 `git diff --check`도 통과했다.
- 실제 `nomic-embed-text`와 `llama3.2`로 `FM250016038 견적 메일의 업체와 선박`을 질문해 `딘텍, MORNING CHANT` 답변과 동일 참조번호의 메일·견적 PDF 두 근거만 반환함을 확인했다.

## 남은 리스크와 후속 작업

- 최초 실제 모델 검증은 모델 cold start를 포함해 약 4분이 걸렸다. 같은 프로세스의 문서 임베딩은 캐시되지만 운영에서는 메일·첨부를 수집 시점에 Qdrant에 영속 색인해 첫 검색 비용을 제거해야 한다.
- 현재 Search는 단일 질문·답변 RAG 계약이다. 대화 이력 기반 후속 질문이 필요하면 세션별 history, 참조 근거 유지, 접근 권한 계약을 별도 추가해야 한다.
- 실제 Gmail 검색 품질은 운영 메일의 파싱·첨부 분석 완성도와 로컬 모델 성능으로 별도 평가해야 하며 이번 Demo 검증을 운영 성능 주장으로 사용하지 않는다.

# 2026-07-31 - 합성 담당자를 기존 담당자 관리 테이블로 통합

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Settings assignee table, synthetic roster, read-only protection, responsive table |
| 관련 파일 | `app/repositories/postgres_assignee_admin_repository.py`, `app/server.py`, `app/templates/views/settings.html`, `app/templates/partials/routing_table.html`, `app/static/app.css`, 담당자 라우팅 문서와 UI 테스트 |

## 요청 또는 배경

- 사용자는 별도 `평가용 합성 담당자` 영역을 없애고 합성 담당자를 기존 담당자 관리 테이블에 표시해 달라고 요청했다.
- 큰 UI 틀을 유지하는 범위에서 세부 UI 수정은 허용했다.

## 확인한 사실

- 기존 화면은 합성 담당자 8명을 별도 카드 패널로 표시하고 운영 담당자 테이블에는 포함하지 않았다.
- 기존 수정·삭제 API는 UUID를 직접 요청하면 합성 사용자도 변경할 수 있어 UI만 읽기 전용으로 만드는 것으로는 충분하지 않았다.
- 첫 Playwright 상호작용은 Settings 메뉴가 일반 링크가 아닌 HTMX 버튼이라 검사 선택자가 시간 초과됐고, 실제 마크업에 맞춰 수정했다.
- 초기 데스크톱 테이블은 긴 합성 이메일 때문에 관리 열이 화면 밖으로 밀려났다.

## 해결 방법

- 별도 합성 담당자 패널과 전용 CSS를 제거하고 운영·합성 담당자를 하나의 담당자 관리 테이블 데이터로 합쳤다.
- 합성 행에 `합성` 배지, capability 개수, 평가 데이터 역할, 업무 유형에서 파생한 담당 카테고리, `읽기 전용` 잠금 상태를 표시했다.
- 합성 행에서는 편집·삭제 UI를 렌더링하지 않고 repository의 update, toggle, deactivate, delete 쿼리에서도 `@coramail.invalid` 사용자를 제외했다.
- 담당자 우선순위 배정은 운영 담당자만 사용하므로 합성 담당자는 Gmail 후보와 운영 규칙에 계속 섞이지 않는다.
- 고정 열 레이아웃과 이메일 줄바꿈을 적용해 데스크톱에서는 전체 열이 보이고 모바일에서는 테이블 내부만 가로 스크롤되게 했다.

## 검증

- 전체 테스트 `98 passed`, 기존 pytest collection warning 1건이며 `ruff check app tests`도 통과했다.
- 실제 8000 웹의 Demo와 Gmail 모드에서 합성 담당자 8행, 별도 패널 0개, 합성 배지와 읽기 전용 상태를 확인했다.
- 합성 행의 편집 버튼과 삭제 버튼이 각각 0개이며 문서 전체 가로 overflow가 없음을 확인했다.
- Dashboard의 Settings HTMX 버튼 클릭 후 통합 테이블이 렌더링되는 상호작용을 검증했다.
- 데스크톱은 테이블 가로 스크롤 없이 전체 열이 보이고, 모바일은 테이블 내부 가로 스크롤이 동작했다.
- Browser 플러그인은 설치되어 있지 않아 로컬 Playwright를 사용했다. 데스크톱 첫 접근의 기존 `/favicon.ico` 404 메시지는 기능과 무관하다.

## 남은 리스크와 후속 작업

- 합성 담당자의 customer, product, project 상세 capability는 라우팅 평가 내부 근거로 유지하며 Settings 표에서는 업무 카테고리와 총개수만 요약한다.
- 동시에 진행 중인 Search 관련 미커밋 변경은 이번 작업 범위에서 수정하거나 stage하지 않는다.

# 2026-07-31 - Settings에서 평가용 합성 담당자와 capability 확인 지원

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Settings, synthetic assignee visibility, capability inspection, Gmail isolation |
| 관련 파일 | `app/repositories/postgres_assignee_admin_repository.py`, `app/server.py`, `app/templates/views/settings.html`, `app/static/app.css`, 담당자 라우팅 문서와 UI 테스트 |

## 요청 또는 배경

- 사용자는 생성된 가짜 담당자가 Settings 탭에 보이지 않아 데이터가 실제로 추가됐는지 확인하기 어렵다고 지적했다.

## 확인한 사실

- PostgreSQL에는 active 합성 담당자 8명과 customer 12, product 8, business type 12, project 12 capability가 정상 저장되어 있었다.
- Settings의 기존 담당자 관리 저장소가 운영 데이터 보호를 위해 `@coramail.invalid` 사용자를 항상 제외해, Demo 모드에서도 합성 담당자를 볼 수 없었다.
- 첫 모바일 브라우저 검수에서 CSS 선언 순서 때문에 합성 담당자 카드가 2열로 남아 텍스트 가독성이 떨어지는 문제를 발견했다.

## 해결 방법

- 운영 담당자 편집 조회는 그대로 유지하고 active 합성 담당자와 유효 capability만 조회하는 읽기 전용 경로를 별도로 추가했다.
- Settings 상단에 표시 모드와 관계없이 `평가용 합성 담당자` 8명을 표시하고, 각 카드를 펼쳐 고객·제품·업무 유형·프로젝트 capability를 확인할 수 있게 했다.
- 합성 데이터와 Demo/Evaluation 전용임을 명시하고 Gmail 운영 배정 후보에는 포함되지 않는다는 안내를 표시했다.
- Gmail 표시 모드에서도 합성 담당자의 존재는 읽기 전용으로 확인할 수 있지만 운영 담당자 편집 표에는 섞지 않았고, 기존 라우팅 후보 조회의 synthetic 제외 정책도 변경하지 않았다.
- 모바일에서는 담당자 카드를 1열로 표시하도록 반응형 cascade를 수정했다.

## 검증

- 전체 테스트 `97 passed`, 기존 pytest collection warning 1건이며 `ruff check app tests`도 통과했다.
- 실제 PostgreSQL 조회에서 active 8명과 capability 분포 customer 12, product 8, business type 12, project 12를 확인했다.
- Playwright 데스크톱·모바일 검사에서 카드 8개, 첫 카드 capability 펼침, 격리 안내, 가로 overflow 없음이 모두 통과했다.
- Gmail 표시 모드 브라우저 검사에서도 합성 담당자 8명이 읽기 전용으로 표시되고 운영 후보 제외 안내가 유지됨을 확인했다.
- GitHub `origin/main`에 기능 커밋 `eeeb4d9`를 push한 뒤, 기존 8000 포트의 이전 프로세스를 최신 main으로 재시작하고 같은 브라우저 검사를 실제 실행 웹에서 다시 통과했다.
- Browser 플러그인은 설치되어 있지 않아 로컬 Playwright를 사용했다. 데스크톱 첫 접근에서 기존 `/favicon.ico` 404 콘솔 메시지 1건이 있었으며 Settings 기능과 무관하다.

## 남은 리스크와 후속 작업

- 이 화면은 합성 평가 조직의 존재와 라우팅 근거를 확인하기 위한 읽기 전용 화면이다. 실제 Gmail 자동 배정에는 별도의 실제 담당자와 capability 등록이 필요하다.

# 2026-07-31 - 합성 담당자 조직으로 Clean v2 자동 배정 오류 제거

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Synthetic organization, assignee capabilities, routing policy, seed replacement, Evaluation |
| 관련 파일 | `app/evaluation/`, `app/routing/policy.py`, `app/services/mail_decision_routing_service.py`, Clean v2 dataset/report, 담당자 라우팅·demo data 문서와 테스트 |

## 요청 또는 배경

- 사용자는 가짜 담당자 데이터를 만들어 담당자 배정 관련 오류가 발생하지 않게 해 달라고 요청했다.
- 직전 Clean v2 결과는 정답 담당자를 후보 5명 안에는 포함했지만 모든 케이스가 `selected_assignee_missing`과 `routing_policy_review_required`로 끝났다.

## 확인한 사실

- Clean v2 사용자와 이전 leaky baseline 사용자가 PostgreSQL에서 모두 active라 동일 customer/history 점수의 중복 후보가 생겼다.
- generator는 `product_group` capability를 저장했지만 Routing Policy는 `product` capability를 조회해 제품 점수가 항상 0이었다.
- 메일 정답 담당자는 고객·제품·업무 유형·프로젝트 소유권과 무관한 단순 순번이어서 최고 점수 0.4495, 후보 margin 0으로 자동 배정 기준을 통과할 수 없었다.
- 자동 배정 성공 후에도 비차단 `attachment_analysis_incomplete`가 terminal review reason으로 남아 trace 무결성 경고를 만들었다.

## 해결 방법

- 고객별 합성 owner를 고정하고 owner가 담당하는 합성 메일에서 customer, product, business type, project capability를 결정적으로 파생했다.
- capability type을 Routing Policy 계약인 `product`로 통일했다.
- seed 시 현재 합성 사용자 8명의 capability를 canonical dataset으로 교체하고, 이전 합성 사용자 8명은 삭제하지 않고 inactive로 전환했다.
- Decision classification이 review required이면 점수가 높아도 자동 배정하지 않는 안전 조건을 추가했다.
- 자동 배정이 성공한 경우 비차단 첨부 경고는 `non_blocking_warnings`로 보존하고 terminal `review_reason`에서는 제거했다.
- Evaluation 화면의 주요 실패 원인에서는 `success` 집계를 제외했다.
- 기존 첨부 fixture 120개는 내용 변경 없이 보존하고 조직·정답·capability와 평가 산출물만 갱신했다.

## 검증

- DB에는 active 합성 담당자 8명, inactive 과거 합성 담당자 8명이 있으며 활성 capability는 customer 12, product 8, business type 12, project 12다.
- 생성기 기준 ground truth 100건 모두 정답 owner가 자동 선택되고 score 0.82 이상인 결정적 테스트를 통과했다.
- 실제 DB·Ollama·Qdrant Clean v2 5건은 모두 `completed`, `auto_assigned=true`, expected rank 1, selected assignee correct다.
- 업무 유형, 담당자 Top-1, 후보 recall, 자동 배정 정확도는 모두 5/5다. review required 0/5, primary failure `success=5`, trace integrity error 0이다.
- 누수 검사는 overlap, near duplicate, answer exposure 모두 0으로 통과했다.
- 전체 테스트는 96 passed, 기존 collection warning 1건이며 Ruff도 통과했다.

## 남은 리스크와 후속 작업

- 5건 결과와 100건 deterministic policy 검증은 합성 데이터 결과이며 실제 Gmail 조직 배정 정확도를 의미하지 않는다.
- 실제 Gmail에서는 `@coramail.invalid` 사용자를 계속 제외한다. 실제 자동 배정을 사용하려면 Settings에 실제 담당자와 capability를 등록해야 한다.
- workload, 휴가, 복수 owner, 신규 고객, 후보 동점 같은 운영 예외는 별도 평가 시나리오로 확장해야 한다.

# 2026-07-31 - Search 탭을 실제 메일·첨부 근거 검색으로 연결

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Search UI/API, 메일·첨부 근거 검색, PostgreSQL, 검색 정확도 |
| 관련 파일 | `app/services/mail_search_service.py`, `app/repositories/postgres_mail_repository.py`, `app/services/*mail_service.py`, `app/server.py`, `app/templates/views/search.html`, `app/templates/partials/search_results.html`, `docs/features/context-search-qdrant-indexing.md`, `tests/test_mail_search_service.py` |

## 요청 또는 배경

- 사용자는 Search 탭이 의도대로 동작하지 않는 근본 원인을 파악하고 개선해 달라고 요청했다.

## 확인한 사실

- Search 화면은 포팅 당시 `demo_search_result()`에 남아 있었고, 검색어가 불일치해도 최신 메일을 대신 반환했다.
- 화면에 보이는 기본 질문은 실제 검색 상태와 연결되지 않았고 `POST /api/search`는 항상 빈 stub 결과를 반환했다.
- 화면 검색, API 검색, Mail Decision 검색이 서로 다른 계약을 사용했다.
- 메일 목록 검색은 첨부 분석 결과와 `MailFacts`를 검색하지 않아 첨부의 납기·금액 같은 업무 근거를 찾을 수 없었다.

## 해결 방법

- 현재 표시 모드의 메일 본문, 발신자, 분류 JSON, `MailFacts`, 첨부 분석 결과를 동일한 근거 문서로 정규화하는 `MailSearchService`를 추가했다.
- Search UI와 `POST /api/search`가 같은 정규화·랭킹·빈 결과 정책을 사용하도록 연결했다.
- 업무 식별자가 포함된 질문은 그 식별자 일치를 필수로 해 일반 단어만 맞는 다른 업무가 노출되지 않게 했다.
- 동점 근거는 최신 회신을 우선하고, 긴 본문은 일치 지점 주변으로 제한했다.
- 결과에 일치 단어, 근거 미리보기, 원본 메일 링크를 표시하고 가짜 기본 질문과 불일치 fallback을 제거했다.

## 검증

- 격리 모드 전체 테스트 `93 passed`, 기존 pytest collection warning 1건이다.
- 변경 파일 Ruff 검사는 통과했다. 저장소 전체 Ruff는 기존 notebook의 shell cell과 미사용 import 3건 때문에 실패했다.
- fixture 화면에서 `BK2502044Q 납기`가 최신 회신의 `2월 28일`을 최상위 근거로 표시하고, 존재하지 않는 식별자는 빈 결과임을 확인했다.
- 실제 PostgreSQL 스키마에서 메일·첨부 검색 문서 738건을 정상 조회했다.
- Browser 플러그인은 없고 WSL 환경의 `npx playwright`도 실행할 수 없어, 렌더링된 HTMX HTML과 API 응답으로 상호작용 결과를 검증했다.

## 남은 리스크와 후속 작업

- 현재 단계는 신뢰 가능한 PostgreSQL 원본과 첨부 분석의 근거 검색이다. Qdrant hybrid/LLM 답변은 합성 평가 collection과 운영 Gmail의 격리, 원본 링크 계약, 검색 trace 저장을 완료한 뒤 연결해야 한다.

# 2026-07-31 - 첨부 Details를 문서 유형별 정보 추출 표로 복원

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Attachment analysis presentation, PostgreSQL mailbox detail, coramail_ai 호환 계약 |
| 관련 파일 | `app/presentation/attachment_analysis.py`, `app/services/postgres_mail_service.py`, `app/templates/partials/email_detail.html`, `docs/features/attachment-analysis.md`, `tests/test_attachment_analysis_presentation.py` |

## 요청 또는 배경

- 사용자는 메일 상세의 첨부파일별 토글 `Details`에 분석 상태가 아니라 원래
  `coramail_ai` UI처럼 파일 유형에 맞는 정보 추출 결과 표가 나오도록 요청했다.

## 확인한 사실

- 현재 UI 서비스는 Mail Decision의 `document_type`/`fields`만 읽었지만 기존
  `coramail_ai` 분석 결과는 `document_category`/`extracted_fields`를 사용했다.
- 일부 기존 구조화 결과는 실제 필드를 `field_name_from_schema` 배열 안에 저장하므로
  직접 필드만 읽으면 값이 있어도 표가 비었다.
- 서비스는 `document_type`만 반환했지만 템플릿은 `document_category`와
  `document_category_label`을 사용해 문서 유형 배지도 표시되지 않았다.
- 빈 결과의 fallback이 분석 상태와 오류를 사용자용 Details 값처럼 표시했다.

## 해결 방법

- 두 분석 JSON 계약과 `field_name_from_schema`를 하나의 사용자용 필드 맵으로
  정규화했다.
- 견적서, 견적의뢰서, 입금요청서, 거래명세서의 원래 필드 순서를 복원하고 품목을
  사용자용 행으로 표시한다.
- Mail Decision 문서 유형을 한국어 라벨로 변환하고 템플릿이 사용하는 category
  키도 함께 반환한다.
- 분석 상태 fallback을 제거하고 실제 추출값, 업무 요약, 추출 텍스트만 표에
  표시한다. 추출 결과 자체가 없으면 상태값 대신 중립적인 빈 결과 안내를 표시한다.

## 검증

- 첨부 presentation, 메일 상세 UI, parser 대상 테스트는 `26 passed`다.
- 전체 테스트는 `89 passed`, `1 failed`였다. 실패한
  `test_runtime_records_attachment_review_and_continues_to_fact_extraction`은 가짜 메일
  UUID를 로컬 PostgreSQL `mail_facts`에 저장하려다 외래키를 위반한 테스트 격리
  문제로, 이번 표시 변경 대상과 무관하다.

## 남은 리스크와 후속 작업

- 실제 운영 첨부가 LLM 또는 Vision 단계에서 추출값을 전혀 만들지 못한 경우에는
  표에 표시할 업무 정보가 없으므로 빈 결과 안내가 나온다. 이는 분석 상태를
  추출 결과처럼 보여주지 않기 위한 의도된 동작이다.

# 2026-07-31 - Clean v2 fact extraction·business type 오류 제거

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | End-to-end evaluation adapter, Fact Extraction, Decision classification contract, Clean v2 report |
| 관련 파일 | `app/evaluation/runner.py`, `tests/test_e2e_evaluation_runner.py`, `data/evaluation/clean-v2/`, `docs/features/llmops-observability-evaluation.md` |

## 요청 또는 배경

- 사용자는 Evaluation에 표시된 `fact_extraction_empty`, `business_type_missing` 오류를 모두 해결하라고 요청했다.
- 화면상의 오류 이름만 바꾸지 않고 최신 Mail Decision 런타임에서 같은 Clean v2 케이스를 다시 실행해 원인을 분리했다.

## 확인한 사실

- 기존 Evaluation 결과는 2026-07-30에 생성된 것으로, 이후 추가된 labeled-body fact 병합과 Ollama structured output 개선을 반영하지 않은 오래된 prediction이었다.
- 최신 코드로 기존 케이스를 재실행하면 customer, project, product group, request type과 evidence가 모두 생성되어 `fact_extraction_empty`는 재현되지 않았다.
- Decision Agent 결과에도 `classification.primary_type`이 정상 생성됐지만 Evaluation Runner는 폐기된 `decision_output.primary_type` 평면 필드를 읽어 업무 유형을 `None`으로 기록했다.
- 따라서 `business_type_missing`은 모델 실패가 아니라 Mail Decision 출력 계약과 평가 adapter 사이의 불일치였다.

## 해결 방법

- Evaluation Runner가 `decision_output.classification.primary_type`을 읽도록 수정했다.
- 새 계약을 사용하는 회귀 테스트와, 오래된 평면 필드가 함께 있어도 nested classification을 우선하는 테스트를 추가했다.
- 기존 Evaluation 화면과 동일한 repair request, order change, technical inquiry, certificate request, claim 5건을 최신 DB·Ollama·Qdrant 경로로 다시 실행했다.
- 새 predictions를 score해 Clean v2 report, cases CSV, developer trace JSONL을 함께 갱신했다.

## 검증

- 최신 Clean v2에서 `fact_extraction_empty=0`, `business_type_missing=0`이다.
- 실행 성공은 5/5, 업무 유형 prediction coverage와 정확도는 5/5, 담당자 후보 recall은 5/5다.
- 5개 업무 유형의 confusion matrix가 모두 정답 대각선 1건으로 기록됐다.
- 실제 `http://127.0.0.1:8000/ui/evaluation` HTML에서 두 오류가 사라지고 새 결과가 표시되는 것을 확인했다.
- 관련 Fact Extraction, Evaluation Runner, score 테스트 15개를 통과했고 전체 회귀는 90 passed, 기존 collection warning 1건이다. Ruff도 통과했다.

## 남은 리스크와 후속 작업

- 모든 케이스에서 정답 담당자가 후보 안에는 있지만 routing policy가 자동 선택하지 않아 `selected_assignee_missing=5`가 새 primary failure다.
- 자동 배정 정확도는 자동 배정 건수가 0이어서 아직 `측정 안 됨`이다. 이는 이번 두 오류와 별개의 라우팅 점수·임계값 작업이다.
- 현재 결과는 5건 합성 smoke 평가이며 실제 Gmail 운영 성능을 의미하지 않는다.

# 2026-07-31 - Evaluation 탭을 스크린샷 중심 품질 리포트로 재구성

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Evaluation dashboard, 품질 합격 판정, 실패 원인, 반응형 케이스 결과 |
| 관련 파일 | `app/server.py`, `app/templates/views/evaluation.html`, `app/static/app.css`, `docs/features/llmops-observability-evaluation.md`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 Evaluation 탭이 난잡하고 불필요한 요소가 많아, 스크린샷만으로도 결과를 바로 보고할 수 있는 화면으로 재구성하라고 요청했다.
- 기존 화면은 13개 지표, 누수 검사 내부 값, 5개 필터, 13열 케이스 표, 모델·collection 정보를 같은 위계로 노출해 현재 품질과 우선 수정 대상을 한눈에 판단하기 어려웠다.

## 확인한 사실

- 기존 `report.passed=true`는 평가 파일과 trace 무결성 통과를 뜻했지만 실제 Clean v2 결과는 업무 유형 정확도, 담당자 Top-1, 후보 recall이 모두 0%이고 자동 배정 정확도는 분모가 0이었다.
- 실행 성공 5/5와 품질 성공을 구분하지 않으면 평가 결과를 실제 성능 통과로 오해할 수 있었다.
- 모바일에서는 13열 표가 좁은 셀로 압축되어 케이스 원인을 읽기 어려웠다.
- Browser 플러그인과 저장소 Playwright 설정은 없었으나 로컬 Playwright Chromium을 사용할 수 있었다.

## 해결 방법

- 첫 화면을 `품질 기준 통과/미달`, 핵심 기준 통과 수, 평가셋·생성 시각, 합성 데이터 표시가 있는 한 장 리포트로 바꿨다.
- 문서의 초기 기준에 맞춰 업무 유형 정확도, 담당자 Top-1, 후보 recall, 자동 배정 정확도만 핵심 카드로 노출했다.
- 분모가 0인 지표는 0%가 아니라 `측정 안 됨`으로 표시하고 전체 품질 합격에서 제외했다.
- 실행 성공, 사람 검토 비율, 데이터 누수 검사와 상위 실패 원인을 별도 요약해 실행 여부와 품질을 분리했다.
- 케이스 표는 기대값→실제값, 성공 여부, 실패 원인 6열로 줄였고 모바일에서는 케이스 카드로 전환했다.
- 모델, Qdrant collection, 데이터셋 내부 정보는 접힌 기술 정보 영역으로 옮겼다.

## 검증

- `uv run ruff check app tests`, `uv run pytest -q`, `git diff --check`를 통과했다. 테스트는 78 passed, 기존 collection warning 1건이다.
- Playwright로 `http://127.0.0.1:8015/ui/evaluation`을 1440×1000과 390×844에서 렌더링해 빈 화면·framework overlay가 없고 제목이 `품질 기준 미달`인지 확인했다.
- 실패 원인 필터를 `business_type_missing`으로 선택했을 때 표시 케이스가 5건에서 1건으로 바뀌었다.
- 데스크톱과 모바일 전체 화면 스크린샷을 `/tmp/coramail-evaluation-desktop.png`, `/tmp/coramail-evaluation-mobile.png`에 생성했다.
- 콘솔의 유일한 404는 애플리케이션 기능과 무관한 `/favicon.ico` 요청이며 템플릿과 CSS는 200으로 로드됐다.

## 남은 리스크와 후속 작업

- 현재 리포트는 명시적으로 합성 데이터이며 운영 Gmail 품질 주장에 사용할 수 없다.
- 현재 Clean v2 자체가 업무 유형·라우팅 품질 0%이므로 화면 개선과 별개로 최신 Mail Decision 구현으로 평가셋을 다시 실행해야 한다.
- 문서에 정의된 첨부 유형 정확도, 필드 F1, macro F1, 자동 배정 precision 등은 현재 리포트 payload에 없어 화면에서 판정하지 않는다.

# 2026-07-31 - coramail_ai 실사용 기준으로 Gmail AI 분석 경로 재구축

| 항목 | 내용 |
|---|---|
| 상태 | 핵심 회귀 해결, 전체 parity 진행 중 |
| 관련 영역 | Gmail MIME, Mail Decision, AI Summary/Classification, Attachment Understanding, Routing UI/Admin, Gmail Trash, Search labeling |
| 관련 파일 | `app/agents/`, `app/document_processing/`, `app/integrations/gmail/`, `app/repositories/`, `app/services/`, `app/templates/partials/`, 관련 기능·개발 문서와 테스트 |

## 요청 또는 배경

- 사용자는 `coramail_agent`가 `coramail_ai`를 개선한 서비스가 아니라 기존 기능도 잃은 상태라고 지적했다.
- 본문 인라인 이미지가 첨부로 표시되고, 첨부 분석 필드와 Mail Decision Inspector가 사용자에게 쓸모없으며, AI Summary가 fallback으로 보이고 모든 Gmail 레이블이 미분류인 문제를 제시했다.
- `coramail_ai`의 실사용 기능을 기준으로 하되 현재 docs의 Mail Decision Run 구조에 맞춰 다시 구현하고 모든 변경을 GitHub에 기록하라고 요청했다.

## 확인한 사실

- Gmail 초기 분류와 Summary 버튼은 Mail Decision과 분리된 `coramail-rule-v1` 키워드 작업기를 호출했다.
- Decision Agent는 LLM/schema 오류를 제목 기반 fallback으로 숨기고 정상 결과처럼 저장했다.
- Ollama gateway가 모델에 실제 JSON schema를 전달하지 않아 모델이 결과 대신 schema 자체를 반환했다.
- 긴 인용 스레드와 관련성이 낮은 합성 검색 사례가 최신 발신자의 납기 요청보다 먼저 모델 문맥을 차지했다.
- Gmail Content-ID 이미지가 일반 첨부 개수, 상세 목록, 재분석, Mail Decision 입력에 포함됐다.
- 첨부 상세는 checksum, analyzer, page/table count 같은 내부 메타데이터를 사용자 결과로 노출했다.
- 담당자 설정과 Gmail 휴지통은 stub이었고 운영 Gmail 후보에 합성 평가 사용자가 포함됐다.
- 운영 담당자는 현재 PostgreSQL에 등록되어 있지 않고 합성 담당자만 존재했다. 따라서 실제 메일을 자동 배정하면 조직 사실을 발명하게 된다.
- UUID 기반 Summary/Classification API도 표시 모드 쿠키가 없으면 demo 저장소만 조회해 Gmail UUID를 404로 처리했다.

## 해결 방법

- `coramail_ai`의 Content-ID/disposition 판별을 이식해 인라인 이미지를 저장 이력에는 보존하되 첨부 개수, 화면, 분석 입력에서는 제외했다.
- rule worker를 제거하고 Gmail 초기 작업과 요약·분류 재생성을 하나의 Mail Decision LLM 경로로 연결했다.
- Ollama native structured output에 Pydantic JSON schema와 업무 유형 enum을 직접 전달하고, schema 실패는 성공 fallback이 아니라 failed/review 상태로 기록했다.
- 최신 본문을 인용 스레드와 분리하고, 명시된 거래처·업무번호·납기·긴급도·요청 행동을 evidence-backed MailFacts로 정규화했다.
- LLM summary의 업무번호와 기한을 검증된 MailFacts로 제한하고 prompt/model/generation mode를 결과에 기록했다.
- retrieval 부족과 첨부 partial 상태에서도 가능한 분석을 계속해 요약·분류와 후보를 만들고 최종 자동 배정만 review policy로 제한했다.
- PDF/문서/표 파싱 뒤 text document-understanding 단계를 추가해 문서 유형, 업무 요약, 참조번호, 금액, 납기, 품목을 추출했다.
- 첨부 화면에서 내부 분석 메타데이터를 제거하고 문서별 업무 필드, 품목, 요약 또는 사용자용 실패 상태만 표시했다.
- Mail Decision Inspector를 업무 판단 및 담당자 추천 카드로 교체하고 정상 화면에서 run UUID와 step을 숨겼다.
- PostgreSQL 운영 담당자 CRUD와 카테고리별 business-type capability 저장을 연결하고 Gmail 라우팅에서 `@coramail.invalid` 합성 사용자를 제외했다.
- Gmail trash는 provider API가 성공한 뒤 로컬 row를 soft-delete하도록 연결했다.
- Gmail sync는 모든 분석 job을 등록한 뒤 background worker가 drain하게 하고, 중단된 running job을 재대기시키는 복구를 추가했다.
- UUID 기반 API는 표시 모드와 무관하게 Gmail/운영 PostgreSQL 저장소를 먼저 조회하도록 수정했다.
- 전체 이관 상태와 미완료 항목을 `docs/development/coramail-ai-feature-parity.md`에 기록했다.

## 검증

- 실제 Gmail 재동기화 후 문제 메일의 표시 첨부가 4개에서 0개로 정정되고 `has_attachment=false`가 된 것을 확인했다.
- 실제 Gmail Mail Decision은 HTTP 200, 약 12~16초에 완료됐다.
- 실제 결과는 조치 중심 한국어 요약, 납기 확인 업무 유형, confidence 0.99, 올바른 업무번호와 기한을 저장했다.
- 운영 담당자가 없으므로 합성 후보를 제시하지 않고 `no_active_candidates`와 담당자 검토 필요 상태를 반환했다.
- 쿠키 없는 실제 Gmail Summary 재생성 API가 HTTP 200, `success`, `source=mail_decision`으로 완료됐다.
- 실제 Gmail 상세 API와 HTML에서 발주 레이블, AI 요약, 업무번호, 첨부 0개, 새 업무 판단 카드가 표시되고 Inspector/Checksum/Analyzer가 노출되지 않는 것을 확인했다.
- `uv run ruff check app tests`와 `uv run pytest -q`를 통과했다. 테스트는 78 passed, 기존 collection warning 1건이다.

## 남은 리스크와 후속 작업

- 실제 운영 담당자가 한 명도 등록되지 않았으므로 자동 배정은 의도적으로 실행하지 않는다. 설정 화면에서 실제 이름, 이메일, 담당 카테고리를 등록해야 한다.
- 수동 담당 확정·Gmail 전달·routing event, 검색 화면의 Qdrant hybrid/LLM answer, Gmail history incremental sync, correction/audit는 parity 문서의 pending 항목이다.
- 현재 변경을 `coramail_ai` 전체 기능 이관 완료로 주장하지 않는다. 다음 우선순위는 수동 담당 확정과 전달 이력이다.

# 2026-07-31 - Gmail 모드를 PostgreSQL Mail Decision 실행 경로에 연결

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gmail sync persistence, Attachment download, Classification/Summary jobs, Mail Decision UUID contract, Runtime deployment |
| 관련 파일 | `app/integrations/gmail/`, `app/repositories/postgres_gmail_sync_repository.py`, `app/services/gmail_mail_service.py`, `app/repositories/postgres_mail_repository.py`, `app/server.py`, `db/postgresql/004_gmail_provider_identifier.sql`, 관련 기능·스키마 문서와 테스트 |

## 요청 또는 배경

- 사용자는 demo가 아니라 Gmail 모드에서 첨부파일 재분석, Summary, Mail Decision, 레이블이 실제로 동작하도록 요청했다.
- 이전 자체 테스트가 통과했지만 실제 Gmail 웹에서는 모든 기능이 실패하거나 `미분류`로 남았다고 지적했다.
- 이전 기능 브랜치 변경이 `main`에 병합됐는지와 실제 웹 서버가 최신 코드를 사용하는지도 확인해 달라고 요청했다.

## 확인한 사실

- 기존 Gmail 모드는 받은 메일을 프로세스 메모리에만 보관하고 모든 분류를 `미분류`로 고정했다.
- Gmail provider message ID 문자열을 UUID 전용 Mail Decision API에 전달해 HTTP 422와 `Mail Decision 요청 형식이 올바르지 않습니다.`가 발생했다.
- Summary와 첨부 재분석은 PostgreSQL email UUID를 전제로 하므로 메모리 Gmail 메일에서 실행할 수 없었다.
- 직전 분류·Summary·첨부 재분석 검증은 Gmail 모드가 아니라 PostgreSQL 합성 메일 경로에서 수행됐다. 실제 운영 경로를 대표하지 못한 테스트였다.
- 원격 `main`은 기능 브랜치의 최신 13개 커밋을 포함하지 않았고, 실행 중인 8010 서버는 Mail Decision API mount 이전 코드, 8000 서버는 기능 브랜치 코드지만 이번 Gmail persistence 수정 이전 코드를 메모리에 로드하고 있었다.
- 실제 Gmail 첨부 provider ID 최대 길이는 426자였고 기존 `VARCHAR(255)` 스키마 때문에 첫 실제 동기화가 중단됐다.
- Gmail이 같은 인라인 파일에 새 opaque attachment ID를 반환한 재동기화에서 이전 attachment row가 화면에 함께 남아 4개가 8개로 보이는 문제도 재현됐다.

## 해결 방법

- Gmail 계정, 메일, 수신자, 첨부 메타데이터를 canonical PostgreSQL 테이블에 idempotent upsert하는 repository를 추가했다.
- 내부 메일·첨부·수신자 ID는 결정적 UUID로 만들고 Gmail ID는 provider 식별자로만 보존했다.
- Gmail 첨부 원본을 ignored runtime 경로 `data/runtime/gmail_attachments/`에 안전한 파일명으로 저장하고 checksum과 다운로드 상태를 기록했다.
- Gmail 화면은 `provider = gmail`로 제한한 PostgreSQL mailbox view를 사용하고, demo PostgreSQL 화면은 `provider = synthetic`으로 분리했다.
- 새로 수집되거나 내용이 바뀐 Gmail 메일은 classification과 executive-summary 작업을 등록하고 즉시 실행한다.
- 첨부 다운로드 파일을 기존 parser 재분석과 Mail Decision Runtime이 그대로 사용하도록 연결했다.
- `email_attachments.provider_attachment_id`를 `TEXT`로 바꾸는 신규 migration을 추가하고 실제 로컬 DB에도 적용했다.
- Gmail 본문 기본 수집 한도를 8,000자에서 100,000자로 늘렸다.
- 재동기화 시 현재 Gmail payload에 없는 과거 attachment row는 삭제하지 않고 `superseded`와 `deleted_at`으로 비활성화해 분석 이력을 보존하면서 화면 중복을 제거했다.

## 검증

- 실제 연결 Gmail 계정에서 50건을 동기화했다.
- PostgreSQL에서 Gmail 메일 50건, 첨부 메일 40건, 첨부 61건을 확인했고 첨부 원본 61건이 모두 `downloaded`, 실패 0건이었다.
- 현재 classification 50건과 executive summary 50건이 모두 `success`였다. 분류 분포는 문의 32, 발주 17, 기술 1이었다.
- 실제 Gmail UUID 한 건으로 Summary 재생성 `success`, 첨부 4건 재분석 요청 `ok`, Mail Decision API HTTP 200과 `review_required`를 확인했다.
- 선택한 메일의 이미지 첨부 4건은 로컬 parser 결과 `partial_success`였고, Mail Decision은 이를 요청 형식 실패가 아니라 `attachment_analysis_incomplete` 사람 검토 상태로 처리했다.
- Gmail cookie를 사용한 `/ui/inbox`, `/ui/emails/{uuid}`, Mail Decision panel이 모두 HTTP 200으로 렌더링됐고 레이블과 Summary가 표시됐다.
- 반복 동기화 후 선택 메일은 활성 첨부 4건, 과거 비활성 첨부 8건으로 분리되어 화면에는 현재 4건만 표시된다.
- `uv run ruff check app tests`, `python -m compileall`, `pytest -q`를 통과했다. 테스트는 73 passed, 기존 collection warning 1건이었다.

## 남은 리스크와 후속 작업

- 초기 classification과 Summary는 현재 `coramail-rule-v1` deterministic worker다. Gmail 실행 경로는 복구됐지만 운영 AI 품질 완료 주장으로 사용하면 안 된다.
- 이미지 첨부가 Vision 모델에서 텍스트를 추출하지 못하면 정상적으로 `partial_success`와 사람 검토가 된다. Vision 모델 품질은 별도 평가가 필요하다.
- OAuth token과 실제 Gmail 원본은 로컬 runtime/DB에만 있고 Git에는 포함하지 않는다. 다중 호스트 운영 전 credentials secrets store가 필요하다.

# 2026-07-31 - 메일 분류, 요약, 첨부파일 재분석 실행 경로 복구

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | UI regeneration routes, Email analysis jobs, Attachment parser persistence, PostgreSQL mailbox view |
| 관련 파일 | `app/server.py`, `app/services/postgres_email_analysis_worker.py`, `app/repositories/postgres_mail_repository.py`, `app/services/postgres_mail_service.py` |

## 요청 또는 배경

- 사용자는 웹에서 분류, 첨부파일 분석, 요약문이 모두 동작하지 않는다고 지적했고, 직접 실행하거나 시각화 가능한 상태로 근본 원인 파악과 해결을 요청했다.

## 확인한 사실

- `/api/emails/{email}/classification/regenerate`와 `/summary/regenerate`는 `processing_jobs` pending row만 생성하고 실제 워커를 실행하지 않았다.
- UI의 분류/요약 재생성 버튼도 pending job id만 이벤트로 넘겨 화면을 갱신했기 때문에 사용자는 분석 완료 결과를 볼 수 없었다.
- `/ui/emails/{email}/attachments/reanalyze`는 `coramail-demo-noop`만 반환하는 noop 라우트였다.
- 첨부파일 조회는 `attachment_analysis_results`를 join하지 않아, 분석 결과가 있어도 상세 화면에는 정적 파일 정보만 표시됐다.
- 요약 재실행 검증 중 기본 카테고리 seed 로직이 `code` conflict만 처리하고 `id` conflict를 처리하지 못해 `categories_pkey` 중복 오류가 발생했다.

## 해결 방법

- `PostgresEmailAnalysisWorker.run_one(job_id)`를 추가해 방금 생성한 분류/요약 작업만 즉시 claim하고 처리할 수 있게 했다.
- UI와 API의 분류/요약 재생성 라우트가 pending job 생성 후 즉시 `run_one()`을 호출하고, 성공/실패 상태와 worker 결과를 반환하도록 변경했다.
- 첨부파일 재분석 UI/API 라우트를 실제 `AttachmentParserDispatcher`와 `PostgresAttachmentAnalysisRepository.save()`에 연결했다.
- `PostgresMailRepository.attachments_for_message()`가 최신 `document_understanding` 분석 결과를 join하도록 변경했다.
- `PostgresMailboxService`가 첨부 분석 상태, analyzer, extracted text, pages/tables/fields/warnings/errors를 상세 화면 행으로 렌더링하도록 변경했다.
- 기본 카테고리 seed 로직을 update-then-insert 방식으로 바꿔 기존 `id` 또는 `code` row가 있어도 워커 초기화가 중복 오류로 실패하지 않게 했다.

## 검증

- `uv run ruff check app tests`를 통과했다.
- `uv run python -m compileall app tests`를 통과했다.
- `uv run pytest -q`는 71 passed, 기존 `TestRetrievalService` collection warning 1건이었다.
- 새 서버를 `http://127.0.0.1:8020`에서 실행했다.
- 실제 API 호출로 Postgres 메일 `dc5c6261-2e05-5b29-8cce-5f9dbbac99dc`의 요약 재생성, 분류 재생성, 첨부 재분석이 모두 `status=success` 또는 `status=ok`로 완료됨을 확인했다.
- 상세 HTML에서 첨부 `Status=completed`, `Analyzer=local-parser-v1`, `Extracted text`, Summary 섹션, 카테고리 `발주`가 렌더링됨을 확인했다.
- `/api/health`는 `status=ok`, `local_ai.ready=true`, `database.ready=true`, `llm.ready=true`, `qdrant.ready=true`를 반환했다.

## 남은 리스크와 후속 작업

- 현재 메일 목록 분류/요약 워커는 `coramail-rule-v1` 기반 deterministic worker다. Mail Decision Runtime의 LLM 경로는 별도로 연결되어 있으나, 이 UI 재생성 버튼은 운영 LLM 품질을 대표하지 않는다.
- Playwright는 현재 가상환경에 설치되어 있지 않아 스크린샷 파일 생성은 하지 못했다. 대신 서버 실행, API 응답, 렌더링 HTML로 확인했다.

# 2026-07-31 - 로컬 LLM Mail Decision 실행 경로 복구

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Local LLM runtime wiring, UI/runtime integration, Fact extraction fallback, Decision/routing flow |
| 관련 파일 | `app/config.py`, `app/server.py`, `app/llm/gateway.py`, `app/api/mail_decision.py`, `app/services/mail_decision_runtime_service.py`, `app/services/mail_decision_routing_service.py`, `app/agents/fact_extraction_agent.py`, `app/agents/decision_agent.py`, `tests/test_mail_decision_routing_service.py`, `tests/test_decision_agent.py`, `tests/test_vision_fact_extraction.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 웹에서 LLM 관련 기능이 전혀 동작하지 않는 것 같다고 지적했고, 근본 원인 파악 후 해결을 요청했다.

## 확인한 사실

- 기존 `8020` UI 서버의 Mail Decision UI는 기본 runtime URL `http://127.0.0.1:8001`을 호출했지만, `8001` runtime 서버는 떠 있지 않았다.
- `app.server`에는 Mail Decision API router가 mount되어 있지 않아, UI 서버 단독 실행만으로는 Mail Decision API를 처리할 수 없었다.
- `.env`가 없고 `CORAMAIL_DATABASE_URL`도 없어서 runtime repository가 명시적으로 설정되지 않았다.
- 로컬 컨테이너는 `coramail-postgres`와 `coramail-qdrant`가 실행 중이었고, Qdrant에는 `coramail_cases`와 `coramail_cases_clean_v2` collection이 있었다.
- 기존 기본 text model `qwen3:8b`는 설치되어 있지 않았다.
- 설치된 qwen 계열 모델은 OpenAI `response_format=json_object` 경로에서 timeout 또는 thinking-only 응답을 만들었다.
- `llama3.2:latest`는 Ollama native JSON 경로에서 정상 JSON을 반환했다.
- UI는 fixture demo 메일 9건을 보여주고 runtime은 Postgres `email_messages`를 조회해, 버튼 실행 시 fixture email ID가 runtime DB에 없어 404가 발생했다.
- FactExtractionAgent가 LLM 호출은 수행했지만 명시 라벨이 있는 합성 메일에서도 핵심 facts를 빈 값으로 반환했다.
- DecisionAgent는 일부 로컬 모델 응답에서 Pydantic schema `$ref` 형태를 반환해 schema validation에 실패했다.
- `MailDecisionRoutingService`는 `DecisionAgentOutput.business_area` 같은 존재하지 않는 평면 필드를 읽는 버그가 있었다.
- routing repository만 여전히 `CORAMAIL_DATABASE_URL`을 직접 읽어 빈 문자열일 때 Unix socket으로 접속하려는 문제가 있었다.

## 해결 방법

- `app.config`를 추가해 로컬 개발 기본값을 중앙화했다. 기본 DB는 `postgresql://coramail:coramail@127.0.0.1:5432/coramail`, 기본 Qdrant collection은 `coramail_cases_clean_v2`, 기본 text model은 `llama3.2:latest`로 설정했다.
- `app.server`에 Mail Decision API router를 mount하고, UI Mail Decision client가 별도 env가 없으면 현재 서버의 `/api/...`를 호출하게 했다.
- `/api/health`가 DB, LLM model presence, Qdrant collection, runtime mount 상태를 함께 반환하게 했다.
- 로컬 DB가 준비된 demo mode에서는 Postgres source를 기본으로 사용해 UI email ID와 runtime email ID를 일치시켰다.
- `LocalLLMGateway`에 `CORAMAIL_LLM_PROVIDER=ollama` native JSON path를 추가했다.
- FactExtractionAgent에 원문 `Customer:`, `Project:`, `Vessel:`, `Product group:`, `Request type:`, `Reference:` 라벨을 evidence-backed facts로 병합하는 fallback을 추가했다.
- DecisionAgent에 LLM schema validation 실패 시 이미 검증된 facts와 retrieval sufficiency로 summary/classification을 구성하는 fallback을 추가했다.
- RoutingService가 nested `output.classification.*` 필드를 사용하도록 수정하고, routing repository도 공통 DB config를 쓰게 했다.

## 검증

- `curl /api/health` 결과는 `status=ok`, `local_ai.ready=true`, `database.ready=true`, `llm.ready=true`, `qdrant.ready=true`, `mail_decision_runtime.api_mounted=true`였다.
- `curl /api/emails`는 Postgres source 기준 400건을 반환했다.
- 실제 Mail Decision 실행은 Postgres 메일 `dc5c6261-2e05-5b29-8cce-5f9dbbac99dc`에서 facts/retrieval까지 진행 후 `retrieval_context_insufficient`로 사람 검토가 됐다.
- 두 번째 실행 `21a081d2-0244-5e99-9b04-005cee6ce449`는 facts와 retrieval sufficiency가 채워지고 DecisionAgent schema 실패 지점까지 진행했다.
- 세 번째 실행 `bd2162ba-9b10-570f-bda6-90a4110270bd` resume 결과는 `business_type=repair_request`, `routing_decision=review_required`, 후보 5명 생성까지 완료됐다.
- 자동 배정은 정책 threshold/margin 때문에 되지 않았지만, 더 이상 runtime connection refused, model not found, fixture ID mismatch, routing field AttributeError로 막히지 않는다.
- `uv run ruff check app tests`를 통과했다.
- `uv run pytest -q`는 71 passed, 기존 `TestRetrievalService` collection warning 1건이었다.
- `uv run python -m compileall app tests`를 통과했다.

## 남은 리스크와 후속 작업

- 현재 로컬 모델은 fallback 의존도가 높다. 운영 품질을 주장하려면 FactExtractionAgent와 DecisionAgent의 structured output 품질을 별도로 개선해야 한다.
- qwen 계열 thinking 모델은 native JSON에서도 content 없이 thinking을 반환할 수 있어 text model 기본값으로 부적합하다.
- 자동 배정까지 가려면 routing policy threshold, 후보 점수 분해, clean-v2 평가 재실행이 필요하다.
- 이전 failed step attempt가 steps UI에 함께 보인다. attempt별 최신 상태 요약이 필요할 수 있다.

# 2026-07-30 - Clean v2 평가 데이터와 누수 검증 baseline 수립

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Evaluation leakage validation, Clean synthetic dataset, Qdrant collection isolation, Evaluation Dashboard |
| 관련 파일 | `app/evaluation/leakage.py`, `app/evaluation/synthetic_dataset.py`, `app/retrieval/qdrant_client.py`, `app/tools/synthetic_evaluation.py`, `app/server.py`, `app/templates/views/evaluation.html`, `app/templates/views/evaluation_case.html`, `app/static/app.css`, `tests/test_synthetic_evaluation.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 기존 평가 데이터 누수를 제거하고 신뢰 가능한 5건 clean baseline을 다시 수립하라고 요청했다.
- FactExtractionAgent, retrieval threshold, routing policy는 이번 작업에서 수정하지 말고, 기존 미커밋 변경과 기존 Qdrant collection을 보존하라고 지시했다.

## 확인한 사실

- 기존 8010 UI 서버는 이 저장소의 `.venv/bin/uvicorn app.server:app --host 127.0.0.1 --port 8010` 프로세스였다.
- 기존 leaky dataset은 ground truth 100건과 Qdrant cases 100건이 target/source id와 normalized content hash 기준으로 겹쳤다.
- 기존 Qdrant payload에는 `business_type`, `assignee_user_id`, target `email_message_id`가 직접 들어가 있었다.
- 기존 generator의 누수 원인은 `emails[:ground_truth_count]`를 ground truth와 Qdrant case 양쪽에 재사용하는 구조였다.

## 해결 방법

- 기존 leaky baseline 산출물을 `data/evaluation/baselines/leaky-20260730171509/`에 보존했다.
- `app.evaluation.leakage`를 추가해 ID overlap, normalized exact content overlap, near duplicate, answer-like payload field, duplicate target/case를 검사하게 했다.
- near duplicate threshold는 `SequenceMatcher >= 0.95` 또는 token Jaccard `>= 0.90`으로 고정했다.
- `synthetic-mail-decision-v2-clean` clean generator를 추가해 evaluation targets와 retrieval cases source email을 분리했다.
- clean Qdrant payload는 `business_type`/`assignee_user_id` 대신 `historical_business_type`/`historical_assignee_user_id`를 사용한다.
- Qdrant retriever는 historical field를 runtime metadata로 매핑해 현재 retrieval/routing code가 깨지지 않게 했다.
- `validate-leakage` CLI를 추가했고 strict 모드에서 finding이 있으면 non-zero exit하도록 했다.
- clean dataset은 `data/evaluation/synthetic_mail_decision_dataset.clean.json`, Qdrant collection은 `coramail_cases_clean_v2`, fixture dir는 `data/evaluation/fixtures-clean-v2/`로 분리했다.
- Dashboard는 `?report=clean-v2`와 `?report=leaky-baseline` registry 기반 선택을 지원하며, query parameter로 직접 path를 조합하지 않는다.

## 검증

- clean leakage validation은 `id_overlap_count=0`, `exact_content_overlap_count=0`, `near_duplicate_count=0`, `answer_exposure_count=0`, `passed=true`였다.
- leaky baseline leakage validation은 실패로 표시되며 `id_overlap_count=200`, `exact_content_overlap_count=100`, `near_duplicate_count=836`, `answer_exposure_count=200`이었다.
- clean seed 결과는 assignees 8, capabilities 71, emails 200, ground_truth 100, qdrant_cases 100, attachments 120, fixtures 120이었다.
- PostgreSQL에는 clean email rows 200, clean ground truth rows 100, clean attachment rows 120이 확인됐다.
- Qdrant `coramail_cases_clean_v2`는 green, points 100, vector size 768이었다.
- clean 5건 자기 검색에서 동일 target ID 반환, exact body hash 중복, direct `assignee_user_id`/`business_type` payload key 노출은 모두 없었다.
- clean 5건 E2E는 prediction 누락/중복 없이 완료됐고 모두 `review_required`였다.
- clean 5건 score는 execution success 5/5, failed 0/5, review_required 5/5, business type coverage 0/5, selected assignee coverage 0/5, candidate recall 0/5였다.
- clean primary failure는 `fact_extraction_empty=4`, `business_type_missing=1`이었다. review reason은 `retrieval_context_insufficient=3`, `attachment_analysis_incomplete=1`, `decision_agent_gateway_failed=1`이었다.
- Dashboard HTTP는 `/ui/evaluation?report=clean-v2`와 `/ui/evaluation?report=leaky-baseline` 모두 200으로 확인했다. clean은 leakage 통과, leaky는 실패로 표시된다.
- `uv run ruff check app tests`, `uv run pytest -q`, `uv run python -m pytest -q`, `uv run python -m compileall app tests`를 통과했다. pytest는 기존 collection warning 1건을 출력했다.

## 남은 리스크와 후속 작업

- clean 5건에서도 business type coverage와 assignee coverage가 0이므로 다음 작업은 FactExtractionAgent 개선이다.
- 이번 작업은 평가 파이프라인 신뢰성 확보가 목적이므로 FactExtractionAgent, retrieval threshold, routing policy는 변경하지 않았다.
- 20건으로 넘어가려면 clean leakage validation 통과, clean 5건 trace/report/dashboard 확인 조건은 충족했지만, 누수 제거 후 성능 개선은 아직 관찰되지 않았다.
- 사용자 지시에 따라 commit/push는 수행하지 않았다.

# 2026-07-30 - Mail Decision 평가 score, Developer Trace, Evaluation Dashboard 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Evaluation metrics, Developer trace, E2E runner, FastAPI/Jinja UI |
| 관련 파일 | `app/evaluation/metrics.py`, `app/evaluation/runner.py`, `app/tools/synthetic_evaluation.py`, `app/server.py`, `app/templates/views/evaluation.html`, `app/templates/views/evaluation_case.html`, `app/templates/partials/evaluation_trace.html`, `app/static/app.css`, `tests/test_synthetic_evaluation.py`, `tests/test_mail_decision_ui.py` |

## 요청 또는 배경

- 사용자는 100건 전체 평가는 실행하지 않고, 현재 평가 하네스 전수 조사, deterministic score pipeline, Developer Evaluation Trace, 5건 smoke E2E, JSON/CSV/JSONL 리포트, Evaluation Dashboard를 구현하라고 요청했다.
- 사용자는 기존 미커밋 변경을 삭제하지 말고, 자동 commit/push/amend/rebase를 하지 말라고 명시했다.

## 확인한 사실

- 브랜치는 `feat/e2e-evaluation-runner`이고 원격보다 ahead 1 상태였다.
- 작업 시작 전부터 Mail Decision Inspector, runtime client, 평가 데이터, 테스트 관련 미커밋 변경과 untracked 파일이 있었다.
- PostgreSQL 컨테이너, Qdrant, Ollama, Runtime, PostgreSQL-source UI health는 응답했다. Docker 확인은 샌드박스 때문에 승인 경로로 확인했다.
- 기존 CLI는 `generate`, `fixtures`, `seed`, `run`, `evaluate`, `e2e`만 제공했고 `score`는 없었다.
- 합성 평가 데이터는 ground truth 100건과 Qdrant case 100건이 같은 email id/body를 공유하고, Qdrant payload에 `business_type`, `assignee_user_id`가 직접 들어가므로 평가 누수가 존재한다.
- ground truth schema는 `email_message_id`, `business_type`, `expected_assignee_user_id`, `customer_name`, `product_group`, `project_code`, `urgent` 단일 assignee 구조다. review_required ground truth와 복수 assignee 정답은 없다.

## 해결 방법

- `score` CLI를 추가해 외부 서비스 없이 `evaluation_report.json`, `evaluation_cases.csv`, `evaluation_trace.jsonl`을 생성하게 했다.
- metric은 null/failed/review_required/missing prediction을 분모에 포함하고, 각 metric을 `{numerator, denominator, value}` 형태로 저장하게 했다.
- `EvaluationCaseResult`, `EvaluationMetricValue`, `EvaluationMetrics`, `EvaluationFailureSummary`, `EvaluationReport`, `DeveloperEvaluationTrace` Pydantic 모델을 추가했다.
- Developer Trace는 원문 body 전체 대신 subject, body preview, body length, body SHA-256, attachment filenames를 저장한다.
- retrieval hit가 prompt에 포함되지 않으면 `excluded_reason`을 비우지 않고, 모르면 `unknown`으로 기록한다.
- review_required trace에는 unresolved context를 채우고, 현재 점수 분해가 없는 routing score는 `not_recorded`와 observability 필요 위치를 구분해 기록한다.
- E2E runner에 `--email-id` 반복 인자를 추가하고, prediction에 facts, attachment analysis, retrieval context, sufficiency, decision, routing 원천 필드를 보존하게 했다.
- `/ui/evaluation`, `/ui/evaluation/cases/{email_message_id}`, `/ui/evaluation/cases/{email_message_id}/trace` route와 Jinja 화면을 추가했다.
- report 파일이 없으면 500 대신 score 명령 안내를 렌더링한다.

## 검증

- 현재 1건 prediction은 score 결과 `total_cases=1`, `review_required=1/1`, business type coverage `0/1`, top1 assignee accuracy `0/1`, candidate recall `0/1`, primary failure stage `retrieval_context_insufficient`로 계산됐다.
- 5건 smoke는 서로 다른 business type, attachment type, customer와 urgent/non-urgent 혼합으로 선택했다. 데이터 생성 패턴상 product group은 `automation`, `engine` 두 값뿐이라 5개 모두 다르게 만들 수 없었다.
- 5건 실제 E2E는 승인된 실행 경로에서 완료됐고 모두 `review_required`였다. review reason은 `retrieval_context_insufficient` 4건, `attachment_analysis_incomplete` 1건이었다.
- 5건 score는 `prediction_count=5/5`, `failed_count=0/5`, `review_required=5/5`, business type coverage `0/5`, selected assignee coverage `0/5`, candidate recall `0/5`, primary failure stage `fact_extraction_empty=5`로 계산됐다.
- `evaluation_report.json`, `evaluation_cases.csv`, `evaluation_trace.jsonl`은 각각 5건 기준으로 읽기 검증했다.
- 기존 8010 서버는 변경 전 코드로 떠 있어 `/ui/evaluation`이 404였다. 서버를 임의 재시작하지 않고 현재 작업 트리 코드의 Jinja route 함수를 직접 렌더링해 summary, case detail, trace HTML을 확인했다.
- `uv run ruff check app tests`, `uv run pytest -q`, `uv run python -m pytest -q`, `uv run python -m compileall app tests`를 통과했다. pytest는 기존 `TestRetrievalService` collection warning 1건을 출력했다.

## 남은 리스크와 후속 작업

- 평가 데이터 누수가 해결되지 않았다. 20건 이상 성능 수치로 해석하기 전에 retrieval corpus에서 target email/정답 payload를 분리하거나 명시 승인해야 한다.
- 가장 큰 품질 병목은 FactExtractionAgent가 본문에 명시된 customer/project/product/request type/vessel을 추출하지 못해 retrieval과 business type 판단으로 품질 손실이 전파되는 점이다.
- 현재 routing score observability는 final/component 일부만 제공되며 capability/rule/retrieval score 분해는 더 세밀한 instrumentation이 필요하다.
- 8010 UI 서버에는 변경 사항이 반영되지 않았다. 사용자가 확인하려면 기존 서버 프로세스를 재시작해야 한다.
- 사용자 지시에 따라 commit/push는 수행하지 않았다.

# 2026-07-30 - 경량 Ollama 모델 기반 로컬 평가 환경 검증

| 항목 | 내용 |
|---|---|
| 상태 | 리스크 |
| 관련 영역 | Local LLM Gateway, Evaluation runner, Development dependencies, uv lockfile |
| 관련 파일 | `app/llm/gateway.py`, `pyproject.toml`, `uv.lock` |

## 요청 또는 배경

- 사용자는 `feat/e2e-evaluation-runner` 브랜치에서 기본 대용량 Ollama 모델을 다운로드하지 않고, 이미 설치된 경량 모델로 CoRA Mail Agent 로컬 파이프라인을 먼저 검증해 달라고 요청했다.
- 임시 검증 모델은 text `qwen3.5:2b`, vision `qwen3-vl:2b`, embedding `nomic-embed-text` 계열로 제한하고, 코드 기본 모델명은 변경하지 않기로 했다.
- Ollama 설치, 서비스 재시작, systemd 변경, 모델 삭제, 기본 모델 자동 다운로드는 하지 않기로 했다.

## 확인한 사실

- 저장소는 `/home/ysh/workspace/coramail_agent`, 브랜치는 `feat/e2e-evaluation-runner`, HEAD는 `00a2597`였다.
- Ollama HTTP API는 `127.0.0.1:11434`에서 정상 응답했고 `/v1/models`에 `qwen3.5:2b`, `qwen3-vl:2b`, `nomic-embed-text:latest`가 있었다.
- `nomic-embed-text`는 `/v1/models`에서 `nomic-embed-text:latest`로 노출되므로 gateway 검증에는 정확한 모델 ID를 사용했다.
- `LocalLLMGateway.embed()`는 `nomic-embed-text:latest`로 벡터 1개, 768차원 응답을 받았다.
- `uv sync`는 성공했으며, `pyproject.toml`에 이미 선언된 `openpyxl`, `pillow`, `pymupdf`, `pypdf`, `python-docx` 및 하위 의존성을 `uv.lock`에 반영했다.
- `uv run python -m compileall app tests`는 성공했다.

## 오류와 중단 원인

- `uv run ruff check .`와 `uv run pytest -q`는 각각 `ruff`, `pytest` 실행 파일이 없어 실패했다. `pyproject.toml`에는 tool 설정은 있지만 dev dependency 선언이 없다.
- 기본 chat completion HTTP 호출은 성공했지만, `LocalLLMGateway.generate_structured()`는 `qwen3.5:2b`에서 120초 timeout으로 실패했다.
- 같은 structured payload를 직접 `curl --max-time 180`으로 호출해도 180초 동안 0바이트 응답 후 timeout됐다.
- 이는 단순 네트워크 장애가 아니라 경량 text 모델이 현재 gateway의 `response_format={"type":"json_object"}` 구조화 출력 요청을 제한 시간 안에 완료하지 못하는 문제로 판단된다.

## 남은 리스크와 후속 작업

- `ruff`와 `pytest`를 실행하려면 최소 dev dependency 선언이 필요하다. 후보는 `pyproject.toml`에 `dependency-groups.dev = ["pytest", "ruff"]`를 추가하고 `uv lock`을 갱신하는 방식이다.
- structured text gateway timeout이 해결되기 전에는 PostgreSQL/Qdrant seed와 1건 E2E로 넘어가도 text generation 단계에서 같은 실패가 재현될 가능성이 높다.
- 경량 모델 검증을 계속하려면 `qwen3.5:2b`의 구조화 출력 timeout 원인을 먼저 줄여야 한다. 예: 더 작은 schema 재시도, timeout 상향, 설치된 다른 text 모델 비교, 또는 기본 `qwen3:8b` 다운로드 검토.

# 2026-07-29 - Email analysis pending job worker와 결과 반영 경로 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Processing jobs, Classification worker, Summary worker, Inbox result rendering |
| 관련 파일 | `app/services/postgres_email_analysis_worker.py`, `app/tools/run_email_analysis_jobs.py`, `app/server.py`, `app/repositories/postgres_mail_repository.py`, `app/services/postgres_mail_service.py`, `docs/features/email-classification.md`, `docs/features/email-summary.md`, `docs/features/processing-jobs-failure-management.md`, `docs/features/implementation-readiness.md` |

## 요청 또는 배경

- 사용자는 end-to-end 개발 완료까지 질문하지 말고 계속 진행해 달라고 요청했다.
- 직전 단계에서 classification/summary regenerate가 pending job을 등록하게 되었으므로, 다음 단계는 pending job을 실행하고 결과가 inbox/detail UI에 반영되는 경로를 완성하는 것이다.

## 확인한 사실

- demo seed DB에는 `categories`와 AI 결과가 없으므로 worker가 기본 category master를 보장해야 classification assignment를 저장할 수 있다.
- `email_analysis_results`를 조회하지 않으면 worker가 summary/classification 결과를 저장해도 inbox detail에 표시되지 않는다.
- 초기 end-to-end 검증에는 외부 LLM 대신 deterministic rule 기반 worker가 적합하다. 실제 LLM/prompt/schema validation runner는 다음 운영 확장으로 남긴다.

## 해결 방법

- `PostgresEmailAnalysisWorker`를 추가해 pending `email_analysis` job 중 `metadata.analysis_type = classification` 또는 `executive_summary`를 claim하고 실행하게 했다.
- classification worker는 기본 categories를 upsert하고, rule 기반 category/score/reason 결과를 `email_analysis_results`와 current `email_category_assignments`에 저장한다.
- summary worker는 subject/snippet/body 기반 summary와 section payload를 `email_analysis_results.result_text`, `result_json.sections`에 저장한다.
- 성공한 job은 `processing_jobs.status = success`, `completed_at`으로 갱신하고, 실패 시 `failed`와 error message를 남긴다.
- `app.tools.run_email_analysis_jobs` CLI와 `POST /api/jobs/run-pending?limit=` API를 추가했다.
- PostgreSQL mail repository/service가 current classification/summary analysis result를 읽고 inbox/detail payload에 반영하도록 했다.

## 검증

- `uv run python -m py_compile app/services/postgres_email_analysis_worker.py app/tools/run_email_analysis_jobs.py app/services/postgres_mail_service.py app/repositories/postgres_mail_repository.py app/server.py`를 통과했다.
- 임시 PostgreSQL 컨테이너에 schema와 demo seed를 적용했다.
- classification/summary job을 등록한 뒤 CLI worker로 2건을 처리했고, `processed_count = 2`, 두 job 모두 `success`로 완료됨을 확인했다.
- DB에서 기존 pending `email_analysis_results`는 `is_current = false`, 새 success 결과는 `is_current = true`로 남는 것을 확인했다.
- `PostgresMailboxService`가 worker 결과를 읽어 첫 메일을 `completed`, `문의`, summary section 3개로 반환함을 확인했다.
- uvicorn을 PostgreSQL source로 실행해 API 기반 `register -> /api/jobs/run-pending -> /api/emails/{email_uid} -> /ui/emails/{email_uid}` 흐름을 검증했다.
- 두 번째 메일에서 `/api/jobs/run-pending`이 2건을 처리했고, 상세 API/UI가 `completed`, `발주`, summary section 렌더링을 반환함을 확인했다.

## 남은 리스크

- worker는 현재 deterministic rule 기반이다. 실제 운영 품질은 LLM prompt, schema validation, model versioning, failure retry 정책을 연결해야 확정할 수 있다.
- retry/cancel API와 stale running job 복구 정책은 아직 구현되지 않았다.

# 2026-07-29 - Classification/Summary regenerate를 PostgreSQL job 등록으로 연결

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Processing jobs, Email analysis results, Classification regenerate, Summary regenerate |
| 관련 파일 | `app/repositories/postgres_job_repository.py`, `app/repositories/postgres_mail_repository.py`, `app/server.py`, `docs/features/email-classification.md`, `docs/features/email-summary.md`, `docs/features/processing-jobs-failure-management.md`, `docs/features/implementation-readiness.md` |

## 요청 또는 배경

- 사용자는 질문 없이 end-to-end 개발 완료까지 계속 진행해 달라고 요청했다.
- UID route 전환 이후 남은 다음 작업은 F-03/F-04의 demo noop regenerate endpoint를 실제 `processing_jobs` 등록 경로로 바꾸는 것이다.

## 확인한 사실

- `processing_jobs`에는 uniqueness 제약이 없으므로, 같은 메일과 같은 analysis type에 대해 `pending`/`running` job이 있으면 재사용하는 application-level 중복 방지가 필요하다.
- 기존 PostgreSQL inbox 조회는 `processing_jobs`를 단순 join하고 있어 job이 여러 건 생기면 메일 row가 중복될 수 있었다.
- `email_analysis_results.model_name`은 NOT NULL이라 pending placeholder에는 명시적 pending model marker가 필요하다.

## 해결 방법

- `PostgresJobRepository`를 추가해 email analysis job 등록, job 목록, job 상세, 메일별 job 조회를 제공하게 했다.
- classification regenerate는 `metadata.analysis_type = classification`, summary regenerate는 `metadata.analysis_type = executive_summary`로 `processing_jobs`를 등록한다.
- job 등록 시 같은 메일/analysis type의 활성 job이 있으면 새 job을 만들지 않고 기존 job을 반환한다.
- job 등록과 함께 `email_analysis_results`에 current `pending` placeholder를 생성하고, 기존 current 결과는 `is_current = false`로 전환한다.
- `/ui/emails/{email_uid}/classification/regenerate`, `/ui/emails/{email_uid}/summary/regenerate`, `/api/emails/{email_uid}/classification/regenerate`, `/api/emails/{email_uid}/summary/regenerate`, `/api/jobs`, `/api/jobs/{job_id}`, `/api/emails/{email_uid}/jobs`를 연결했다.
- PostgreSQL inbox query는 최신 email analysis job 1건만 LATERAL join하도록 바꿔 여러 job으로 인한 목록 중복을 방지했다.

## 검증

- `uv run python -m py_compile app/repositories/postgres_job_repository.py app/repositories/postgres_mail_repository.py app/server.py`를 통과했다.
- DB URL이 없는 demo fallback에서 job 등록 helper가 `None`을 반환해 기존 noop 동작이 유지됨을 확인했다.
- 임시 PostgreSQL 컨테이너에 schema와 demo seed를 적용했다.
- `PostgresJobRepository.create_email_analysis_job()`로 classification과 executive summary job을 등록했고, 같은 classification 요청이 기존 pending job을 재사용함을 확인했다.
- uvicorn을 PostgreSQL source로 실행해 `/ui/emails/{email_uid}/classification/regenerate`, `/ui/emails/{email_uid}/summary/regenerate`, `/api/emails/{email_uid}/classification/regenerate`, `/api/emails/{email_uid}/jobs`, `/api/jobs?job_type=email_analysis`, `/api/emails`, `/ui/mail-rows`가 정상 응답함을 확인했다.
- HX trigger에 `mail-classification-regenerated`, `mail-summary-regenerated`, `processing_job_id`, `status = pending`이 포함됨을 확인했다.
- DB에서 `email_analysis_results`에 `classification`, `executive_summary` current pending row가 생성됨을 확인했다.
- job 추가 후에도 `/api/emails`는 9개 unique `email_uid`를 유지해 목록 중복이 없음을 확인했다.

## 남은 리스크

- 실제 worker는 아직 pending job을 실행하지 않는다. 다음 구현은 pending job runner가 `email_analysis_results`를 `success` 또는 `failed`로 갱신하고, classification 결과를 `email_category_assignments`에 반영하는 것이다.
- retry/cancel API와 stale running job 복구 정책은 아직 운영 목표로 남아 있다.

# 2026-07-29 - Inbox 상세/첨부 route를 email_uid 우선으로 전환

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox UI, API route contract, Stable email identity |
| 관련 파일 | `app/server.py`, `app/services/demo_mail_service.py`, `app/services/gmail_mail_service.py`, `app/services/postgres_mail_service.py`, `app/repositories/demo_mail_repository.py`, `app/repositories/postgres_mail_repository.py`, `app/templates/partials/mail_rows.html`, `app/templates/partials/email_detail.html`, `app/templates/shell.html`, `docs/features/inbox-list-detail.md`, `docs/features/implementation-readiness.md` |

## 요청 또는 배경

- 이전 단계에서 PostgreSQL-backed inbox service가 연결되었고, 다음 작업으로 index 기반 URL을 stable `email_uid` route로 전환하기로 했다.
- 사용자는 계속 진행을 승인했다.

## 확인한 사실

- UI에는 이미 `selectedEmailUid` hidden state와 row별 `data-email-uid`가 있어 전환 폭을 작게 잡을 수 있었다.
- 기존 `/ui/emails/0`, `/api/emails/0`, `/api/emails/0/attachments/0` 형태는 과거 UI/검증 로그와 호환을 위해 fallback으로 남겨 두는 것이 안전하다.

## 해결 방법

- demo, Gmail, PostgreSQL mailbox service에 `email_detail_by_uid`를 추가했다.
- demo와 PostgreSQL attachment 조회에 `attachment_path_by_uid`를 추가했다.
- `app.server`의 상세/첨부/액션 route는 `{email_ref}`를 받아 `email_uid` 우선, 숫자 index fallback 순서로 해석하게 했다.
- inbox row, detail action, related mail link, attachment link, JS refresh 경로가 UID URL을 생성하도록 바꿨다.
- feature readiness 문서에서 UID route 전환 완료 상태를 반영했다.

## 검증

- `uv run python -m py_compile app/repositories/demo_mail_repository.py app/repositories/postgres_mail_repository.py app/services/demo_mail_service.py app/services/gmail_mail_service.py app/services/postgres_mail_service.py app/server.py`를 통과했다.
- demo service에서 `email_detail_by_uid`와 `attachment_path_by_uid`가 첫 메일/첨부파일을 조회함을 확인했다.
- uvicorn을 실제 실행해 `/ui/inbox`, `/ui/emails/{email_uid}`, `/api/emails/{email_uid}`, `/api/emails/{email_uid}/attachments/0`, 기존 `/ui/emails/0` fallback이 HTTP 200으로 응답함을 확인했다.
- 렌더링된 inbox/detail HTML에 UID 기반 `hx-get`, `hx-post`, attachment link가 포함됨을 확인했다.
- 임시 PostgreSQL 컨테이너에 schema와 demo seed를 적용한 뒤 `PostgresMailboxService.email_detail_by_uid`와 `attachment_path_by_uid`가 동작함을 확인했다.

## 남은 리스크

- 기존 route payload의 `email_index` 필드는 화면 표시와 호환용으로 남아 있다. 운영 API contract에서는 cursor/pagination 도입 시 index 의존도를 더 줄여야 한다.
- F-03/F-04의 재분류/요약 재생성 endpoint는 아직 demo noop이며 다음 단계에서 `processing_jobs` 등록으로 연결해야 한다.

# 2026-07-29 - PostgreSQL-backed inbox repository/service 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox UI, PostgreSQL repository, Attachment serving |
| 관련 파일 | `app/repositories/postgres_mail_repository.py`, `app/services/postgres_mail_service.py`, `app/server.py` |

## 요청 또는 배경

- 사용자는 end-to-end 검증 가능 상태까지 계속 진행해 달라고 요청했다.
- 이전 단계에서 실제 PostgreSQL schema 적용과 demo seed 적재가 검증되었으므로, 다음 단계는 UI/API가 fixture가 아닌 PostgreSQL seed 데이터를 읽을 수 있게 하는 것이다.

## 확인한 사실

- 현재 inbox UI는 `DemoMailService` 형태의 dictionary contract에 의존한다.
- PostgreSQL seed에는 원본 메일, 수신자, 첨부파일, pending analysis job은 있으나 AI 분류/요약 결과는 아직 없다.
- 따라서 PostgreSQL adapter는 현재 UI contract를 유지하되, 미분류/미할당/queued 상태를 정상 상태로 표시해야 한다.

## 해결 방법

- `PostgresMailRepository`를 추가해 `email_messages`, `email_recipients`, `email_attachments`, 현재 category assignment, analysis job 상태를 조회하게 했다.
- `PostgresMailboxService`를 추가해 기존 inbox UI/API가 기대하는 email row, detail, attachment payload 형태로 PostgreSQL row를 변환하게 했다.
- `CORAMAIL_DEMO_SOURCE=postgres`와 `CORAMAIL_DATABASE_URL`이 설정된 demo mode에서는 PostgreSQL-backed service를 사용하도록 `app.server`를 연결했다.
- `/api/emails/{email_index}/attachments/{attachment_index}`가 현재 선택된 mail service의 attachment path를 사용하도록 바꿔 PostgreSQL seed 첨부파일도 열 수 있게 했다.
- 검색/카테고리 필터가 있을 때는 SQL limit보다 filter를 먼저 적용해 결과 누락을 피하도록 했다.

## 검증

- `uv run python -m py_compile app/repositories/postgres_mail_repository.py app/services/postgres_mail_service.py app/server.py`를 통과했다.
- fixture mode regression에서 9개 demo mail과 상세 조회가 유지됨을 확인했다.
- 임시 PostgreSQL 컨테이너에 schema를 적용하고 demo seed를 적재했다.
- `PostgresMailboxService` 직접 호출로 9개 메일, 첫 메일 `queued`, `미분류`, 상세/첨부파일 payload를 확인했다.
- `CORAMAIL_DEMO_SOURCE=postgres` 환경에서 `app.server.mail_service()`가 `PostgresMailboxService`를 선택하고 inbox context가 9개 메일을 로드함을 확인했다.
- uvicorn을 실제 실행해 `/ui/inbox`, `/ui/mail-rows`, `/ui/emails/0`, `/api/emails`, `/api/emails/0/attachments/0`가 HTTP 200으로 응답함을 확인했다.

## 남은 리스크

- FastAPI `TestClient` 기반 테스트는 현재 환경에 `httpx`가 없어 수행하지 못했다.
- 다음 단계는 email index 기반 URL을 stable `email_uid` 기반 route로 전환하거나, classification/summary job runner를 PostgreSQL job table에 연결하는 것이다.

# 2026-07-29 - PostgreSQL schema와 demo seed end-to-end 검증

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | PostgreSQL schema, Demo seed loading, Dependency management |
| 관련 파일 | `pyproject.toml`, `uv.lock` |

## 요청 또는 배경

- 사용자는 PostgreSQL schema 적용과 demo seed 적재가 end-to-end로 검증 가능할 때까지 진행해 달라고 요청했다.

## 확인한 사실

- 프로젝트에는 PostgreSQL 드라이버가 없었으므로 `psycopg[binary]` 의존성이 필요했다.
- 로컬에는 `postgres:17` Docker image가 있었고, 기존 Langfuse용 PostgreSQL 컨테이너가 실행 중이었으므로 별도 임시 컨테이너를 사용했다.

## 해결 방법

- `uv add 'psycopg[binary]'`로 `pyproject.toml`과 `uv.lock`에 PostgreSQL 드라이버 의존성을 추가했다.
- 임시 Docker 컨테이너 `coramail_agent_postgres_e2e`를 `postgres:17` 이미지로 실행했다.
- `app.tools.apply_postgres_schema`로 초기 schema를 실제 PostgreSQL DB에 적용했다.
- `app.tools.load_demo_seed_postgres`로 demo seed bundle을 실제 PostgreSQL DB에 적재했다.
- schema apply와 seed load를 재실행해 idempotency를 확인했다.
- 검증 후 임시 PostgreSQL 컨테이너를 종료했고, `docker ps`로 남아 있지 않음을 확인했다.

## 검증

- `uv run python -c "import psycopg; ... select current_database(), current_user ..."`로 DB 접속을 확인했다.
- `uv run python -m app.tools.apply_postgres_schema --database-url ...`를 통과했고 64개 statement 적용을 확인했다.
- `uv run python -m app.tools.load_demo_seed_postgres --database-url ...`를 통과했다.
- 최종 row count는 `email_accounts=1`, `email_messages=9`, `email_recipients=14`, `email_attachments=6`, `processing_jobs=9`였다.
- `processing_jobs`의 `pending`/`email_analysis` 작업 수는 9건이었다.
- `email_messages.attachment_count < 0`인 잘못된 행은 0건이었다.
- schema apply와 seed load 재실행 후 row count가 변하지 않았다.

## 남은 리스크

- 실제 운영 DB에서는 연결 정보, 권한, migration 적용 방식, 백업/복구 절차를 별도로 정해야 한다.
- 다음 구현은 PostgreSQL-backed inbox repository와 service 전환이다.

# 2026-07-29 - 초기 PostgreSQL DDL과 schema apply CLI 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | PostgreSQL schema, DDL, Demo seed loading |
| 관련 파일 | `db/postgresql/001_initial_schema.sql`, `app/tools/apply_postgres_schema.py`, `docs/development/demo-ui-porting-plan.md` |

## 요청 또는 배경

- 사용자는 PostgreSQL 실제 DB 경로를 붙이는 다음 단계 진행을 승인했다.
- seed loader가 실제로 검증되려면 문서 스키마를 기반으로 DB 테이블을 생성할 DDL이 필요하다.

## 확인한 사실

- 현재 저장소에는 Alembic 설정이나 SQLAlchemy 모델이 없다.
- `psql` CLI와 `psycopg` Python 패키지는 현재 실행 환경에 없다.
- 따라서 실제 DB 적용은 현재 환경에서 수행하지 않고, DDL과 적용 CLI의 dry-run 검증까지 진행했다.

## 해결 방법

- `docs/architecture/postgresql_schema.md` 기준의 초기 DDL `db/postgresql/001_initial_schema.sql`을 추가했다.
- correction/evaluation 전용 테이블은 아직 decision gate가 남아 있어 초기 DDL에서 제외했다.
- `app.tools.apply_postgres_schema` CLI를 추가해 `CORAMAIL_DATABASE_URL` 또는 `--database-url`로 schema를 적용할 수 있게 했다.
- `docs/development/demo-ui-porting-plan.md`에 schema dry-run과 schema apply 후 seed load 순서를 기록했다.

## 검증

- `python -m py_compile app/tools/apply_postgres_schema.py app/repositories/postgres_seed_writer.py app/tools/load_demo_seed_postgres.py`를 통과했다.
- `uv run python -m app.tools.apply_postgres_schema --dry-run`을 통과했고 SQL statement count가 64개임을 확인했다.
- `uv run python -m app.tools.load_demo_seed_postgres --dry-run`을 통과했다.
- `git diff --check`를 통과했다.

## 남은 리스크

- 실제 PostgreSQL 서버와 `psycopg`가 있는 환경에서 `apply_postgres_schema`와 `load_demo_seed_postgres`를 end-to-end로 검증해야 한다.
- migration 관리 도구는 아직 도입하지 않았다. 스키마 변경이 잦아지면 Alembic 또는 SQL migration 관리 방식을 결정해야 한다.

# 2026-07-29 - 데모 seed PostgreSQL loader CLI 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo seed, PostgreSQL writer, F-01/F-10 implementation readiness |
| 관련 파일 | `app/repositories/postgres_seed_writer.py`, `app/tools/load_demo_seed_postgres.py`, `docs/development/demo-ui-porting-plan.md` |

## 요청 또는 배경

- 사용자는 features 문서 작업 이후 다음 작업도 계속 이어서 진행해 달라고 요청했다.
- `implementation-readiness.md`의 다음 구현 순서 첫 항목은 demo seed bundle을 실제 PostgreSQL insert 경로로 연결하는 것이다.

## 확인한 사실

- `DemoSeedService`는 이미 `email_accounts`, `email_messages`, `email_recipients`, `email_attachments`, `processing_jobs` row bundle을 deterministic하게 생성한다.
- `pyproject.toml`에는 PostgreSQL 드라이버가 아직 없다.
- 실제 DB 접속과 schema 적용은 현재 환경에서 확인되지 않았다.

## 해결 방법

- `PostgresSeedWriter`를 추가해 기존 seed bundle을 정해진 테이블 순서로 PostgreSQL에 upsert할 수 있게 했다.
- `app.tools.load_demo_seed_postgres` CLI를 추가해 `--dry-run` 검증과 `CORAMAIL_DATABASE_URL` 기반 실제 write 경로를 제공했다.
- `psycopg`는 선택적 runtime dependency로 처리해, 설치되지 않은 환경에서는 명확한 오류를 내도록 했다.
- `docs/development/demo-ui-porting-plan.md`에 dry-run과 실제 load 명령을 기록했다.

## 검증

- `python -m py_compile app/repositories/postgres_seed_writer.py app/tools/load_demo_seed_postgres.py`를 통과했다.
- `uv run python -m app.tools.load_demo_seed_postgres --dry-run`을 통과했고 row count가 `email_accounts=1`, `email_messages=9`, `email_recipients=14`, `email_attachments=6`, `processing_jobs=9`임을 확인했다.
- `uv run python -m app.tools.export_demo_seed --check`를 통과했다.
- `git diff --check`를 통과했다.

## 남은 리스크

- 실제 PostgreSQL write는 schema가 적용된 DB와 `psycopg`가 설치된 runtime에서 추가 검증해야 한다.
- 아직 PostgreSQL-backed inbox repository는 구현하지 않았다.

# 2026-07-29 - features 구현 준비 게이트 문서 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Features documentation, Implementation readiness, Decision gates |
| 관련 파일 | `docs/features/README.md`, `docs/features/implementation-readiness.md` |

## 요청 또는 배경

- 사용자는 features 문서 작업을 모두 진행하고 다음 작업도 이어서 진행해 달라고 요청했다.
- 전체 feature 상세 문서 작성 후, 문서들에 흩어진 Open Questions와 구현 가능 항목을 정리할 필요가 있었다.

## 해결 방법

- `docs/features/implementation-readiness.md`를 추가해 feature 상세 문서 coverage, 바로 구현 가능한 작업, 의사결정 게이트, 권장 다음 구현 순서를 정리했다.
- correction/review/evaluation 저장소, category/priority code 체계, LLMOps 도구 선택을 결정 게이트로 분리했다.
- `docs/features/README.md` 관련 문서 목록에 구현 준비 문서를 링크했다.

## 검증

- `git diff --check`를 통과했다.
- 문서 변경만 수행했기 때문에 애플리케이션 실행 테스트는 수행하지 않았다.

## 남은 리스크

- 구현 준비 문서는 권장 방향을 제시하지만, 실제 스키마 변경은 별도 의사결정 문서 또는 architecture 문서 갱신 후 진행해야 한다.

# 2026-07-29 - 남은 features 상세 계약 문서 일괄 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Features documentation, F-01, F-05, F-06, F-07, F-08, F-10, F-11, F-12 |
| 관련 파일 | `docs/features/README.md`, `docs/features/mailbox-synchronization.md`, `docs/features/key-information-extraction.md`, `docs/features/attachment-analysis.md`, `docs/features/context-search-qdrant-indexing.md`, `docs/features/assignee-routing.md`, `docs/features/processing-jobs-failure-management.md`, `docs/features/llmops-observability-evaluation.md`, `docs/features/notifications-work-status.md` |

## 요청 또는 배경

- 사용자는 features 문서 작업을 이어서 모두 진행하고 다음 작업도 계속 이어 달라고 요청했다.
- 이전 작업에서 F-02, F-03, F-04, F-09 상세 문서가 추가되어 있었고, 나머지 기능은 README 목록 수준에 머물러 있었다.

## 확인한 사실

- PostgreSQL 스키마에는 첨부파일, 문서 분류, 첨부 분석 결과, 라우팅 규칙과 배정 이력, 알림, Qdrant 색인 기록, processing job, audit log 구조가 정의되어 있다.
- Qdrant point schema에는 이메일 point와 첨부파일 chunk point의 payload 기준이 정의되어 있다.
- DECISION-005는 LLMOps 초기 구조를 PostgreSQL 기록과 OpenTelemetry trace 중심으로 설계하고 Phoenix/Langfuse를 D3/D4에서 비교하도록 제안한다.

## 해결 방법

- F-01 일반 메일 수집/동기화 상세 문서 `mailbox-synchronization.md`를 추가했다.
- F-05 핵심 정보 추출, F-06 첨부파일 분석, F-07 문맥 검색/Qdrant 색인, F-08 담당자 라우팅 상세 문서를 추가했다.
- F-10 처리 작업/실패 관리, F-11 LLMOps 관찰/평가, F-12 알림/업무 현황 상세 문서를 추가했다.
- `docs/features/README.md`의 각 기능 항목에 상세 문서 링크를 연결했다.

## 검증

- `git diff --check`를 통과했다.
- 문서 변경만 수행했기 때문에 애플리케이션 실행 테스트는 수행하지 않았다.

## 남은 리스크

- 상세 문서들이 Open Questions로 남긴 correction/evaluation 저장소, categories code 체계, review 상태 저장 단위, LLMOps 도구 최종 선택은 후속 결정 문서 또는 스키마 변경으로 확정해야 한다.

# 2026-07-29 - F-09 사람 검토 및 사용자 수정 기능 문서 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Features documentation, Human review, User corrections, Evaluation candidates |
| 관련 파일 | `docs/features/README.md`, `docs/features/human-review-corrections.md` |

## 요청 또는 배경

- 사용자가 F-04에 이어 features 문서 작성을 계속 진행해 달라고 요청했다.
- Codex는 우선 구현 순서에 따라 F-09 사람 검토 및 사용자 수정 상세 문서를 작성했다.

## 확인한 사실

- 현재 코드에는 사용자 수정 저장 API와 수정 form UI가 아직 없다.
- SC-06은 최초 AI 결과와 사용자 수정 결과를 분리 저장하고, 수정 사례를 평가 데이터 후보로 등록하는 흐름을 요구한다.
- 기존 PostgreSQL 스키마로 업무 레이블 수정은 `email_category_assignments`, 담당자 변경은 `routing_events`, 감사 기록은 `audit_logs`에 남길 수 있다.
- 요약, 긴급도, 핵심 정보의 사용자 확정값과 평가 승인 상태는 현재 스키마에 전용 테이블이 없어 후속 설계가 필요하다.

## 해결 방법

- `docs/features/human-review-corrections.md`를 추가해 F-09의 목적, 입력, 출력, review 상태, 정상 흐름, 예외 흐름, 사람 검토 조건, API 계약, 저장 위치, 테스트 기준, LLMOps 관찰 항목을 정리했다.
- 현재 미구현 상태와 운영 목표 API를 분리해 기록했다.
- AI 결과를 덮어쓰지 않고 사용자 확정값을 별도 source 또는 이력으로 저장하는 원칙을 문서화했다.
- `docs/features/README.md`의 F-09 항목에 상세 문서 링크를 추가했다.

## 검증

- `git diff --check`를 통과했다.
- 문서 변경만 수행했기 때문에 애플리케이션 실행 테스트는 수행하지 않았다.

## 남은 리스크

- 사용자 확정 요약·긴급도·핵심 정보 저장 방식, review 상태의 저장 단위, 평가 데이터셋 관리 위치는 운영 준비 전 추가 스키마 결정이 필요하다.

# 2026-07-29 - F-04 업무 분류 기능 문서 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Features documentation, Email classification, D3 AI analysis demo |
| 관련 파일 | `docs/features/README.md`, `docs/features/email-classification.md` |

## 요청 또는 배경

- 사용자가 F-03에 이어 features 문서 작성을 계속 진행해 달라고 요청했다.
- Codex는 우선 구현 순서에 따라 F-04 업무 분류 상세 문서를 작성했다.

## 확인한 사실

- 현재 데모 fixture에는 `quotation_received`, `purchase_delivery_followup`, `specification_check`, `specification_recheck` 같은 세부 subtype이 있고, UI는 이를 `문의`, `발주`, `기술` 정규 업무 레이블로 매핑한다.
- Gmail mode는 영구 분석 파이프라인 연결 전까지 `미분류`, `미할당`을 표시한다.
- 분류 재생성 endpoint인 `POST /ui/emails/{email_index}/classification/regenerate`와 bulk endpoint는 현재 demo noop 또는 상태 fragment 반환 수준이다.
- PostgreSQL 스키마는 분류 레이블 정의를 `categories`, 현재 분류와 이력을 `email_category_assignments`에 저장하도록 정의되어 있다.

## 해결 방법

- `docs/features/email-classification.md`를 추가해 F-04의 정규 업무 레이블, 입력, 출력, 상태, 정상 흐름, 예외 흐름, 사람 검토 조건, API 계약, 저장 위치, 테스트 기준, LLMOps 관찰 항목을 정리했다.
- `발주`, `문의`, `서비스`, `기술`, `기타`, `미분류`를 초기 정규 업무 레이블로 문서화했다.
- 현재 데모/Gmail 계약과 운영 목표 PostgreSQL 기반 계약을 분리했다.
- `docs/features/README.md`의 F-04 항목에 상세 문서 링크를 추가했다.

## 검증

- `git diff --check`를 통과했다.
- 문서 변경만 수행했기 때문에 애플리케이션 실행 테스트는 수행하지 않았다.

## 남은 리스크

- `categories.code`의 최종 코드 체계, 분류 근거와 후보 점수의 저장 위치, 긴급도 판단을 분류와 함께 처리할지 별도 priority 분석으로 분리할지는 후속 논의가 필요하다.

# 2026-07-29 - F-03 이메일 요약 기능 문서 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Features documentation, Email summary, D3 AI analysis demo |
| 관련 파일 | `docs/features/README.md`, `docs/features/email-summary.md` |

## 요청 또는 배경

- 사용자가 F-02에 이어 다음 features 문서 작성을 계속 진행해 달라고 요청했다.
- Codex는 우선 구현 순서에 따라 F-03 이메일 요약 상세 문서를 작성하기로 했다.

## 확인한 사실

- 현재 데모 화면은 `DemoMailService._summary_sections()`가 만든 `executive_summary_sections`를 `Summary` 영역에 표시한다.
- Gmail mode는 영구 분석 파이프라인이 연결되기 전까지 빈 summary와 `미분류` 상태를 표시한다.
- `POST /ui/emails/{email_index}/summary/regenerate`와 bulk summary endpoint는 현재 demo noop 또는 상태 fragment 반환 수준이다.
- 운영 목표 저장소는 `email_analysis_results.analysis_type = executive_summary`와 `processing_jobs.job_type = email_analysis`를 기준으로 잡는 것이 PostgreSQL 스키마와 맞다.

## 해결 방법

- `docs/features/email-summary.md`를 추가해 F-03의 목적, 입력, 출력, 상태, 정상 흐름, 예외 흐름, 사람 검토 조건, API 계약, 저장 위치, 테스트 기준, LLMOps 관찰 항목을 정리했다.
- 현재 데모 구현과 운영 목표 구현을 분리해 기록했다.
- `docs/features/README.md`의 F-03 항목에 상세 문서 링크를 추가했다.

## 검증

- `git diff --check`를 통과했다.
- 문서 변경만 수행했기 때문에 애플리케이션 실행 테스트는 수행하지 않았다.

## 남은 리스크

- 요약 section 제목 표준, 사용자 수정 summary 저장 위치, 첨부 분석 완료 후 요약 자동 대체 정책은 후속 문서에서 확정해야 한다.

# 2026-07-29 - F-02 받은편지함 목록 및 상세 기능 문서 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Features documentation, Inbox UI contract, D2 screen demo |
| 관련 파일 | `docs/features/README.md`, `docs/features/inbox-list-detail.md` |

## 요청 또는 배경

- 사용자는 CoRA Mail Agent의 features 문서 파일들을 함께 만들자고 요청했고, Codex가 현재 프로젝트 상황을 파악한 뒤 논의를 리드해 달라고 했다.
- 현재 `docs/features/README.md`에는 F-01~F-12 기능 목록과 우선순위가 있지만, 상세 기능 문서는 Gmail Web Sync Settings 하나만 존재했다.
- Codex는 F-02 받은편지함 목록 및 상세 화면을 먼저 문서화하는 방향을 제안했고, 사용자가 진행을 승인했다.

## 확인한 사실

- Inbox 화면은 현재 `GET /ui/inbox`, `GET /ui/mail-rows`, `GET /ui/emails/{email_index}` HTML fragment 계약으로 동작한다.
- JSON 조회는 `GET /api/emails`, `GET /api/emails/{email_index}`가 제공된다.
- 데모 모드는 fixture 기대값을 사용해 분류 완료 상태를 표시하고, Gmail mode는 영구 분석 파이프라인 연결 전까지 `미분류`, `미할당` 상태를 표시한다.
- 운영 목표 저장 위치는 PostgreSQL 스키마의 `email_messages`, `email_recipients`, `email_attachments`, `email_analysis_results`, `email_category_assignments`, `routing_assignments`, `processing_jobs`, `audit_logs`와 연결된다.

## 해결 방법

- `docs/features/inbox-list-detail.md`를 추가해 F-02의 목적, 사용자, 관련 시나리오, 입력·출력, 상태, 정상 흐름, 예외 흐름, 사람 검토 조건, API 계약, 저장 위치, 테스트 기준, LLMOps 관찰 항목을 정리했다.
- 현재 데모/Gmail UI 계약과 운영 목표 PostgreSQL 기반 계약을 분리해 기록했다.
- `docs/features/README.md`의 F-02 항목에 상세 문서 링크를 추가했다.

## 검증

- `git diff --check`를 통과했다.
- 문서 변경만 수행했기 때문에 애플리케이션 실행 테스트는 수행하지 않았다.

## 남은 리스크

- 운영 UI의 기본 정렬 기준, 영구 상세 조회 식별자 전환 방식, 사람 검토 필요 상태의 저장 방식은 후속 기능 문서에서 확정해야 한다.

# 2026-07-28 - 설정탭 라우팅 카테고리 목록 복구

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Settings UI, assignee routing categories |
| 관련 파일 | `app/server.py` |

## 요청 또는 배경

- 사용자는 설정탭 복구를 위해 담당자 우선순위 배정에 `발주`, `문의`만 보이는 문제와 담당자 관리의 담당 카테고리에 일부 카테고리만 보이는 문제를 고쳐 달라고 요청했다.
- 원래처럼 전체 업무 카테고리를 선택/배정 대상으로 보여야 한다.

## 확인한 사실

- 설정 화면의 `routing_summary.html`과 `routing_table.html`은 모두 `settings_context()`가 내려주는 카테고리 목록을 사용한다.
- 기존 구현은 현재 표시 모드의 메일 데이터에서 `mail_service().category_order()`를 계산해 설정 카테고리로 사용했다.
- 이 방식은 현재 로드된 메일에 없는 `서비스`, `기타` 같은 업무 카테고리가 설정탭에서 사라지는 원인이 된다.

## 해결 방법

- `BUSINESS_CATEGORY_ORDER = ["발주", "문의", "서비스", "기술", "기타", "미분류"]` 상수를 추가했다.
- 설정탭은 메일 데이터 분포와 무관하게 이 전체 업무 카테고리 목록을 사용하도록 `settings_context()`를 수정했다.
- 담당자 우선순위 배정은 기존 템플릿 규칙대로 `미분류`를 제외한 `발주`, `문의`, `서비스`, `기술`, `기타`를 렌더링하고, 담당자 관리 select는 `미분류`까지 포함한 전체 목록을 제공한다.

## 검증

- `python -m py_compile app/server.py`를 통과했다.
- `settings_context()`가 `category_order`, `routing_table_options.mail_categories`, `route_assignments`에 `["발주", "문의", "서비스", "기술", "기타", "미분류"]`를 내려주는 것을 확인했다.
- Jinja 렌더링으로 `routing_summary.html`에 `발주`, `문의`, `서비스`, `기술`, `기타`가 포함되고, `routing_table.html` select option에 `발주`, `문의`, `서비스`, `기술`, `기타`, `미분류`가 포함되는 것을 확인했다.

## 남은 리스크

- 실제 브라우저 시각 검증은 수행하지 않았다.

# 2026-07-28 - 데모 사양확인 메일 FWD 제목 정정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo data, D1 sample data, specification check fixture |
| 관련 파일 | `data/demo/specification_checks.fixture.json` |

## 요청 또는 배경

- 사용자는 데모 데이터 중 실제 전달된 메일이 아닌데 제목에 `FWD`가 붙어 있는 메일의 제목 정정을 요청했다.

## 확인한 사실

- `data/demo/specification_checks.fixture.json`에 `FWD:` 제목 prefix가 붙은 메일 2건이 있었다.
- 두 메일은 `demo-spec-check-nyk-rumina-002`, `demo-spec-check-nyk-rumina-003`이며, fixture에는 전달 체인 메타데이터가 없는 일반 사양확인 요청/재요청 메일로 저장되어 있었다.
- `subject_normalized`는 이미 prefix 없는 제목으로 저장되어 있었다.

## 해결 방법

- 두 메일의 raw `subject`에서 `FWD:` prefix만 제거했다.
- `subject_normalized`, 본문, 첨부파일, 기대 라벨은 변경하지 않았다.

## 검증

- `python -m json.tool data/demo/specification_checks.fixture.json`를 통과했다.
- `rg -n "FWD|Fwd|FW:|Fw:" data/demo docs app` 결과가 없음을 확인했다.
- `uv run python -m app.tools.export_demo_seed --check`를 통과했고 row count가 기존과 같은 `email_messages=9`, `email_attachments=6`임을 확인했다.

## 남은 리스크

- 없음.

# 2026-07-28 - 데모 fixture PostgreSQL seed bundle 경로 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo data, PostgreSQL seed, D1/D2 completion, D3 preparation |
| 관련 파일 | `app/services/demo_seed_service.py`, `app/tools/export_demo_seed.py`, `docs/development/demo-ui-porting-plan.md` |

## 요청 또는 배경

- 사용자는 8010 임시 서버 종료를 요청했고, 8011에 이미 앱이 떠 있다고 알렸다.
- 사용자는 현재까지 만든 데모 데이터 생성은 일단 마무리하고 다음 단계를 진행하고 싶다고 했다.
- 사용자는 앞서 제안한 데모 UI 동작 확인을 모두 마쳤다고 확인했다.

## 확인한 사실

- 8010에서 실행 중이던 임시 `uvicorn` 세션을 정상 종료했다.
- 현재 데모 fixture는 3개이며 메일 9건, 첨부 6건을 로딩한다.
- 문서상 D3는 AI 분석 데모지만, `demo-ui-porting-plan.md`는 fixture UI 수락 후 PostgreSQL seed/import path를 다음 통합 단계로 기록하고 있다.
- D3 AI 분석 결과를 저장하려면 먼저 fixture를 PostgreSQL 테이블 구조로 변환하는 경로가 필요하다.

## 수락한 내용

- 지금은 추가 synthetic fixture를 만들지 않고, 현재 9건 fixture를 기준으로 D1 데모 데이터 생성을 일단 마무리한다.
- 다음 작업은 live DB 연결 전 단계로, fixture를 PostgreSQL 적재용 row bundle로 deterministic하게 변환하는 seed 경로를 추가한다.

## 해결 방법

- `DemoSeedService`를 추가해 `data/demo/*.fixture.json`을 `email_accounts`, `email_messages`, `email_recipients`, `email_attachments`, `processing_jobs` row bundle로 변환하게 했다.
- 메시지 `content_hash`와 분석 작업 `processing_jobs.id`는 안정적으로 재생성되도록 deterministic하게 계산한다.
- `app.tools.export_demo_seed` CLI를 추가해 `--check` 검증과 JSON export를 지원한다.
- `docs/development/demo-ui-porting-plan.md`에 seed bundle 명령과 현재 row count를 기록했다.

## 검증

- `python -m py_compile app/services/demo_seed_service.py app/tools/export_demo_seed.py`를 통과했다.
- `uv run python -m app.tools.export_demo_seed --check`를 통과했고 `email_accounts=1`, `email_messages=9`, `email_recipients=14`, `email_attachments=6`, `processing_jobs=9`를 확인했다.

## 남은 리스크

- 아직 PostgreSQL 드라이버와 실제 INSERT writer는 없다. 다음 구현에서 `psycopg` 또는 SQLAlchemy/Alembic 도입 여부를 결정해야 한다.
- 현재 seed bundle은 D3 분석 작업을 위한 `processing_jobs`만 만들며, AI 결과 테이블과 category assignment는 아직 생성하지 않는다.

## 후속 작업

- PostgreSQL schema migration 또는 초기 DDL 구현 방식을 결정한다.
- seed bundle을 실제 PostgreSQL 트랜잭션으로 insert하는 writer를 추가한다.
- 이후 D3에서 `email_analysis_results`와 `email_category_assignments`를 생성하는 AI 분석 흐름을 연결한다.

# 2026-07-28 - 서비스/긴급 클레임/기타 합성 데모 데이터 추가 취소

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo data, D1 sample coverage, revert |
| 관련 파일 | `data/demo/service_requests.fixture.json`, `data/demo/urgent_claims.fixture.json`, `data/demo/other_messages.fixture.json`, `data/demo/README.md`, `docs/development/demo-data-standard.md`, `app/schemas/demo_mail.py`, `app/services/demo_mail_service.py` |

## 요청 또는 배경

- 사용자는 직전에 추가한 서비스, 긴급 클레임, 기타 합성 데모 데이터 변경을 취소해 달라고 요청했다.

## 해결 방법

- 커밋 `d2c7f61`의 변경을 이력 보존을 위해 `git revert --no-commit d2c7f61` 방식으로 되돌렸다.
- 신규 합성 fixture 3개와 해당 fixture를 지원하기 위해 추가했던 schema, label mapping, 문서 변경을 제거했다.
- 취소 요청 자체는 세션 로그에 새 항목으로 남긴다.

## 남은 리스크

- D1 범위에서 서비스, 긴급 클레임, 기타 샘플은 다시 비어 있다.
- 이후 같은 유형을 다시 추가하려면 synthetic data 생성 기준을 재검토한 뒤 별도 커밋으로 진행한다.

# 2026-07-28 - BK OCEAN 납기 문의와 부분 발송 요청 데모 데이터 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo data, D1 sample coverage, purchase follow-up thread |
| 관련 파일 | `data/demo/purchase_followups.fixture.json`, `data/demo/README.md`, `docs/development/demo-data-standard.md` |

## 요청 또는 배경

- 사용자는 BK OCEAN의 발주 접수 완료 건 `BK2502044Q`와 관련된 수신 메일 2건도 데모 데이터로 추가해 달라고 요청했다.
- 첫 메일은 예상 납기 재문의이고, 둘째 메일은 FLAME DETECTOR item 15를 제외한 나머지 품목의 선입고와 item 15의 후속 입고를 요청하는 내용이다.

## 확인한 사실

- 두 메일은 같은 `provider_thread_id`로 묶을 수 있는 no-attachment purchase follow-up thread다.
- 둘째 메일 본문에는 플루맥스가 2025-02-20 10:09에 예상 납품일을 2025-02-28로 회신했다는 인용 문맥이 포함되어 있다.
- 부분 발송 요청은 일반 납기 문의보다 후속 업무 영향이 크므로 expected priority를 `high`로 두는 것이 적절하다.

## 수락한 내용

- 두 메일을 기존 `purchase_followups.fixture.json`에 추가했다.
- `BK2502044Q`를 business reference로 기록하고, counterparty는 `BK OCEAN`으로 기록했다.
- 첫 메일은 예상 납기 회신 요청, 둘째 메일은 부분 입고 가능 여부와 item 15 후속 입고 일정 확인 요청으로 key fields를 분리했다.
- 둘째 메일은 `follow_up_of`로 첫 메일을 참조하도록 했다.

## 검증

- `python -m json.tool data/demo/purchase_followups.fixture.json`를 통과했다.
- `python -m py_compile app/services/demo_mail_service.py app/repositories/demo_mail_repository.py app/schemas/demo_mail.py`를 통과했다.
- `uv run python -c ...`로 demo service fixture 로딩을 확인했고, 총 9건 중 BK OCEAN 두 메일이 모두 `발주`로 표시되는 것을 확인했다.

## 남은 리스크

- 발주서 첨부가 있는 원 발주 메일 자체는 아직 fixture에 없다.
- 부분 발송 요청의 상태 전이와 담당자 작업 큐 반영은 D3/D4 이후 구현 범위다.

# 2026-07-28 - KOPA 납기 확인 발주 follow-up 데모 데이터 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo data, D1 sample coverage, no-attachment purchase follow-up |
| 관련 파일 | `data/demo/purchase_followups.fixture.json`, `data/demo/README.md`, `docs/development/demo-data-standard.md`, `app/services/demo_mail_service.py` |

## 요청 또는 배경

- 사용자는 D1 데모 데이터 범위를 채우는 작업 중이며, KOPA Marine Services의 납기 확인 메일을 데모 데이터로 추가해 달라고 요청했다.
- 메일은 `RE: 납기 확인 : [FLUEMAX] 발주 접수 완료(KOPA24103773)` 제목으로, 발주 접수 완료 건의 물품 준비 상태와 납품 가능 일정을 확인해 달라는 내용이다.

## 확인한 사실

- 기존 fixture는 견적 수신과 기술 사양 확인/재확인 중심이었다.
- 이번 메일은 첨부가 없는 업무 메일이며, D1에서 부족했던 `발주` 계열과 no-attachment 샘플을 보강한다.
- 기존 demo repository는 `data/demo/*.fixture.json`을 자동 순회하므로 새 fixture 파일을 추가하면 서비스 로딩 대상에 포함된다.

## 수락한 내용

- 새 메일은 `data/demo/purchase_followups.fixture.json`에 별도 fixture로 저장했다.
- 원본 메일 필드와 기대 데모 라벨을 분리하고, AI 생성 결과는 fixture에 넣지 않았다.
- `purchase_delivery_followup` subtype은 UI 정규 업무 레이블 `발주`로 표시되도록 mapping했다.
- 문서 유형은 `delivery_followup`으로 두고 UI 표시 label은 `납기 확인`으로 추가했다.
- business reference는 `KOPA24103773`, counterparty는 `KOPA Marine Services`, assignee area는 `sales`로 기록했다.

## 검증

- `python -m json.tool data/demo/purchase_followups.fixture.json`를 통과했다.
- `python -m py_compile app/services/demo_mail_service.py app/repositories/demo_mail_repository.py app/schemas/demo_mail.py`를 통과했다.
- `uv run python -c ...`로 demo service fixture 로딩을 확인했고, 총 7건 중 새 KOPA 메일이 `발주`로 표시되는 것을 확인했다.

## 남은 리스크

- 실제 발주서 첨부가 있는 PO 메일, 발주 변경/취소, 서비스 요청, 클레임, 기타 메일 샘플은 아직 별도 fixture가 필요하다.

# 2026-07-28 - Inbox Queue sender/subject 컬럼 폭 조정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo UI, Inbox Queue table layout |
| 관련 파일 | `app/static/app.css` |

## 요청 또는 배경

- 사용자는 Inbox Queue에서 sender 영역을 현재의 반 정도로 줄이고, 줄어든 만큼 subject 컬럼 너비로 배정해 달라고 요청했다.

## 확인한 사실

- Inbox Queue 테이블은 `app/templates/views/inbox.html`의 colgroup과 `app/static/app.css`의 `.inbox-*-col` 규칙으로 폭을 제어한다.
- 기존 CSS 하단에는 Inbox 전용 override가 있어 `.inbox-sender-col` 168px, `.inbox-subject-col` 38%가 최종 데스크톱 폭으로 적용되고 있었다.

## 해결 방법

- `.inbox-sender-col`을 168px에서 84px로 줄였다.
- `.inbox-subject-col`은 `calc(38% + 84px)`로 조정해 sender에서 줄인 폭을 subject 영역이 가져가도록 했다.
- 앞쪽 기본 규칙과 모바일 media query의 sender 폭도 같은 절반 기준으로 맞췄다.

## 검증

- `python -m py_compile app/server.py`를 통과했다.
- `.venv/bin/python -c "from app.server import app, templates; templates.get_template('views/inbox.html'); templates.get_template('partials/mail_rows.html'); print('ok')"`를 통과했다.
- `/ui/inbox` `TestClient` 검증은 현재 가상환경의 `starlette.testclient`가 `httpx2` 설치를 요구해 실행하지 못했다.

## 남은 리스크

- 실제 브라우저 시각 검증은 수행하지 않았다. CSS 컬럼 폭만 변경했으므로 동작 로직 영향은 없다.

# 2026-07-28 - Gmail 팝업 token 직접 등록 흐름

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gmail account modal, user-level token setup, bidirectional sync preparation |
| 관련 파일 | `app/repositories/gmail_account_repository.py`, `app/server.py`, `app/templates/partials/gmail_sync_settings.html`, `app/static/app.css`, `docs/features/gmail-web-sync-settings.md` |

## 요청 또는 배경

- 사용자는 Gmail 동기화 설정을 백엔드 환경변수 준비가 아니라 사용자 단계에서 팝업 화면 안에서 처리하고 싶다고 정정했다.
- 보유한 값은 `GOOGLE_TOKEN_JSON`과 `GOOGLE_SEND_TOKEN_JSON`이며, 이 값을 팝업에서 등록해 Gmail 모드 동기화에 쓰는 구성을 요구했다.

## 확인한 사실

- 이전 구현은 env token을 연결 상태로 인식할 수는 있었지만, 사용자가 웹 팝업에서 token JSON을 직접 등록하는 입력 경로가 없었다.
- Gmail 읽기 전용 scope로는 삭제 등 양방향 동기화 준비가 부족하므로 primary token은 `https://mail.google.com/` scope를 포함한 token을 기대해야 한다.

## 수락한 내용

- Gmail 계정 팝업의 기본 흐름을 `GOOGLE_TOKEN_JSON`과 선택 `GOOGLE_SEND_TOKEN_JSON` 등록으로 바꿨다.
- Google OAuth client 설정과 권한 요청은 새 token을 만들어야 할 때 쓰는 고급/보조 흐름으로 낮췄다.
- 팝업에서 저장한 token은 `data/runtime/gmail_token.json`, `data/runtime/gmail_send_token.json`에 저장하고, UI에는 token 내용 대신 연결 상태와 scope만 표시한다.
- demo mode에서는 기존처럼 Gmail 계정 팝업 오프너와 팝업이 렌더링되지 않는다.

## 해결 방법

- `POST /ui/settings/gmail/tokens`를 추가해 팝업 form에서 token JSON을 저장하고 JSON 오류를 부분 화면에 표시하게 했다.
- `GmailAccountRepository`가 env token과 runtime token을 모두 읽고, runtime token은 연결 해제 시 제거하도록 확장했다.
- Gmail 설정 partial에 token 등록 form을 추가하고, 저장된 runtime token과 `GOOGLE_SEND_TOKEN_JSON` 존재 여부를 상태 영역에 표시했다.
- 문서의 정상 흐름, API contract, storage, test criteria를 팝업 token 등록 중심으로 갱신했다.

## 검증

- `uv run python -m py_compile app/server.py app/repositories/gmail_account_repository.py app/services/gmail_oauth_service.py app/services/gmail_mail_service.py app/integrations/gmail/sync_client.py`를 통과했다.
- 임시 repository 테스트에서 fake primary/send token 저장 후 `connected=True`, `token_source=runtime`, `has_send_token=True`, scope `https://mail.google.com/`가 반영되고, disconnect 후 연결이 해제되는 것을 확인했다.
- 임시 `uvicorn` 서버에서 `/ui/settings/gmail-sync`가 `보유 token 등록`, `GOOGLE_TOKEN_JSON`, `GOOGLE_SEND_TOKEN_JSON`, `새 Google 권한 요청으로 token 만들기`를 렌더링하는 것을 확인했다.
- 같은 서버에서 `/ui/settings/gmail/tokens`에 fake token JSON을 POST한 뒤 `Gmail 권한 승인됨`, `user@example.com`, `팝업 저장 token 사용 중`, `GOOGLE_SEND_TOKEN_JSON 있음`, `https://mail.google.com/`가 표시되는 것을 확인했다.

## 남은 리스크

- 현재 runtime token 파일은 Git에서 제외되는 로컬 파일이지만 평문 token이다. 운영 배포에서는 문서화된 credentials reference 또는 secrets store로 교체해야 한다.
- 사용자가 등록한 token JSON에 이메일 필드가 없으면 Gmail profile 조회 전까지 상단 계정 표시는 미확인으로 남을 수 있다.

# 2026-07-28 - GOOGLE_TOKEN_JSON 기반 Gmail 연결 상태 인식

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gmail token env compatibility, Gmail account modal, coramail_ai parity |
| 관련 파일 | `app/repositories/gmail_account_repository.py`, `app/templates/partials/gmail_sync_settings.html`, `docs/features/gmail-web-sync-settings.md` |

## 요청 또는 배경

- 사용자는 보유한 값이 `GOOGLE_TOKEN_JSON`과 `GOOGLE_SEND_TOKEN_JSON`이며, 이것만으로 `coramail_ai`에서 Gmail 동기화가 잘 되었을 것이라고 설명했다.

## 확인한 사실

- `coramail_ai`의 Gmail fetch path는 `GOOGLE_TOKEN_JSON`을 우선 읽고, 발송 path는 `GOOGLE_SEND_TOKEN_JSON`을 별도로 읽는다.
- `coramail_agent`의 Gmail API 호출 자체는 `GOOGLE_TOKEN_JSON`을 사용할 수 있었지만, 웹 UI의 연결 상태 판단은 runtime token file만 보고 있었다.
- 따라서 기존 token env만 가진 정상 운영 케이스가 UI에서는 미연결처럼 보이고, OAuth client 설정을 요구하는 흐름으로 안내됐다.

## 수락한 내용

- `GmailAccountRepository`가 `GOOGLE_TOKEN_JSON`을 primary Gmail token으로 인식하도록 했다.
- `GOOGLE_SEND_TOKEN_JSON` 존재 여부도 UI 상태에 표시하도록 했다.
- token JSON에 `account`, `email`, `email_address` 중 하나가 있으면 상단 Gmail 계정 표시와 모달 연결 계정에 사용하도록 했다.
- env token으로 연결된 경우 웹에서 token을 삭제할 수 없으므로 연결 해제 버튼은 비활성화한다.

## 해결 방법

- `/tmp` env 파일에 fake `GOOGLE_TOKEN_JSON`과 `GOOGLE_SEND_TOKEN_JSON`을 넣어 앱을 import했을 때 `connected=True`, `token_source=env`, `has_send_token=True`, scope `https://mail.google.com/`가 public status에 반영되는 것을 확인했다.
- 임시 `uvicorn` 서버에서 `/ui/settings/gmail-sync` 응답에 `Gmail 권한 승인됨`, `mailbox@example.com`, `GOOGLE_TOKEN_JSON 사용 중`, `GOOGLE_SEND_TOKEN_JSON 있음`, `https://mail.google.com/`이 렌더링되는 것을 확인했다.
- 같은 환경에서 `/` 응답의 상단 Gmail 계정 배너가 `mailbox@example.com`을 표시하는 것을 확인했다.

## 남은 리스크

- 사용자의 실제 token JSON에 계정 이메일 필드가 없으면 Gmail API profile 조회 전까지 상단 배너는 이메일을 표시하지 못할 수 있다. 동기화 실행 후에는 Gmail profile 결과를 표시한다.

# 2026-07-28 - Google 권한 요청 버튼 무반응 원인 수정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gmail OAuth, dotenv loading, permission request button UX |
| 관련 파일 | `app/server.py`, `app/templates/partials/gmail_sync_settings.html`, `app/templates/shell.html` |

## 요청 또는 배경

- 사용자는 `Google 권한 요청` 버튼을 클릭해도 아무 반응이 없다고 보고했고, 근본 원인 파악 후 해결을 요청했다.

## 확인한 사실

- `coramail_ai`는 앱 시작 시 `CORAMAIL_ENV_FILE` 또는 프로젝트 `.env`를 직접 읽어서 `GOOGLE_CREDENTIALS_JSON`을 환경변수로 올린다.
- `coramail_agent`는 `.env`를 로드하지 않아, 기존 방식대로 `.env`에 OAuth client JSON이 있어도 웹 앱 런타임에서는 client 설정이 없는 것으로 판단했다.
- client 설정이 없을 때 `Google 권한 요청` 버튼은 disabled로 렌더링되어 클릭해도 아무 반응이 없었다.
- 직접 `/ui/settings/gmail/connect`를 호출해도 오류가 `X-CoRA-Gmail-Connect-Error` 헤더와 `/ui/settings` redirect로만 전달되어 사용자가 모달 안에서 원인을 보기 어려웠다.

## 해결 방법

- `app/server.py`에 `coramail_ai`와 같은 방식의 `.env` 로더를 추가하고 앱 초기화 전에 실행되게 했다.
- 이제 `CORAMAIL_ENV_FILE` 또는 프로젝트 `.env`에 있는 `GOOGLE_CREDENTIALS_JSON`이 `GmailAccountRepository` 초기화 전에 환경변수로 반영된다.
- client 설정이 없는 경우에도 권한 요청 버튼을 disabled로 두지 않고, 클릭하면 `OAuth client 설정` 고급 영역을 열고 입력란으로 focus가 이동하게 했다.
- `/tmp` env 파일에 가짜 `GOOGLE_CREDENTIALS_JSON`을 넣어 앱을 시작했을 때 `/ui/settings/gmail/connect`가 Google OAuth URL로 303 redirect되고, `location`에 `https://mail.google.com/`, `prompt=consent`, OAuth state cookie가 포함되는 것을 확인했다.
- OAuth 설정이 없는 상태에서는 버튼이 `data-gmail-open-advanced`를 가진 안내 버튼으로 렌더링되는 것을 확인했다.

## 남은 리스크

- 실제 Google 권한 승인 성공은 유효한 client id/secret과 Google Cloud Console에 등록된 redirect URI가 필요하다.

# 2026-07-28 - Gmail 권한 요청 scope와 client 설정 경로 정정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gmail OAuth scope, Google permission request, bidirectional sync preparation |
| 관련 파일 | `app/repositories/gmail_account_repository.py`, `app/services/gmail_oauth_service.py`, `app/templates/partials/gmail_sync_settings.html`, `docs/features/gmail-web-sync-settings.md` |

## 요청 또는 배경

- 사용자는 Google 로그인 버튼이 동작하지 않는다고 보고했다.
- Gmail 읽기 전용 권한만으로는 양방향 동기화와 삭제 반영이 불가능하므로 삭제도 적용 가능한 권한이 필요하다고 지적했다.
- `coramail_ai`에서 이미 의도한 방식의 양방향 동기화와 Google 권한 요청 설정을 구현해 두었으므로 이를 참고하라고 요청했다.

## 확인한 사실

- `coramail_ai/pipeline/gmail_postgres_fetcher.py`는 modify/delete 목적에 `https://mail.google.com/` full access scope를 사용한다.
- `coramail_ai/legacy/tools/refresh_gmail_token.py`는 modify mode에서 `GMAIL_PRIMARY_SCOPES`를 사용하고, client 설정은 `GOOGLE_CREDENTIALS_JSON`에서 읽는다.
- 현재 `coramail_agent`의 웹 OAuth service는 `gmail.readonly`를 요청하고 있었고, client 설정도 저장 파일 또는 `CORAMAIL_GMAIL_CREDENTIALS_PATH`만 인식했다.

## 수락한 내용

- 웹 OAuth 권한 요청 scope를 `gmail.readonly`에서 `https://mail.google.com/`로 변경했다.
- `GOOGLE_CREDENTIALS_JSON` 환경변수를 OAuth client 설정으로 인식하도록 추가했다.
- 권한 요청 버튼 문구를 `Google로 로그인`에서 `Google 권한 요청`으로 변경했다.
- 권한 설명을 Gmail 전체 접근과 삭제/상태 변경 반영 기준으로 수정했다.

## 해결 방법

- `GOOGLE_CREDENTIALS_JSON`만 설정한 `/tmp` 런타임 검증에서 authorization URL 생성이 성공하고 URL에 `mail.google.com` scope와 `prompt=consent`가 포함되는 것을 확인했다.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m py_compile app/server.py app/repositories/gmail_account_repository.py app/services/gmail_mail_service.py app/services/gmail_oauth_service.py app/integrations/gmail/sync_client.py`가 통과했다.
- 임시 `uvicorn` 서버에서 `/ui/settings/gmail-sync` partial에 `Google 계정 권한 요청`, `Google 권한 요청`, `Gmail 전체 접근`, `https://mail.google.com/`, `삭제 반영` 문구가 렌더링되는 것을 확인했다.

## 남은 리스크

- 실제 Google 권한 승인 성공은 유효한 `GOOGLE_CREDENTIALS_JSON` 또는 OAuth client JSON과 Google Cloud Console redirect URI가 준비된 환경에서 추가 검증해야 한다.

# 2026-07-28 - Gmail 계정 권한 팝업 재구성 및 데모 모드 비활성화

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gmail account modal, OAuth login UI, demo mode behavior |
| 관련 파일 | `app/templates/shell.html`, `app/templates/partials/gmail_sync_settings.html`, `app/static/app.css`, `app/repositories/gmail_account_repository.py`, `docs/features/gmail-web-sync-settings.md` |

## 요청 또는 배경

- 사용자는 기존 계정 동기화 설정 팝업 화면을 전부 밀고 처음부터 다시 구성하라고 요청했다.
- 설정 화면에서 Google 로그인을 했을 때 계정 권한을 가져올 수 있게 하고 싶다고 요청했다.
- 번외 요구로 데모 모드에서는 해당 팝업 화면을 띄우지 않게 하라고 요청했다.

## 수락한 내용

- Gmail 설정 partial을 Google 로그인 중심의 계정 권한 패널로 재구성했다.
- 요청 권한 섹션에 Gmail 읽기 전용 scope와 설명을 명시했다.
- 연결 상태와 권한 scope를 로그인 후 확인할 수 있게 했다.
- OAuth client JSON 입력은 하단 고급 설정으로 낮췄고, client 설정이 없으면 Google 로그인 버튼을 비활성화한다.
- `CORAMAIL_GMAIL_CREDENTIALS_PATH`로 제공한 OAuth client JSON도 Google 로그인에 사용할 수 있게 repository 경로를 보강했다.
- 데모 모드에서는 상단 Gmail 계정 배너가 모달 opener를 렌더링하지 않고, 모달 HTML과 관련 JavaScript도 렌더링하지 않게 했다.

## 해결 방법

- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m py_compile app/server.py app/repositories/gmail_account_repository.py app/services/gmail_mail_service.py app/services/gmail_oauth_service.py app/integrations/gmail/sync_client.py`가 통과했다.
- 임시 `uvicorn` 서버에서 데모 모드 `/` 응답에 `data-gmail-settings-open`과 `gmailSettingsModal`이 렌더링되지 않는 것을 확인했다.
- Gmail 모드 쿠키로 `/`를 호출했을 때 `data-gmail-settings-open`, `gmailSettingsModal`, `Gmail 계정 권한 설정`, `Google로 로그인`, `요청 권한`, `OAuth client 설정`이 렌더링되는 것을 확인했다.
- `/ui/settings/gmail-sync` partial에 `Google 로그인으로 Gmail 연결`, `Google로 로그인`, `Gmail 읽기 전용`, `OAuth client 설정`이 렌더링되는 것을 확인했다.

## 남은 리스크

- 실제 OAuth 로그인 성공은 Google Cloud Console redirect URI와 유효한 client JSON이 준비된 환경에서 추가 검증해야 한다.
- Google OAuth scope 승인을 통한 권한 저장은 구현되어 있지만, 현재 Gmail 수집 결과는 여전히 프로세스 메모리 캐시다.

# 2026-07-28 - Gmail 설정 진입점을 Settings 탭에서 상단 계정 배너 모달로 이동

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gmail settings UI, topbar, modal interaction |
| 관련 파일 | `app/templates/shell.html`, `app/templates/views/settings.html`, `app/static/app.css` |

## 요청 또는 배경

- 사용자는 Settings 탭에 추가한 Gmail 설정 항목을 제거하라고 요청했다.
- 대신 상단의 `Gmail 계정 미확인` 영역을 클릭하면 계정 동기화 설정 팝업이 열리고, 그 안에서 계정 연결을 진행하는 방식으로 바꾸길 원했다.

## 수락한 내용

- Settings 탭에서 Gmail Sync 카드를 제거했다.
- 상단 Gmail 계정 표시 pill을 클릭 가능한 button으로 변경했다.
- 루트 shell에 Gmail 설정 modal dialog를 추가하고 기존 `gmail_sync_settings.html` partial을 모달 본문으로 재사용했다.
- 배경 클릭, 닫기 버튼, Escape 키로 모달을 닫을 수 있게 했다.

## 해결 방법

- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m py_compile app/server.py app/repositories/gmail_account_repository.py app/services/gmail_mail_service.py app/services/gmail_oauth_service.py app/integrations/gmail/sync_client.py`가 통과했다.
- 임시 `uvicorn` 서버에서 `/` 응답에 `data-gmail-settings-open`, `gmailSettingsModal`, `Gmail 계정 동기화 설정`, `gmailSyncSettings`가 포함되는 것을 확인했다.
- `/ui/settings` 응답에는 `담당자 우선순위 배정`과 `담당자 관리`만 남고 `Gmail 계정 연결` 및 `gmailSyncSettings`가 제거된 것을 확인했다.
- `/ui/settings/gmail-sync` partial은 모달 본문용으로 계속 렌더링되는 것을 확인했다.

## 남은 리스크

- 실제 브라우저에서 focus trap까지 강제하지는 않았다. 닫기 버튼, 배경 클릭, Escape 키는 구현되어 있으며 modal role과 focus 이동은 적용했다.

# 2026-07-28 - 웹 Settings 기반 Gmail OAuth 설정 기획 구현

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Gmail OAuth, Settings UI, runtime credential storage, manual sync |
| 관련 파일 | `.gitignore`, `app/server.py`, `app/repositories/gmail_account_repository.py`, `app/services/gmail_oauth_service.py`, `app/services/gmail_mail_service.py`, `app/templates/views/settings.html`, `app/templates/partials/gmail_sync_settings.html`, `app/static/app.css`, `app/integrations/gmail/README.md`, `docs/features/README.md`, `docs/features/gmail-web-sync-settings.md` |

## 요청 또는 배경

- 사용자는 Gmail 동기화를 웹 서비스 내에서 설정할 수 있게 개발 기획을 요청했다.
- 이후 해당 방향으로 일단 개발하고 확인 및 검토 후 되돌릴지 유지할지 결정하겠다고 요청했다.

## 확인한 사실

- 현재 프로젝트에는 PostgreSQL repository/runtime connection이 아직 없으므로, 즉시 사용 가능한 웹 설정 저장소를 PostgreSQL로 구현할 수는 없다.
- OAuth client JSON과 token은 Git에 절대 포함되면 안 되므로 로컬 runtime 경로를 `.gitignore`에 추가해야 했다.
- 기존 Gmail 동기화 서비스는 환경변수 token path만 읽었고, 웹에서 저장한 token을 읽는 경로가 없었다.

## 수락한 내용

- `data/runtime/`를 Git ignore 대상에 추가했다.
- 임시 `GmailAccountRepository`를 추가해 OAuth client JSON, token JSON, 계정 상태, 마지막 동기화 상태를 로컬 runtime 파일에 저장하도록 했다.
- `GmailOAuthService`를 추가해 웹 OAuth authorization URL 생성과 callback token 교환을 분리했다.
- Settings 화면에 Gmail Sync 카드를 추가해 client JSON 저장, Gmail 연결, 수동 동기화, 연결 해제를 수행할 수 있게 했다.
- Gmail 동기화 서비스가 웹에서 저장한 token path를 기본으로 사용하도록 연결했다.
- 기능 문서 `docs/features/gmail-web-sync-settings.md`를 추가하고 F-01 기능 목록에 연결했다.

## 해결 방법

- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m py_compile app/server.py app/repositories/gmail_account_repository.py app/services/gmail_mail_service.py app/services/gmail_oauth_service.py app/integrations/gmail/sync_client.py`가 통과했다.
- 임시 `uvicorn` 서버에서 `/ui/settings` 응답에 `Gmail 계정 연결`, `OAuth 설정 저장`, 기존 `담당자 관리`가 함께 렌더링되는 것을 확인했다.
- `/ui/settings/gmail-sync` partial이 미설정 상태에서 `Not Set`, `Client JSON 미등록`, `수동 동기화`를 렌더링하는 것을 확인했다.
- 잘못된 OAuth client JSON 저장 요청이 `Google OAuth client JSON 형식이 올바르지 않습니다.` 오류를 partial로 반환하는 것을 확인했다.
- `/tmp` runtime 저장소로 client config 저장, connected account 저장, disconnect 상태 전이를 단위 검증했다.

## 남은 리스크

- 실제 Google OAuth 성공과 Gmail API 동기화 성공은 유효한 OAuth client JSON 및 Google callback URL 설정이 있는 환경에서 추가 검증해야 한다.
- 현재 token 저장은 로컬 runtime 파일 기반 임시 구현이며 운영 전 PostgreSQL `email_accounts.credentials_reference` 또는 내부 secrets store로 교체해야 한다.
- Gmail 모드의 메일 저장은 아직 메모리 캐시이며, 재시작 시 수집한 메일 목록은 유지되지 않는다.

# 2026-07-28 - Gmail 모드 화면 전환 및 수동 동기화 연결

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Display mode, Gmail sync, Inbox UI compatibility, dependencies |
| 관련 파일 | `app/server.py`, `app/services/gmail_mail_service.py`, `app/integrations/gmail/sync_client.py`, `app/integrations/gmail/README.md`, `docs/development/demo-ui-porting-plan.md`, `pyproject.toml`, `uv.lock` |

## 요청 또는 배경

- 사용자는 UI 이식 후 데모 모드와 Gmail 모드가 모두 동작하길 원했다.
- `/ui/display-mode/toggle`이 `204 No Content`만 반환하고 화면이 바뀌지 않아 Gmail 모드 전환이 되지 않는다고 보고했다.
- Gmail 모드에서 지메일함 동기화가 가능한 화면을 이식해 달라고 요청했다.

## 확인한 사실

- 기존 `ui_display_mode_toggle`은 204 응답만 반환하고 쿠키 변경이나 HTMX refresh 신호를 보내지 않았다.
- `CORAMAIL_DEMO_MODE=false`일 때 루트 화면은 Gmail 모드 UI 대신 503을 반환했다.
- `app/integrations/gmail/`에는 OAuth credential 로딩과 MIME parsing 일부가 있었지만 UI 런타임에는 연결되어 있지 않았다.
- Gmail 의존성은 optional dependency였기 때문에 기본 `uv run` 환경에서 수동 동기화가 `Install the gmail optional dependencies`로 실패했다.

## 수락한 내용

- display mode를 `coramail_display_mode` 쿠키 기반으로 전환하고, 토글 응답에 `HX-Refresh: true`를 추가했다.
- PostgreSQL 저장소가 준비되기 전까지 사용할 임시 `GmailMailboxService`를 추가해 Gmail INBOX 목록을 메모리 캐시에 담고 기존 Jinja UI row/detail dict로 매핑했다.
- `/ui/auto-sync/run`은 Gmail 모드에서 Gmail API 동기화를 실행하고 성공 시 화면 refresh, 실패 시 HTMX 이벤트 메시지를 반환하도록 연결했다.
- Gmail API 패키지를 기본 의존성으로 이동해 Gmail 모드가 기본 실행 환경에서 import 가능하도록 했다.

## 해결 방법

- `uv run python -m py_compile app/server.py app/integrations/gmail/sync_client.py app/services/gmail_mail_service.py`가 통과했다.
- 샌드박스 밖 임시 `uvicorn` 서버에서 `/` 데모 모드가 200으로 렌더링되고 `Demo fixture data`와 `mode-switch-text">Demo`가 포함되는 것을 확인했다.
- `/ui/display-mode/toggle` 응답이 `204`, `HX-Refresh: true`, `Set-Cookie: coramail_display_mode=gmail`을 반환하는 것을 확인했다.
- `coramail_display_mode=gmail` 쿠키로 `/`와 `/ui/inbox`가 200으로 렌더링되고 Gmail 모드 라벨과 Inbox 화면이 표시되는 것을 확인했다.
- Gmail 토큰이 없는 환경에서 `/ui/auto-sync/run`은 `Gmail token is unavailable or invalid.` 이벤트를 반환하고 `/api/auto-sync`에 실패 상태를 기록하는 것을 확인했다.

## 남은 리스크

- 현재 Gmail 모드는 PostgreSQL 저장, 증분 cursor, 첨부 본문 다운로드, LLM 분류, Qdrant 색인을 수행하지 않고 프로세스 메모리에만 최근 INBOX 메시지를 보관한다.
- 실제 Gmail 계정 동기화 성공은 `GOOGLE_TOKEN_JSON` 또는 `CORAMAIL_GMAIL_TOKEN_PATH`를 제공한 환경에서 추가 확인이 필요하다.
- Gmail 모드의 분류와 라우팅 값은 아직 `미분류`와 `미할당` placeholder다.

# 2026-07-28 - Cc 접기/펼치기 동작 및 오른쪽 고정 배치 정정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox detail UI, email header actions, CSS |
| 관련 파일 | `app/templates/partials/email_detail.html`, `app/static/app.css` |

## 요청 또는 배경

- 사용자는 이전 요청의 "마우스 오버했을 때 정보창이 뜨는 것처럼"이라는 표현은 시각적 표시 방식 설명이었고, 실제 원하는 동작은 접기/펼치기 방식이라고 정정했다.
- Cc 위치가 각 메일 제목 길이에 따라 변동되지 않도록 고정하고, 중요 정보가 아니므로 가장 오른쪽 끝 정도의 적절한 위치로 옮기라고 요청했다.

## 확인한 사실

- 직전 구현은 hover/focus 시 팝오버를 표시하도록 해 사용자가 원한 클릭 기반 접기/펼치기 동작과 달랐다.
- Cc 트리거가 발신자 metadata 영역 안에 있어 제목과 발신자 영역의 폭에 영향을 받았다.

## 수락한 내용

- Cc를 발신자 metadata 영역에서 제거하고, 상세 header 오른쪽 액션 영역으로 이동했다.
- Cc는 `<details>/<summary>` 기반으로 클릭하면 열리고 다시 클릭하면 닫히는 접기/펼치기 구조로 변경했다.
- 펼쳐진 Cc 정보는 기존 화면 영역을 밀지 않도록 absolute 팝업 레이어로 유지했다.

## 해결 방법

- `python -m py_compile app/server.py app/services/demo_mail_service.py`가 통과했다.
- `/api/health` 응답이 200이고 데모 메일 6건을 반환하는 것을 확인했다.
- `/ui/emails/3` 응답에서 `detail-action-row` 안에 `details.detail-head-cc`, `summary.detail-head-cc-trigger`, `detail-head-cc-popover`, Cc 주소가 렌더링되는 것을 확인했다.

## 남은 리스크

- 실제 브라우저에서 클릭 시 팝업 위치와 겹침은 추가 시각 검수가 필요하다. HTML 구조와 CSS 상태 전환은 응답 기준으로 확인했다.

# 2026-07-28 - Cc 정보를 hover 팝오버로 표시

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox detail UI, email header metadata, CSS |
| 관련 파일 | `app/templates/partials/email_detail.html`, `app/static/app.css` |

## 요청 또는 배경

- 사용자는 Cc가 중요한 항목은 아니므로 항상 길게 노출하지 말고, Cc 버튼을 누르거나 확인할 때 정보가 펼쳐져 보이는 방식으로 바꾸고 싶다고 요청했다.
- 펼쳐졌을 때 기존 화면 영역이 확장되는 방식이 아니라, 마우스 오버 시 정보창이 뜨는 것 같은 방식으로 구현하라고 요청했다.

## 확인한 사실

- Cc는 `email_detail.html`의 선택 메일 header metadata 안에서 `email.cc` 문자열을 그대로 inline 표시하고 있었다.
- 기존 구조는 Cc 주소가 길어질수록 header metadata 영역의 시각적 비중이 커질 수 있었다.

## 수락한 내용

- Cc 주소 문자열을 기본 노출하지 않고 `Cc` 버튼만 표시하도록 변경했다.
- 버튼 hover와 keyboard focus 시 `role="tooltip"` 팝오버가 absolute layer로 떠서 Cc 수신자 정보를 보여주도록 했다.
- 팝오버는 상세 카드 영역을 확장하지 않으며, 오른쪽 정렬로 카드 오른쪽에서 잘릴 가능성을 줄였다.

## 해결 방법

- `python -m py_compile app/server.py app/services/demo_mail_service.py`가 통과했다.
- 실행 중인 로컬 서버의 `/api/health` 응답이 200이고 데모 메일 6건을 반환하는 것을 확인했다.
- `/ui/emails/3` 응답에서 `detail-head-cc-trigger`, `cc-popover-3`, `role="tooltip"`, Cc 주소가 렌더링되는 것을 확인했다.

## 남은 리스크

- 브라우저 픽셀 단위 hover 위치와 clipping은 실제 화면에서 추가 확인이 필요하다. 현재 환경에서는 HTML 응답과 CSS 구조 기준으로 검증했다.

# 2026-07-27 - 원본 날짜 포맷 및 정규 메일 유형 레이블 복구

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Demo UI, date formatter, mail category labels, inbox table layout |
| 관련 파일 | `app/server.py`, `app/services/demo_mail_service.py`, `app/static/app.css` |

## 요청 또는 배경

- 사용자는 날짜 표시 방식이 바뀌었으므로 `coramail_ai` 방식대로 유지하라고 요청했다.
- Inbox Queue의 제목 칼럼 폭을 좁혀 오른쪽 칼럼 값이 잘리지 않게 하라고 요청했다.
- 문서 어딘가에 메일 유형 레이블을 `문의`, `발주` 등으로 한다고 적어둔 것으로 기억하는데 왜 적용되지 않았는지 원인 파악을 요청했다.

## 확인한 사실

- `coramail_ai/app.py`의 테이블 날짜 포맷은 오늘 메일이면 `오전 9:35`, 과거 메일이면 `2월 21일`처럼 표시한다.
- `coramail_agent/app/server.py`의 이식용 임시 formatter는 `YYYY-MM-DD HH:MM`을 반환하고 있어 원본 UI 표시 방식과 달랐다.
- `README.md`에는 현재 직원들이 메일을 `발주`, `문의`, `서비스`, `기술`, `기타`로 직접 분류한다고 정의되어 있다.
- `docs/development/README.md`에는 데모 샘플 데이터도 `문의`, `발주`, `서비스`, `기술`, `기타` 유형을 최소 1건 이상 준비한다고 정의되어 있다.
- `docs/product/data-reality-gap.md`에는 실제 서비스 목표 데이터의 분류 정보가 `발주`, `문의`, `서비스`, `기술`, `기타`라고 정의되어 있다.
- `coramail_agent/app/services/demo_mail_service.py`는 데모 fixture subtype인 `quotation_received`, `specification_check`, `specification_recheck`를 각각 `견적 수신`, `사양 확인`, `사양 재확인`으로 직접 매핑하고 있었다.
- `coramail_agent/app/server.py`의 demo routing 기본 담당자에도 `견적 수신`, `사양 확인`, `사양 재확인`이 남아 있었다.

## 수락한 내용

- 날짜 formatter를 `coramail_ai` 방식으로 맞춰 table, detail, title 날짜 표시를 복구했다.
- Inbox Queue에서 subject column을 38%로 제한하고 classification, routing, time column 폭을 늘려 오른쪽 값이 잘리지 않게 조정했다.
- 데모 subtype은 `demo_mail_subtype`으로 보존하되, UI에 노출되는 `mail_category`와 `business_label`은 정규 업무 레이블로 매핑했다.
- `quotation_received`는 `문의`, `specification_check`와 `specification_recheck`는 `기술`로 표시되게 했다.
- category chip class도 기존 CSS의 `category-chip--inquiry`, `category-chip--technical` 계열을 사용하도록 맞췄다.
- demo routing 기본 담당자 label도 `문의`, `기술`로 맞췄다.

## 원인

- `coramail_agent` 문서는 정규 업무 레이블을 요구했지만, 이번 데모 fixture 이식 과정에서 `CATEGORY_LABELS`와 demo routing 기본값이 세부 workflow label을 UI label로 직접 노출했다.
- 템플릿은 `email.mail_category`를 우선 사용하므로, 문서 기준 label과 별개로 서비스에서 만든 세부 label이 먼저 표시됐다.

## 해결 방법

- `/ui/mail-rows?view=inbox` 응답에서 category가 `문의`와 `기술`로 렌더링되는 것을 확인했다.
- 같은 응답에서 table time이 `2월 21일`, `1월 30일`, `9월 11일`처럼 원본 방식으로 렌더링되는 것을 확인했다.
- `/ui/emails/4` 응답에서 detail time이 `2025. 1. 30. 오후 3:24`로 렌더링되는 것을 확인했다.
- Settings routing 기본 담당자 label을 `문의`, `기술`로 정리했다.
- `python -m py_compile app/server.py app/services/demo_mail_service.py`가 통과했다.

## 남은 리스크

- 현재 데모 데이터에는 `발주`, `서비스`, `기타` 샘플이 아직 없어 해당 label의 실제 화면 밀도와 필터 UX는 별도 샘플 추가 후 확인해야 한다.

# 2026-07-27 - Inbox Queue 폭/본문 preview/Cc 표시 긴급 수정

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Inbox UI, email detail header, CSS |
| 관련 파일 | `app/templates/partials/mail_rows.html`, `app/templates/partials/email_detail.html`, `app/static/app.css` |

## 요청 또는 배경

- 사용자는 Inbox Queue에 가로 스크롤이 절대 있으면 안 된다고 요청했다.
- Inbox Queue의 메일 제목 밑 부가 설명을 제거하라고 요청했다.
- Cc 표시 UI가 이상하다고 피드백했다.

## 확인한 사실

- `mail_rows.html`의 inbox row는 제목 아래 `body_preview` 또는 `snippet`을 별도 줄로 렌더링하고 있었다.
- `app.css` 뒤쪽의 inbox 전용 override에서 `.inbox-list table`에 `min-width: 1160px`와 `.inbox-table-wrap { overflow: auto; }`가 지정되어 가로 스크롤이 생길 수 있었다.
- Cc는 detail header 아래 별도 meta block으로 표시되어 헤더와 본문 사이 레이아웃이 어색하게 벌어졌다.

## 수락한 내용

- Inbox row에서는 제목과 첨부 아이콘만 보이도록 preview 렌더링을 제거했다.
- Inbox table은 `width: 100%`, `min-width: 0`, `overflow-x: hidden`을 사용하도록 조정하고 고정 컬럼 폭을 줄였다.
- Cc는 별도 block 대신 선택 메일 header의 sender metadata 안에 compact inline metadata로 표시되도록 옮겼다.

## 발생한 오류

- Playwright가 현재 venv에 설치되어 있지 않아 브라우저 기반 scrollWidth 검증은 실행하지 못했다.

## 해결 방법

- `/ui/mail-rows?view=inbox` 응답에서 `inbox-subject-preview` 출력이 사라진 것을 확인했다.
- `/ui/emails/4` 응답에서 `detail-head-cc` 구조와 `plant@hanilss.com` Cc 값이 렌더링되는 것을 확인했다.
- `/api/health`가 200으로 응답하는 것을 확인했다.

## 남은 리스크

- 실제 브라우저 픽셀 기준 검증은 Playwright 미설치로 수행하지 못했으므로, 사용자가 브라우저에서 확인 후 특정 viewport에서 overflow가 보이면 해당 viewport 기준으로 추가 조정한다.

# 2026-07-27 - coramail_ai 템플릿 원본 유지 방식으로 재이식

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Jinja2 templates, CSS, compatibility layer, 데모 UI |
| 관련 파일 | `app/templates/`, `app/static/app.css`, `app/server.py`, `docs/development/demo-ui-porting-plan.md` |

## 요청 또는 배경

- 사용자는 이미 완성된 UI를 가져오면서 고쳐야 할 부분이 너무 많아졌다고 피드백했다.
- 사용자는 최대한 그대로 가져오는 방향으로 다시 이식하라고 요청했다.

## 확인한 사실

- 이전 수정은 원본 class 구조를 일부 반영했지만, 여전히 여러 템플릿을 수정한 상태였다.
- `coramail_ai/templates`는 dashboard, inbox, search, settings, routing partial, bulk regeneration partial까지 포함하는 완성 UI다.
- 원본 UI를 유지하려면 템플릿을 줄이는 대신 `coramail_agent/app/server.py`에서 부족한 context와 no-op endpoint를 제공하는 편이 낫다.

## 수락한 내용

- `coramail_ai/templates` 전체를 `coramail_agent/app/templates`로 그대로 복사했다.
- `coramail_ai/static/app.css`를 `coramail_agent/app/static/app.css`로 그대로 복사했다.
- Dashboard, Inbox, Search, Settings 원본 view가 모두 렌더링되도록 fixture 기반 context를 추가했다.
- 아직 구현되지 않은 재분류, 재요약, 첨부 재분석, 수동 라우팅, settings 저장, auto-sync UI action은 no-op endpoint로 받아 UI가 깨지지 않게 했다.

## 발생한 오류

- 이번 수정 중 새 런타임 오류는 없었다.

## 해결 방법

- `diff -qr /home/ysh/workspace/coramail_ai/templates app/templates`로 템플릿 디렉터리가 원본과 동일함을 확인했다.
- `cmp`로 `static/app.css`가 원본과 동일함을 확인했다.
- `/`, `/ui/dashboard`, `/ui/inbox`, `/ui/mail-rows?view=dashboard`, `/ui/emails/0`, `/ui/search`, `/ui/search-results?q=NYK%20RUMINA`, `/ui/settings`, `/ui/settings/routing-table`, `/api/ui-state`, 첨부파일 endpoint가 200으로 응답하는지 확인했다.

## 남은 리스크

- UI는 원본 그대로지만 서버의 Dashboard/Search/Settings 데이터는 fixture 기반 stub이므로 실제 저장/검색/설정 변경은 아직 동작하지 않는다.
- 원본 JavaScript가 호출하는 endpoint 중 실제 운영 동작은 no-op으로 처리된다.

## 후속 작업

- 사용자가 UI를 브라우저에서 확인한 뒤, stub endpoint 중 실제 구현할 우선순위를 정한다.

# 2026-07-27 - 데모 UI를 coramail_ai templates 기반으로 재이식

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Jinja2 templates, CSS, 데모 UI |
| 관련 파일 | `app/templates/shell.html`, `app/templates/views/inbox.html`, `app/templates/partials/mail_rows.html`, `app/templates/partials/email_detail.html`, `app/templates/macros.html`, `app/static/app.css`, `app/server.py`, `docs/development/demo-ui-porting-plan.md` |

## 요청 또는 배경

- 사용자는 이전 데모 UI가 잘못된 것을 가져온 것 같다고 피드백했다.
- 사용자는 `static`이 아니라 `coramail_ai/templates`에 있는 UI를 기준으로 가져오라고 요청했다.

## 확인한 사실

- 이전 구현은 `coramail_ai/templates`의 class 구조를 충분히 보존하지 않고 새로 축약한 UI에 가까웠다.
- `coramail_ai/templates`는 `static/app.css`와 강하게 맞물려 있으므로 템플릿 구조를 살리려면 해당 CSS도 함께 맞춰야 한다.

## 수락한 내용

- `shell.html`, `views/inbox.html`, `partials/mail_rows.html`, `partials/email_detail.html`를 원본 Jinja 템플릿 class 구조에 맞춰 재구성했다.
- Dashboard/Search/Settings, 삭제, 재분류, 재요약, 첨부 재분석처럼 현재 데모 runtime에 없는 액션은 제거하거나 disabled 상태로 두었다.
- `coramail_ai/static/app.css`를 템플릿용 stylesheet로 차용했다.
- 서버에 원본 템플릿이 기대하는 helper 함수와 context 값을 보강했다.

## 발생한 오류

- 이번 수정 중 새 런타임 오류는 없었다.

## 해결 방법

- `uvicorn`을 재시작하고 `/`, `/ui/mail-rows`, `/ui/emails/0`, 첨부파일 endpoint가 200으로 응답하는지 확인했다.
- 렌더링 결과에서 `app-shell`, `gmail-account-banner`, `inbox-view-tools`, `inbox-table-wrap`, `detail-head-copy`, `executive-summary-list` 등 원본 템플릿 계열 class가 포함되는지 확인했다.

## 남은 리스크

- 전체 `app.css`를 가져왔기 때문에 아직 사용하지 않는 dashboard/search/settings 스타일도 포함되어 있다.
- 브라우저에서 실제 시각 검수 후 불필요한 스타일 정리 여부를 결정해야 한다.

## 후속 작업

- 사용자가 웹에서 확인한 뒤 유지할 UI 영역과 정리할 스타일 범위를 결정한다.

# 2026-07-27 - fixture 기반 데모 UI 1차 이식

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | FastAPI, Jinja2, HTMX, 데모 UI, Gmail sync 격리 |
| 관련 파일 | `pyproject.toml`, `app/server.py`, `app/repositories/demo_mail_repository.py`, `app/services/demo_mail_service.py`, `app/schemas/demo_mail.py`, `app/templates/`, `app/static/`, `app/integrations/gmail/`, `docs/development/demo-ui-porting-plan.md` |

## 요청 또는 배경

- 사용자는 웹 UI는 일단 `coramail_ai`를 차용하고, 데모모드일 때 이번에 생성한 데모데이터가 나오게 하자고 요청했다.
- 사용자는 Gmail sync는 가져와놓는 편이 낫다는 의견을 냈고, 데모 UI가 별로면 프로젝트 코드를 복원 가능하게 진행하라고 요청했다.

## 확인한 사실

- `coramail_ai/app.py`는 Gmail, Qdrant, Ollama, Celery, 인증, UI가 한 파일에 강하게 결합되어 있어 그대로 복사하면 `coramail_agent`의 Service/Repository/Schema 구조와 충돌한다.
- `coramail_agent`는 아직 애플리케이션 코드가 거의 없어 작은 FastAPI 앱을 새로 구성할 수 있다.

## 수락한 내용

- `coramail_ai`의 UI 상호작용 패턴만 차용하고, `coramail_agent`에는 fixture 기반 read-only 데모 UI를 새로 구현한다.
- 데모모드는 `data/demo/*.fixture.json`을 직접 읽어 Inbox 목록, 상세, 첨부 View/Download를 제공한다.
- Gmail sync는 `app/integrations/gmail/` 아래에 격리하고 데모 UI runtime에서는 import하지 않는다.
- Celery, 로그인 인증, Qdrant 검색, LLM 재생성, Gmail 삭제/전달 액션은 초기 runtime에서 제외한다.

## 발생한 오류

- 기본 Python 환경에는 FastAPI가 없어 앱 import 검증이 실패했다.
- FastAPI `TestClient`는 현재 설치된 Starlette가 `httpx2` 테스트 의존성을 요구해 사용할 수 없었다.

## 해결 방법

- `pyproject.toml`을 추가하고 `uv sync`로 로컬 `.venv`를 구성했다.
- `uvicorn` 서버를 실제로 띄운 뒤 `curl`로 `/`, `/ui/mail-rows`, `/ui/emails/0`, `/api/health`, 첨부파일 응답을 검증했다.
- 복원 가능성을 위해 변경을 하나의 기능 커밋으로 묶고, 마음에 들지 않으면 `git revert`로 되돌릴 수 있게 한다.

## 남은 리스크

- CSS와 템플릿은 `coramail_ai`의 전체 UI를 축약한 첫 버전이므로 실제 브라우저에서 시각 검수 후 다듬어야 한다.
- Gmail sync 모듈은 아직 PostgreSQL 저장소와 연결되지 않았다.

## 후속 작업

- 로컬 서버 실행과 화면 렌더링을 확인한다.
- 이후 PostgreSQL seed/import 경로를 추가한다.

# 2026-07-27 - NYK RUMINA 사양확인 데모 데이터 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | 데모 데이터, fixture, 첨부파일, 기술 사양 확인 |
| 관련 파일 | `data/demo/specification_checks.fixture.json`, `data/demo/README.md`, `data/demo/attachments/`, `data/demo/received_quotations.fixture.json`, `docs/development/demo-data-standard.md` |

## 요청 또는 배경

- 사용자는 `data/demo/attachments`에 새 데모 첨부파일을 직접 추가했고, NYK RUMINA 관련 사양 확인 이메일 본문 3건을 제공했다.
- 새 데이터는 Steam Damping Valve 도면과 Control Valve 65A 기술 사양 확인 및 재요청 흐름을 표현한다.

## 확인한 사실

- 새 첨부파일은 `NYK_RUMINA_KANGRIM_MA070_R26_VALVE_DRAWING.pdf`와 `NYK_RUMINA_MTH_CONTROL_VALVE_65A_SPEC.pdf` 두 개다.
- 2번과 3번 이메일은 같은 `NYK_RUMINA_MTH_CONTROL_VALVE_65A_SPEC.pdf` 파일을 반복 첨부한 흐름이다.
- 이전에 unmapped attachment로 기록했던 `dc02309ce5_100135686_13800017844_11.pdf`는 현재 `data/demo/attachments`에서 삭제되어 있었다.

## 수락한 내용

- 새 데이터는 기존 견적 수신 fixture와 분리해 `specification_checks.fixture.json`으로 저장한다.
- 같은 PDF가 여러 이메일에 첨부된 경우에도 이메일별 `email_attachments.id`는 별도로 두고, 동일한 `storage_uri`와 checksum을 참조한다.
- 기대 라벨은 `specification_check`, `specification_recheck`, `technical_drawing`, `technical_specification`, `technical_sales`처럼 데모 평가 힌트로 분리한다.
- 삭제된 unmapped PDF는 되돌리지 않고 `received_quotations.fixture.json`의 unmapped 참조를 제거해 현재 파일 상태와 fixture를 맞춘다.

## 발생한 오류

- 이번 작업에서 새 오류는 없었다.

## 해결 방법

- JSON 문법을 검증했다.
- 모든 demo fixture의 첨부 `storage_uri`, 파일 크기, SHA-256 checksum을 실제 파일과 대조했다.

## 남은 리스크

- 이 fixture는 실제 Gmail 원본 export가 아니므로 provider-specific ID와 header는 데모용 deterministic 값이다.
- 사양 확인 업무 흐름은 추가됐지만, 발주, 클레임, 서비스, 첨부 없는 일반 문의 샘플은 아직 부족하다.

## 후속 작업

- PostgreSQL seed/import 스크립트가 여러 fixture 파일을 순회하도록 구현한다.
- thread 관계와 재요청 관계를 UI에서 활용할지 별도 데이터 계약으로 정한다.

# 2026-07-27 - 수신 견적서 데모 데이터 fixture 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | 데모 데이터, fixture, 첨부파일, 개발 표준 |
| 관련 파일 | `data/demo/README.md`, `data/demo/received_quotations.fixture.json`, `data/demo/attachments/`, `docs/development/demo-data-standard.md`, `.gitignore` |

## 요청 또는 배경

- 사용자는 `coramail_agent`의 `data` 경로에 데모 첨부파일을 넣어두었고, 해당 첨부파일과 연결되는 본문 이메일 3건을 제공했다.
- 이 데이터를 시스템에 어떤 표준으로 데모 데이터로 저장해야 하는지 물었다.

## 확인한 사실

- 현재 프로젝트는 문서 우선 단계이며, PostgreSQL 스키마는 `email_messages`, `email_recipients`, `email_attachments`를 원본 저장 단위로 정의한다.
- Qdrant는 원본 저장소가 아니라 PostgreSQL 원본 ID를 참조하는 검색 인덱스로 정의되어 있다.
- PDF 생성 시각 기준으로 `CoRAMail_demo_received_quotation.pdf`, `_2.pdf`, `_3.pdf`는 각각 제공된 이메일 1, 2, 3번과 매핑할 수 있다.
- `dc02309ce5_100135686_13800017844_11.pdf`는 이번에 제공된 세 이메일 본문과 직접 매칭되지 않아 unmapped attachment로 기록했다.

## 수락한 내용

- 데모 데이터의 canonical source는 DB가 아니라 `data/demo/*.fixture.json`으로 둔다.
- 이메일 원본 필드, 수신자, 첨부 메타데이터, 기대 데모 라벨을 fixture에 분리해 저장한다.
- AI 분석 결과는 raw fixture에 섞지 않고, 향후 구현 시 `email_analysis_results`와 `attachment_analysis_results`에 저장한다.
- 첨부파일은 `data/demo/attachments/`에 두고 fixture에서 상대 경로, 파일 크기, SHA-256 checksum으로 참조한다.

## 발생한 오류

- `pdfinfo`가 로컬 환경에 설치되어 있지 않아 PDF 메타데이터 확인 명령은 실패했다.

## 해결 방법

- `strings`, `file`, `sha256sum`과 JSON 검증 스크립트로 PDF 생성 시각, 파일 유형, 파일 크기, checksum을 확인했다.
- Windows sidecar 파일인 `*:Zone.Identifier`가 커밋되지 않도록 `.gitignore`에 제외 규칙을 추가했다.

## 남은 리스크

- 세 수신 견적서 fixture는 견적서 수신 흐름만 다루므로 문의, 발주, 클레임, 기술 검토, 긴급 요청, 첨부 없는 메일을 대표하지 않는다.
- 실제 Gmail export가 아니므로 provider-specific header와 attachment ID는 데모용 deterministic 값이다.

## 후속 작업

- `data/demo/received_quotations.fixture.json`을 PostgreSQL seed로 변환하는 import 스크립트를 추가한다.
- 다른 업무 유형 fixture를 추가해 D1 샘플 데이터 범위를 채운다.

# 2026-07-24 - Codex 전용 AGENTS.md 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | 문서, 개발 프로세스, Codex 지침 |
| 관련 파일 | `AGENTS.md`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 Codex가 이 프로젝트에서 매번 참고할 지속 지침 파일이 필요하다고 요청했다.
- 후보 파일명이 `AGENTS.md`가 Codex에 적합한지 재검토한 뒤 진행하라고 요청했다.

## 확인한 사실

- 공식 Codex 매뉴얼은 `AGENTS.md`를 repository에서 Codex가 자동으로 context에 넣는 open-format agent README로 설명한다.
- 매뉴얼은 `AGENTS.md`가 repo layout, 실행 방법, build/test/lint 명령, engineering conventions, do-not rules, done 기준을 담기에 적합하다고 안내한다.
- 매뉴얼은 루트 repo-level `AGENTS.md`와 하위 디렉터리별 더 구체적인 `AGENTS.md`를 둘 수 있으며, 가까운 지침이 우선한다고 설명한다.

## 수락한 내용

- 이 프로젝트의 Codex 지속 지침 파일명은 `AGENTS.md`가 적합하다고 판단했다.
- 루트 `AGENTS.md`에 문서 우선 개발, 변경 기록, git commit/push, 데이터/보안, 검증, 복구 원칙을 실행 지침으로 추가했다.

## 거부한 내용

- 별도 파일명이나 장문의 중복 운영 문서를 만들지 않았다.
- 기존 `docs/development/git-codex-workflow.md`와 `docs/development/codex-history/README.md`의 상세 내용을 모두 복제하지 않고, 루트 지침에는 핵심 실행 규칙과 참조 경로만 남겼다.

## 발생한 오류

- 공식 Codex 매뉴얼을 가져오는 로컬 helper는 이 환경에 `node`가 없어 실행되지 않았다.

## 해결 방법

- 공식 Codex 매뉴얼 URL을 `curl`로 직접 확인했다.
- 루트 `AGENTS.md`를 추가해 Codex가 작업 전 참고할 프로젝트 전용 지침을 만들었다.

## 남은 리스크

- `AGENTS.md`는 지침이므로, 세션 로그 누락을 기계적으로 막으려면 별도 pre-commit hook이나 검사 스크립트가 추가로 필요하다.

## 후속 작업

- 필요하면 후속 작업으로 session-log 누락 방지용 pre-commit hook 또는 검사 스크립트를 추가한다.

# 2026-07-24 - Git 기록의 원상복구 목적 명시

| 항목 | 내용 |
|---|---|
| 상태 | 진행 |
| 관련 영역 | Git, 개발 프로세스, 복구 |
| 관련 파일 | `docs/development/git-codex-workflow.md`, `docs/development/codex-history/session-log.md` |

## 요청 또는 배경

- 사용자는 GitHub 기반 개발 과정 관리의 목적에 원상복구가 포함된다고 알려주었다.
- 개발 히스토리와 Git 기록은 단순한 작업 기록이 아니라, 문제가 생겼을 때 검증된 과거 상태로 돌아가기 위한 기준점이 되어야 한다.

## 확인한 사실

- 기존 Git/Codex 워크플로우 문서에는 커밋, push, 태그 규칙은 있었지만 원상복구 절차가 별도 섹션으로 분리되어 있지 않았다.

## 수락한 내용

- Git 기록의 목적에 원인 추적과 원상복구를 명시한다.
- 커밋된 변경을 되돌릴 때는 이력을 보존하는 `git revert`를 기본 방식으로 둔다.
- 위험한 복구 방식인 `git reset --hard`, 강제 push, 추적 파일 삭제는 사용자의 명시 요청과 승인 없이는 사용하지 않는다.

## 거부한 내용

- 이번 항목에서는 사용자가 명시적으로 거부한 제안은 없었다.

## 발생한 오류

- 없음.

## 해결 방법

- `docs/development/git-codex-workflow.md`에 원상복구 기준 섹션을 추가했다.
- 커밋 확인, diff 확인, revert, 과거 상태 확인용 브랜치 생성, 위험한 복구 방식 제한 원칙을 문서화했다.

## 남은 리스크

- 복구 가능한 상태를 만들려면 앞으로도 작업 단위가 너무 큰 커밋을 피해야 한다.
- DB 마이그레이션, 데이터 변경, 외부 서비스 상태 변경은 Git만으로 완전 복구되지 않을 수 있으므로 별도 백업과 롤백 절차가 필요하다.

## 후속 작업

- 이번 변경을 커밋하고 GitHub에 push한다.

# 2026-07-24 - GitHub 원격 저장소 연결

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | Git, 개발 프로세스 |
| 관련 파일 | `docs/development/git-codex-workflow.md`, `docs/development/codex-history/session-log.md` |
| 관련 커밋 | `89aedb7` |

## 요청 또는 배경

- 사용자는 GitHub 원격 저장소 `the-hwistle/coramail_agent`를 만들었고, 앞으로 개발 과정을 모두 이 GitHub 저장소로 자동 관리하라고 요청했다.
- 저장소 URL은 `https://github.com/the-hwistle/coramail_agent`이다.

## 확인한 사실

- 로컬 브랜치는 `main`이다.
- 원격 저장소는 아직 등록되어 있지 않았다.
- 로컬 작업 트리는 깨끗했다.

## 수락한 내용

- `origin` 원격을 `https://github.com/the-hwistle/coramail_agent.git`로 등록한다.
- 이후 의미 있는 작업은 로컬 커밋을 만든 뒤 GitHub 원격 저장소에 push한다.

## 거부한 내용

- 이번 항목에서는 사용자가 명시적으로 거부한 제안은 없었다.

## 발생한 오류

- 아직 없음.

## 해결 방법

- `git remote add origin https://github.com/the-hwistle/coramail_agent.git`로 원격 저장소를 등록했다.
- Git/Codex 공동 개발 워크플로우 문서에 실제 원격 저장소 주소와 push 원칙을 반영했다.
- `docs: document github remote workflow` 커밋 `89aedb7`을 생성했다.
- `git push -u origin main`으로 로컬 `main`을 GitHub `origin/main`에 최초 push했고, upstream 추적 설정을 완료했다.

## 남은 리스크

- GitHub 원격 저장소에 push되었지만, 원격 저장소 보호 규칙이나 협업자 권한 정책은 아직 별도 확인하지 않았다.

## 후속 작업

- 이후 의미 있는 변경마다 세션 로그를 갱신하고 커밋한 뒤 GitHub에 push한다.

# 2026-07-24 - Git과 Codex 공동 개발 시스템 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | 문서, 개발 프로세스, Git |
| 관련 파일 | `.gitignore`, `docs/development/git-codex-workflow.md`, `docs/development/codex-history/session-log.md`, `README.md`, `docs/development/README.md` |
| 관련 커밋 | `9283b20` |

## 요청 또는 배경

- 사용자는 아직 Git 원격 저장소가 없지만, 개발 히스토리 기록과 함께 Git에서도 계속 기록하면서 AI와 공동 개발할 수 있는 시스템을 만들고 싶다고 요청했다.
- 목표는 로컬 개발 단계에서도 작업 단위, 대화 맥락, 오류 해결 과정, 리스크를 함께 남기고 이후 원격 저장소가 생기면 그대로 연결할 수 있게 하는 것이다.

## 확인한 사실

- 프로젝트 루트에 `.git` 디렉터리는 존재하지만 내부 파일이 없고, `git status --short`는 `fatal: not a git repository (or any of the parent directories): .git` 오류를 반환했다.
- `data/qdrant/` 아래에는 Qdrant 런타임 파일과 `.lock` 파일이 있어 기본 커밋 대상에서 제외하는 것이 적절하다.
- 프로젝트에는 `.gitignore`가 아직 없었다.

## 수락한 내용

- 원격 저장소가 없어도 로컬 Git 커밋을 기준으로 작업 이력을 남긴다.
- Git은 파일 변경과 재현 가능한 상태를 기록하고, Codex 세션 로그는 요청 배경, 수락과 거부, 오류, 해결 방법, 리스크를 기록한다.
- 민감 정보와 로컬 런타임 데이터는 Git에서 제외한다.

## 거부한 내용

- 이번 항목에서는 사용자가 명시적으로 거부한 제안은 없었다.

## 발생한 오류

- `git status --short` 실행 시 Git 저장소가 아니라는 오류가 발생했다.
- `git init -b main`을 처음 실행했을 때 `.git/hooks/: Read-only file system` 오류가 발생했다.

## 해결 방법

- `.gitignore`를 추가해 Python 캐시, 가상환경, 환경 변수 파일, 인증 키, Qdrant 런타임 데이터, SQLite/DB 파일, lock 파일, 노트북 체크포인트를 제외하도록 했다.
- `docs/development/git-codex-workflow.md`를 추가해 작업 흐름, 커밋 단위, 커밋 메시지 규칙, 브랜치 규칙, 태그 규칙, 원격 저장소 연결 절차를 문서화했다.
- `.git` 디렉터리가 샌드박스에서 읽기 전용으로 보여 일반 실행은 실패했으며, 승인된 escalated 실행으로 `git init -b main`을 완료했다.
- `docs: establish codex git workflow` 메시지로 첫 기준선 커밋 `9283b20`을 생성했다.

## 남은 리스크

- `.gitignore`가 `data/qdrant/`를 제외하므로, 재현 가능한 샘플 데이터는 별도 추적 경로를 정해야 한다.
- 원격 저장소 연결 전까지는 로컬 디스크 장애나 디렉터리 삭제에 대한 백업이 없다.

## 후속 작업

- 원격 저장소가 준비되면 `origin`을 연결하고 `main`을 push한다.

# 2026-07-24 - Codex 개발 히스토리 공간 추가

| 항목 | 내용 |
|---|---|
| 상태 | 해결 |
| 관련 영역 | 문서, 개발 프로세스 |
| 관련 파일 | `docs/development/codex-history/README.md`, `docs/development/codex-history/session-log.md`, `docs/development/codex-history/entry-template.md`, `README.md`, `docs/development/README.md` |

## 요청 또는 배경

- 사용자는 CoRA Mail Agent를 Codex와 함께 개발하면서 요청한 것, Codex가 답변하며 알게 된 것, 사용자가 거부하거나 수락한 것, 발생했던 오류와 해결 방법, 잠재 리스크 등을 프로젝트 디렉터리 안에 남겨야 한다고 요청했다.
- 기존 문서 구조에는 기술 의사결정을 남기는 `docs/decisions/`와 개발 단계를 남기는 `docs/development/`가 있었지만, 대화 기반 개발 히스토리를 누적하는 별도 공간은 없었다.

## 확인한 사실

- 프로젝트는 문서 우선 개발 방식을 따르고 있다.
- `docs/development/README.md`는 개발 단계와 완료 기준을 관리한다.
- `docs/decisions/README.md`는 확정된 기술 선택과 판단 근거를 관리한다.
- 대화 중 생긴 임시 판단, 오류, 수락과 거부, 후속 리스크는 `docs/decisions/`보다 별도 세션 로그에 남기는 편이 적합하다.
- 현재 작업 디렉터리 `/home/ysh/workspace/coramail_agent`는 `git status` 기준 Git 저장소로 인식되지 않았다.

## 수락한 내용

- 프로젝트 내부에 Codex 개발 히스토리를 누적하는 공간을 둔다.
- 기록 대상에는 요청, 답변 중 확인한 사실, 수락과 거부, 오류, 해결 방법, 잠재 리스크, 후속 작업을 포함한다.

## 거부한 내용

- 이번 항목에서는 사용자가 명시적으로 거부한 제안은 없었다.

## 발생한 오류

- `git status --short` 실행 시 `fatal: not a git repository (or any of the parent directories): .git`가 발생했다.

## 해결 방법

- Git 상태 확인 실패는 문서 생성 자체를 막지 않으므로, 변경 파일 추적은 파일 시스템 기준으로 진행했다.
- `docs/development/codex-history/` 디렉터리를 추가하고 운영 규칙, 누적 로그, 항목 템플릿을 분리했다.

## 남은 리스크

- Codex가 과거 대화 전체를 항상 완전하게 복원할 수 있는 것은 아니므로, 중요한 결정은 발생 직후 이 로그에 요약해야 한다.
- 실제 고객 메일, 개인정보, 인증 정보가 로그에 섞이지 않도록 민감 정보 제외 원칙을 유지해야 한다.
- 기술적으로 확정된 결정은 이 로그에만 두지 말고 `docs/decisions/`에도 승격해야 한다.

## 후속 작업

- 이후 Codex와 의미 있는 개발 요청을 진행할 때마다 `session-log.md` 상단에 새 항목을 추가한다.
- 기능, 아키텍처, 제품 범위에 영향을 주는 내용은 관련 문서에도 함께 반영한다.

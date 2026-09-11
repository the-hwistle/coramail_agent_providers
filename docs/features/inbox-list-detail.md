# F-02 Inbox List And Detail

## Purpose

사용자가 수집된 메일을 목록에서 확인하고, 선택한 메일의 원문, 메타데이터, 첨부파일, AI 분석 결과, 라우팅 상태를 한 화면에서 검토할 수 있게 한다.

이 기능은 다른 AI 기능의 결과를 표시하는 화면 계약의 기준점이다. 요약, 업무 분류, 핵심 정보 추출, 첨부파일 분석, 담당자 라우팅, 사람 검토 기능은 모두 이 화면에 표시될 수 있는 상태와 필드를 맞춰야 한다.

## Users

- 업무 담당자
- 업무 관리자
- AI 운영·개발 담당자

## Related Scenarios

- SC-01 신규 문의 메일 자동 분석
- SC-02 견적의뢰서 첨부 메일 분석
- SC-03 발주 메일 식별 및 담당자 연결
- SC-05 클레임 및 긴급 서비스 요청 탐지
- SC-06 AI 오분류 수정 및 평가 데이터 축적
- SC-07 AI 분석 실패와 안전한 대체 흐름

## Input Data

현재 데모 입력:

- `data/demo/*.fixture.json`의 수신 메일 샘플
- Gmail mode에서 메모리에 동기화한 INBOX 메시지
- 목록 검색어 `q`
- 업무 카테고리 필터 `category`
- 선택 메일 기준 `email_index` 또는 `email_uid`

운영 목표 입력:

- `email_messages` 원본 메일과 메타데이터
- `email_recipients`의 To, CC, BCC 수신자 정보
- `email_attachments`의 첨부파일 메타데이터
- `email_analysis_results`의 현재 요약, 중요도, 핵심 필드, 상태
- `email_category_assignments`의 현재 업무 분류
- `routing_assignments`의 현재 담당 후보 또는 확정 담당자
- `processing_jobs`의 수집, 분석, 첨부 처리, 색인 작업 상태

## Output Data

목록 행은 다음 정보를 제공한다.

| 필드 | 의미 |
|---|---|
| `email_uid` | 화면 선택과 원본 연결에 사용하는 안정 식별자 |
| `sender_name`, `sender_address` | 발신자 표시명과 주소 |
| `subject` | 원본 제목 |
| `body_preview` | 목록 검색과 미리보기에 사용하는 본문 일부 |
| `received_at` 또는 `date` | 목록 정렬과 표시 시간 |
| `has_attachment`, `attachment_count` | 첨부파일 존재 여부와 개수 |
| `work_status`, `work_status_label` | 목록 `Status` 컬럼에 표시할 종합 업무 처리 상태 |
| `classification_state`, `classification_state_label` | AI 분석 또는 데모/Gmail 표시 상태 |
| `mail_category` | 현재 업무 카테고리 표시값 |
| `routing_display` | 현재 담당 영역, 담당자, 또는 미할당 표시값 |

상세 패널은 다음 정보를 제공한다.

- 메일 제목, 발신자, 발신자 주소, CC, 수신 시각
- 원문 본문 또는 HTML 본문 `srcdoc`
- 첨부파일 목록, 보기/다운로드 링크, 첨부 분석 상태
- AI executive summary
- 업무 카테고리, 긴급도, 핵심 요청, 담당자, 전달 상태
- 관련 메일 또는 거래처 히스토리
- 재요약, 재분류, 첨부 재분석 실행 버튼 상태

## State

목록과 상세 화면은 다음 상태를 표현해야 한다.

| 상태 | 의미 | 화면 처리 |
|---|---|---|
| `unclassified` | 메일 원문은 있지만 AI 분류 결과가 없음 | 원문을 표시하고 `미분류`, `미할당`으로 표시 |
| `queued` | 분석 작업 대기 중 | 원문을 표시하고 대기 상태를 표시 |
| `running` | 분석 또는 재생성 작업 실행 중 | 진행 중 표시와 polling 대상 |
| `completed` | 현재 AI 결과가 있음 | 요약, 분류, 담당 상태 표시 |
| `failed` | 분석 또는 재생성 실패 | 원문을 유지하고 실패 메시지와 재시도 가능 상태 표시 |
| `cancelled` | 작업이 취소됨 | 원문을 유지하고 취소 상태 표시 |
| `review_required` | 분류 또는 Mail Decision Run은 완료됐지만 자동 배정 기준을 만족하지 못함 | 사람 검토 필요 상태를 강조하고 원문, 근거, 라우팅 후보를 표시 |
| `auto_assigned` | Mail Decision Run이 자동 배정을 완료함 | 자동 배정 상태와 담당자를 표시 |
| `assigned` | 담당자가 확정됐지만 Mail Decision Run 자동 배정 완료 상태는 아님 | 담당자 확정 상태를 표시 |

현재 데모 모드는 fixture 기대값을 사용해 `completed`와 `Demo` 상태를 표시한다. Gmail mode는 영구 분석 파이프라인이 연결되기 전까지 `unclassified`, `Gmail`, `미분류`, `미할당`을 표시한다.

Inbox 목록의 `Status` 컬럼은 `classification_state`만 표시하지 않고 `work_status`를 우선 표시한다. `work_status`는 최신 Mail Decision Run 상태, 분석 작업 상태, 현재 분류 상태, 라우팅 상태를 다음 우선순위로 합성한다: `failed`, `running`, `queued`, `review_required`, `auto_assigned`, `assigned`, `completed`, `unclassified`. `classification_state`는 분류 컬럼과 기존 집계 호환을 위해 별도로 유지한다.

## Normal Flow

1. 사용자가 Inbox 탭을 연다.
2. 시스템은 메일 목록을 조회하고 첫 번째 메일 또는 요청된 `email_uid`를 선택한다.
3. 목록 행에는 상태, 발신자, 제목, 업무 카테고리, 라우팅, 수신 시각이 표시된다.
4. 사용자가 검색어 또는 카테고리 필터를 변경하면 목록 부분만 갱신된다.
5. 사용자가 목록 행을 선택하면 상세 패널만 갱신된다.
6. 상세 패널은 원문, 첨부파일 메타데이터, AI 요약, 업무 개요, 담당 상태를 표시한다.
7. AI 결과가 없거나 실패해도 원문과 메타데이터는 계속 표시된다.
8. 진행 중인 요약, 분류, 첨부 분석 작업이 있으면 화면은 polling으로 상태 변화를 반영한다.

## Exception Flow

- 선택한 `email_index`가 없으면 404를 반환한다.
- `email_uid`가 현재 목록에 없으면 기본 선택 메일을 사용한다.
- 목록 검색 결과가 비어 있으면 빈 상태 행을 표시한다.
- AI 분석 결과가 없으면 `미분류`, `미할당`, 빈 summary로 표시한다.
- 첨부파일 원본이 없으면 첨부 행은 유지하되 `Missing` 또는 분석 불가 상태를 표시한다.
- HTML 본문은 sandboxed iframe으로 표시하고, 원문 HTML이 없으면 plain text fallback을 사용한다.
- Gmail API 동기화가 실패해도 기존 메모리 목록 또는 빈 목록과 오류 상태를 분리해 다룬다.

## Human Review Conditions

이 기능 자체는 사람 검토 결과를 생성하지 않지만, 다음 상태를 사용자가 알아볼 수 있게 표시해야 한다.

- 업무 분류가 `미분류`이거나 신뢰도가 기준값보다 낮다.
- 요약, 핵심 요청, 담당자 중 하나가 비어 있다.
- 분석 상태가 `failed`, `cancelled`, `queued`, `running`이다.
- 본문 판단과 첨부 판단이 충돌한다.
- 담당자가 없거나 라우팅 후보 간 점수 차이가 작다.
- 첨부파일 분석 결과가 없거나 첨부 원본이 없다.

## API Contract

현재 구현된 UI 계약:

- `GET /ui/inbox`
  - Query: optional `email_index`, optional `email_uid`
  - Response: Inbox 전체 HTML fragment
- `GET /ui/mail-rows`
  - Query: optional `q`, optional `category`, optional `limit`, optional `view`, optional `selected_email_index`, optional `selected_email_uid`
  - Response: 목록 행 HTML fragment
- `GET /ui/assignees`
  - Query: optional `assignee`, optional `q`, optional `category`
  - Response: 담당자별 업무 메일 HTML fragment
  - Note: Inbox와 Dashboard의 `Receiver`/담당자 칩에서 해당 담당자의 업무 화면으로 이동한다.
- `GET /ui/emails/{email_uid}`
  - Response: 이메일 상세 HTML fragment
  - Note: 기존 `email_index` 값은 호환 fallback으로만 처리한다.
- `GET /api/emails`
  - Response: `{ "emails": [...] }`
- `GET /api/emails/{email_uid}`
  - Response: `{ "email": {...} }`
- `GET /api/emails/{email_uid}/attachments/{attachment_index}`
  - Response: 데모 첨부파일 inline 또는 download
  - Note: 기존 index 기반 attachment URL은 호환 fallback으로만 처리한다.

운영 목표 API 계약:

- `GET /api/emails`는 offset 또는 cursor 기반 pagination, category/status/assignee/date 필터, 검색어를 지원해야 한다.
- `GET /api/emails/{email_uid}`는 내부 UUID 기준 상세 조회를 제공한다.
- UI의 선택 기준은 index가 아니라 `email_messages.id` 기반 `email_uid`를 우선 사용한다.
- 화면 fragment API와 JSON API는 같은 서비스 계층의 조회 계약을 사용해야 한다.

## Storage

현재 데모 저장 위치:

- 원본 샘플: `data/demo/*.fixture.json`
- 데모 첨부파일: `data/demo/attachments/`
- Gmail mode 임시 메시지: `GmailMailboxService` in-memory cache
- Gmail OAuth runtime 설정: `data/runtime/`

운영 목표 저장 위치:

- 원본 메일: `email_messages`
- 수신자: `email_recipients`
- 첨부파일 메타데이터: `email_attachments`
- 업무 분류 현재값과 이력: `email_category_assignments`
- 요약, 중요도, 핵심 필드: `email_analysis_results`
- 첨부 분석 결과: `attachment_analysis_results`
- 담당자 후보와 확정값: `routing_assignments`
- 작업 상태: `processing_jobs`
- 사용자 변경과 시스템 변경 이력: `audit_logs`

## Test Criteria

- Inbox 화면은 메일이 없을 때도 깨지지 않는다.
- 데모 모드에서 fixture-backed 목록과 첫 번째 상세 패널이 렌더링된다.
- Gmail mode에서 분석 결과가 없어도 `미분류`, `미할당` 상태로 목록과 상세가 렌더링된다.
- 검색어 `q`는 발신자, 제목, 본문 미리보기, 카테고리를 대상으로 필터링한다.
- 카테고리 필터는 현재 표시 가능한 업무 카테고리를 기준으로 동작한다.
- 목록 행 선택 시 hidden selected state와 상세 패널이 같은 메일을 가리킨다.
- 첨부파일이 있는 메일은 첨부 개수와 첨부 목록을 표시한다.
- 첨부파일 원본이 없으면 상세 화면이 실패하지 않고 missing 상태를 표시한다.
- AI 상태가 `queued`, `running`, `failed`, `unclassified`일 때 원문 표시가 유지된다.
- 분류가 완료됐더라도 최신 Mail Decision Run 또는 라우팅 상태가 `review_required`이면 목록 `Status`는 완료가 아니라 사람 검토 필요로 표시된다.
- 담당자가 확정된 행은 분류 상태와 별개로 목록 `Status`에서 배정 완료를 확인할 수 있다.
- 담당자명이 있는 `Receiver` 칩은 행 상세 선택과 분리되어 담당자 업무 화면으로 이동한다.
- 담당자 업무 화면은 로그인 사용자의 권한 범위 안에서 본인 또는 허용된 담당자의 현재 업무 메일만 표시한다.
- `/api/emails`와 `/api/emails/{email_index}`는 UI가 사용하는 핵심 필드를 포함한다.

## LLMOps Notes

이 기능은 직접 LLM을 호출하지 않는다. 다만 AI 결과를 사용자가 해석하고 수정하는 첫 화면이므로 다음 관찰 항목을 표시하거나 연결할 수 있어야 한다.

- 현재 업무 분류와 신뢰도
- 현재 summary의 상태, 모델명, 프롬프트 버전
- 분석 작업 상태와 실패 사유
- 재요약, 재분류, 첨부 재분석 요청 상태
- 사용자 수정 전후 결과로 이동할 수 있는 식별자
- 메일 한 건의 processing job과 trace 조회 기준

## Open Questions

- 운영 UI에서 목록 기본 정렬은 `received_at DESC`로 고정할지, 긴급도와 미검토 상태를 우선할지 결정해야 한다.
- 상세 조회의 영구 식별자는 `email_messages.id`를 우선 사용하되, Gmail mode 전환기에는 provider message id와의 호환 계층이 필요하다.
- 사람 검토 필요 상태를 별도 컬럼으로 둘지, 여러 분석 결과와 라우팅 상태에서 계산할지 결정해야 한다.

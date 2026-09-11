# F-03 Email Summary

## Purpose

메일 본문, 주요 메타데이터, 첨부파일 분석 결과를 바탕으로 업무 담당자가 원문 전체를 읽기 전에 핵심 요청과 후속 조치 맥락을 파악할 수 있는 구조화된 요약을 생성한다.

요약은 원본 메일을 대체하지 않는다. 사용자가 업무 판단을 빠르게 시작하도록 돕는 AI 결과이며, 원문, 첨부파일, 분류 결과, 사용자 수정 이력과 분리해 저장한다.

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

- Demo fixture의 `body_text`, `snippet`, `expected_demo_labels`
- 첨부파일 fixture의 filename, content type, processing status
- 화면에서 선택한 `email_index`
- 요약 재생성 액션 `POST /ui/emails/{email_index}/summary/regenerate`

운영 목표 입력:

- `email_messages.subject`, `sender_address`, `body_text`, `received_at`
- `email_recipients`의 To, CC 정보
- `email_attachments`의 첨부파일 메타데이터
- `attachment_analysis_results`의 현재 문서 유형, 추출 필드, OCR 또는 파싱 결과
- `email_category_assignments`의 현재 업무 분류
- 관련 메일 또는 검색 문맥
- 프롬프트 이름, 프롬프트 버전, 모델명, 생성 설정

## Output Data

요약 결과는 사람이 스캔하기 쉬운 section 목록으로 제공한다.

| 필드 | 의미 |
|---|---|
| `summary_text` | 한 줄 또는 한 문단으로 압축한 핵심 요청 |
| `sections` | 화면 표시용 제목과 본문 목록 |
| `requested_action` | 사용자가 수행해야 할 다음 행동 |
| `business_refs` | 발주번호, 견적번호, 참조번호 등 업무 식별자 |
| `vessel_names` | 선박명 또는 프로젝트명 |
| `key_entities` | 고객명, 제품명, 수량, 납기 등 핵심 엔티티 |
| `confidence` | 요약 품질 또는 입력 완전성에 대한 신뢰도 |
| `evidence` | 원문 또는 첨부 분석 결과의 근거 위치 |
| `review_required` | 사람 검토 필요 여부 |

현재 UI는 `executive_summary_sections` 배열을 사용해 `title`, `body` 쌍을 표시한다. 운영 저장 시에는 `email_analysis_results`에 `analysis_type = executive_summary`로 현재 결과를 저장하고, section 구조는 `result_json`에 둔다.

## State

| 상태 | 의미 | 저장 위치 |
|---|---|---|
| `pending` | 요약 작업이 등록되었지만 아직 실행되지 않음 | `email_analysis_results.status`, `processing_jobs.status` |
| `processing` | 요약 생성 중 | `email_analysis_results.status`, `processing_jobs.status` |
| `success` | 현재 요약 결과가 유효함 | `email_analysis_results.status` |
| `failed` | 요약 생성 실패 | `email_analysis_results.status`, `error_message` |
| `superseded` | 새 요약 결과로 대체된 과거 결과 | `is_current = false` |

화면 표시 상태는 F-02의 `queued`, `running`, `completed`, `failed`, `unclassified` 상태와 호환되어야 한다.

## Normal Flow

1. 메일 수집 또는 사용자의 재생성 요청으로 요약 작업을 등록한다.
2. 시스템은 메일 원문, 메타데이터, 첨부 분석 결과, 현재 분류 결과를 조회한다.
3. 요약 입력 payload를 구성하고 프롬프트 버전과 모델 설정을 고정한다.
4. LLM 또는 요약 파이프라인을 호출한다.
5. 출력이 정해진 JSON 구조를 만족하는지 검증한다.
6. `summary_text`, section 목록, requested action, 근거, 신뢰도를 저장한다.
7. 기존 current 요약이 있으면 `is_current = false`로 전환하고 새 결과를 current로 둔다.
8. Inbox 상세 화면은 새 요약을 표시한다.

Mail Decision Run에서 검색 문맥이 부족해도 메일 본문과 첨부 근거가 충분하면 제한적 요약을 생성하고 저장한다. 이 경우 요약 결과는 `review_required = true`와 부족한 문맥 reason을 포함하며, 담당자 자동 배정 가능 여부와 별도로 표시한다.

## Exception Flow

- 메일 본문이 비어 있으면 첨부 분석 결과와 제목 중심으로 제한 요약을 생성한다.
- 첨부 분석이 아직 끝나지 않았으면 본문 기반 임시 요약을 만들거나 요약 작업을 대기 상태로 둔다.
- LLM 호출이 실패하면 원본 메일은 유지하고 요약 상태만 `failed`로 저장한다.
- 검색 문맥이나 담당자 문맥이 부족하면 요약 자체를 실패시키지 않고 `review_required = true`로 저장한다.
- 출력 JSON 검증이 실패하면 원본 모델 출력의 안전한 요약 가능 여부를 판단하고, 실패 사유를 기록한다.
- 재생성 요청이 중복되면 같은 메일의 활성 요약 작업을 중복 실행하지 않는다.
- 새 요약이 기존 사용자 확정 요약을 덮어쓰면 안 된다.

## Human Review Conditions

- 요약이 핵심 요청 행동을 포함하지 못했다.
- 본문과 첨부파일에서 서로 다른 요청을 감지했다.
- 필수 업무 식별자 또는 제품명이 누락되었다.
- 요약 신뢰도가 기준값보다 낮다.
- 요약 결과가 분류 결과와 충돌한다.
- 사용자 또는 운영 담당자가 요약을 직접 수정했다.

## API Contract

현재 구현된 UI/API 계약:

- `POST /ui/emails/{email_uid}/summary/regenerate`
  - PostgreSQL 작업 저장소가 설정된 경우 `processing_jobs`에 `metadata.analysis_type = executive_summary` job을 등록한다.
  - `email_analysis_results`에 `analysis_type = executive_summary`, `status = pending`, `is_current = true` placeholder를 저장한다.
  - Response: `204 No Content`, `HX-Trigger: mail-summary-regenerated`
  - PostgreSQL 작업 저장소가 없으면 demo fallback으로 `HX-Trigger: coramail-demo-noop`를 반환한다.
- `POST /api/emails/{email_uid}/summary/regenerate`
  - 새 요약 작업을 등록하고 `processing_job` payload를 반환한다.
- `POST /api/jobs/run-pending?limit=`
  - pending summary job을 실행해 `email_analysis_results.status = success`와 current summary result를 저장한다.
- `GET /ui/emails/{email_uid}`
  - Response: 상세 HTML fragment에 `executive_summary_sections` 포함
- `GET /api/emails/{email_uid}`
  - Response: `{ "email": {...} }`에 현재 summary 관련 필드 포함

운영 목표 API 계약:

- `GET /api/emails/{email_uid}/summary`
  - 현재 요약 결과와 상태를 반환한다.
- `GET /api/emails/{email_uid}/summary/history`
  - 프롬프트와 모델 버전별 과거 요약 결과를 반환한다.
- `POST /api/summaries/regenerate`
  - 필터 조건에 맞는 메일 요약 재생성 작업을 bulk 등록한다.

## Storage

현재 데모/worker 저장 위치:

- 요약 원천: `data/demo/*.fixture.json`의 본문과 expected labels
- 화면 표시 payload: `DemoMailService._summary_sections()`
- Gmail mode: PostgreSQL 동기화 직후 새/변경 메일에 summary job을 실행하고 current 결과를 표시
- PostgreSQL worker: Mail Decision의 schema-validated LLM summary를
  `email_analysis_results.result_text`, `result_json.sections`에 저장

운영 목표 저장 위치:

- 현재 요약 결과: `email_analysis_results`
  - `analysis_type = executive_summary`
  - `result_text = summary_text`
  - `result_json = sections`, requested action, 근거, 신뢰도, review flag
  - `model_name`, `prompt_version`, `status`, `error_message`, `is_current`
- 요약 작업 상태: `processing_jobs`
  - `job_type = email_analysis`
  - `metadata.analysis_type = executive_summary`
- 사용자 수정 이력: `audit_logs` 또는 F-09에서 확정할 사용자 수정 저장소

## Test Criteria

- 요약 결과가 없는 메일도 상세 화면이 원문을 표시한다.
- 요약 section은 title이 없어도 body를 표시할 수 있다.
- 데모 fixture 메일은 `요청`, `업무번호`, `선박`, `담당 영역` section을 표시한다.
- Gmail mode 메일은 summary가 비어 있어도 `미분류` 상태와 함께 화면이 깨지지 않는다.
- 단일 요약 재생성 요청은 PostgreSQL 작업 저장소가 설정된 경우 pending job과 pending current analysis result를 생성한다.
- worker 실행 후 현재 summary는 `email_analysis_results.is_current = true` 결과에서 상세 화면으로 렌더링된다.
- 운영 구현에서는 LLM 출력이 schema validation을 통과한 경우에만 `success` current 결과가 된다.
- 실패한 요약 작업은 원본 메일 조회와 업무 분류 조회를 막지 않는다.
- 재생성은 기존 current 결과를 삭제하지 않고 이력으로 남긴다.
- 프롬프트 버전 또는 모델명이 없는 AI 요약 결과는 운영 완료로 보지 않는다.

## LLMOps Notes

요약 기능은 다음 항목을 기록해야 한다.

- 메일 ID와 입력 payload hash
- 프롬프트 이름과 버전
- 모델명과 생성 설정
- 입력·출력 토큰 수
- 전체 지연 시간과 LLM 호출 지연 시간
- 첨부 분석 결과 사용 여부
- 검색 문맥 사용 여부와 사용한 문서 ID
- JSON schema validation 결과
- 요약 신뢰도와 사람 검토 필요 여부
- 사용자 수정 전후 요약
- 재생성 요청자와 재생성 사유

## Open Questions

- 요약 section의 고정 제목을 `요청`, `업무번호`, `선박`, `담당 영역`으로 유지할지, 업무 유형별 section 구성을 다르게 둘지 결정해야 한다.
- 사용자 수정 summary를 `email_analysis_results`의 `source` 확장으로 둘지, 별도 correction 테이블로 둘지 F-09에서 확정해야 한다.
- 첨부 분석이 늦게 끝난 경우 본문 기반 요약을 자동으로 첨부 포함 요약으로 대체할지 결정해야 한다.

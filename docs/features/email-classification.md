# F-04 Email Classification

## Purpose

수집된 메일을 업무 처리 기준에 맞는 정규 업무 레이블로 분류하고, 사용자가 받은편지함에서 후속 조치의 성격을 빠르게 판단할 수 있게 한다.

분류 결과는 담당자 라우팅, 요약 표시, 핵심 정보 추출 우선순위, 검색 필터, 관리자 현황의 기준 데이터가 된다. AI 분류는 원본 메일을 변경하지 않으며, AI 결과와 사용자 확정 결과는 이력으로 분리해 저장한다.

## Users

- 업무 담당자
- 업무 관리자
- AI 운영·개발 담당자

## Related Scenarios

- SC-01 신규 문의 메일 자동 분석
- SC-02 견적의뢰서 첨부 메일 분석
- SC-03 발주 메일 식별 및 담당자 연결
- SC-04 기술 검토 요청 분석
- SC-05 클레임 및 긴급 서비스 요청 탐지
- SC-06 AI 오분류 수정 및 평가 데이터 축적
- SC-07 AI 분석 실패와 안전한 대체 흐름

## Classification Labels

초기 정규 업무 레이블은 다음 순서를 기준으로 한다.

| 코드 후보 | 화면 표시 | 의미 |
|---|---|---|
| `order` | 발주 | 구매 주문, 주문 승인, 납기 확인, 발주 변경 또는 취소 |
| `inquiry` | 문의 | 가격, 납기, 재고, 제공 가능 여부, 견적 요청 |
| `service` | 서비스 | 하자, 고장, 수리, 클레임, A/S, 긴급 대응 |
| `technical` | 기술 | 사양 확인, 도면 검토, 호환성, 기술 질의 |
| `general` | 기타 | 업무 외 메일 또는 위 기준으로 확정하기 어려운 일반 메일 |
| `unclassified` | 미분류 | 아직 분류하지 않았거나 분류 실패 후 임시 표시 |

Demo fixture에는 `quotation_received`, `purchase_delivery_followup`, `specification_check`, `specification_recheck` 같은 세부 subtype이 존재한다. UI는 이를 정규 업무 레이블인 `문의`, `발주`, `기술`로 매핑해 표시한다.

## Input Data

현재 데모 입력:

- Demo fixture의 `expected_demo_labels.mail_category`
- `DemoMailService.CATEGORY_LABELS`의 subtype-to-business-label mapping
- Gmail mode의 수집 메시지 메타데이터와 본문 preview
- 분류 재생성 액션 `POST /ui/emails/{email_index}/classification/regenerate`

운영 목표 입력:

- `email_messages.subject`, `body_text`, `sender_address`, `provider_thread_id`
- `email_recipients`의 수신자 정보
- `email_attachments`의 첨부파일 존재 여부와 파일명
- `attachment_analysis_results`의 문서 유형과 추출 결과
- 관련 스레드 또는 Qdrant 검색 문맥
- `categories`의 활성 분류 레이블과 설명
- 프롬프트 이름, 프롬프트 버전, 모델명, 생성 설정

## Output Data

| 필드 | 의미 |
|---|---|
| `category_code` | 안정적인 내부 분류 코드 |
| `category_name` | 화면 표시명 |
| `confidence` | 선택한 분류에 대한 신뢰도 |
| `label_scores` | 후보 레이블별 점수 |
| `reason` | 분류 근거 요약 |
| `evidence` | 판단에 사용한 본문, 첨부, 검색 문맥의 근거 |
| `review_required` | 사람 검토 필요 여부 |
| `source` | `ai`, `rule`, `user` 중 결정 주체 |
| `model_name` | AI 분류를 만든 모델 |
| `prompt_version` | AI 분류 프롬프트 또는 파이프라인 버전 |

현재 UI는 `mail_category`, `business_label`, `classification_state`, `classification_state_label`, `classification.confidence`, `classification.label_scores`를 읽을 수 있어야 한다.

## State

| 상태 | 의미 | 화면 처리 |
|---|---|---|
| `unclassified` | 분류 결과 없음 | `미분류` chip과 `미할당` 표시 |
| `queued` | 분류 작업 대기 중 | 대기 상태와 원문 표시 |
| `running` | 분류 또는 재분류 실행 중 | 진행률 표시와 polling |
| `completed` | 현재 분류 결과 있음 | 카테고리 chip, 신뢰도, 근거 표시 |
| `failed` | 분류 실패 | 실패 상태 표시와 사람 검토 전환 |
| `cancelled` | 분류 작업 취소 | 취소 상태 표시 |

운영 저장 상태는 `processing_jobs.status`와 `email_analysis_results.status`를 사용하고, 현재 확정 분류는 `email_category_assignments.is_current = true`로 표현한다.

## Normal Flow

1. 신규 메일 수집 후 분류 작업을 등록한다.
2. 시스템은 원본 메일, 첨부파일 메타데이터, 첨부 분석 결과, 관련 문맥을 조회한다.
3. 활성 `categories`와 각 레이블의 설명을 기준으로 분류 입력 payload를 구성한다.
4. 규칙으로 명확히 판단 가능한 경우 rule source 결과를 만들 수 있다.
5. AI가 필요한 경우 분류 프롬프트와 모델 설정을 고정해 호출한다.
6. AI 출력의 label, confidence, 후보 점수, 근거, review flag를 schema validation한다.
7. `email_category_assignments`에 새 분류 이력 행을 생성한다.
8. 이전 current 분류가 있으면 `is_current = false`로 전환한다.
9. 분류 근거와 후보 점수는 `email_analysis_results` 또는 분류 이력의 확장 데이터에 연결한다.
10. Inbox 목록, 상세 화면, dashboard 분포가 현재 분류를 표시한다.

Mail Decision Run에서 검색 문맥이 부족해도 본문과 첨부 근거로 제한적 분류를 만들 수 있으면 결과를 저장한다. 이 경우 `review_required = true`와 `retrieval_context_insufficient` reason을 함께 기록하며, 담당자 자동 배정은 별도 라우팅 정책에서 차단한다.

## Exception Flow

- 분류 모델 호출이 실패하면 원본 메일은 유지하고 분류 상태만 `failed`로 저장한다.
- 출력 label이 활성 `categories`에 없으면 schema validation 실패로 처리한다.
- 후보 점수 차이가 작으면 자동 확정하지 않고 `review_required = true`로 표시한다.
- 본문과 첨부파일 판단이 충돌하면 사람 검토 대상으로 전환한다.
- 검색 문맥이 낮은 관련성을 보이면 해당 문맥을 분류 근거로 사용하지 않는다.
- 검색 문맥이나 담당자 문맥이 부족하면 분류 자체를 실패시키지 않고 `review_required = true`로 저장한다.
- 여러 사용자가 동시에 수정하면 F-09의 사용자 수정 정책에 따라 최종 current 값을 결정한다.

## Human Review Conditions

- 최고 후보 confidence가 기준값보다 낮다.
- 최고 후보와 차순위 후보 점수 차이가 기준값보다 작다.
- `문의`와 `발주`, `문의`와 `기술`, `서비스`와 `기타`처럼 업무 경계가 가까운 후보가 충돌한다.
- 안전, 긴급, 클레임 표현이 탐지되었지만 서비스 여부가 불확실하다.
- 본문 판단과 첨부파일 분석 결과가 서로 다른 업무 유형을 가리킨다.
- 분류 결과가 요약의 requested action과 충돌한다.
- AI 출력 schema validation이 실패했다.

## API Contract

현재 구현된 UI/API 계약:

- `POST /ui/emails/{email_uid}/classification/regenerate`
  - PostgreSQL 작업 저장소가 설정된 경우 `processing_jobs`에 `metadata.analysis_type = classification` job을 등록한다.
  - `email_analysis_results`에 `analysis_type = classification`, `status = pending`, `is_current = true` placeholder를 저장한다.
  - Response: `204 No Content`, `HX-Trigger: mail-classification-regenerated`
  - PostgreSQL 작업 저장소가 없으면 demo fallback으로 `HX-Trigger: coramail-demo-noop`를 반환한다.
- `POST /ui/emails/{email_uid}/classify`
  - 현재는 같은 classification job 등록 경로에 연결된다.
- `POST /api/emails/{email_uid}/classification/regenerate`
  - 새 분류 작업을 등록하고 `processing_job` payload를 반환한다.
- `POST /api/jobs/run-pending?limit=`
  - pending classification job을 실행해 `email_analysis_results.status = success`와 current `email_category_assignments`를 저장한다.
- `GET /ui/mail-rows`
  - Query: optional `category`
  - Response: 현재 분류 기준으로 필터링한 목록 행 HTML
- `GET /api/emails`
  - Response: 각 row에 `mail_category`, `business_label`, `classification_state`, `classification` 포함

운영 목표 API 계약:

- `GET /api/emails/{email_uid}/classification`
  - 현재 분류, 후보 점수, 근거, review flag를 반환한다.
- `GET /api/emails/{email_uid}/classification/history`
  - AI, rule, user source별 분류 이력을 반환한다.
- `PATCH /api/emails/{email_uid}/classification`
  - 사용자가 분류를 수정하고 F-09 사용자 수정 이력을 남긴다.
- `POST /api/classifications/regenerate`
  - 필터 조건에 맞는 메일 분류 작업을 bulk 등록한다.

## Storage

현재 데모/worker 저장 위치:

- 원본 기대값: `data/demo/*.fixture.json`의 `expected_demo_labels.mail_category`
- UI mapping: `DemoMailService.CATEGORY_LABELS`
- Gmail mode: PostgreSQL 동기화 직후 새/변경 메일에 classification job을 실행하고 current 결과를 표시
- PostgreSQL worker: Mail Decision의 enum-validated AI 결과를 `email_analysis_results`와
  `email_category_assignments`에 `source = ai`로 저장

운영 목표 저장 위치:

- 분류 레이블 정의: `categories`
- 현재 분류와 이력: `email_category_assignments`
  - `source = ai`, `rule`, `user`
  - `confidence`, `model_name`, `reason`, `assigned_by_user_id`, `is_current`
- 분류 실행 상태와 근거: `email_analysis_results`
  - `analysis_type = classification`
  - `result_json = label_scores`, evidence, review flag, schema validation result
- 비동기 작업 상태: `processing_jobs`
  - `job_type = email_analysis`
  - `metadata.analysis_type = classification`
- 사용자 수정과 시스템 변경 이력: `audit_logs`

## Test Criteria

- 데모 fixture subtype은 정규 업무 레이블로 매핑되어 표시된다.
- Gmail mode 메일은 분석 전 `미분류`, `미할당`으로 표시된다.
- Inbox category filter는 현재 `mail_category`를 기준으로 동작한다.
- 분류가 없어도 목록, 상세, dashboard가 깨지지 않는다.
- 단일 재분류 요청은 PostgreSQL 작업 저장소가 설정된 경우 pending job과 pending current analysis result를 생성한다.
- worker 실행 후 현재 분류는 `email_category_assignments.is_current = true`로 조회된다.
- 운영 구현에서는 활성 `categories`에 없는 label을 성공 결과로 저장하지 않는다.
- confidence는 `0` 이상 `1` 이하로 저장된다.
- 같은 메일의 current 분류는 하나만 존재한다.
- 사용자 수정은 기존 AI 분류를 덮어쓰지 않고 새 이력으로 남긴다.
- 분류 실패는 메일 원문 조회와 요약 표시를 막지 않는다.

## LLMOps Notes

분류 기능은 다음 항목을 기록해야 한다.

- 메일 ID와 입력 payload hash
- 후보 레이블 목록과 레이블 설명 버전
- 프롬프트 이름과 버전
- 모델명과 생성 설정
- 입력·출력 토큰 수
- 전체 지연 시간과 LLM 호출 지연 시간
- 첨부 분석 결과 사용 여부
- 검색 문맥 사용 여부와 문서별 점수
- 후보 레이블별 점수
- 선택 label, confidence, review flag
- schema validation 결과
- 사용자 수정 전후 label과 수정 사유
- 업무 유형별 정확도, 정밀도, 재현율

## Open Questions

- `categories.code`의 최종 값을 영어 코드로 고정할지, 기존 한국어 표시값을 code로도 사용할지 결정해야 한다.
- 분류 근거와 후보 점수를 `email_analysis_results.result_json`에 둘지, 별도 classification detail 테이블을 둘지 운영 구현 전 확정해야 한다.
- `서비스`와 `긴급도`를 하나의 분류 결과에서 함께 판단할지, 긴급도는 별도 `email_analysis_results.analysis_type = priority`로 독립시킬지 결정해야 한다.

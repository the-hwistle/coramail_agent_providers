# coramail_ai Feature Parity and Replacement Plan

## Goal

`coramail_agent`는 별도 데모를 만드는 프로젝트가 아니라, `coramail_ai`의 실사용 기능을
문서화된 Mail Decision Run 구조로 교체하는 프로젝트다. 성공 기준은 웹 사용자가 Gmail
메일을 수집하고, 본문과 실제 첨부를 분석하고, 조치 중심 요약과 업무 분류를 확인하고,
신뢰할 수 있는 담당자를 선택·전달·수정할 수 있는지다.

## Confirmed Regression Baseline

2026-07-31 실 Gmail 검증에서 다음 원인을 확인했다.

- Gmail 초기 요약·분류가 운영 AI가 아닌 `coramail-rule-v1` 작업기를 사용했다.
- Decision Agent가 LLM schema 실패를 숨기고 제목 기반 fallback을 성공처럼 저장했다.
- Ollama에는 실제 JSON schema가 전달되지 않아 모델이 schema 자체를 답할 수 있었다.
- 본문 `Content-ID` 이미지를 일반 첨부로 집계·표시·분석했다.
- 첨부 화면은 checksum, analyzer, page/table count 같은 운영자용 내부 필드를 노출했다.
- Mail Decision Inspector는 run UUID와 step을 표시했지만 사용자의 업무 판단을 돕지 못했다.
- 검색의 “AI 답변”, 담당자 설정, 휴지통, 수동 전달 중 일부는 demo 또는 stub이었다.
- Gmail 운영 라우팅 후보에 합성 평가 사용자가 섞였다.

## Replacement Contract

한 메일의 본문, 실제 첨부, MailFacts, 검색 근거, 요약, 분류, 담당 후보는 하나의
Mail Decision Run에서 생성한다. 요약·분류 재생성 버튼과 Gmail 초기 분석은 이 결과를
`email_analysis_results`와 `email_category_assignments`에 투영한다.

LLM 호출 또는 schema 검증 실패는 `failed` 또는 `review_required`로 기록한다. 규칙이나
fallback 결과를 AI 성공으로 표시하지 않는다. 명시적인 본문 근거를 정규화하거나 LLM
결과를 taxonomy에 맞추는 deterministic validation은 `generation_mode`에 기록한다.

## Feature Matrix

| User capability | coramail_ai baseline | coramail_agent replacement | Status |
|---|---|---|---|
| Gmail 수집과 영구 UUID | Gmail/PostgreSQL 수집 | MIME 메타데이터와 원본을 PostgreSQL에 저장 | implemented |
| 본문 인라인 이미지 제외 | Content-ID/disposition 필터 | 목록, 상세, 분석, Mail Decision에서 동일 필터 | implemented |
| 첨부 파싱/OCR/비전 | PDF/문서/표/이미지 분석 | parser + vision + text document understanding | implemented |
| 첨부 결과 표시 | 문서별 업무 필드와 품목 | checksum 등 내부 필드를 제거하고 업무 필드만 표시 | implemented |
| 조치 중심 AI 요약 | LLM 요약, 예외 시 fallback | Mail Decision LLM schema 결과만 성공 저장 | implemented |
| 업무 분류 | LLM + 근거 + 정규 레이블 | MailFacts와 enum schema로 발주/문의/서비스/기술/기타 투영 | implemented |
| 담당 후보 | 카테고리/히스토리 기반 | 운영 사용자 capability + 검색 근거 점수 | implemented |
| 담당자 설정 | 웹 CRUD | PostgreSQL 운영 사용자와 업무 카테고리 CRUD | implemented |
| 합성/운영 데이터 분리 | 일부 런타임 분리 | Gmail 라우팅에서 `@coramail.invalid` 평가 사용자 제외 | implemented |
| Gmail 초기 분석 | 동기화 후 분석 | DB queue 등록 후 background drain, UI 요청 비차단 | implemented |
| 중단 작업 복구 | worker 재시도 | stale running job 재대기 | implemented |
| Gmail 휴지통 | Gmail trash | Gmail API 성공 후 DB soft-delete | implemented |
| 업무 판단 화면 | 요약/overview 중심 | Inspector 제거, 요약·유형·업무번호·담당 후보 표시 | implemented |
| 키워드 검색 | 메일/첨부 검색 | 현재 표시 모드의 메일·MailFacts·첨부 분석 통합 근거 검색, UI/API 단일 계약 | implemented |
| Qdrant hybrid 검색 답변 | hybrid search + LLM answer | Search 화면에 LLM query planner, 메일함 메타데이터 조회, 로컬 embedding hybrid retrieval, 근거 제한 LLM 답변을 연결함. 운영 영속 Qdrant 메일 색인은 추가 필요 | partial |
| 수동 담당 확정/전달 | 담당자 선택, Gmail 전달, 이력 | 후보와 review 상태 저장, 확정/전달 UI/API 필요 | pending |
| Gmail history incremental sync | history cursor | 현재 INBOX upsert, history cursor 전환 필요 | pending |
| bulk 재분석 진행 상태 | background workers | DB queue는 연결, bulk UI/worker 운영 보강 필요 | partial |
| 사용자 분류/요약 수정 이력 | 일부 수정 경로 | correction/audit API 구현 필요 | pending |

## Acceptance Checks

- 실제 Gmail의 Content-ID 서명 이미지는 첨부 개수에 포함하지 않는다.
- 동일 메일의 요약, 분류, 첨부 분석, 후보 생성이 같은 UUID와 Mail Decision 근거를 사용한다.
- 요약 결과에는 최신 발신자의 요청과 필요한 조치가 포함되고 인용 스레드가 이를 덮지 않는다.
- 분류 결과는 정규 taxonomy 밖의 값을 저장하지 않는다.
- 첨부 화면에는 checksum, analyzer, raw page/table count를 표시하지 않는다.
- Gmail 운영 라우팅에는 합성 사용자를 후보로 제시하지 않는다.
- 운영 사용자가 없거나 근거가 부족하면 임의 배정하지 않고 status는 검토 필요, Receiver는 미할당으로 표시한다.
- 모든 변경은 session log, commit, main push로 남긴다.

## Remaining Priority

다음 구현 순서는 수동 담당 확정·Gmail 전달·routing event, Qdrant 검색 화면, Gmail history
incremental sync, 사용자 correction/audit다. 이 항목이 완료되기 전에는
`coramail_ai` 전체 기능 이관 완료라고 주장하지 않는다.

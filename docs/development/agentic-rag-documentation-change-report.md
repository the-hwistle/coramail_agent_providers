# Agentic RAG 문서 변경 보고서

## 변경 목적

기존 규칙 기반 데모 흐름을 확장하는 문서 구조를 폐기하고, 첨부파일 분석·사실 추출·검색·요약·세부 업무 유형 분류·담당자 배정·검증을 하나의 `Mail Decision Run`으로 실행하는 Agentic RAG 목표 구조로 문서 기준선을 다시 세웠다.

## 변경 파일

### `AGENTS.md`

- 최종 성공 기준을 근거 기반 담당자 배정으로 명시했다.
- 사용자의 요청 목록에만 머물지 않고 목표 달성에 필요한 선행 작업, 합성 데이터, 스키마, 테스트, 평가, 문서, 폐기 작업을 자율적으로 판단하고 수행하도록 규칙을 추가했다.
- 기존 구조를 존재한다는 이유만으로 보존하지 않도록 했다.
- 실제 데이터가 부족하면 합성 담당자·역량·고객·제품·프로젝트·메일·첨부·정답 데이터를 만들도록 했다.
- 임시 규칙 기반 데모를 완성된 AI 기능으로 보고하지 않도록 했다.

### `docs/architecture/agentic_rag_mail_decision_system.md`

새 목표 아키텍처 문서를 추가했다.

주요 내용:

- `Mail Decision Run` 통합 실행
- Attachment Agent와 문서별 분석 경로
- `MailFacts`와 근거 추적
- 정확 검색·규칙 검색·Qdrant·담당자 역량 검색
- 최대 3회의 검색 재계획
- 구조화 요약과 세부 업무 유형 taxonomy
- 담당자 후보 점수와 자동 배정 정책
- Validation Agent와 사람 검토 조건
- 로컬 텍스트 LLM·Vision LLM·임베딩·reranker Gateway
- 신규 실행·근거·검색·후보 테이블
- 합성 개발·평가 데이터 규모
- 담당자 배정 중심 평가 기준

### `docs/development/README.md`

기존 데모 우선 D0~D6 단계를 M0~M8 구현 단계로 교체했다.

- M0: 문서와 폐기 범위
- M1: Mail Decision 실행 기반
- M2: 첨부파일 이해
- M3: 통합 사실·요약·분류
- M4: 조직·합성 데이터
- M5: Agentic Retrieval
- M6: 담당자 배정
- M7: 운영 평가와 안정화
- M8: 부가 기능

분류와 요약을 독립적으로 완성하는 단계는 제거했다.

### `docs/features/README.md`

기능 목록을 최종 담당자 배정에 기여하는 통합 기능 지도로 다시 작성했다.

- 요약·분류·추출·첨부 분석이 동일한 실행과 근거를 공유하도록 명시했다.
- 세부 업무 유형 분류와 상위 화면 영역을 분리했다.
- F-07을 단순 문맥 검색에서 Agentic Retrieval로 확장했다.
- F-08에 `assignee_capabilities`, `routing_candidates`, 후보별 점수와 근거를 추가했다.
- F-10을 `Mail Decision Run` 실행과 실패 관리 중심으로 바꿨다.
- 합성 데이터 요구사항을 기능 기준선에 포함했다.

### `docs/decisions/README.md`

다음 결정을 채택 상태로 추가했다.

- 고객 내부 로컬 LLM Gateway
- `Mail Decision Run` 최상위 실행 단위
- Agentic Retrieval
- LLM과 담당자 점수·자동 배정 정책 분리
- 합성 조직·메일·첨부·정답 데이터 구축
- 규칙 기반 데모 Worker의 목표 아키텍처 폐기

기존의 “Agent workflow는 나중에 검토” 방향은 제거했다.

## 제거 파일

### `docs/features/implementation-readiness.md`

삭제 이유:

- 규칙 기반 demo worker를 실제 LLM runner로 확장하는 것을 다음 단계로 권장했다.
- classification과 summary의 독립 job 구조를 전제로 했다.
- 6개 상위 분류 코드를 최종 담당자 배정 기준으로 고정하려 했다.
- 새 `Mail Decision Run` 개발 단계 문서와 역할이 중복됐다.

유효한 결정 게이트는 새 아키텍처·개발·기능·기술결정 문서로 통합했다.

## 폐기 또는 교체 대상으로 명시한 구현

이번 변경은 문서 변경이며 코드 삭제는 수행하지 않았다. 다음 구현 단계에서 아래 항목을 운영 경로에서 제거하거나 교체해야 한다.

- `PostgresEmailAnalysisWorker`
- 키워드 기반 `_classify_email()`
- 제목과 snippet 기반 `_summary_text()`
- classification과 executive summary 독립 작업
- `coramail-rule-v1` 운영 결과 기록
- 담당자 `미할당` 고정 변환

## 검증 결과

- 새 문서에서 `Mail Decision Run`, 로컬 LLM, 근거 추적, 합성 데이터, Agentic Retrieval, 자동 배정 precision 우선 원칙을 일관되게 사용했다.
- 기존 Codex 세션 로그가 도구 출력 길이 제한으로 잘릴 위험을 발견해 원본 blob으로 복원했다. 과거 세션 이력은 변경하지 않았다.
- 코드나 런타임 변경이 없으므로 애플리케이션 테스트는 실행하지 않았다.

## 후속 문서 작업

다음 상세 문서는 구현 착수 전에 신규 실행 ID와 테이블 컬럼 수준으로 추가 정합화가 필요하다.

- `docs/features/attachment-analysis.md`
- `docs/features/email-summary.md`
- `docs/features/email-classification.md`
- `docs/features/key-information-extraction.md`
- `docs/features/context-search-qdrant-indexing.md`
- `docs/features/assignee-routing.md`
- `docs/features/processing-jobs-failure-management.md`
- `docs/architecture/postgresql_schema.md`
- `docs/architecture/qdrant_point_schema.md`

상세 문서는 목표 아키텍처를 반복 설명하기보다 각 노드의 입출력, 저장 컬럼, API, 실패 상태, 평가 사례를 구체화해야 한다.

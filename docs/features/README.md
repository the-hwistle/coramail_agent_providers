# CoRA Mail 기능 정의

## 문서 목적

이 문서는 CoRA Mail 기능의 책임과 구현 경계를 정의한다. 모든 AI 기능은 [Agentic RAG Mail Decision System](../architecture/agentic_rag_mail_decision_system.md)의 `Mail Decision Run` 안에서 협력해야 한다.

첨부파일 분석, 사실 추출, 요약, 분류, 검색, 담당자 배정은 독립적으로 완성되는 기능이 아니다. 동일한 메일 사실, 근거, 검색 문맥, 실행 ID를 공유하고 최종 담당자 배정 정확도를 높여야 한다.

## 기능 문서 공통 규칙

각 기능 문서는 다음 항목을 포함한다.

1. 목적과 최종 담당자 배정에 기여하는 방식
2. 입력·출력 스키마
3. 사용하는 `Mail Decision Run` 노드와 상태
4. 근거와 검색 trace
5. 정상·실패·부분 성공·사람 검토 흐름
6. 저장 위치와 이력 정책
7. API 계약
8. 평가 기준
9. 모델·프롬프트·workflow version 기록

## 구현 우선순위

| 우선순위 | 기능 묶음 | 완료 기준 |
|---|---|---|
| P0 | 메일 수집·원본 저장·받은편지함 | 원본과 첨부파일을 안정적으로 저장하고 조회한다. |
| P0 | Mail Decision 실행 기반 | 통합 실행 상태, 노드 기록, 로컬 LLM Gateway, 구조화 출력 검증이 동작한다. |
| P0 | 첨부파일 분석·사실 추출 | 본문과 첨부의 핵심 사실과 근거를 통합한다. |
| P0 | 요약·세부 업무 유형 분류 | 동일 사실과 근거로 업무 행동과 세부 유형을 생성한다. |
| P0 | 조직 검색·담당자 배정 | 신뢰 가능한 후보만 생성하고 자동 배정 또는 사람 검토로 전환한다. |
| P1 | 사람 검토·평가·관찰 | 사용자 수정과 실행 trace를 평가 데이터로 축적한다. |
| P2 | 답변 초안·견적 폼 등 부가 기능 | 담당자 배정 흐름 안정화 후 추가한다. |

## 기능 목록

### F-01 메일 수집 및 동기화

메일 공급자에서 원본 메일, 수신자, 스레드 정보, 첨부파일을 중복 없이 저장한다.

- 문서: [Mailbox Synchronization](mailbox-synchronization.md), [Gmail Web Sync Settings](gmail-web-sync-settings.md)
- 주요 데이터: `email_accounts`, `email_messages`, `email_recipients`, `email_attachments`
- 완료 기준: 원본과 파일 저장 위치가 안정적으로 연결되고 `Mail Decision Run`을 한 번만 생성한다.

### F-02 받은편지함 목록 및 상세 화면

원문, 첨부파일, 통합 분석 상태, 요약, 세부 업무 유형, 후보 담당자, 근거, 사람 검토 상태를 표시한다.

- 문서: [Inbox List And Detail](inbox-list-detail.md)
- 완료 기준: 분석 실패나 미완료 상태에서도 원문을 확인할 수 있고 실행 단계와 검토 필요 이유가 표시된다.

### F-03 구조화 요약

메일 본문과 첨부 분석 결과, 통합 사실, 검색 문맥으로 업무 수행용 요약을 생성한다.

- 문서: [Email Summary](email-summary.md)
- 출력: 한 줄 요약, 요청 행동, 기한, 업무 식별자, 위험, 누락 정보, 근거
- 완료 기준: 분류와 동일한 `MailFacts`와 근거를 사용하며 근거 없는 날짜·수량·식별자를 생성하지 않는다.

### F-04 세부 업무 유형 분류

상위 업무 영역과 담당자 배정에 필요한 세부 업무 유형을 복수 후보와 근거로 판단한다.

- 문서: [Email Classification](email-classification.md)
- 상위 영역: `sales`, `order`, `technical`, `service`, `finance`, `general`
- 완료 기준: 본문·첨부 충돌과 인접 유형 경계를 탐지하고 불확실하면 사람 검토로 전환한다.

### F-05 통합 사실 추출

고객, 요청 행동, 제품, 부품번호, PO·견적·프로젝트·선박 식별자, 수량, 납기, 긴급 신호를 본문과 첨부에서 통합한다.

- 문서: [Key Information Extraction](key-information-extraction.md)
- 주요 데이터: `mail_facts`, `evidence_items`
- 완료 기준: 모든 핵심 값이 원문 또는 첨부 근거와 연결되고 충돌·누락이 명시된다.

### F-06 첨부파일 분석

PDF, 이미지, XLSX, DOCX의 문서 유형, 텍스트, 표, 필드, 페이지·bbox 근거를 생성한다.

- 문서: [Attachment Analysis](attachment-analysis.md)
- 상태: `pending`, `processing`, `completed`, `partial_success`, `failed`, `unsupported`
- 완료 기준: 핵심 첨부 실패가 자동 담당자 배정을 막고 사람 검토 이유로 전달된다.

### F-07 Agentic Retrieval 및 Qdrant 색인

정확 일치, 라우팅 규칙, 과거 확정 사례, 담당자 역량을 검색하고 부족하면 검색 계획을 바꿔 최대 3회 반복한다.

- 문서: [Context Search And Qdrant Indexing](context-search-qdrant-indexing.md)
- 주요 데이터: `qdrant_index_records`, `retrieval_traces`
- 완료 기준: 검색 결과가 PostgreSQL 원본으로 역추적되고 낮은 관련성 결과는 최종 문맥에서 제외된다.

### F-08 담당자 라우팅

고객, 제품군, 업무 유형, 프로젝트, 과거 확정 배정, 유사 사례, 활성 상태로 후보를 계산하고 검증한다.

- 문서: [Assignee Routing](assignee-routing.md)
- 주요 데이터: `users`, `assignee_capabilities`, `routing_rules`, `routing_candidates`, `routing_assignments`, `routing_events`
- 완료 기준: LLM이 사용자를 생성하지 않으며 후보별 점수와 근거, 자동 배정 또는 검토 이유가 저장된다.

### F-09 사람 검토 및 사용자 수정

사용자가 요약, 사실, 분류, 담당자를 확정하거나 수정하고 변경 전후를 평가 데이터로 축적한다.

- 문서: [Human Review And Corrections](human-review-corrections.md)
- 완료 기준: 사용자 값이 AI 값을 덮어쓰지 않고 별도 이력으로 남으며 다음 회귀 평가에 사용할 수 있다.

### F-10 Mail Decision 실행 및 실패 관리

`Mail Decision Run`과 노드별 실행, 재시도, timeout, 중복 방지, stale run 복구를 관리한다.

- 문서: [Processing Jobs And Failure Management](processing-jobs-failure-management.md)
- 주요 데이터: `mail_decision_runs`, `mail_decision_steps`, `processing_jobs`, `audit_logs`
- 완료 기준: 실패 노드, 원인, 재시도 횟수, 재개 지점, 사람 검토 전환을 조회할 수 있다.

### F-11 관찰 및 평가

모델·프롬프트·workflow version별 품질, 지연, 검색, 근거, 사용자 수정, 담당자 배정 지표를 기록한다.

- 문서: [LLMOps Observability And Evaluation](llmops-observability-evaluation.md)
- 핵심 지표: 첨부 유형 정확도, 필드 F1, 세부 유형 macro F1, 담당자 Top-1, Top-3 recall, 자동 배정 precision, 재배정률
- 완료 기준: 합성 평가셋과 실제 운영 평가를 구분하고 회귀 결과를 비교할 수 있다.

### F-12 알림 및 업무 현황

긴급 미할당, 사람 검토 대기, 전달 실패, 처리 지연을 관리자와 담당자에게 알린다.

- 문서: [Notifications And Work Status](notifications-work-status.md)
- 완료 기준: 배정과 실제 전달 상태를 분리하고 중복 알림을 방지한다.

### F-13 첨부 문서 유형별 메일 탐색

첨부파일 분석 결과의 문서 유형을 기준으로 관련 이메일을 섹션별로 모아 조회한다.

- 문서: [Attachment Document Type Navigation](attachment-document-type-navigation.md)
- 주요 데이터: `email_messages`, `email_attachments`, `attachment_analysis_results`
- 완료 기준: 한 이메일이 여러 문서 유형 첨부를 포함하면 각 유형 섹션에 노출되고, 미분석·실패 첨부도 운영자가 놓치지 않게 표시된다.

## 합성 데이터 요구사항

실제 조직 데이터가 부족한 동안 담당자 8명, 고객 12개, 제품군 6개, 프로젝트 15개, 라우팅 규칙 40개, 수신 메일 200건, 첨부파일 120개, 정답 평가 사례 100건을 구축한다.

합성 데이터에는 신규 고객, 후보 동점, 비활성 담당자, 본문·첨부 충돌, 긴급 오탐, 스캔 문서, 다중 시트 Excel, 첨부 분석 실패를 포함한다.

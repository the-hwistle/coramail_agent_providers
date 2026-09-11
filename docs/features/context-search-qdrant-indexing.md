# F-07 Context Search And Qdrant Indexing

## Purpose

이메일과 첨부파일 내용을 벡터로 색인해 자연어 검색, 관련 메일 검색, 라우팅 근거 검색, 평가 데이터 탐색에 사용한다.

## Users

- 업무 담당자
- 업무 관리자
- AI 운영·개발 담당자

## Related Scenarios

- SC-01 신규 문의 메일 자동 분석
- SC-03 발주 메일 식별 및 담당자 연결
- SC-06 AI 오분류 수정 및 평가 데이터 축적

## Input Data

- 이메일 제목, 본문, 발신자, 수신자, 업무 분류, 업무 식별자
- 첨부파일 파싱/OCR/이미지 설명 청크
- 임베딩 모델명, 차원, Qdrant collection 설정

## Output Data

- Qdrant email point
- Qdrant attachment chunk point
- PostgreSQL 원본과 point 연결 레코드
- 검색 결과와 원본 메일 링크
- 검색에 사용한 query, filter, score

## State

| 상태 | 의미 |
|---|---|
| `pending` | 색인 대기 |
| `indexed` | 색인 완료 |
| `stale` | 원본 변경으로 재색인 필요 |
| `failed` | 색인 실패 |
| `deleted` | 원본 삭제에 따라 point 삭제됨 |

## Normal Flow

1. 원본 이메일 또는 첨부 분석 결과의 content hash를 계산한다.
2. 색인 대상 텍스트를 구성한다.
3. 임베딩 모델과 vector dimension을 확인한다.
4. 결정적 point id를 생성한다.
5. Qdrant point를 upsert한다.
6. `qdrant_index_records`에 collection, point id, schema version, content hash를 저장한다.
7. 검색 API는 Qdrant 결과를 PostgreSQL 원본 메일과 조인해 반환한다.

### 현재 단계의 사용자 검색

- Search 탭과 `POST /api/search`는 동일한 `MailSearchService` 계약을 사용한다.
- Chats 탭은 현재 Search 탭을 발전시킨 대화형 화면 표면이다. 같은 `MailSearchService`와 근거 제한 답변 계약을 사용하되, 사용자의 질문과 AI 답변을 말풍선 형태로 표시하고 후속 질문 UI를 분리한다.
- 현재 Chats 탭은 서버에 대화 이력을 저장하지 않는 1턴 질의 화면이다. 후속 단계에서 세션별 history, 이전 근거 참조, follow-up 질문의 생략 표현 resolve를 추가할 때 Search 단발 검색 계약과 분리해 확장한다.
- 현재 표시 모드(Demo/Gmail)의 메일 본문, 발신자, 분류 결과, `MailFacts`, 첨부파일 분석 결과를 근거 단위로 검색한다.
- 로컬 텍스트 LLM query planner가 먼저 질문을 `document_qa` 또는 `mailbox_lookup`으로 분류하고 의미 검색어, 발신자·업무유형·기간 필터, 최신/오래된 정렬, 결과 개수를 구조화 출력한다.
- `document_qa` 검색은 planner 결과를 원 질문에서 추출한 `QuerySignals`와 병합한다. `QuerySignals`는 업무 식별자, 요청 필드명, 한/영 필드 alias(예: 납기/delivery/lead time, 총액/total/amount)를 포함한다.
- Query rewrite 모듈은 구조화 LLM 출력으로 planner 의미 검색어, 원 질문, 업무 식별자와 요청 필드 중심 변형을 별도 검색 질의로 만든다. 원 질문 또는 이전 대화의 신뢰 가능한 근거에서 확인된 업무 식별자는 모든 rewrite query에 유지해야 하며, 모델이 새로 만든 식별자·업체·날짜는 필수 필터로 승격하지 않는다.
- `가장 최신 메일`, `마지막으로 온 메일`, `가장 오래된 메일`처럼 순서가 명확한 질문은 결정적 검증 규칙으로 planner 결과를 보정한다.
- `mailbox_lookup`은 첨부 중복을 제외한 원본 메일만 대상으로 `received_at`을 정렬하고 필터링한다. 이 경로는 임베딩 유사도에 의존하지 않는다.
- 사용자 질문 재작성 결과와 검색 문서를 로컬 임베딩 모델로 비교하고 단어 일치 점수를 함께 사용하는 hybrid retrieval로 1차 후보를 만든다.
- Rerank 모듈은 구조화 LLM 출력으로 1차 후보를 질문 직접성, 업무 식별자 충족도, 요청 필드 coverage, source 제약으로 다시 정렬한다. 모델이 반환한 점수는 실제 후보 `evidence_id`와 신뢰 식별자 제약을 통과한 경우에만 반영하고, 실패하거나 잘못된 ID를 반환하면 deterministic rerank 점수로 닫는다.
- 질문에 업무 식별자가 있으면 동일 식별자가 없는 문서는 후보에서 제외한다. planner가 질문에 없는 식별자를 만들더라도 그 값은 필수 필터로 쓰지 않는다.
- 긴 메일·첨부 분석문은 첫 매칭 위치만 자르지 않고 업무 식별자와 요청 필드 주변의 여러 조각을 결합해 LLM 답변 prompt에 전달한다.
- 로컬 텍스트 LLM은 후보 근거만 입력받아 질문 관련성, 답변 충분성, 최종 답변과 인용 근거를 구조화 출력으로 생성한다.
- LLM 호출 메시지는 역할을 분리한다. 시스템 규칙은 `system`, 현재 사용자 질문과 작업 요청은 `user`, 이전 대화 context와 검색 후보 근거는 애플리케이션이 만든 `tool` context로 구성하고, provider가 standalone tool role을 허용하지 않는 경우 gateway가 named user message로 호환 변환한다.
- 관련성 점수 0.55 미만, 존재하지 않는 근거 ID, LLM이 선택하지 않은 문서는 화면과 API 결과에서 제외한다.
- 충분한 인용 근거가 없으면 최신 메일이나 의미상 유사해 보이는 메일을 대신 반환하지 않고 명시적인 빈 근거 답변을 반환한다.
- 결과에는 LLM 관련성 설명, 근거 미리보기, 원본 메일 이동 링크, retrieval/rerank 점수, query rewrite/reranker module, rewrite/reranker prompt version, rewritten queries, fallback error, retrieval/answer 모델과 prompt version trace를 포함한다.
- 문서 임베딩은 `embedding_model + content hash`를 키로 프로세스 메모리에 최대 10,000개 캐시하며 원문이 달라지면 다시 계산한다. 긴 문서는 식별자·메타데이터를 포함한 앞뒤 6,000자로 제한한다. 운영 영속 색인은 아래 Qdrant 계약으로 교체한다.
- Qdrant 유사 사례는 합성 평가 데이터와 운영 메일의 격리·원본 연결을 보장한 뒤 이 검색 계약에 추가한다. 현재 Search 탭은 운영 Gmail에 합성 사례를 섞지 않는다.
- 담당자 배정용 `QdrantSimilarCaseRetriever`는 Search 탭과 별도의 `RetrievalScope`를 사용한다. 운영 Gmail routing은 `provider=gmail`, `dataset_type=production`, `synthetic=false`, `evaluation=false`, 현재 mailbox account, `assignment_confirmed=true`를 최종 Qdrant query에서 mandatory filter로 강제한다. planner가 dataset filter를 누락하거나 충돌하는 filter를 전달해도 mandatory filter는 제거되지 않는다.
- Demo와 evaluation은 같은 Qdrant infrastructure를 쓸 수 있지만 scope가 다르다. Demo retrieval은 `dataset_type=demo`, `evaluation=false`만 허용하고, evaluation retrieval은 명시된 evaluation dataset/version만 허용한다. Metadata가 없는 legacy point는 운영 production routing evidence로 승격하지 않는다.
- Production similar-case 색인은 `ProductionSimilarCaseIndexer`가 PostgreSQL 원본에서 재생성한다. 수동 배정, 재배정, 자동 배정, 전달 완료 후에는 같은 point id를 다시 upsert해 `assignment_confirmed`, assignee, business type provenance가 최신 assignment row와 일치하도록 갱신한다.
- Knowledge Graph와 미래 Search Agent의 역할 분리는 [Knowledge Graph Context And Search Agent](../architecture/knowledge-graph-context-and-search-agent.md)를 따른다. 담당자 배정 workflow에서는 Text-to-SQL/Text-to-Cypher 없이 검증된 routing context retrieval strategy를 우선하고, 자유 질의 Search Agent에서 필요성이 입증될 때만 선택적으로 검토한다.

### 전문가 피드백: Agentic Search RAG 목표 구조

현재 Search 탭의 방향은 맞지만, 단일 `semantic_query -> hybrid retrieval -> LLM answer` 흐름만으로는 업무 메일 질의 전반을 안정적으로 처리하기 어렵다. 견적서 납기·총액 사례는 단순 유사도 문제가 아니라 질문 의도, 필수 제약, 필요한 근거 종류, 답변 가능성 판단이 분리되지 않아 생긴 문제다.

객관적인 평가:

- LLM planner는 유용하지만 신뢰 경계 밖에 둬야 한다. planner가 업무 식별자를 누락하거나 생성할 수 있으므로, 원 질문에서 결정적으로 뽑은 식별자·날짜·발신자·요청 필드는 별도 `QuerySignals`로 보존해야 한다.
- 검색 도구는 하나가 아니라 의도별로 분리해야 한다. 메일함 조회, 문서 QA, 첨부 필드 조회, 원본 메일 상세 조회, 관련 스레드 조회, 라우팅/조직 지식 조회는 실패 양상과 검증 기준이 다르다.
- 모든 질문에 RAG를 먼저 적용하면 오히려 품질이 낮아진다. "가장 최신 메일"은 deterministic mailbox lookup이 맞고, "이 견적서의 총액"은 식별자 기반 attachment-field retrieval이 먼저다.
- LLM은 답변 생성기이기 전에 evidence judge 역할을 해야 한다. 후보를 많이 넣는 것보다, 후보가 질문에 필요한 필드를 실제로 포함하는지 검증하고 부족하면 재검색해야 한다.
- "근거 부족"은 최종 상태가 아니라 중간 상태여야 한다. 초기 후보가 부족하면 query rewrite, tool 변경, exact lookup 강화, 상세 원문 재조회 중 하나를 시도한 뒤에도 부족할 때만 사용자에게 부족 답변을 반환한다.

목표 Agent 흐름:

```text
사용자 질문
→ Intent Analyzer
→ Query Signal Extractor
→ Tool Planner
→ Tool Executor
→ Evidence Evaluator
→ 필요 시 Replanner 또는 Detail Fetch
→ Grounded Answer Generator
→ Citation/Validation
```

초기 intent 설계 근거:

- `mailbox_lookup`은 문서 내용 질문이 아니라 메일 메타데이터 조회다. 수신 시각, 발신자, 카테고리, 기간 필터는 PostgreSQL 원본 메타데이터가 정답 소스이므로 임베딩이나 Qdrant 유사도보다 결정적 query가 우선한다.
- `document_field_qa`는 견적서 납기·총액처럼 특정 필드 값을 묻는다. 정답은 첨부 분석 `fields`, 표, 추출 텍스트, `MailFacts` 안의 값으로 존재해야 하므로 일반 semantic retrieval보다 필드 단위 exact/alias retrieval이 우선한다.
- `document_summary_qa`는 "요청사항", "내용", "요약"처럼 단일 필드가 아니라 메일·첨부의 여러 근거를 압축해야 한다. 따라서 exact 제약이 있으면 해당 메일 안에서만 요약하고, 제약이 없을 때만 hybrid retrieval로 후보를 넓힌다.
- `thread_lookup`은 같은 업무번호 또는 Gmail thread 안의 흐름을 묻는다. 시간순 관계와 후속 메일 여부가 중요하므로 `provider_thread_id`, 업무 식별자, normalized subject 기반 조회가 필요하다.
- `routing_context_qa`는 메일 내용보다 조직 지식과 확정 배정 이력이 정답 소스다. 운영 메일 본문 검색으로 담당자를 추론하면 LLM이 사용자를 만들거나 잘못된 담당자를 합성할 위험이 있다.
- `unsupported_or_ambiguous`는 보안과 품질을 위한 명시적 intent다. 근거 범위 밖 질문이나 제약이 너무 모호한 질문을 억지로 RAG 답변으로 만들지 않는다.

객관적 재검토와 개선:

- 기존 `document_qa`와 `mailbox_lookup` 2분류는 너무 거칠다. 특히 필드 추출형 질문과 요약형 질문의 retrieval 단위가 달라야 하므로 `document_field_qa`와 `document_summary_qa`를 분리한다.
- `unsupported_or_ambiguous` 하나에 모든 예외를 넣으면 사용자가 수정할 수 있는 모호성과 시스템이 답하면 안 되는 범위 밖 질문이 섞인다. 운영 구현에서는 `clarification_needed`와 `unsupported`를 결과 상태에서 분리한다.
- 단일 intent만 강제하면 "FM250016318 견적서의 납기와 총액을 알려주고 원본 메일도 보여줘" 같은 복합 질문을 놓친다. Agent plan은 primary intent와 optional secondary actions를 함께 가질 수 있어야 한다.
- intent는 LLM 단독 출력이 아니라 deterministic signals로 보정해야 한다. `최신/오래된`, 업무 식별자, 이메일 주소, 날짜 범위, 필드명은 정규식과 parser로 먼저 추출하고 LLM 판단과 충돌하면 deterministic signal을 우선한다.
- tool 이름만 있으면 구현자가 임의로 해석한다. 각 tool은 신뢰 소스, 입력, 출력, 실패 조건, LLM 사용 가능 여부를 명시해야 한다.

개선된 intent taxonomy:

| intent | 의미 | 우선 tool |
|---|---|---|
| `mailbox_lookup` | 최신/오래된 메일, 발신자별 메일, 기간별 메일 조회 | metadata mailbox lookup |
| `document_field_qa` | 특정 메일·첨부의 납기, 금액, 수량, 품번 같은 필드 질의 | exact identifier lookup, attachment field retrieval |
| `document_summary_qa` | 특정 메일·첨부의 요약, 요청사항, 주요 내용 질의 | exact lookup, hybrid document retrieval |
| `thread_lookup` | 같은 업무번호/스레드의 과거 후속 메일 조회 | business ref/thread exact lookup |
| `routing_context_qa` | 담당자, 부서, 라우팅 근거 조회 | routing rule/capability retriever |
| `clarification_needed` | 답변 가능한 범위지만 식별자, 기간, 대상 메일 같은 제약이 부족한 질문 | clarification question |
| `unsupported` | 메일·첨부·조직 지식 근거 범위 밖 질문 | explicit unsupported answer |

Tool registry:

| tool | 신뢰 소스 | 입력 | 출력 | 실패/중단 조건 | LLM 역할 |
|---|---|---|---|---|---|
| `metadata_mail_lookup` | PostgreSQL `email_messages`, `email_accounts`, category assignments | sender, category, date range, sort, limit | 원본 메일 evidence | 필터 결과 없음, 날짜 파싱 실패 | 사용 안 함 또는 결과 문장화만 |
| `business_ref_exact_lookup` | `business_refs`, 제목, 본문, 첨부 분석 text의 exact/normalized match | required identifiers, provider, source scope | 관련 메일·첨부 후보 | 사용자 질문 식별자와 일치하는 후보 없음 | 사용 안 함 |
| `attachment_field_retriever` | `attachment_analysis_results.result_json`, `result_text`, `mail_facts` | email/attachment scope, requested fields, alias terms | 필드 단위 evidence | 요청 필드 근거 없음, 첨부 분석 실패/미완료 | field alias 판단 보조, 값 생성 금지 |
| `document_hybrid_retriever` | 현재 메일/첨부 검색 문서, 향후 Qdrant chunks | semantic query, filters, top_k | 문서/청크 후보 | 낮은 relevance, 필수 identifier 불일치 | query rewrite, rerank 보조 |
| `email_detail_fetcher` | PostgreSQL 원본 메일, recipients, attachments | email_message_id | 상세 본문·첨부 metadata | 원본 없음, 권한/provider 불일치 | 사용 안 함 |
| `thread_lookup` | `provider_thread_id`, normalized subject, business refs | thread id or business refs | 시간순 thread evidence | thread 없음, unrelated subject drift | thread 요약 보조 |
| `routing_context_lookup` | routing rules, assignee capabilities, confirmed assignment history | customer, product, business type, project | 담당자/규칙 evidence | active 담당자 없음, 규칙 충돌 | 후보 설명 보조, 사용자 생성 금지 |

Tool selection policy:

1. Deterministic extractor가 이메일 주소, 날짜 범위, 최신/오래된 표현, 업무 식별자, 요청 필드명을 먼저 추출한다.
2. Intent Analyzer는 위 signals와 질문 문장을 함께 보고 primary intent, secondary actions, 필요한 evidence type을 구조화 출력한다.
3. Tool Planner는 primary intent별 최소 tool set을 선택한다. 예를 들어 `document_field_qa`는 `business_ref_exact_lookup -> attachment_field_retriever -> email_detail_fetcher` 순서가 기본이다.
4. Tool Executor는 LLM이 만든 값이 아니라 deterministic extractor 또는 trusted tool output에 있는 값만 필수 filter로 사용한다.
5. Evidence Evaluator가 required field coverage와 source constraint를 검사한다. 부족하면 최대 3회까지 `fetch_detail`, `switch_tool`, `rewrite_query` 중 하나만 수행한다.
6. Grounded Answer Generator는 evaluator가 승인한 evidence만 입력받는다. tool 결과가 충분하면 LLM 없이 template answer를 사용할 수 있다.

Tool 호출 정책:

- `mailbox_lookup`은 임베딩 없이 메타데이터 필터와 정렬만 사용한다.
- `document_field_qa`는 exact identifier match를 1순위로 사용하고, 첨부 분석 `fields`, `tables`, `extracted_text`, `MailFacts`를 필드 단위 evidence로 분해해 찾는다.
- `document_summary_qa`는 exact match가 있으면 해당 메일·첨부 안에서만 검색하고, 식별자가 없으면 hybrid retrieval과 rerank를 사용한다.
- `thread_lookup`은 `provider_thread_id`, `business_refs`, 제목 normalized thread key를 사용한다.
- `routing_context_qa`는 운영 메일 본문이 아니라 라우팅 규칙, 담당자 역량, 확정 배정 이력 저장소를 사용한다.
- 어떤 의도든 LLM이 만든 식별자, 날짜, 발신자, 담당자는 필수 필터로 승격하지 않는다. 원 질문 또는 신뢰 저장소에서 확인된 값만 tool argument로 쓴다.

Evidence Evaluator는 다음 조건을 구조화 출력으로 판정한다.

- 질문에 필요한 필드 목록
- 각 필드의 근거 존재 여부
- 후보 근거가 원 질문의 식별자, 메일, 첨부, 스레드 제약을 만족하는지 여부
- 답변 가능한 필드와 부족한 필드
- 다음 재검색 action: `rewrite_query`, `fetch_email_detail`, `fetch_attachment_detail`, `switch_tool`, `ask_clarification`, `answer_insufficient`

최종 답변 생성 규칙:

- 답변 생성 LLM은 Evidence Evaluator가 `answerable=true`로 표시한 evidence만 사용한다.
- 일부 필드만 찾은 경우에는 찾은 값과 부족한 값을 분리해서 답한다.
- 값이 여러 개이면 출처별로 나열하고, 충돌하면 단일 값으로 합치지 않는다.
- 모든 날짜, 금액, 수량, 식별자는 citation을 가져야 한다.

단계별 해결안:

1. M5-a: `SearchIntent`, `QuerySignals`, tool plan, evidence sufficiency schema를 API trace에 노출한다.
2. M5-b: `document_field_qa` 전용 retriever를 추가해 첨부 분석 JSON의 `fields`, `tables`, `extracted_text`, `MailFacts`를 필드 evidence로 chunking한다.
3. M5-c: 현재 `MailSearchService`의 planner를 Agent loop로 분리한다. 한 번의 LLM plan에 의존하지 않고 최대 3회까지 tool 결과 기반 replan을 허용한다.
4. M5-d: `mailbox_lookup`, `document_field_qa`, `document_summary_qa`, `thread_lookup`, `routing_context_qa`별 golden regression set을 만든다.
5. M5-e: Qdrant 운영 색인으로 전환할 때 chunk payload에 `source_type`, `field_name`, `business_refs`, `email_message_id`, `attachment_id`, `page`, `table_name`, `received_at`을 필수 저장한다.

## Exception Flow

- 임베딩 실패는 색인 실패로 기록하고 원본 조회를 막지 않는다.
- Qdrant upsert 실패는 재시도 작업으로 남긴다.
- 임베딩 모델 또는 차원이 변경되면 새 collection으로 전체 재색인한다.
- PostgreSQL 원본과 Qdrant point 연결이 끊기면 색인 복구 대상으로 표시한다.
- Runtime scope 도입 전 legacy similar-case point는 production으로 간주하지 않는다. 운영 전에는 새 collection version에 `python -m app.tools.qdrant_similar_case_index reindex-production --provider gmail`로 재색인하고 `verify`로 provenance 누락과 invalid production point를 확인한다.

## Human Review Conditions

- 검색 결과가 라우팅 또는 분류 판단에 사용되었지만 관련성이 낮다.
- 사용자가 검색 근거가 부적절하다고 수정했다.
- 원본 메일 또는 첨부파일로 이동할 수 없는 검색 결과가 발생했다.

## API Contract

운영 목표:

- `POST /api/index/emails/{email_uid}`
- `POST /api/index/attachments/{attachment_id}`
- `POST /api/search`
- `GET /api/index-records?source_type=&status=`
- `POST /api/index/rebuild`
- `python -m app.tools.qdrant_similar_case_index reindex-production --provider gmail`
- `python -m app.tools.qdrant_similar_case_index verify`

## Storage

- 색인 상태: `qdrant_index_records`
- 이메일 collection: `coramail_emails_v1`
- 첨부파일 collection: `coramail_attachments_v1`
- 담당자 배정 유사 사례 collection: `CORAMAIL_QDRANT_CASE_COLLECTION`
- 작업 상태: `processing_jobs`

## Test Criteria

- Qdrant point는 PostgreSQL 원본 ID로 역추적 가능하다.
- 같은 원본과 같은 hash는 같은 point id를 만든다.
- 색인 실패는 원본 메일 조회를 막지 않는다.
- 검색 결과는 원본 메일 또는 첨부파일 상세로 이동할 수 있다.
- 같은 검색어에 대해 Search 탭과 `POST /api/search`가 같은 근거 순서와 빈 결과 정책을 사용한다.
- 일치하지 않는 검색은 임의의 최신 메일을 반환하지 않는다.
- 자연어 질문은 임베딩 후보 검색을 거치고 LLM이 선택한 근거만 반환한다.
- `가장 최신 메일이 뭐야`는 첨부를 중복 반환하지 않고 `received_at`이 가장 큰 원본 메일 한 건을 답변 근거로 사용한다.
- 메일함 조회의 발신자, 업무유형, 기간 필터와 최신·오래된 정렬은 문서 내용의 의미 유사도가 아니라 메타데이터로 적용한다.
- LLM의 낮은 관련성 인용과 존재하지 않는 근거 ID는 결과에서 제외된다.
- LLM이 근거 부족으로 판단한 답변은 근거 목록을 비우고 불충분 상태를 사용자에게 알린다.
- 업무 식별자가 포함된 질문은 해당 식별자가 없는 문서를 의미 유사도만으로 반환하지 않는다.
- planner가 업무 식별자를 누락해도 원 질문의 식별자는 검색어와 필수 후보 필터에 유지된다. 반대로 planner가 질문에 없는 식별자를 만들면 필수 필터로 승격하지 않는다.
- query rewrite는 planner 의미 검색어, 원 질문, 식별자·요청 필드 중심 변형, 구조화 LLM rewrite 변형을 별도 embedding query로 전달한다.
- query rewrite는 모델이 질문 범위 밖 식별자·업체·날짜를 만든 경우 해당 변형을 제외한다.
- rerank는 동일 식별자 후보 중 사용자가 요청한 필드를 직접 포함한 첨부 또는 메일 본문을 상위 후보로 올린다.
- rerank는 모델이 존재하지 않는 `evidence_id`를 반환해도 결과에 포함하지 않고, 신뢰 식별자 제약을 만족하지 않는 후보의 점수를 낮춘다.
- 긴 첨부 분석 근거에서 업무 식별자와 요청 필드가 멀리 떨어져 있어도 둘 다 LLM prompt preview에 포함된다.
- 한글 필드명으로 질문해도 영어 첨부 필드명(`Delivery date`, `Grand total`, `Amount`, `Qty` 등)을 lexical retrieval과 excerpt 후보 위치에 반영한다.
- intent classifier는 `mailbox_lookup`, `document_field_qa`, `document_summary_qa`, `thread_lookup`, `routing_context_qa`, `clarification_needed`, `unsupported`의 golden set에서 평가한다.
- 각 intent는 허용된 tool만 호출한다. 예를 들어 최신 메일 조회는 `metadata_mail_lookup`을 사용하고, 견적서 납기·총액 질의는 `business_ref_exact_lookup`과 `attachment_field_retriever`를 우선 사용한다.
- tool argument의 필수 식별자, 날짜, 발신자, 담당자는 원 질문 또는 trusted tool output에서 확인된 값이어야 하며 LLM이 생성한 값만으로는 필수 필터를 만들 수 없다.
- Evidence Evaluator는 required field coverage, source constraint match, missing fields, next action을 구조화 trace로 남긴다.
- tool 결과만으로 답변 가능한 필드형 질문은 template answer를 허용하고, LLM 답변은 citation/validation을 통과한 evidence에만 사용한다.
- 담당자 배정 similar-case retrieval은 provider/dataset/evaluation scope가 없는 Qdrant point를 반환하지 않는다.

## LLMOps Notes

검색 query, hybrid candidate 수, embedding/answer model, prompt name/version, LLM 관련성 점수, 최종 프롬프트 포함 여부, 사용자 수정 결과와의 관계를 기록한다. 현재 대화형 검색 응답은 이 trace를 API에 포함하며, 영속 trace 저장은 Qdrant 운영 색인과 함께 추가한다.

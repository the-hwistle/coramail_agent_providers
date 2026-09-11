# Knowledge Graph Context And Search Agent

## 문서 목적

이 문서는 CoRA Mail Agent에서 Knowledge Graph, GraphRAG, 담당자 배정 문맥 검색, 미래 Search Agent의 역할을 정리하는 기준 문서다.

현재 기준은 Graph DB 도입 자체가 아니라 담당자 배정에 필요한 관계 기반 업무 근거를 검색해 `Mail Decision Run`의 Context로 제공하는 것이다. 기존 PostgreSQL, Qdrant, Mail Decision workflow, deterministic `RoutingPolicy`는 유지한다.

이 문서는 과거 [Routing Knowledge Graph Architecture](graph-routing-architecture.md)와 [DECISION-011 Routing Knowledge Graph](../decisions/DECISION-011-routing-knowledge-graph.md)의 Graph DB 및 Apache AGE 선확정 전제를 대체한다.

## 현재 검증 가설

핵심 가설은 다음과 같다.

```text
담당자 배정에 필요한 관계 기반 업무 근거를 Knowledge Graph에서 검색하여 Context로 제공하면,
메일 본문·요약 또는 Vector RAG만 사용하는 방식보다 담당자 배정 정확도와 설명 가능성을 개선할 수 있는가?
```

따라서 1차 목표는 Graph DB 제품을 고르는 것이 아니라 이 가설을 검증할 수 있는 Context retrieval 계약, 근거 형식, 평가 기준을 준비하는 것이다.

## 역할 분리

| Store | 역할 |
|---|---|
| PostgreSQL | 원본 메일, 첨부 메타데이터, 사용자, 라우팅 규칙, 확정 배정 이력, audit, workflow state의 source of truth |
| Qdrant | 메일·첨부·과거 사례의 semantic/vector retrieval |
| Knowledge Graph | 고객, 발신자, 프로젝트, 선박, 제품, 업무 유형, 담당자, 확정 이력 사이의 관계 기반 Context retrieval |

Knowledge Graph는 PostgreSQL이나 Qdrant를 대체하지 않는다. Graph가 도입되더라도 PostgreSQL에서 검증된 원본과 이력을 기준으로 재구축 가능한 read model이어야 한다.

## Assignment Workflow

담당자 배정 목표 흐름은 다음과 같다.

```text
Incoming Email
-> 본문 + 첨부 분석
-> Structured Mail Context
-> Entity Linking
-> Assignment Context Retrieval
   - Vector Retrieval
   - Knowledge Graph Retrieval
-> Context Builder
-> Candidate + Evidence
-> Routing / Decision Layer
-> 담당자 판단 + 근거
```

이 흐름에서 Knowledge Graph의 1차 역할은 최종 담당자를 직접 결정하는 것이 아니라 `Assignment Context Retrieval`이다. 최종 후보 생성, ranking, threshold, 자동 배정 또는 사람 검토 전환은 별도 Routing/Decision 계층에서 검증한다.

LLM은 조직에 없는 사용자, 라우팅 규칙, 고객 관계를 생성해서는 안 된다. 담당자 후보는 신뢰 가능한 조직 저장소와 검증된 retrieval 결과에서만 생성한다.

## Assignment Context Retriever

`Assignment Context Retriever`는 `MailFacts`, 첨부 분석 결과, entity linking 결과를 입력으로 받아 담당자 배정에 필요한 후보 근거를 반환한다.

책임:

- 고객, 발신자, 프로젝트, 선박, 제품, 제품군, 업무 유형, 과거 확정 배정 이력과 연결된 관계 근거를 조회한다.
- Vector retrieval과 Graph retrieval 결과를 같은 Context Builder 계약으로 정규화한다.
- 각 근거에 source, confidence, confirmed 여부, temporal validity를 포함한다.
- 담당자 후보를 만들 수 없는 경우에도 no-candidate, conflict, insufficient-context 이유를 명시한다.
- Graph 장애 또는 미구축 상태에서는 PostgreSQL/Qdrant baseline으로 안전하게 degrade한다.

1차 구현에서는 open-ended QA가 아니므로 Text-to-SQL이나 Text-to-Cypher에 의존하지 않는다. 검증된 고정 query 또는 retrieval strategy를 우선한다.

예시:

- `retrieve_customer_history()`
- `retrieve_project_history()`
- `retrieve_product_expertise()`
- `retrieve_recent_assignments()`
- `retrieve_business_type_history()`
- `retrieve_cross_entity_assignment_evidence()`

## Fixed Graph Query 우선 원칙

담당자 배정은 사용자가 자유 질의를 던지는 Search 문제가 아니다. 입력은 구조화된 메일 문맥이고, 필요한 근거 유형도 제한적이다.

따라서 초기 Graph retrieval은 다음 원칙을 따른다.

- 검증된 고정 Graph query와 bounded traversal을 사용한다.
- query 입력값은 원문, `MailFacts`, entity linking, trusted store에서 확인된 값만 사용한다.
- LLM이 만든 식별자, 고객명, 담당자명은 필수 query argument로 승격하지 않는다.
- Graph path가 있더라도 source와 evidence가 없으면 자동 배정 근거로 쓰지 않는다.
- 관계 근거는 후보 점수와 설명을 보강하지만 deterministic baseline을 대체하지 않는다.

Text-to-SQL, Text-to-Cypher, GraphRAG framework는 Graph retrieval의 필수 조건이 아니다.

## 미래 Search Agent

Search Agent는 담당자 배정 workflow와 별도의 사용자 질의 시스템이다.

목표 구조:

```text
User Question
-> Query Router
-> 적절한 retrieval 선택
   - Vector Retrieval / Qdrant
   - SQL Retrieval / PostgreSQL
   - Graph Retrieval / Knowledge Graph
-> Context Fusion
-> LLM
-> Answer + Evidence
```

Retrieval 역할:

| Retrieval | 용도 |
|---|---|
| Vector Retrieval / Qdrant | 의미적으로 유사한 메일·첨부 검색 |
| SQL Retrieval / PostgreSQL | 정형 조회, 집계, 기간/담당자별 통계 |
| Graph Retrieval / Knowledge Graph | 고객-프로젝트-제품-담당자 등 관계 탐색 |

Text-to-SQL은 정형 조회와 집계가 자연어 질문에서 반복적으로 필요하다는 근거가 생긴 뒤 검토한다. Text-to-Cypher도 자유 질의 범위가 커지고 고정 Graph query만으로 요구를 감당하기 어려울 때 검토한다.

## Assignment Workflow와 Search Agent의 차이

| 구분 | Assignment Workflow | Search Agent |
|---|---|---|
| 입력 | 분석된 신규 메일과 첨부 | 사용자 자연어 질문 |
| 목적 | 담당자 후보와 근거 생성 | 질문에 대한 답변과 근거 생성 |
| Query 범위 | 제한된 routing context | 메일, 첨부, 통계, 관계 전반 |
| Graph 접근 | 고정 query와 retrieval strategy 우선 | 필요 시 query router와 자유 질의 확장 |
| Text-to-SQL | 필요 없음 | 필요성이 입증되면 검토 |
| Text-to-Cypher | 필요 없음 | 자유 graph 질의 요구가 커지면 검토 |
| 최종 판단 | Routing/Decision 계층과 사람 검토 | Grounded Answer Generator와 citation validation |

## 최소 Entity와 Relation 예시

초기 예시는 production ontology 확정이 아니라 retrieval 계약 검증용이다.

Entity 후보:

- `Email`
- `Attachment`
- `Contact`
- `Customer`
- `Employee`
- `Product`
- `ProductGroup`
- `Project`
- `Vessel`
- `BusinessType`
- `Assignment`

Relation 후보:

- `Email -> FROM -> Contact`
- `Contact -> WORKS_FOR -> Customer`
- `Email -> MENTIONS_CUSTOMER -> Customer`
- `Email -> MENTIONS_PRODUCT -> Product`
- `Product -> IN_GROUP -> ProductGroup`
- `Email -> MENTIONS_PROJECT -> Project`
- `Project -> FOR_CUSTOMER -> Customer`
- `Project -> FOR_VESSEL -> Vessel`
- `Employee -> RESPONSIBLE_FOR -> Customer`
- `Employee -> EXPERT_IN -> ProductGroup`
- `Employee -> HANDLES_TYPE -> BusinessType`
- `Employee -> HANDLED -> Email`
- `Assignment -> ASSIGNED_TO -> Employee`

이 목록은 현재 데이터 부족 상태에서 확정 ontology로 취급하지 않는다.

## Fact, Inference, Provenance

Knowledge Graph는 관찰 사실과 추론 관계를 구분해야 한다.

예:

```text
Observed:
Email -> MENTIONS_PERSON -> Employee

Inferred:
Project -> LIKELY_HANDLED_BY -> Employee
```

권장 metadata:

- `source_type`
- `source_id`
- `evidence_id`
- `confidence`
- `confirmed`
- `extraction_version`
- `resolver_version`
- `observed_at`
- `valid_from`
- `valid_to`

관찰 사실은 원본 메일, 첨부, 확정 사용자 행동, 라우팅 규칙에서 추적 가능해야 한다. 추론 관계는 추론 방법, 버전, confidence, 검증 여부를 별도로 남기고 confirmed fact처럼 취급하지 않는다.

## Temporal Context

담당자 배정 관계는 시간에 따라 바뀐다. 고객 owner, 제품 담당, 프로젝트 담당, 업무 유형 담당, 휴직 또는 비활성 상태, 과거 확정 배정은 모두 유효 기간을 가져야 한다.

정책:

- 현재 배정 판단에는 메일 수신 시점과 현재 운영 상태를 모두 고려한다.
- 과거 배정 이력은 `assigned_at`, `fixed_at`, `valid_from`, `valid_to`를 기준으로 해석한다.
- expired 관계는 설명에는 사용할 수 있어도 현재 자동 배정 근거로 쓰려면 별도 검증이 필요하다.
- Graph projection이 stale이면 자동 배정 대신 baseline 또는 사람 검토로 degrade한다.

## Context Builder 출력 계약

Context Builder는 retrieval 결과를 Decision 계층이 검증할 수 있는 구조로 반환한다.

현재 구현 상태:

- `app.schemas.retrieval.AssignmentEvidence`, `AssignmentCandidateContext`, `AssignmentContext`가 typed assignment evidence 계약을 제공한다.
- `app.retrieval.assignment_context.AssignmentContextBuilder`는 기존 `RetrievalContext.selected_hits`를 담당자별 candidate context로 정규화한다.
- 이 구현은 아직 기존 `RoutingPolicy` 입력을 대체하지 않는다. 현재 담당자 점수 계산과 자동 배정 판단은 기존 `RetrievalContext -> RoutingPolicy` 경로를 유지한다.

예시 계약:

```text
AssignmentContext {
  mail_decision_run_id
  linked_entities[]
  candidate_contexts[]
  evidence_items[]
  retrieval_traces[]
  conflicts[]
  missing_context[]
  warnings[]
  context_version
}

CandidateContext {
  assignee_user_id
  source = postgres | qdrant | knowledge_graph
  evidence_type
  relation_path[]
  score_hint
  confidence
  confirmed
  valid_from
  valid_to
  reasons[]
}
```

`score_hint`는 최종 점수가 아니다. 최종 후보 ranking과 자동 배정 여부는 Routing/Decision 계층에서 별도로 계산하고 검증한다.

## 최종 담당자 판단 계층

최종 담당자 판단 계층은 별도 검증 대상이다.

- deterministic `RoutingPolicy`는 baseline으로 유지한다.
- 후보 생성과 점수 계산은 조직 저장소와 검증된 retrieval result만 사용한다.
- LLM은 후보 이유 설명, 모순 검토, 부족 정보 요약을 도울 수 있지만 최종 담당자를 단독 결정하지 않는다.
- 자동 배정은 precision을 우선하고, 근거 부족·후보 충돌·Graph stale·entity linking 불확실성은 사람 검토로 전환한다.

## Graph DB 제품 선택

현재 Graph DB 제품은 선택하지 않는다.

보류 대상:

- Apache AGE
- Neo4j
- Memgraph
- GraphRAG framework
- production ontology
- Text-to-SQL
- Text-to-Cypher

제품 선택은 실제 수신 메일, 실제 담당자 이력, alias/entity resolution 사례, Graph context retrieval 평가가 준비된 뒤 수행한다. 선택 기준은 운영 단순성, 온프레미스 적합성, rebuild 가능성, provenance, latency, 평가 개선 여부다.

## 합성 데이터의 역할과 한계

현재 유의미한 실제 업무 데이터가 부족하므로 합성 데이터는 필요하다. 단, 합성 데이터는 검증 범위를 제한한다.

사용 가능한 용도:

- 기술적 feasibility
- schema와 retrieval 동작 검증
- Context Builder 계약 검증
- regression
- demo

사용하면 안 되는 주장:

- 실제 담당자 배정 정확도
- 실제 ontology completeness
- 실제 GraphRAG 우위
- 실제 entity resolution 정확도
- 실제 운영 성능

합성 데이터는 목적, 생성 방법, masking policy, 기대 label, 운영 데이터와의 차이를 문서화해야 한다.

## 구현 우선순위

1. 기존 PostgreSQL/Qdrant/Mail Decision baseline을 유지한다.
2. `MailFacts`와 첨부 분석 결과에서 entity linking 후보를 분리해 기록한다.
3. Assignment Context Builder의 입력과 출력 계약을 문서화하고 테스트한다.
4. PostgreSQL 기반 고정 retrieval strategy로 고객, 제품, 프로젝트, 업무 유형, 최근 확정 배정 근거를 조회한다.
5. 합성 데이터로 relation/provenance/temporal context 회귀 테스트를 구성한다.
6. 실제 수신 메일과 담당자 이력이 확보되면 baseline 대비 개선 여부를 평가한다.
7. 개선 가설이 유효할 때 Graph DB 제품과 projection 방식을 비교한다.
8. Graph retrieval은 degraded optional component로 연결하고 자동 배정 의존도는 별도 평가 후 높인다.

## 채택, 보류, 폐기 전제

채택:

- PostgreSQL source of truth
- Qdrant semantic/vector retrieval
- 기존 `Mail Decision Run`
- deterministic `RoutingPolicy` baseline
- Knowledge Graph의 1차 역할은 Assignment Context Retrieval
- 관계 근거의 source, provenance, confidence, temporal metadata 기록
- 합성 데이터와 실제 운영 평가 분리

보류:

- Graph DB 제품 선택
- Apache AGE, Neo4j, Memgraph 중 특정 제품 선택
- production ontology 확정
- GraphRAG framework 도입
- Text-to-SQL 구현
- Text-to-Cypher 구현
- Graph context를 최종 자동 배정 판단에 얼마나 반영할지

폐기:

- Graph DB 도입 자체를 목표로 삼는 전제
- Apache AGE를 실제 데이터 검증 전 1순위 구현안으로 확정하는 전제
- Knowledge Graph가 PostgreSQL이나 Qdrant를 대체한다는 전제
- sLLM이 조직 저장소 없이 최종 담당자를 직접 판단하는 구조
- 합성 데이터 결과를 운영 성능 주장으로 사용하는 해석

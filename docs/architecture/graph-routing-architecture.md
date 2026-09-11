# Routing Knowledge Graph Architecture

> Deprecated: 이 문서는 과거 Routing Knowledge Graph 목표 설계를 기록한 문서다. 현재 기준 문서는 [Knowledge Graph Context And Search Agent](knowledge-graph-context-and-search-agent.md)다.
>
> Graph DB 도입과 제품 선택은 현재 보류한다. 본 문서의 Graph DB 최종 채택, Apache AGE 1순위 목표 구현안, 실제 데이터 검증 전 상세 ontology/graph architecture 확정 전제는 더 이상 최신 결정이 아니다. 과거 설계 이력 보존을 위해 본문은 유지한다.

## 문서 목적

이 문서는 CoRA Mail Agent에 Graph DB를 최종적으로 도입한다는 전제에서, 어떤 설계가 가장 적절한지 사전에 결정한다. 이번 단계의 결론은 구현 지시가 아니다. Graph DB 라이브러리, Docker Compose, migration, repository, retriever, service, test는 이 문서 이후 별도 승인 전까지 추가하지 않는다.

## 최종 권고 설계

CoRA의 최적 Graph 설계는 다음 구조다.

```text
PostgreSQL source of truth
  - 원본 메일, 첨부, 사용자, 배정, 이력, audit
  - canonical entity registry
  - entity aliases
  - graph projection outbox/status

Qdrant
  - 과거 메일과 첨부의 의미 기반 유사 사례 검색

Apache AGE on PostgreSQL
  - Routing Knowledge Graph projection
  - openCypher 관계 탐색
  - PostgreSQL 백업/복구/운영 경계와 최대한 결합

Mail Decision Run
  - Retrieval Planner가 exact/rule/capability/Qdrant/Graph를 함께 계획
  - Graph는 후보 evidence와 관계 설명을 반환
  - RoutingPolicy가 deterministic ranking과 auto assign/review를 결정
```

핵심 결정:

- Graph DB는 최종적으로 도입한다. 다만 첫 구현 단위는 범용 Knowledge Graph가 아니라 `Routing Knowledge Graph`다.
- Graph engine의 1순위 목표 구현안은 Apache AGE다. PostgreSQL source of truth, 온프레미스 운영, 재구축 가능한 projection, 낮은 운영 복잡도라는 CoRA의 제약에 가장 잘 맞기 때문이다.
- Neo4j와 Memgraph는 대체 후보로 유지한다. Apache AGE가 traversal 성능, Cypher 호환성, 운영 tooling, PostgreSQL 버전 호환성에서 실패할 때만 승격한다.
- Graph에 들어갈 node/edge identity는 Graph DB가 아니라 PostgreSQL canonical registry가 결정한다.
- Entity resolution은 Graph 구현보다 먼저 완료해야 한다. false merge는 자동 오배정으로 이어질 수 있으므로 false split보다 더 위험하다.
- Graph는 PostgreSQL/Qdrant를 대체하지 않는다. Graph 장애 시 core mail workflow와 baseline routing은 계속 동작해야 한다.
- Graph 도입 후에도 LLM은 담당자를 직접 선택하지 않는다. LLM은 사실 추출, 검색 계획, 근거 설명, 예외 검토 보조에만 사용한다.

이 설계가 최적인 이유:

| 기준 | 판단 |
|---|---|
| 현재 코드와의 정합성 | 기존 `MailDecisionRun`, `RetrievalHit`, `routing_candidates`, `RoutingPolicy`를 보존하고 `RetrieverType.GRAPH`만 확장하면 된다. |
| 운영 복잡도 | Apache AGE는 PostgreSQL 확장이므로 별도 graph cluster보다 운영 경계가 작다. |
| 재구축 가능성 | canonical registry와 outbox/status가 PostgreSQL에 있으면 Graph를 삭제해도 재생성할 수 있다. |
| 설명 가능성 | 관계 path를 retrieval trace와 candidate reason으로 남길 수 있다. |
| 정확도 위험 관리 | Graph는 candidate evidence만 만들고 deterministic policy가 threshold를 적용하므로 오배정 위험을 통제할 수 있다. |
| 장기 확장성 | Routing Graph가 안정화되면 Business Case Graph로 확장할 수 있다. |

## 현재 구조 분석

### 문서 기준

- `README.md`와 `docs/development/README.md`는 최종 성공 기준을 근거 기반 담당자 배정으로 둔다.
- `docs/architecture/agentic_rag_mail_decision_system.md`는 `Mail Decision Run`을 최상위 실행 단위로 정의하고 `EXTRACT_FACTS -> PLAN_RETRIEVAL -> RETRIEVE_CONTEXT -> EVALUATE_CONTEXT -> GENERATE_DECISION -> GENERATE_ROUTING_CANDIDATES` 흐름을 둔다.
- PostgreSQL은 업무 데이터의 source of truth이고, Qdrant는 의미 기반 유사 사례 검색 저장소다.
- 담당자 후보 계산은 LLM과 분리된 결정적 정책이어야 한다.

### 실제 코드 기준

- `app/schemas/mail_decision.py`에는 `MailFacts`, `RoutingCandidate`, `RoutingDecision`, `MailDecisionNode`가 구현되어 있다.
- `app/workflows/mail_decision/orchestrator.py`는 결정적 상태 머신이고, `app/services/mail_decision_routing_service.py`가 routing 연결 버전의 node handler를 제공한다.
- `GENERATE_ROUTING_CANDIDATES`는 현재 구현되어 있다. `RoutingPolicy.score()`가 active user와 capability, MailFacts, classification, retrieval hit를 받아 후보를 계산하고 `routing_candidates`에 저장한다.
- `app/retrieval/planner.py`와 `app/retrieval/service.py`는 `EXACT`, `ROUTING_RULE`, `ASSIGNEE_CAPABILITY`, `SIMILAR_CASE` retriever를 사용한다. 아직 `GRAPH` retriever type은 없다.
- `db/postgresql/002_mail_decision_foundation.sql`에는 `mail_decision_runs`, `mail_decision_steps`, `evidence_items`, `mail_facts`, `retrieval_traces`, `assignee_capabilities`, `routing_candidates`가 있다.
- 현재 운영 엔터티 테이블은 제한적이다. `users`, `categories`, `routing_rules`, `routing_assignments`, `routing_events`, `assignee_capabilities`는 있으나, `customers`, `contacts`, `vessels`, `projects`, `products`, `product_groups`, `business_cases` 같은 canonical registry는 없다.
- `MailFacts`는 `customer_name`, `customer_candidates`, `product_names`, `product_groups`, `project_numbers`, `vessel_names` 등을 JSON/Pydantic 구조로 들고 있지만 canonical entity linking 결과는 아니다.
- 합성 seed에는 `product_group` capability가 있지만 `RoutingPolicy._match()`는 `product` capability type을 조회한다. Graph 도입 전 capability taxonomy 정합화가 필요하다.

### 문서와 코드의 차이

| 영역 | 문서 기대 | 현재 코드 상태 | Graph 설계 영향 |
|---|---|---|---|
| 조직 엔터티 | 고객·제품·프로젝트 관계 검색 | capability 문자열과 라우팅 규칙 중심 | Graph보다 canonical registry가 먼저 필요하다. |
| 담당자 후보 | 고객, 제품군, 업무 유형, 프로젝트, 이력, 유사 사례 | 동일 component 컬럼과 weight 구현 | Graph는 점수식을 대체하지 않고 component evidence를 보강한다. |
| retrieval | exact/rule/Qdrant/capability + 재계획 | 구현됨, Graph 없음 | `RetrieverType.GRAPH`는 후속 확장 지점이다. |
| provenance | evidence, facts, trace 연결 | email/attachment/retrieval evidence와 trace 있음 | Graph node/edge도 source와 confidence를 가져야 한다. |
| entity resolution | 명시 필요 | 일부 문자열 sanitizing만 있음 | Graph 도입 gate의 핵심 선행 과제다. |

## Graph DB 필요성 판단

현재 PostgreSQL + Qdrant만으로도 초기 M6 담당자 배정은 가능하다. 라우팅 규칙, 담당자 capability, 과거 확정 배정, Qdrant 유사 사례를 조합하면 좁은 합성 데이터와 명확한 업무 유형에서는 충분하다. 그러나 이것은 Graph가 불필요하다는 뜻이 아니라 baseline 역할이다.

Graph DB가 의미 있는 구간은 다음 조건이 생길 때다.

- 한 메일이 고객, 발신자, 선박, 프로젝트, 제품군, 업무 유형, 과거 case를 동시에 참조하고 단일 SQL 조건으로 후보 설명이 복잡해진다.
- 고객명 alias, 선박명 변형, 프로젝트 번호, 제품명 변형이 늘어 단순 문자열 capability 매칭의 false split이 많아진다.
- 담당자가 고객 owner, 제품 전문가, 프로젝트 보조 담당, 과거 처리자, 대체 담당자 관계를 여러 hop으로 설명해야 한다.
- Business Case 단위로 여러 이메일을 묶고 case phase 흐름을 탐색해야 한다.

따라서 최종 목표 설계에서는 Graph DB를 도입한다. 단, 구현 순서는 `canonical registry -> entity resolution/linking -> projection -> graph retrieval -> routing evaluation -> auto assignment integration`이어야 한다. Graph를 먼저 붙이면 alias 오염과 근거 없는 node/edge가 누적되어 routing 품질을 악화시킨다.

## Graph Scope

### 채택 범위

Phase 1 Graph 범위는 범용 knowledge graph가 아니라 `Routing Knowledge Graph`다.

Graph의 질문:

```text
현재 고객 + 발신자 + 선박 + 프로젝트 + 제품/제품군 + 업무 유형과 관계상 가장 가까운 active 담당자는 누구인가?
```

Graph가 반환하는 것은 최종 담당자가 아니라 후보 evidence다. 최종 후보 생성, ranking, threshold, auto assign/review 전환은 기존 `RoutingPolicy` 계층 또는 그 후속 deterministic policy가 담당한다.

### 비범위

- PostgreSQL 원본 업무 데이터 대체
- Qdrant 의미 검색 대체
- LLM이 직접 담당자를 고르는 구조
- 원본 메일 전체 저장
- 운영 데이터의 유일 source of truth
- Business Case Graph의 Phase 1 구현

## Source Of Truth

| 데이터 | Source of truth | Graph 역할 |
|---|---|---|
| Email, Attachment | PostgreSQL, file/object storage | `Mail` node 또는 edge projection 대상 |
| User, status | PostgreSQL `users` | active candidate filtering용 projection |
| Routing assignment/event | PostgreSQL | `HANDLED`, `ASSIGNED_TO` history projection |
| Routing rule/capability | PostgreSQL | `RESPONSIBLE_FOR`, `EXPERT_IN`, `HANDLES_TYPE` projection |
| MailFacts/evidence | PostgreSQL `mail_facts`, `evidence_items` | extracted relationship 후보의 source |
| Similar case | Qdrant + PostgreSQL row | Graph score 보조가 아니라 별도 retrieval hit |
| Customer/Product/Project canonical entity | 향후 PostgreSQL registry | Graph node identity의 기준 |

Graph DB는 삭제되어도 PostgreSQL에서 전체 rebuild할 수 있어야 한다. 운영 기준으로는 PostgreSQL registry와 outbox/status가 source of truth이고, Apache AGE graph는 재생성 가능한 read model이다.

## Domain Model

### Node

| Node | 주요 property | ID 정책 | uniqueness |
|---|---|---|---|
| `Contact` | `external_id`, `email`, `name`, `domain`, `status`, `source_ref` | canonical registry ID 또는 normalized email UUIDv5 | `email` canonical unique |
| `Customer` | `external_id`, `display_name`, `normalized_name`, `status`, `registry_version` | PostgreSQL canonical customer ID | canonical ID unique |
| `User` | `user_id`, `email`, `name`, `status`, `role` | PostgreSQL `users.id` | `user_id` unique |
| `Vessel` | `external_id`, `display_name`, `normalized_name`, `imo_number` | canonical vessel ID | canonical ID unique, optional IMO unique |
| `Project` | `external_id`, `project_number`, `display_name`, `status` | canonical project ID | canonical ID unique, project number scoped unique |
| `Product` | `external_id`, `display_name`, `part_number`, `normalized_name` | canonical product ID | canonical ID unique, scoped part number unique |
| `ProductGroup` | `external_id`, `code`, `display_name` | canonical product group ID | `code` unique |
| `BusinessType` | `code`, `business_area`, `status` | taxonomy code | `code` unique |
| `Mail` | `email_message_id`, `sent_at`, `received_at`, `provider`, `thread_id` | PostgreSQL `email_messages.id` | `email_message_id` unique |
| `BusinessReference` | `ref_type`, `value`, `normalized_value` | type + normalized value UUIDv5 | `(ref_type, normalized_value)` unique |

`Customer`, `Contact`, `Vessel`, `Project`, `Product`, `ProductGroup`는 Graph에서 먼저 만들지 않는다. PostgreSQL canonical registry 또는 확정된 seed가 생긴 뒤 projection한다.

### Edge

| Edge | 의미 | 주요 property |
|---|---|---|
| `(Contact)-[:WORKS_FOR]->(Customer)` | 발신자가 고객 조직 소속 | `source_type`, `source_id`, `confidence`, `confirmed`, `valid_from`, `valid_to` |
| `(Mail)-[:FROM]->(Contact)` | 메일 발신자 | `source_type=email_messages`, `source_id`, `confirmed=true` |
| `(Mail)-[:ABOUT_CUSTOMER]->(Customer)` | 메일이 고객을 언급 | `evidence_id`, `confidence`, `confirmed`, `extraction_version` |
| `(Mail)-[:ABOUT_VESSEL]->(Vessel)` | 메일이 선박을 언급 | `evidence_id`, `confidence`, `confirmed` |
| `(Mail)-[:ABOUT_PROJECT]->(Project)` | 메일이 프로젝트를 언급 | `evidence_id`, `confidence`, `confirmed` |
| `(Mail)-[:ABOUT_PRODUCT]->(Product)` | 메일이 제품을 언급 | `evidence_id`, `confidence`, `confirmed` |
| `(Product)-[:IN_GROUP]->(ProductGroup)` | 제품군 소속 | `source_type`, `source_id`, `confirmed` |
| `(Mail)-[:HAS_BUSINESS_TYPE]->(BusinessType)` | 업무 유형 | `classification_confidence`, `prompt_version`, `confirmed` |
| `(Mail)-[:REFERENCES]->(BusinessReference)` | PO, RFQ, 견적, 프로젝트 참조 | `evidence_id`, `confidence`, `ref_type` |
| `(Project)-[:FOR_CUSTOMER]->(Customer)` | 프로젝트 고객 | `source_type`, `source_id`, `confirmed` |
| `(Project)-[:FOR_VESSEL]->(Vessel)` | 프로젝트 선박 | `source_type`, `source_id`, `confirmed` |
| `(User)-[:RESPONSIBLE_FOR]->(Customer)` | 고객 owner | `priority`, `valid_from`, `valid_to`, `source_id` |
| `(User)-[:EXPERT_IN]->(ProductGroup)` | 제품군 역량 | `priority`, `valid_from`, `valid_to`, `source_id` |
| `(User)-[:HANDLES_TYPE]->(BusinessType)` | 업무 유형 역량 | `priority`, `valid_from`, `valid_to`, `source_id` |
| `(User)-[:RESPONSIBLE_FOR_PROJECT]->(Project)` | 프로젝트 담당 | `priority`, `valid_from`, `valid_to`, `source_id` |
| `(User)-[:HANDLED]->(Mail)` | 과거 확정 처리 이력 | `assignment_id`, `source`, `confirmed_by`, `assigned_at`, `fixed_at` |

### Lifecycle

- create: PostgreSQL source row 또는 canonical registry 확정 후 projection job이 idempotent upsert한다.
- update: source row version, `updated_at`, `valid_from/valid_to`, `deleted_at` 변경을 projection한다.
- delete: 원본 물리 삭제보다 `valid_to`, `deleted_at`, `status=inactive` projection을 우선한다.
- rebuild: Graph 전체 삭제 후 PostgreSQL source rows와 canonical registry에서 재생성 가능해야 한다.
- version: Graph schema version, projection job version, extraction version, entity resolver version을 별도 property로 남긴다.

## Entity Resolution And Linking

Graph 품질은 Graph DB 제품보다 entity resolution에 더 크게 좌우된다. `Hyundai Heavy Industries`, `HHI`, `HD Hyundai Heavy Industries`, `현대중공업` 또는 `M/V BLUE OCEAN`, `MV BLUE OCEAN`, `BLUE OCEAN`을 별도 node로 만들면 라우팅 recall이 낮아지고 설명이 흔들린다. 반대로 잘못 merge하면 엉뚱한 고객 담당자에게 자동 배정될 수 있으므로 false merge가 false split보다 위험하다.

권장 흐름:

```text
Fact Extraction
-> Entity Resolution
-> Entity Linking
-> Validation
-> Graph Projection
```

PostgreSQL 선행 registry 설계:

```text
canonical_entities(
  id, entity_type, display_name, normalized_key, status,
  confidence, confirmed, created_at, updated_at, deleted_at
)

entity_aliases(
  id, canonical_entity_id, alias, normalized_alias,
  source_type, source_id, confidence, confirmed,
  valid_from, valid_to, created_at, updated_at
)
```

추가 registry 테이블:

```text
entity_links(
  id, mail_decision_run_id, email_message_id,
  source_field, raw_value, entity_type,
  canonical_entity_id, link_status,
  confidence, resolver_version,
  evidence_item_id, created_at
)

entity_merge_events(
  id, entity_type, source_entity_id, target_entity_id,
  action, before_json, after_json,
  actor_type, actor_user_id, reason, created_at
)
```

정책:

- canonical ID는 PostgreSQL UUID를 기준으로 한다. Graph native ID를 외부 계약으로 쓰지 않는다.
- exact normalization은 대소문자, 공백, punctuation, `M/V`, `MV`, 법인 접미사, 한영 표기 alias를 처리한다.
- fuzzy matching은 후보 제안까지만 자동화하고, 낮은 confidence 또는 복수 후보는 사람 검토로 보낸다.
- LLM은 alias 후보 설명과 증거 요약에만 사용한다. LLM 단독 merge는 금지한다.
- ambiguous entity는 `unlinked` 또는 `candidate_links` 상태로 남기고 자동 routing evidence로 승격하지 않는다.
- merge는 source entity와 target canonical ID, before/after alias, actor, reason을 audit로 남긴다.
- unmerge는 기존 edge를 원 source evidence로 재생성할 수 있어야 한다.
- 잘못된 merge 복구를 위해 모든 node/edge는 `source_type`, `source_id`, `evidence_id`, `projection_version`을 갖는다.

## Provenance

Graph node/edge property에는 다음 추적 정보를 둘 수 있어야 한다.

```text
source_type
source_id
evidence_id
confidence
confirmed
extraction_method
extraction_version
resolver_version
projection_version
valid_from
valid_to
created_at
```

연결 정책:

- `MailFacts.evidence`와 `evidence_items`는 추출 edge의 근거다.
- `retrieval_traces`는 Graph retrieval 결과가 최종 prompt에 포함되었는지 기록한다.
- user correction 또는 manual routing은 AI edge를 덮어쓰지 않고 별도 confirmed edge 또는 version으로 남긴다.
- Graph 관계가 자동 추출인지, 라우팅 규칙인지, 사용자 확정인지, 합성 seed인지 구분해야 한다.

## Graph Routing Algorithm

### Candidate Generation

Graph 기반 candidate generation은 결정적이다.

입력:

- linked `Customer`, `Contact`, `Vessel`, `Project`, `Product`, `ProductGroup`, `BusinessType`
- current active `User`
- confirmed assignment history
- valid capability/rule edges

기본 traversal:

```text
Mail
-> ABOUT_CUSTOMER / FROM.WORKS_FOR / ABOUT_PROJECT.FOR_CUSTOMER
-> User.RESPONSIBLE_FOR

Mail
-> ABOUT_PRODUCT.IN_GROUP
-> User.EXPERT_IN

Mail
-> HAS_BUSINESS_TYPE
-> User.HANDLES_TYPE

Mail
-> ABOUT_PROJECT
-> User.RESPONSIBLE_FOR_PROJECT

Mail
-> similar or referenced historical Mail
-> User.HANDLED
```

Traversal 범위는 Phase 1에서 2 hop, Business Case 확장 후 최대 3 hop으로 제한한다. cycle이나 weak edge는 후보 설명에는 포함할 수 있으나 auto assignment score에는 평가 승인 전 사용하지 않는다.

### Component Score

기존 `routing_candidates` component와 호환한다.

| Component | Graph evidence 예 |
|---|---|
| `customer_score` | 고객 owner, contact works_for customer owner |
| `product_score` | product -> product group -> expert user |
| `business_type_score` | business type handler |
| `project_score` | project owner, project-customer-vessel 관계 |
| `history_score` | confirmed `User-HANDLED-Mail` history |
| `similarity_score` | Qdrant similar case score, Graph가 직접 계산하지 않음 |
| `availability_score` | PostgreSQL user active/status, 향후 leave/workload |

Graph 도입 시 추가 후보 signal:

- `vessel_affinity`: 선박 관련 프로젝트/고객 처리 이력
- `customer_affinity`: 고객 owner가 아니어도 반복 처리한 이력
- `project_affinity`: 프로젝트 참여 이력
- `product_expertise`: 제품군 또는 part family 역량
- `business_type_expertise`: 업무 유형 역량
- `historical_handling`: 확정 담당 이력

초기 weight는 현재 코드의 `WEIGHTS`를 그대로 운영 확정값으로 보지 않는다. Graph 도입 실험에서는 설정값으로 두고 합성/운영 승인 평가 데이터에서 grid search 또는 업무 위험 기반 튜닝으로 결정한다.

### Decision Policy

- Top score, margin, classification confidence, contradiction, evidence missing 조건은 기존 정책을 유지한다.
- 동점이면 `confirmed customer/project owner > business_type expert > recent confirmed handler > lower workload` 순서로 tie break 후보를 검토한다. 이 순서는 구현 전 평가 데이터로 확인한다.
- no candidate면 `review_required`.
- Graph timeout/error면 PostgreSQL + Qdrant baseline으로 degrade하고 `graph_unavailable` warning을 남긴다.
- Graph evidence는 `routing_candidates.reasons_json`과 `retrieval_traces`에 원 source ID와 함께 기록한다.

## Retrieval Integration

후속 schema 확장 후보:

```python
class RetrieverType(str, Enum):
    EXACT = "exact"
    ROUTING_RULE = "routing_rule"
    SIMILAR_CASE = "similar_case"
    ASSIGNEE_CAPABILITY = "assignee_capability"
    GRAPH = "graph"
```

책임 분리:

| Store | 질문 |
|---|---|
| PostgreSQL | 확정된 정확 데이터와 현재 상태는 무엇인가? |
| Qdrant | 의미적으로 비슷한 과거 메일 또는 첨부 사례는 무엇인가? |
| Graph | 관계상 가까운 고객, 프로젝트, 선박, 제품, 업무 및 담당자는 누구인가? |

Graph retrieval hit는 기존 `RetrievalHit` 형태로 반환한다.

- `retriever_type = graph`
- `source_type = graph_path` 또는 source PostgreSQL entity type
- `source_id = 가장 직접적인 PostgreSQL source row ID`
- `metadata.graph_path = node/edge source IDs`
- `metadata.assignee_user_id = candidate user`
- `retrieval_score = normalized path score`
- `content = 사람이 읽을 수 있는 관계 설명`

## Projection Design

초기에는 Kafka, Debezium, 복잡한 CDC를 도입하지 않는다. 최적 projection 방식은 PostgreSQL transactional outbox + idempotent worker다. scheduled full rebuild는 proof와 복구 경로로 남기되 운영 증분 동기화의 기본값으로 삼지 않는다.

권장 방식:

```text
PostgreSQL transaction
-> source row commit
-> graph_projection_outbox insert in same transaction
-> graph projection worker
-> Apache AGE idempotent upsert
-> graph_projection_status update
```

후보 비교:

| 방식 | 장점 | 단점 | 판단 |
|---|---|---|---|
| Scheduled full rebuild | 가장 단순, 복구 쉬움 | freshness 낮음, 규모 증가 시 비용 | proof와 recovery path |
| Outbox + worker | retry, lag 측정, 부분 upsert 가능 | outbox schema와 worker 필요 | 운영 목표 설계로 채택 |
| Trigger direct write | commit과 가까움 | Graph 장애가 업무 transaction에 영향 | 비권장 |
| CDC/Kafka | 확장성 높음 | 현재 규모에 과함 | 보류 |

Projection 요구사항:

- PostgreSQL ID 기반 external ID
- deterministic idempotent upsert
- uniqueness constraint로 duplicate 방지
- retry 가능
- projection job version과 graph schema version 기록
- projection lag 측정
- Graph 삭제 후 전체 rebuild 가능
- source row 삭제/비활성화 반영

Projection 대상 우선순위:

1. `users`, `assignee_capabilities`, `routing_rules`
2. `routing_assignments`, `routing_events`
3. `canonical_entities`, `entity_aliases`, `entity_links`
4. `mail_facts`, `evidence_items`
5. `email_messages`의 최소 metadata

Graph에는 원문 본문이나 첨부 전체를 저장하지 않는다. Graph path 설명에 필요한 label, normalized key, source ID, confidence만 저장한다.

## Failure And Fallback

정책:

- Graph query timeout: 초기 300~800ms 범위에서 운영 측정 후 설정한다.
- retry: 같은 Mail Decision Run 안에서는 1회 이하, 이후는 degraded mode.
- circuit breaker: 연속 timeout/error가 일정 기준을 넘으면 일정 시간 Graph retrieval을 건너뛴다.
- health check: DB 연결, schema version, projection lag, minimum node/edge count를 확인한다.
- degraded mode: PostgreSQL exact/routing/capability + Qdrant만 사용한다.
- rebuild 중: core mail workflow, fact extraction, summary, classification, PostgreSQL routing baseline은 계속 동작해야 한다.

Graph 없이 가능한 기능:

- 메일 수집과 원본 조회
- 첨부 분석
- MailFacts 추출
- 요약과 업무 유형 분류
- PostgreSQL routing rule/capability 기반 후보 생성
- Qdrant 유사 사례 검색
- 사람 검토와 수동 배정

Graph가 있어야만 가능한 기능은 Phase 1에서는 만들지 않는다. Graph는 최종 목표 설계에 포함되지만 운영 경로에서는 degraded optional read model이어야 한다. 자동 배정 자체는 Graph 없이도 사람 검토로 안전하게 degrade되어야 한다.

## Business Case Graph Future

Phase 1 범위는 Routing Graph다. 장기적으로는 Email보다 Case가 업무 단위에 더 적합할 수 있다.

후보 흐름:

```text
RFQ -> Quotation -> Revision -> Purchase Order -> Drawing Approval -> Delivery -> Claim -> Service
```

미래 node:

- `Case`
- `Quotation`
- `PurchaseOrder`
- `Part`
- `Delivery`
- `Claim`
- `ServiceEvent`

Case 연결 후보 기준:

- customer
- quotation_number
- po_number
- project_number
- vessel
- part_number
- provider_thread_id
- normalized subject
- time proximity
- semantic similarity

이 확장은 담당자 routing이 안정화되고 실제 수신 메일과 담당 이력이 확보된 뒤 별도 ADR로 판단한다.

## Technology Candidates

공식 문서 기준으로 확인한 후보는 다음과 같다.

| 후보 | 온프레미스 | 라이선스/운영 | Python | Query | 장점 | 제약 |
|---|---|---|---|---|---|---|
| Neo4j Community/Enterprise | 가능 | Community는 GPLv3, Enterprise는 상용. Community는 single-instance 중심이고 clustering/online backup 등은 Enterprise 기능 | 공식 Python driver | Cypher | 성숙도, 생태계, Cypher, tooling | 운영 기능은 Enterprise 의존 가능성이 크고 별도 DB 운영 부담 |
| Memgraph Community/Enterprise | 가능 | Community는 Business Source License, Enterprise는 상용. Community도 production-ready로 설명되지만 Enterprise가 보안/컴플라이언스/자동 failover 제공 | Bolt/Cypher 생태계 | Cypher | 빠른 in-memory graph, Python 친화, HA/monitoring 옵션 | 메모리 중심 운영, 라이선스 검토 필요 |
| Apache AGE | 가능 | Apache License 2.0, PostgreSQL extension, PostgreSQL 11~18 release 제공 | PostgreSQL driver + AGE support | openCypher over SQL | 기존 PostgreSQL 운영과 가깝고 projection/rebuild 모델에 적합 | graph DB 전문 운영 도구와 성능/기능은 Neo4j/Memgraph보다 검증 필요 |
| PostgreSQL tables only | 가능 | 기존 채택 기술 | psycopg/SQLAlchemy | SQL | 새 의존성 없음, 초기 구현 단순 | multi-hop 관계 설명과 graph traversal이 복잡해질 수 있음 |

최종 CoRA 권고:

1. Apache AGE를 목표 구현안으로 채택한다.
2. PostgreSQL canonical registry와 outbox/rebuild 가능한 projection 계약을 먼저 구현한다.
3. Apache AGE는 같은 PostgreSQL 운영 경계 안에서 Routing Knowledge Graph projection을 제공한다.
4. Neo4j 또는 Memgraph는 Apache AGE proof가 실패할 때만 대체 검토한다.

Apache AGE를 1순위로 정하는 근거:

- Apache AGE 공식 문서는 PostgreSQL extension으로 graph 기능을 제공하고, PostgreSQL의 relational model 안에서 openCypher graph query를 사용할 수 있다고 설명한다.
- Apache AGE는 Apache License 2.0이고, PostgreSQL과 같은 transactional/storage 경계에 붙는 구조라 온프레미스 고객 환경에서 법무·운영 검토가 상대적으로 단순하다.
- CoRA의 Graph는 primary store가 아니라 derived projection이므로, 전문 graph DB의 cluster/HA 기능보다 PostgreSQL과의 ID 정합성, backup/rebuild, 운영 단순성이 더 중요하다.
- Neo4j는 가장 성숙하지만 Enterprise 기능이 clustering/online backup 등 운영 요구에 걸릴 가능성이 크고 별도 DB 운영 경계가 생긴다.
- Memgraph는 빠르고 Python/Cypher 친화적인 후보지만 메모리 중심 운영과 Enterprise HA/보안 기능 의존 가능성을 별도 검토해야 한다.

Apache AGE 채택을 재검토할 조건:

- PostgreSQL extension 설치가 고객 운영 정책과 맞지 않는다.
- PostgreSQL 버전 호환성이 실제 배포 버전과 맞지 않는다.
- 2~3 hop traversal P95 latency가 routing 목표를 초과한다.
- graph projection rebuild 시간이 운영 복구 목표를 초과한다.
- openCypher 기능 또는 Python client ergonomics가 구현 속도를 크게 떨어뜨린다.

참고 공식 문서:

- Apache AGE overview/download: https://age.apache.org/overview/, https://age.apache.org/download/
- Neo4j operations and Python driver docs: https://neo4j.com/docs/operations-manual/current/introduction/, https://neo4j.com/docs/python-manual/current/install/
- Neo4j licensing overview: https://neo4j.com/open-core-and-neo4j/
- Memgraph pricing/legal/enterprise: https://memgraph.com/pricing, https://memgraph.com/legal, https://memgraph.com/enterprise

## Evaluation Plan

Graph 도입 성공 기준은 DB 추가 자체가 아니라 baseline 대비 담당자 배정 품질과 설명력 개선이다.

Baseline:

```text
PostgreSQL exact
+ routing_rules
+ assignee_capabilities
+ Qdrant similar case
```

Candidate:

```text
PostgreSQL exact
+ Graph relationship retrieval
+ Qdrant similar case
```

지표:

| 지표 | 판단 기준 |
|---|---|
| Top-1 assignee accuracy | 기존 0.85 목표 대비 개선 |
| Top-3 assignee recall | 0.95 목표 유지 또는 개선 |
| auto-assignment precision | recall보다 우선, 0.95 이상 유지 |
| review-required rate | precision 유지 전제에서 감소 |
| candidate coverage | 신규/alias 고객에서 후보 누락 감소 |
| routing explanation quality | 근거 source와 관계 path가 사람이 검토 가능 |
| retrieval latency | Graph query P95가 전체 decision latency를 과도하게 늘리지 않음 |
| total decision latency | 운영 Gmail 처리량에 영향 없음 |
| graph projection lag | 허용 lag 내 유지 |

Graph가 충분한 개선을 만들지 못하면 자동 배정 의존도를 높이지 않는다. 그러나 최종 설계의 Graph projection 자체는 설명 가능한 routing과 Business Case 확장을 위한 기반으로 유지한다. 특히 자동 배정은 중복 전달보다 오배정 위험이 크므로 recall보다 precision을 우선한다.

최소 합격 기준:

| 항목 | 기준 |
|---|---|
| Graph candidate coverage | baseline 대비 alias/customer/project 관련 no-candidate 감소 |
| Top-1 accuracy | baseline 이상, 목표 0.85 이상 |
| Top-3 recall | baseline 이상, 목표 0.95 이상 |
| auto-assignment precision | 0.95 이상 유지 |
| Graph query latency | P95 800ms 이하를 1차 목표로 측정 |
| Projection lag | 운영 기본 5분 이하, 긴급 메일 경로는 stale graph면 degraded |
| Rebuild | Graph 삭제 후 PostgreSQL에서 전체 rebuild 가능 |
| Provenance | 후보 이유마다 source row/evidence/edge path 추적 가능 |

## Implementation Gate

| 항목 | 현재 권고안 | 근거 | 추가 검증 | 구현 전 결정 필요 |
|---|---|---|---|---|
| Graph DB 제품 | Apache AGE 목표 구현안 채택 | PostgreSQL 파생 projection과 라이선스·운영 단순성 | 성능/운영 proof | 예 |
| canonical registry | PostgreSQL에 먼저 둔다 | Graph node identity 기준 필요 | 고객/선박/제품 alias 데이터 | 예 |
| entity merge threshold | conservative, false merge 방지 | 오배정 위험 | 실제 alias 평가셋 | 예 |
| routing score weight | 현재 weight는 baseline config로만 사용 | 근거 없이 확정 금지 | 평가 데이터 튜닝 | 예 |
| auto assignment threshold | 현재 0.82/0.15/0.78 유지 후 검증 | 코드와 설정 존재 | 업무 유형별 precision | 예 |
| projection 방식 | outbox + worker 채택, full rebuild는 복구 경로 | 현재 규모에 CDC 과함 | lag/재시도 요구 | 예 |
| Case Graph | Phase 2+ 보류 | Email routing 안정화가 먼저 | 실제 case linkage 데이터 | 아니오 |
| capability taxonomy | `product` vs `product_group` 정합화 | seed와 policy 불일치 | 스키마/seed 점검 | 예 |

## Implementation Readiness

상태: `READY WITH CONDITIONS`

의미:

- 목표 설계는 결정 가능하다.
- 바로 Graph DB부터 설치하면 안 된다.
- 첫 구현은 Graph 제품 설치가 아니라 canonical registry와 entity resolution/linking 기반이어야 한다.
- Apache AGE proof는 canonical registry와 projection source가 준비된 뒤 진행한다.

구현 전 사용자가 확인해야 할 결정:

- Apache AGE를 목표 구현안으로 삼고 Neo4j/Memgraph를 fallback 후보로 둘지
- canonical entity registry를 PostgreSQL에 먼저 추가하는 방향 수락 여부
- entity merge를 자동화하지 않고 conservative/human-review 우선으로 갈지
- Graph가 optional degraded component여야 한다는 운영 원칙 수락 여부

아직 데이터가 부족한 부분:

- 실제 고객·담당자·제품·프로젝트·선박 registry
- 실제 담당자 전달 이력과 사용자 확정 이력
- alias와 ambiguous entity 평가셋
- Graph path explanation이 실제 운영자에게 충분한지에 대한 검토 데이터

구현해도 되는 Phase:

- Phase 0: 문서 검토와 구현 결정 확정
- Phase 1: PostgreSQL canonical registry와 entity alias/linking 구현
- Phase 2: outbox/status 기반 projection source 구현
- Phase 3: Apache AGE projection proof와 full rebuild
- Phase 4: `RetrieverType.GRAPH`를 degraded optional retriever로 연결
- Phase 5: routing evaluation 통과 후 candidate scoring에 graph evidence 반영

구현하면 안 되는 Phase:

- Graph DB를 source of truth로 승격
- Graph 장애 시 core mail workflow 차단
- LLM 직접 담당자 선택
- Business Case Graph 운영 의존
- 충분한 평가 없이 auto assignment threshold 완화

예상 변경 파일:

- `docs/architecture/postgresql_schema.md`
- `db/postgresql/*.sql`
- `app/schemas/retrieval.py`
- `app/retrieval/*`
- `app/repositories/*`
- `app/routing/policy.py`
- `app/evaluation/*`
- `data/evaluation/*`

예상 migration:

- `canonical_entities`
- `entity_aliases`
- `graph_projection_outbox`
- `graph_projection_status`
- 필요 시 `graph_entity_links`

예상 신규 서비스 의존성:

- Apache AGE PostgreSQL extension
- Neo4j 또는 Memgraph는 Apache AGE proof 실패 시 대체 후보
- Docker/운영 의존성 추가는 별도 승인 후 진행한다.

예상 테스트 범위:

- entity normalization/linking unit tests
- false merge/false split regression set
- graph projection idempotency/rebuild tests
- graph retrieval fallback tests
- routing Top-1/Top-3/auto precision 비교 평가
- retrieval trace provenance integrity tests

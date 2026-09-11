# DECISION-011 Routing Knowledge Graph 목표 설계 채택

## 상태

대체

---

## 대체 사유

이 ADR은 [Knowledge Graph Context And Search Agent](../architecture/knowledge-graph-context-and-search-agent.md) 기준 문서로 대체되었다.

실제 업무 수신 메일, 실제 담당자 전달 이력, 고객·제품·프로젝트 alias와 entity resolution 평가 데이터가 부족한 상태에서는 Graph Context가 실제 담당자 배정 품질을 개선하는지 아직 검증되지 않았다. 따라서 Graph DB 도입과 Apache AGE 선택을 선확정하지 않는다.

Knowledge Graph는 우선 담당자를 직접 결정하는 구조가 아니라 `Assignment Context Retrieval` 가설로 검증한다. Graph DB 제품 선택은 관계 기반 Context가 baseline 대비 담당자 배정 정확도와 설명 가능성을 개선한다는 근거가 생긴 뒤 수행한다.

아래 내용은 과거 의사결정 이력으로 보존한다.

---

## 맥락

CoRA Mail Agent의 최종 성공 기준은 메일을 근거와 함께 정확한 담당자에게 배정하는 것이다. 현재 구조는 PostgreSQL을 source of truth로 사용하고, Qdrant를 의미 기반 유사 사례 검색에 사용한다. Mail Decision workflow, `MailFacts`, retrieval trace, `routing_candidates`, `assignee_capabilities`, deterministic `RoutingPolicy`는 이미 구현되어 있다.

하지만 실제 운영에서는 고객, 발신자, 선박, 프로젝트, 제품군, 업무 유형, 과거 담당 이력이 복합 관계로 얽힌다. 단순 문자열 capability와 SQL exact/rule 검색만으로는 alias, multi-hop 관계, 설명 가능한 routing에 한계가 생길 수 있다.

---

## 결정

Routing Knowledge Graph를 CoRA Mail Agent의 목표 설계로 채택한다.

Graph는 PostgreSQL과 Qdrant를 대체하지 않고, PostgreSQL에서 언제든 재구축할 수 있는 derived projection/read model로만 사용한다.

Graph engine의 목표 구현안은 Apache AGE다. Apache AGE는 PostgreSQL extension으로 CoRA의 PostgreSQL source of truth, 온프레미스 운영, 재구축 가능한 projection 설계와 가장 잘 맞는다.

다만 구현은 보류한다. 구현은 canonical entity registry, entity resolution/linking, projection outbox/status, baseline evaluation 준비가 끝난 뒤 별도 승인으로 시작한다.

---

## 근거

- 현재 routing 후보 생성은 Graph 없이도 동작하지만, 최종 운영에서는 고객·발신자·선박·프로젝트·제품군·업무 유형·과거 처리 이력의 multi-hop 관계가 필요하다.
- Graph DB 부재보다 더 큰 위험은 고객·선박·제품·프로젝트 alias를 잘못 merge하거나 분리하는 entity resolution 문제다.
- PostgreSQL source of truth 원칙을 유지해야 감사, 재구축, fallback, 사람 검토가 단순하다.
- Qdrant는 유사 사례 검색에 계속 필요하며 Graph가 semantic similarity를 대체하지 않는다.
- Graph는 후보 생성 evidence와 설명력을 보강하는 데 가치가 있다.
- 현재 규모에서 Kafka/CDC/별도 HA Graph 인프라는 과하다.
- Apache AGE는 PostgreSQL extension이고 Apache License 2.0이라 CoRA의 온프레미스·PostgreSQL 중심 설계와 가장 잘 맞는다.
- Neo4j와 Memgraph는 더 전문적인 graph DB 후보지만, CoRA의 첫 구현에서는 별도 DB 운영 경계와 Enterprise 기능 검토 부담이 더 크다.

---

## 대안

| 대안 | 판단 |
|---|---|
| PostgreSQL + Qdrant만 유지 | baseline으로 유지한다. 최종 목표 설계로는 multi-hop 관계 설명과 Business Case 확장성이 부족하다. |
| Neo4j | 가장 성숙한 graph DB 후보지만 Enterprise 운영 기능 의존과 별도 DB 운영 부담이 있다. Apache AGE proof 실패 시 대체 후보로 둔다. |
| Memgraph | Cypher와 Python 친화성이 좋고 빠른 graph query 후보지만 메모리 중심 운영과 라이선스 검토가 필요하다. Apache AGE proof 실패 시 대체 후보로 둔다. |
| Apache AGE | 목표 구현안으로 채택한다. PostgreSQL extension이라 source-of-truth/projection 모델에 적합하다. |
| Graph DB를 source of truth로 사용 | 폐기. 원본 업무 데이터, audit, user correction, workflow state는 PostgreSQL에 남아야 한다. |

---

## 영향

- 구현 전 `canonical_entities`, `entity_aliases`, `entity_links`, `entity_merge_events` 같은 PostgreSQL registry 설계를 먼저 수행한다.
- `RetrieverType.GRAPH` 추가는 Graph proof와 baseline 비교 평가 후에만 진행한다.
- Graph 장애 시 core mail workflow와 PostgreSQL/Qdrant baseline routing은 계속 동작해야 한다.
- Graph node/edge에는 source, evidence, confidence, confirmed, version, valid_from/valid_to를 남긴다.
- Graph 도입이 자동 배정 threshold 완화를 의미하지 않는다.

---

## 변경 판단 기준

Graph 구현을 진행할 조건:

- canonical registry와 entity alias/linking schema가 확정된다.
- false merge/false split 평가셋과 사람 검토 복구 흐름이 준비된다.
- Apache AGE projection을 PostgreSQL에서 idempotent하게 rebuild할 수 있다.
- baseline 대비 Top-1 accuracy, Top-3 recall, review-required rate, explanation quality가 개선된다.
- auto-assignment precision 0.95 이상을 유지한다.
- projection lag와 Graph query latency가 운영 처리량에 영향을 주지 않는다.
- Graph 장애 fallback이 검증된다.
- canonical entity false merge 위험을 사람이 검토하고 복구할 수 있다.

Apache AGE 목표 구현안을 재검토할 조건:

- PostgreSQL extension 설치가 고객 운영 정책과 맞지 않는다.
- PostgreSQL 버전 호환성이 실제 배포 버전과 맞지 않는다.
- 2~3 hop traversal P95 latency가 routing 목표를 초과한다.
- graph projection rebuild 시간이 운영 복구 목표를 초과한다.
- openCypher 기능 또는 Python client ergonomics가 구현 속도를 크게 떨어뜨린다.

Graph 자동 배정 의존도를 낮출 조건:

- baseline 대비 담당자 후보 품질 개선이 작다.
- entity resolution 품질이 낮아 오배정 위험을 키운다.
- Graph 결과 provenance가 운영자가 검토하기 어렵다.

---

## 관련 문서

- [Routing Knowledge Graph Architecture](../architecture/graph-routing-architecture.md)
- [Agentic RAG Mail Decision System](../architecture/agentic_rag_mail_decision_system.md)
- [DECISION-001 PostgreSQL을 원본 업무 데이터 저장소로 사용](DECISION-001-postgresql-primary-store.md)
- [DECISION-002 Qdrant를 벡터 검색 저장소로 사용](DECISION-002-qdrant-vector-store.md)

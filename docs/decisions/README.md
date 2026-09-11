# 기술 의사결정 기록

## 문서 목적

이 디렉터리는 CoRA Mail Agent의 주요 기술 선택과 변경 근거를 기록한다. 목표 아키텍처는 [Agentic RAG Mail Decision System](../architecture/agentic_rag_mail_decision_system.md)을 따른다.

## 작성 형식

| 항목 | 설명 |
|---|---|
| 상태 | 제안, 채택, 보류, 대체, 폐기 |
| 맥락 | 이 결정을 해야 하는 배경 |
| 결정 | 현재 선택 |
| 근거 | 선택 이유 |
| 대안 | 검토한 다른 선택지 |
| 영향 | 장점, 제약, 후속 작업 |
| 변경 판단 기준 | 선택을 유지하거나 바꿀 기준 |

## 의사결정 목록

| ID | 제목 | 상태 |
|---|---|---|
| DECISION-001 | PostgreSQL을 원본 업무 데이터 저장소로 사용 | 채택 |
| DECISION-002 | Qdrant를 벡터 검색 저장소로 사용 | 채택 |
| DECISION-003 | FastAPI 기반 Python API 서버 사용 | 채택 |
| DECISION-004 | 고객 내부 로컬 LLM Gateway 사용 | 채택 |
| DECISION-005 | PostgreSQL 실행 기록과 OpenTelemetry 기반 관찰 | 채택 |
| DECISION-006 | `Mail Decision Run`을 최상위 AI 실행 단위로 사용 | 채택 |
| DECISION-007 | 정확 검색·규칙 검색·벡터 검색을 결합한 Agentic Retrieval 사용 | 채택 |
| DECISION-008 | 담당자 후보 계산과 자동 배정 정책을 LLM과 분리 | 채택 |
| DECISION-009 | 합성 조직·메일·첨부·정답 데이터로 초기 평가 기반 구축 | 채택 |
| DECISION-010 | 규칙 기반 데모 Worker를 목표 AI 아키텍처에서 폐기 | 채택 |
| DECISION-011 | Routing Knowledge Graph 목표 설계 채택 | 대체 |

## 현재 결정 요약

| 영역 | 결정 |
|---|---|
| 원본 업무 데이터 | PostgreSQL |
| 벡터 검색 | Qdrant |
| API 서버 | FastAPI |
| 구조화 검증 | Pydantic |
| 로컬 AI 호출 | `app/llm/` OpenAI 호환 Gateway |
| 텍스트·Vision 실행 | 고객 내부 모델 서버; 개발은 Ollama 허용, 운영 실행기는 성능 평가 후 선택 |
| Agent 실행 단위 | `Mail Decision Run` |
| Orchestrator | 결정적 상태 머신; 구현 시 LangGraph를 우선 후보로 평가 |
| Retrieval | exact match + routing rules + Qdrant + reranker + 최대 3회 재계획 |
| 담당자 배정 | 조직 저장소 후보만 사용, 결정적 점수와 정책, Validation Agent 결합 |
| 관찰 | PostgreSQL node 기록 + OpenTelemetry trace ID |
| 평가 | 합성 평가셋과 실제 운영 평가를 분리 |
| Graph DB | 제품 선택 보류. Knowledge Graph는 우선 Assignment Context Retrieval 가설로 검증 |

## 채택한 핵심 원칙

### 하나의 통합 실행

첨부파일 분석, 사실 추출, 검색, 요약, 분류, 담당자 배정, 검증을 독립 작업으로 실행하지 않는다. 동일한 실행 ID, 사실, 근거, 검색 문맥을 공유한다.

### 로컬 LLM은 필수 실행 경로

규칙 기반 분류나 문자열 요약은 데모 화면 검증에만 사용된 임시 코드다. 운영 목표 기능은 로컬 텍스트 LLM 또는 Vision LLM의 구조화 출력을 사용하고 모델·프롬프트·workflow version을 기록한다.

### RAG는 담당자 배정의 근거 계층

벡터 유사도만으로 담당자를 고르지 않는다. 고객·도메인·제품·프로젝트 정확 일치와 명시적 라우팅 규칙을 먼저 조회하고, 과거 확정 사례 의미 검색은 보완 신호로 사용한다.

### LLM과 조직 정책 분리

LLM은 메일 의미를 구조화하고 검색 계획과 검증을 지원한다. 사용자 후보 생성, 역량, 활성 상태, 점수 계산, 자동 배정 임계값은 신뢰 가능한 조직 데이터와 결정적 서비스가 담당한다.

### 합성 데이터 선행 구축

실제 수신 메일과 조직 데이터가 부족하다는 이유로 담당자 배정 구현을 미루지 않는다. 명시적으로 합성임을 표시한 담당자·역량·고객·제품·프로젝트·메일·첨부·정답 데이터를 만들어 구현과 평가를 진행한다.

## 보류 중인 결정

다음 항목은 실제 하드웨어와 평가 결과를 보고 확정한다.

- 운영 텍스트 LLM과 Vision LLM 모델명
- vLLM과 llama.cpp server 중 운영 실행기
- 임베딩·reranker 모델
- LangGraph 채택 여부와 자체 상태 머신 비교
- Phoenix와 Langfuse 중 보조 관찰 UI
- 자동 배정 임계값의 업무 유형별 세분화
- Knowledge Graph context retrieval이 baseline 대비 담당자 배정 품질과 설명 가능성을 개선하는지 여부
- Graph DB 제품 선택과 Apache AGE/Neo4j/Memgraph 비교
- canonical entity registry와 entity alias merge 정책

## 온프레미스 원칙

- 업무 메일 원문과 첨부파일은 내부 저장소에 둔다.
- 텍스트 LLM, Vision LLM, 임베딩, reranker는 고객 내부 또는 명시적으로 승인된 환경에서 실행한다.
- trace와 평가 데이터에는 민감 정보 마스킹 정책을 적용한다.
- 외부 SaaS 연동은 별도 승인 없이는 운영 경로에 포함하지 않는다.

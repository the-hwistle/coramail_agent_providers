# LLM 프레임워크 후보

## 문서 목적

이 문서는 노트북에서 직접 실험해볼 LLM 프레임워크 후보를 정리한다.

현재 목표는 이메일 분석 데모에 필요한 기능을 기준으로 후보를 좁히고, 초기 구현에서 채택할 방식을 명확히 하는 것이다.

---

## 비교 기준

노트북에서는 다음 기준으로 후보를 비교한다.

| 기준 | 확인할 내용 |
|---|---|
| Ollama 연동 | 로컬 모델 호출이 간단한가 |
| 구조화 출력 | Pydantic 또는 JSON schema 형태로 안정적인 출력을 받을 수 있는가 |
| 재시도 처리 | JSON 파싱 실패, schema validation 실패를 다루기 쉬운가 |
| 프롬프트 관리 | 프롬프트 이름, 버전, 입력 변수를 관리하기 쉬운가 |
| trace 연동 | Phoenix, Langfuse, OpenTelemetry와 연결하기 쉬운가 |
| 프레임워크 의존성 | 도메인 코드가 특정 프레임워크 객체에 과하게 묶이는가 |
| workflow 확장 | 사람 검토, 재시도, 단계별 상태 저장으로 확장하기 쉬운가 |
| 학습 비용 | 처음 개발하는 LLM 애플리케이션에서 이해하고 디버깅하기 쉬운가 |

---

## 1차 후보

### C-01 Ollama 직접 호출 + LLM 호출 전용 모듈

Ollama API를 직접 호출하되, 호출 코드는 `app/llm/` 아래에 모은다. 이메일 분석 Agent와 Service는 `app/llm/`의 함수를 통해 LLM을 호출한다.

| 항목 | 판단 |
|---|---|
| 장점 | 구조가 단순하고 프레임워크 의존성이 낮다. |
| 장점 | 데모에서 필요한 이메일 분석 호출을 빠르게 만들 수 있다. |
| 장점 | OpenAI 호환 API 방식으로 외부 모델 전환 가능성을 남길 수 있다. |
| 주의점 | structured output, retry, tracing을 직접 설계해야 한다. |
| 판단 | fallback 또는 진단용 구현으로 유지한다. |

### C-02 LangChain + langchain-ollama

LangChain의 chat model interface와 `langchain-ollama`를 사용한다.

| 항목 | 판단 |
|---|---|
| 장점 | prompt template, structured output, parser, callback 구성을 사용할 수 있다. |
| 장점 | Phoenix, Langfuse, LangSmith 연동 자료가 많다. |
| 장점 | 여러 모델 provider로 확장하기 쉽다. |
| 주의점 | 도메인 코드가 LangChain Runnable 구조에 묶일 수 있다. |
| 판단 | 초기 전면 도입은 보류한다. structured output, retry, tracing 반복 비용이 실제로 커질 때 확대한다. |

### C-03 LangGraph

LangGraph로 이메일 분석 workflow를 상태 그래프 형태로 구성한다.

| 항목 | 판단 |
|---|---|
| 장점 | 단계별 상태, 분기, 재시도, 사람 검토 재개 흐름에 적합하다. |
| 장점 | 향후 복잡한 Agent workflow로 확장하기 좋다. |
| 주의점 | 첫 데모 단계에서는 구조가 커질 수 있다. |
| 판단 | 초기 도입은 보류한다. 사람 검토 후 재개, checkpoint, 장기 실행 workflow가 필요해질 때 도입한다. |

---

## 2차 후보

### C-04 OpenAI SDK 호환 방식

Ollama의 OpenAI 호환 API를 OpenAI SDK 형태로 호출한다.

| 항목 | 판단 |
|---|---|
| 장점 | 로컬 Ollama endpoint를 표준 client 형태로 호출할 수 있다. |
| 장점 | `app/llm/` 내부 구현으로 분리하기 좋다. |
| 주의점 | Ollama 호환 API의 세부 지원 범위를 확인해야 한다. |
| 판단 | 초기 채택안. `app/llm/` 내부 기본 구현으로 사용한다. |

### C-05 LlamaIndex

문서 검색과 RAG 중심 기능이 커질 때 검토한다.

| 항목 | 판단 |
|---|---|
| 장점 | 문서 ingestion, index, retrieval 중심 기능에 강점이 있다. |
| 주의점 | 현재 1차 목표는 메일 분류, 중요도 산정, `assignee_area` 제안이다. |
| 판단 | RAG와 문맥 검색이 본격화될 때 별도 RAG 계층으로 검토한다. |

---

## 노트북 실험 순서

1. 같은 샘플 이메일 3건을 준비한다.
2. 공통 출력 스키마를 정의한다.
3. C-01 Ollama 직접 호출을 실험한다.
4. C-02 LangChain + `langchain-ollama`를 실험한다.
5. 두 방식의 코드량, 실패 처리, 출력 안정성, trace 연결 난이도를 비교한다.
6. D3 이후 사람 검토와 재시도 workflow가 복잡해지면 C-03 LangGraph를 실험한다.

---

## 결정

초기 구현은 C-04 OpenAI SDK 호환 방식을 `app/llm/` 내부 구현으로 채택한다.

Agent와 Service는 OpenAI SDK, Ollama SDK, LangChain, LangGraph 객체를 직접 알지 않는다. 이메일 분석 코드는 `app/llm/client.py`의 프로젝트 전용 인터페이스만 호출한다.

| 선택 | 조건 |
|---|---|
| C-04 채택 | 로컬 Ollama를 표준 client 형태로 호출하면서 프레임워크 종속성을 최소화한다. |
| C-01 유지 | Ollama native API 차이를 확인하거나 장애 진단이 필요할 때 fallback으로 사용한다. |
| C-02 확대 | structured output, retry, tracing에서 LangChain 사용 이점이 구현 비용보다 커질 때 사용한다. |
| C-03 도입 | 사람 검토, 재시도, 단계별 상태 저장과 재개가 빠르게 복잡해질 때 사용한다. |
| C-05 도입 | Qdrant 기반 문맥 검색과 RAG 답변 생성이 핵심 기능이 될 때 사용한다. |

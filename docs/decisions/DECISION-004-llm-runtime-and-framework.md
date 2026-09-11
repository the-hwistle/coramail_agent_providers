# DECISION-004 LLM 런타임과 프레임워크 선택 기준

## 상태

채택

---

## 맥락

CoRA Mail Agent는 처음 개발하는 LLM 애플리케이션이며, 현재 LLM 런타임과 프레임워크 선택을 확정해야 한다.

초기에는 Ollama를 사용해 로컬 모델을 실행해 왔다. 구현 단계에서 `langchain-ollama`, LangChain, LangGraph, OpenAI 호환 API 직접 호출 중 어떤 방식을 기준으로 삼을지 결정해야 한다.

이 결정은 다음 이유로 중요하다.

- Agent 코드가 특정 프레임워크에 강하게 묶일 수 있다.
- 구조화 출력, 재시도, 도구 호출, trace 기록 방식이 달라진다.
- 로컬 모델 실행 방식과 프레임워크를 바꿔 쓰기 어려워질 수 있다.
- 데모 이후 운영 확장 시 마이그레이션 비용이 커질 수 있다.

---

## 결정

초기 구현에서는 범용 LLM 프레임워크를 전면 채택하지 않는다.

대신 `app/llm/` 아래에 LLM 호출 전용 모듈을 두고, 이 모듈 내부에서 OpenAI SDK 호환 호출을 1차 구현 방식으로 사용한다.

Agent와 Service는 Ollama, LangChain, OpenAI SDK 호환 호출 코드를 직접 사용하지 않고 이 모듈을 통해 LLM을 호출한다. 이렇게 하면 나중에 OpenAI 호환 로컬 endpoint, Ollama native API, `langchain-ollama` 중 어느 방식으로 바꿔도 이메일 분석 Service의 변경 범위를 줄일 수 있다.

1차 데모에서는 Ollama의 OpenAI 호환 API를 OpenAI SDK 형태로 호출한다. Ollama native API 직접 호출은 fallback 또는 진단용 구현으로만 둔다.

`langchain-ollama`와 LangChain은 다음 조건에서만 사용한다.

- LangChain의 callback/tracing 연동이 필요하다.
- LangChain chat model interface를 사용한 구조화 출력 실험이 필요하다.
- prompt-template, parser, runnable 조합이 실제 코드량을 줄인다는 근거가 생긴다.

LangGraph는 D3 AI 분석 데모 이후 다음 조건이 확인되면 도입을 검토한다.

- 여러 Agent 단계가 상태를 공유해야 한다.
- 사람 검토를 포함한 장기 실행 workflow가 필요하다.
- 재시도, 분기, persistence가 코드에서 복잡해진다.
- 단순 함수 호출 조합으로 처리 흐름을 설명하기 어려워진다.

LlamaIndex는 이메일/첨부파일 문맥 검색과 RAG가 본격화되는 Phase 6 이후 별도 기능 영역에서 검토한다. 초기 이메일 요약, 분류, 중요도 산정, 사람 검토 loop의 중심 프레임워크로는 채택하지 않는다.

---

## 권장 초기 구조

초기 코드는 다음 구조를 따른다.

```text
app/
  agents/
    email_analysis_agent.py
  services/
    email_analysis_service.py
  llm/
    client.py
    openai_compatible_client.py
    ollama_native_client.py
    schemas.py
  schemas/
    email_analysis.py
```

`app/llm/client.py`는 프로젝트 안에서 LLM을 호출할 때 사용할 입력과 출력 형식을 정의한다.

```python
def generate_structured(
    *,
    model: str,
    prompt_name: str,
    prompt_version: str,
    messages: list[dict],
    output_schema: type,
    temperature: float,
) -> object:
    ...
```

예를 들어 이메일 분석 Agent는 다음 사실만 알면 된다.

- 어떤 모델을 사용할지
- 어떤 프롬프트 이름과 버전을 사용할지
- 어떤 메시지를 보낼지
- 어떤 출력 스키마로 결과를 받을지

OpenAI 호환 로컬 endpoint를 호출하는지, Ollama native API를 직접 호출하는지, `langchain-ollama`를 사용하는지는 `app/llm/` 내부 구현에서 결정한다.

---

## 근거

- Ollama는 OpenAI 호환 API 일부를 제공하므로 OpenAI API 형태의 클라이언트로 로컬 모델을 호출할 수 있다.
- Ollama의 OpenAI 호환 API는 chat completions, streaming, JSON mode, tools 등 초기 데모에 필요한 기능을 지원한다.
- OpenAI SDK 호환 호출은 특정 agent framework가 아니라 transport/client 선택이므로, 도메인 코드를 LangChain Runnable 또는 LangGraph state 객체에 묶지 않는다.
- LangChain은 공통 chat model interface와 structured output wrapper를 제공한다.
- LangChain을 전면 도입하면 빠르게 Agent를 만들 수 있지만, 도메인 로직이 LangChain 객체와 Runnable 구성에 묶일 수 있다.
- LangGraph는 durable execution, persistence, human-in-the-loop이 필요한 workflow에 적합하다.
- LlamaIndex는 index, retrieval, query engine 중심 기능에 강점이 있지만, 현재 우선순위는 RAG보다 이메일 분석 결과를 저장, 검증, 수정하는 loop다.
- 현재 1차 데모 목표는 이메일 분석, 분류, 중요도 산정, `assignee_area` 제안이다. 이 범위는 LLM 호출 전용 모듈과 일반 Python 서비스 구조로 먼저 구현할 수 있다.

---

## 대안

| 대안 | 판단 |
|---|---|
| OpenAI SDK 호환 호출 + `app/llm/` 격리 | 채택. 로컬 Ollama를 표준 client 형태로 호출하면서 도메인 코드를 프레임워크에 묶지 않는다. |
| Ollama 직접 호출만 사용 | 미채택. 데모는 빠르지만 외부 모델 전환, trace 연동, 구조화 출력 전략이 코드 곳곳에 흩어질 수 있다. |
| `langchain-ollama` 전면 사용 | 미채택. LangChain 생태계와 tracing 연동에는 유리하지만, 초기 코드가 프레임워크 중심 구조로 고정되는 비용이 크다. |
| LangGraph 즉시 도입 | 보류. 복잡한 workflow에는 유리하지만, 현재 데모의 첫 단계에서는 설계 비용이 이점보다 크다. |
| LlamaIndex 중심 구현 | 보류. RAG에는 강점이 있지만 현재 1차 목표는 메일 분류, 라우팅, 사람 검토 흐름이다. |

---

## 채택 기준

### 초기 채택

초기에는 `app/llm/` 아래에 LLM 호출 전용 모듈을 두고, 내부 구현은 OpenAI SDK 호환 호출을 기본값으로 한다.

### LangChain 채택 조건

다음 조건 중 2개 이상이 필요해지면 LangChain 사용을 확대한다.

- provider별 model wrapper를 직접 관리하는 비용이 커진다.
- structured output과 retry 구성이 반복된다.
- Phoenix 또는 Langfuse tracing 연동에 callback 기반 계층이 필요하다.
- prompt-template, parser, runnable 조합이 생산성을 높인다.

### LangGraph 채택 조건

다음 조건 중 2개 이상이 필요해지면 LangGraph를 도입한다.

- 분석 단계가 5개 이상으로 늘어난다.
- 단계별 상태 저장과 재시작이 필요하다.
- 사람 검토 이후 workflow 재개가 필요하다.
- 분기와 재시도 로직이 Service 코드에서 복잡해진다.

### LlamaIndex 채택 조건

다음 조건 중 2개 이상이 필요해지면 LlamaIndex를 별도 RAG 계층으로 도입한다.

- 이메일과 첨부파일을 chunking, indexing, retrieval pipeline으로 관리해야 한다.
- Qdrant 검색 결과를 LLM 답변 생성과 강하게 결합해야 한다.
- 단순 Qdrant client 직접 조회보다 query engine, retriever, response synthesis 구성이 생산성을 높인다.
- 문서 검색 품질 평가와 RAG 실험이 핵심 기능이 된다.

---

## 영향

- 초기 구현은 프레임워크 교체 가능성을 유지한다.
- 코어 도메인 로직은 OpenAI SDK, Ollama SDK, LangChain, LangGraph 객체를 직접 노출하지 않는다.
- Agent 출력은 Pydantic 스키마로 검증한다.
- LLM 호출 기록은 프레임워크와 별도로 PostgreSQL에 저장한다.
- LLMOps 도구는 OpenTelemetry 또는 별도 SDK를 통해 연결한다.
- 데모 이후 LangChain 또는 LangGraph를 도입해도 도메인 서비스 변경을 최소화한다.

---

## 변경 판단 기준

- Ollama 모델의 structured output 품질이 데모 요구를 충족하지 못한다.
- 온프레미스 환경에서 다른 로컬 모델 실행 방식이 필요하다.
- Agent workflow가 장기 실행과 사람 검토 재개를 요구한다.
- LLMOps 도구가 특정 프레임워크 연동을 강하게 요구한다.

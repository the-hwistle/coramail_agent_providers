# DECISION-005 LLMOps 관찰 및 평가 도구 선택 기준

## 상태

제안

---

## 맥락

CoRA Mail Agent는 LLM이 이메일 의도, 첨부파일 의미, 핵심 정보, 중요도, `assignee_area`를 판단한다.

LLM 결과는 확률적이며, 같은 코드와 같은 입력에서도 모델, 프롬프트, 검색 문맥, 출력 스키마에 따라 품질이 달라질 수 있다. 따라서 데모 단계부터 실행 기록, 실패 원인, 사용자 수정, 평가 데이터를 남겨야 한다.

필요한 LLMOps 기능은 다음과 같다.

- LLM 호출 입력과 출력 기록
- 프롬프트 이름과 버전 기록
- 모델 이름과 생성 설정 기록
- token 사용량과 latency 기록
- tool 호출과 retrieval 단계 기록
- schema validation 실패 기록
- 사용자 수정과 사람 검토 기록
- 샘플 데이터 기반 평가
- 프롬프트와 모델 변경 비교

---

## 결정

초기에는 PostgreSQL 실행 기록과 OpenTelemetry trace를 기본으로 설계한다.

Phoenix와 Langfuse는 D3 AI 분석 데모와 D4 사람 검토 데모에서 비교한 뒤 최종 선택한다.

---

## 초기 구조

초기 LLMOps 구조는 다음과 같다.

| 계층 | 역할 |
|---|---|
| PostgreSQL | 영구 감사 기록, AI 실행 결과, 사용자 수정, 평가 후보 저장 |
| OpenTelemetry | 요청 단위 trace와 span 표준화 |
| Phoenix 또는 Langfuse | trace 확인, 평가, prompt 실험, dashboard 비교 |
| 테스트 코드 | deterministic schema validation과 회귀 테스트 |

PostgreSQL 기록은 운영 감사와 재현성의 기준으로 사용한다. Phoenix와 Langfuse는 디버깅, 실험, 평가 화면, 프롬프트 관리 편의성을 비교한다.

---

## 근거

- Phoenix는 trace, evaluation, prompt engineering, datasets & experiments 기능을 제공한다.
- Phoenix는 OpenTelemetry와 OpenInference instrumentation 기반으로 trace를 받을 수 있다.
- Phoenix는 LangChain, LangGraph, OpenAI 등 주요 LLM 생태계와 연동할 수 있다.
- OpenTelemetry는 특정 LLMOps 제품에 종속되지 않는 관찰 데이터 표준으로 사용할 수 있다.
- Langfuse는 tracing, prompt management, evaluation, metrics 기능을 제공하므로 Phoenix와 함께 비교한다.
- 초기 프로젝트는 로컬 데모와 실험 검증이 중요하므로 self-hosted 또는 로컬 실행이 쉬운 도구를 우선한다.

---

## 대안

| 대안 | 판단 |
|---|---|
| PostgreSQL 로그만 사용 | 감사 기록에는 충분하다. trace UI, span 분석, 평가 실험 관리는 별도 도구가 필요하다. |
| Phoenix | OpenTelemetry 기반 trace, eval, dataset, experiment 흐름을 확인한다. |
| Langfuse | tracing, prompt management, score, dashboard 기능이 강하고 self-host 가능하다. Phoenix와 함께 비교한다. |
| LangSmith | LangChain/LangGraph 중심 개발에는 강점이 있다. LangChain 도입 여부가 확정된 뒤 재검토한다. |
| 직접 만든 대시보드 | 요구에 맞출 수 있지만 초기 개발 비용이 크고 LLMOps 표준 기능을 직접 구현해야 한다. |

---

## 채택 기준

### Phoenix 확인 항목

Phoenix는 다음 기능을 확인한다.

- 이메일 1건 분석 trace 확인
- LLM 호출 span 확인
- retrieval 또는 tool 호출 span 확인
- schema validation 실패 기록 확인
- 사용자 수정 결과와 trace 연결 가능성 확인
- 샘플 데이터 기반 evaluation 실행 가능성 확인

### Langfuse 확인 항목

Langfuse는 다음 기능을 확인한다.

- 이메일 1건 분석 trace 확인
- 프롬프트 이름과 버전 관리 확인
- LLM 호출별 score 또는 평가값 저장 확인
- 사용자 수정 결과와 trace 연결 가능성 확인
- dashboard에서 비용, 지연 시간, 실패율 확인 가능성 확인

### 최종 도구 선택 기준

다음 기준으로 Phoenix, Langfuse, LangSmith를 비교한다.

| 기준 | 설명 |
|---|---|
| 로컬 또는 self-host 운영 | 온프레미스 운영 가능성 |
| OpenTelemetry 호환성 | 도구 교체 가능성과 trace 표준화 |
| 프롬프트 버전 관리 | 프롬프트 변경과 결과 비교 |
| 평가 데이터 관리 | 샘플과 실제 운영 데이터를 평가셋으로 관리 |
| 사용자 피드백 연결 | 사람 수정과 AI 결과를 비교 |
| 비용·지연 시간 분석 | 모델별 token, latency, cost 비교 |
| 프레임워크 독립성 | LangChain 미사용 또는 부분 사용 상황 대응 |

---

## 영향

- AI 실행 결과는 애플리케이션 DB에 먼저 남긴다.
- trace id를 AI 실행 결과, processing job, 사용자 수정 이력과 연결한다.
- LLMOps 도구가 바뀌어도 데이터 재현성과 감사 기록을 유지한다.
- 데모에서는 Phoenix와 Langfuse 중 최소 하나를 연결해 LLM 호출과 Agent 실행 과정을 시각적으로 확인한다.
- 최종 LLMOps 도구는 실제 데모 구현 후 관찰 요구를 기준으로 결정한다.

---

## 변경 판단 기준

- Phoenix가 필요한 prompt management 또는 dashboard 요구를 충족하지 못한다.
- Langfuse의 score, prompt, dashboard 기능이 프로젝트 요구에 더 적합하다고 확인된다.
- LangChain/LangGraph를 전면 도입해 LangSmith 사용 이점이 커진다.
- 고객 환경에서 특정 도구의 self-host 운영이 제한된다.

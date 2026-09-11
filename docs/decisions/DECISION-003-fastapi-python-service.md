# DECISION-003 FastAPI 기반 Python API 서버 사용

## 상태

채택

---

## 맥락

CoRA Mail Agent는 웹 화면, API, Agent 실행, 데이터 저장, LLM 호출, 평가 로그를 하나의 Python 중심 애플리케이션으로 시작한다.

초기 데모에서는 빠르게 화면과 API를 연결해야 하며, 이후 운영 준비 단계에서는 스키마 검증, 테스트, 비동기 작업, OpenAPI 문서화가 필요하다.

---

## 결정

FastAPI를 API 서버 프레임워크로 사용한다.

데이터 모델 검증에는 Pydantic을 사용하고, PostgreSQL 접근에는 SQLAlchemy를 사용한다.

---

## 근거

- FastAPI는 Python type hint와 Pydantic을 기반으로 요청·응답 스키마를 정의할 수 있다.
- OpenAPI 문서가 자동 생성되어 데모와 API 계약 검증에 유리하다.
- 테스트 클라이언트, background task, static file serving 등 초기 데모에 필요한 기능을 제공한다.
- Python 기반 LLM SDK, Qdrant client, SQLAlchemy, OpenTelemetry 연동과 맞다.
- Agent, Service, Repository 구조를 Python 패키지 안에서 명확히 나눌 수 있다.

---

## 대안

| 대안 | 판단 |
|---|---|
| Flask | 단순 API에는 충분하다. 요청·응답 스키마와 OpenAPI 자동 문서화 측면에서는 FastAPI가 더 적합하다. |
| Django | 관리자 화면과 ORM 통합에는 강점이 있지만 초기 데모와 LLM 중심 서비스 구조에는 무겁다. |
| Node.js/Next.js API | 프론트엔드 통합에는 강점이 있지만 Python LLM 생태계와 데이터 처리 실험을 중심으로 하는 현재 방향과 맞지 않는다. |

---

## 영향

- API 스키마는 Pydantic 모델로 관리한다.
- 화면이 기대하는 응답 구조를 OpenAPI와 테스트로 검증한다.
- Agent 출력 스키마도 Pydantic으로 검증한다.
- SQLAlchemy Session 경계를 Service 또는 Repository 계층에서 명확히 관리한다.

---

## 변경 판단 기준

- 프론트엔드 중심 애플리케이션으로 전환되어 Python API 서버의 역할이 축소된다.
- 고객 운영 환경에서 Python 서버 운영이 제한된다.
- 대규모 실시간 처리 요구가 생겨 별도 이벤트 기반 백엔드가 필요하다.

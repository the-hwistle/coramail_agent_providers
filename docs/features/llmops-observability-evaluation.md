# F-11 LLMOps Observability And Evaluation

## Purpose

AI 실행의 입력, 출력, 프롬프트 버전, 모델 설정, 검색 문맥, 지연 시간, 실패, 사용자 수정 결과를 기록해 품질을 재현하고 비교한다.

## Users

- AI 운영·개발 담당자
- 업무 관리자

## Related Scenarios

- SC-06 AI 오분류 수정 및 평가 데이터 축적
- SC-07 AI 분석 실패와 안전한 대체 흐름
- SC-08 대량 메일 유입 시 우선순위 처리

## Input Data

- AI 실행 입력 payload
- LLM 출력과 schema validation 결과
- 프롬프트 이름과 버전
- 모델명과 생성 설정
- 검색 문맥과 점수
- 사용자 수정 결과

## Output Data

- trace id와 span id
- generation record
- token usage와 latency
- schema validation 실패 원인
- 평가 데이터 후보
- 평가 결과와 회귀 비교

## State

| 상태 | 의미 |
|---|---|
| `recorded` | 실행 기록 저장 |
| `validated` | 출력 schema 검증 성공 |
| `validation_failed` | 출력 schema 검증 실패 |
| `evaluation_candidate` | 평가 후보 |
| `evaluation_approved` | 평가 데이터 승인 |
| `regression_failed` | 변경 평가 실패 |

## Normal Flow

1. AI 작업 시작 시 trace id를 생성하거나 상위 요청에서 전달받는다.
2. 입력 payload hash, 프롬프트 버전, 모델 설정을 기록한다.
3. retrieval, tool, LLM 호출을 span으로 기록한다.
4. 출력 schema validation 결과를 저장한다.
5. AI 결과를 기능별 결과 테이블에 저장하고 trace id와 연결한다.
6. 사용자 수정이 발생하면 원래 AI 결과와 연결한다.
7. 승인된 수정 사례를 평가 데이터셋에 포함한다.
8. 프롬프트 또는 모델 변경은 동일 평가셋으로 비교한다.

## Exception Flow

- LLMOps 외부 도구가 실패해도 애플리케이션 결과 저장은 계속한다.
- 민감 정보는 외부 trace 도구 반출 전 마스킹 정책을 적용한다.
- schema validation 실패 원본 출력은 보존하되 화면에는 안전한 요약만 표시한다.

## Human Review Conditions

- 특정 업무 유형의 수정률이 급증한다.
- 같은 프롬프트 버전에서 schema validation 실패가 반복된다.
- 평가 회귀가 주요 시나리오 성능 저하를 탐지한다.
- 긴급 또는 서비스 메일의 false negative가 발생한다.

## API Contract

운영 목표:

- `GET /api/llm/runs?email_uid=`
- `GET /api/llm/runs/{run_id}`
- `GET /api/evaluations/datasets`
- `POST /api/evaluations/run`
- `GET /api/evaluations/runs/{run_id}`

## Storage

- 영구 AI 결과: `email_analysis_results`, `attachment_analysis_results`
- 작업 상태: `processing_jobs`
- 사용자 수정과 감사: `audit_logs`
- trace: OpenTelemetry, Phoenix 또는 Langfuse 후보
- 평가 데이터: D4/D5에서 확정할 dataset 저장소

## Test Criteria

- 모든 AI 결과는 모델명과 프롬프트 버전을 가진다.
- schema validation 실패는 실패 상태로 기록된다.
- 사용자 수정 사례는 원래 AI 결과로 역추적 가능하다.
- 평가셋은 같은 입력으로 재실행할 수 있다.

## Web Report

- 첫 화면은 스크린샷 한 장으로 현재 평가셋, 생성 시각, 핵심 합격 기준, 실행 성공, 사람 검토 비율, 데이터 누수 검사와 주요 실패 원인을 확인할 수 있어야 한다.
- `report.passed`는 리포트 파일의 무결성 결과일 뿐 제품 품질 합격으로 표시하지 않는다. 제품 품질 상태는 문서화된 업무 유형, 담당자 Top-1, 후보 recall, 자동 배정 정확도 기준을 각각 판정한다.
- 분모가 0인 지표는 0%가 아니라 `측정 안 됨`으로 표시하고 전체 품질 합격으로 계산하지 않는다.
- 케이스 목록은 기대값과 실제값, 성공 여부, 우선 확인할 실패 원인만 기본 노출한다. 모델, collection, 원시 trace 같은 개발 정보는 상세 영역으로 분리한다.
- 합성 평가 결과는 운영 성능으로 오해되지 않도록 화면에 명시한다.
- Mail Decision의 업무 유형 평가값은 `decision_output.classification.primary_type`을 기준으로 변환한다. 폐기된 평면 `decision_output.primary_type`을 평가 계약으로 사용하지 않는다.
- Fact Extraction 또는 Decision 출력 계약이 바뀌면 저장된 prediction을 다시 score하는 데 그치지 않고 동일 고정 케이스를 런타임에서 재실행해 report, cases, trace를 함께 갱신한다.
- 평가 leakage 검사는 target/source id overlap, content overlap, answer-like payload 노출을 탐지하는 dataset 검증 장치다. 이 검사는 운영 runtime safety를 대체하지 않는다. Evaluation run에서 Qdrant retrieval을 사용할 때는 `RetrievalScope`로 `dataset_type=evaluation`, `evaluation=true`, 지정된 `dataset_version`을 mandatory filter로 강제한다.
- Production Qdrant verification은 `python -m app.tools.qdrant_similar_case_index verify`로 수행한다. 리포트에는 required provenance 누락, dataset type 분포, production-invalid synthetic/evaluation flag, production account scope 누락을 포함한다.

## LLMOps Notes

DECISION-005에 따라 초기에는 PostgreSQL 기록과 OpenTelemetry trace를 기본으로 하고, Phoenix와 Langfuse를 D3/D4에서 비교한다.

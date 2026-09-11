# F-10 Processing Jobs And Failure Management

## Purpose

수집, 분석, 첨부파일 처리, 색인, 라우팅 같은 비동기 작업의 상태와 실패 원인을 추적한다. 한 단계의 실패가 원본 메일 조회나 다른 메일 처리를 중단시키지 않도록 한다.

## Users

- 업무 관리자
- AI 운영·개발 담당자

## Related Scenarios

- SC-07 AI 분석 실패와 안전한 대체 흐름
- SC-08 대량 메일 유입 시 우선순위 처리

## Input Data

- 작업 유형
- 대상 source type과 source id
- 실행 예정 시각
- 최대 재시도 횟수
- 작업 metadata

## Output Data

- 작업 상태
- 시도 횟수
- 시작/완료 시각
- 실패 원인
- 마지막 성공 단계
- 재시도 가능 여부

## State

| 상태 | 의미 |
|---|---|
| `pending` | 실행 대기 |
| `running` | 실행 중 |
| `success` | 성공 |
| `failed` | 최종 실패 또는 재시도 대기 전 실패 |
| `cancelled` | 취소 |

## Normal Flow

1. 후속 처리가 필요한 이벤트가 작업을 등록한다.
2. worker가 due 상태의 작업을 가져간다.
3. `attempt_count`, `started_at`, `status`를 갱신한다.
4. 작업을 실행하고 결과를 저장한다.
5. 성공하면 `success`와 `completed_at`을 기록한다.
6. 실패하면 오류 유형과 message를 저장하고 재시도 여부를 결정한다.

## Exception Flow

- 재시도 가능한 오류는 `scheduled_at`을 뒤로 미룬다.
- 최대 시도 횟수를 넘으면 최종 실패로 남긴다.
- 작업 실행 중 프로세스가 종료되면 stale running 작업 복구 정책을 적용한다.
- 부분 성공은 성공한 결과를 보존하고 실패 단계만 재시도한다.

## Human Review Conditions

- 최대 재시도 횟수를 모두 사용했다.
- 분류, 첨부 분석, 라우팅 실패가 업무 처리에 영향을 준다.
- 긴급 후보 메일의 분석이 실패했다.
- 같은 오류가 반복 발생한다.

## API Contract

현재 구현된 API:

- `GET /api/jobs?status=&job_type=`
- `GET /api/jobs/{job_id}`
- `GET /api/emails/{email_uid}/jobs`
- `POST /api/jobs/run-pending?limit=`
  - 현재 pending email analysis job을 worker로 실행한다.
  - `metadata.analysis_type = classification` 또는 `executive_summary`인 job을 처리한다.

운영 목표:

- `POST /api/jobs/{job_id}/retry`
- `POST /api/jobs/{job_id}/cancel`

## Storage

- 작업 상태: `processing_jobs`
- 실패와 사용자 조치 감사: `audit_logs`
- 기능별 결과 테이블: 각 feature 저장소

## Test Criteria

- 실패 작업은 오류 메시지와 attempt count를 가진다.
- 원본 메일 저장 성공 후 AI 실패가 메일 조회를 막지 않는다.
- 재시도는 최대 횟수를 넘지 않는다.
- 한 메일의 실패가 다른 메일 작업을 중단시키지 않는다.
- worker 실행 후 성공 job은 `status = success`, `completed_at`을 가진다.

## LLMOps Notes

단계별 실패율, 재시도 성공률, queue 대기 시간, P95/P99 처리 시간, 오류 유형 분포를 기록한다.

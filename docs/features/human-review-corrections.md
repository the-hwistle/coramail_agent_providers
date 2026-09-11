# F-09 Human Review And Corrections

## Purpose

사용자가 AI 분석 결과를 확인하고 잘못된 업무 레이블, 요약, 긴급도, 핵심 정보, 담당 대상을 수정할 수 있게 한다. 수정 전 AI 결과와 사용자 확정 결과는 분리해 저장하며, 사용자 수정 사례는 평가 데이터 후보와 모델 개선 자료로 축적한다.

이 기능의 핵심 원칙은 원본 메일과 최초 AI 결과를 보존하는 것이다. 사용자가 값을 수정하더라도 AI 결과를 덮어쓰지 않고, 별도 source 또는 이력으로 사용자 확정값을 남긴다.

## Users

- 업무 담당자
- 업무 관리자
- AI 운영·개발 담당자

## Related Scenarios

- SC-06 AI 오분류 수정 및 평가 데이터 축적
- SC-07 AI 분석 실패와 안전한 대체 흐름
- SC-01 신규 문의 메일 자동 분석
- SC-02 견적의뢰서 첨부 메일 분석
- SC-03 발주 메일 식별 및 담당자 연결
- SC-05 클레임 및 긴급 서비스 요청 탐지

## Input Data

현재 상태:

- 아직 사용자 수정 저장 API와 UI는 구현되어 있지 않다.
- Inbox 상세 화면은 분류, 요약, 긴급도, 담당 상태를 표시하지만 수정 form은 제공하지 않는다.
- 데모 fixture의 expected labels는 운영상 사용자 수정값이 아니라 데모 기대값이다.

운영 목표 입력:

- 사용자가 선택한 `email_uid`
- 수정 대상 필드: 업무 레이블, 요약, 긴급도, 핵심 정보, 담당자, 검토 완료 상태
- 수정 전 현재 AI 결과 또는 자동 결과
- 수정 후 사용자 확정값
- 수정 사유 코드 또는 자유 입력 사유
- 수정 사용자 `user_id`
- 요청 추적 ID
- AI 결과의 모델명, 프롬프트 버전, 검색 문맥, 토큰 수, 실행 시간

## Output Data

| 필드 | 의미 |
|---|---|
| `correction_id` | 사용자 수정 이벤트 식별자 |
| `email_uid` | 수정 대상 메일 |
| `field_name` | 수정 대상 필드 |
| `before_value` | 수정 전 값 |
| `after_value` | 수정 후 값 |
| `reason` | 수정 사유 |
| `corrected_by_user_id` | 수정 사용자 |
| `corrected_at` | 수정 시각 |
| `review_status` | 검토 대기, 검토 완료, 평가 후보, 평가 승인, 평가 제외 |
| `linked_ai_result_id` | 수정 대상이 된 AI 결과 |
| `evaluation_candidate` | 평가 데이터 후보 여부 |

## Review State

| 상태 | 의미 |
|---|---|
| `review_required` | AI 또는 시스템이 사람 검토가 필요하다고 판단 |
| `review_pending` | 사용자가 아직 확인하지 않은 검토 대상 |
| `reviewed` | 사용자가 확인했고 수정이 없거나 수정 후 확정 |
| `corrected` | 사용자가 하나 이상의 AI 결과를 수정 |
| `evaluation_candidate` | 수정 사례가 평가 데이터 후보로 등록 |
| `evaluation_approved` | AI 운영 담당자가 평가 데이터로 승인 |
| `evaluation_excluded` | 오조작, 정책 불명확, 민감 정보 등으로 평가 데이터에서 제외 |

현재 PostgreSQL 스키마에는 전용 review/correction 테이블이 없다. 초기 운영 구현은 기존 이력 테이블과 `audit_logs`로 시작하되, 평가 데이터 승인 상태까지 관리하려면 별도 correction 또는 evaluation dataset 테이블이 필요하다.

## Normal Flow

1. 사용자가 Inbox 상세 화면에서 AI 결과를 확인한다.
2. 사용자가 업무 레이블, 요약, 긴급도, 핵심 정보 또는 담당자를 수정한다.
3. 사용자가 가능한 경우 수정 사유를 선택하거나 입력한다.
4. 시스템은 수정 전 값을 조회하고, 수정 대상 AI 결과 또는 자동 결과 ID를 연결한다.
5. 업무 레이블 수정은 `email_category_assignments`에 `source = user`인 새 current 행을 생성한다.
6. 담당자 수정은 `routing_assignments` 현재값을 갱신하고 `routing_events`에 `source = user` 이벤트를 추가한다.
7. 요약, 긴급도, 핵심 정보 수정은 최초 AI 결과와 분리된 사용자 확정값으로 저장한다.
8. 모든 수정은 `audit_logs`에 before/after payload와 actor를 기록한다.
9. 수정 사례는 평가 데이터 후보로 조회 가능해야 한다.
10. AI 운영 담당자는 후보 사례를 승인, 제외, 보류 상태로 관리한다.

## Exception Flow

- 수정 사유가 없어도 before/after 값과 사용자, 시각은 반드시 저장한다.
- 여러 사용자가 같은 필드를 수정하면 최종 current 값과 전체 이력을 모두 보존한다.
- 사용자가 AI 결과와 동일한 값으로 확정하면 correction이 아니라 review completion으로 기록한다.
- 민감 정보가 포함된 사례는 평가 데이터 후보로 만들되 승인 전 비식별화 필요 상태로 표시한다.
- 담당자 확정 이후 자동 라우팅 규칙이 바뀌어도 사용자 확정값을 자동 변경하지 않는다.
- 사용자가 실수로 수정한 경우 평가 데이터에서 제외할 수 있어야 한다.

## Human Review Conditions

다음 경우 메일 또는 특정 AI 결과를 사람 검토 대상으로 표시한다.

- 분류, 요약, 추출, 라우팅 중 하나가 실패했다.
- AI confidence가 기준값보다 낮다.
- 필수 핵심 정보가 누락되었다.
- 후보 점수 차이가 작아 자동 확정이 위험하다.
- 본문과 첨부 분석 결과가 충돌한다.
- 긴급, 클레임, 안전 관련 표현이 탐지되었지만 판단 근거가 부족하다.
- 사용자가 같은 유형의 수정 사례를 반복해서 만들고 있다.

## API Contract

현재 구현 상태:

- 담당자 수동 배정은 `PATCH /api/emails/{email_uid}/routing`와 Inbox 업무 판단 패널에서 지원한다.
- `review_required` 상태의 최신 Mail Decision Run 또는 라우팅 배정만 수동 배정할 수 있다.
- 수동 담당자 배정은 `routing_assignments`를 `assigned`/`source=user`로 갱신하고 `routing_events`, `audit_logs`에 before/after를 남긴다.
- 담당자 배정으로 검토가 해결되면 최신 `mail_decision_runs.status`를 `completed`로 닫고 `state_json.context.human_review`에 해결 이력을 남긴다.
- 업무 레이블, 요약, 긴급도, 핵심 정보 수정 저장 API는 아직 없다.
- 현재 UI의 재분류, 재요약, 첨부 재분석 버튼은 demo noop endpoint에 연결되어 있다.

운영 목표 API 계약:

- `PATCH /api/emails/{email_uid}/classification`
  - 업무 레이블 사용자 수정
  - 저장: `email_category_assignments`, `audit_logs`
- `PATCH /api/emails/{email_uid}/summary`
  - 요약 사용자 수정
  - 저장: 사용자 확정 요약 저장소, `audit_logs`
- `PATCH /api/emails/{email_uid}/priority`
  - 긴급도 사용자 수정
  - 저장: 사용자 확정 priority 저장소, `audit_logs`
- `PATCH /api/emails/{email_uid}/extracted-fields`
  - 핵심 정보 사용자 수정
  - 저장: 사용자 확정 추출 필드 저장소, `audit_logs`
- `PATCH /api/emails/{email_uid}/routing`
  - 담당자 사용자 수정
  - 저장: `routing_assignments`, `routing_events`, `audit_logs`
- `POST /api/emails/{email_uid}/review`
  - 검토 완료 또는 검토 보류 상태 저장
- `GET /api/review-queue`
  - 사람 검토 대상 목록 조회
- `GET /api/evaluation-candidates`
  - 사용자 수정 기반 평가 후보 조회
- `PATCH /api/evaluation-candidates/{candidate_id}`
  - 평가 승인, 제외, 보류 상태 변경

## Storage

현재 사용 가능한 저장 위치:

- 업무 레이블 수정 이력: `email_category_assignments`
- 담당자 변경 이력: `routing_events`
- 주요 변경 감사 기록: `audit_logs`
- 최초 AI 결과: `email_analysis_results`

추가로 필요한 운영 저장소:

- 요약, 긴급도, 핵심 정보의 사용자 확정값을 저장할 correction 테이블 또는 확장 정책
- review 상태를 메일 단위 또는 AI 결과 단위로 저장할 테이블
- 평가 데이터 후보와 승인 상태를 관리할 evaluation dataset 테이블
- 개인정보 비식별화 상태와 평가 반입 정책을 기록할 메타데이터

## Test Criteria

- 업무 레이블 수정은 기존 AI 분류 행을 덮어쓰지 않고 새 `source = user` 행을 만든다.
- 같은 메일의 current 업무 레이블은 하나만 존재한다.
- 담당자 수정은 `routing_events`에 before/after 담당자를 남긴다.
- 모든 사용자 수정은 `audit_logs`에 actor, action, entity, before_data, after_data를 남긴다.
- 수정 사유가 비어 있어도 수정 저장은 실패하지 않는다.
- 사용자가 AI 결과와 같은 값으로 검토 완료하면 수정 사례와 구분된다.
- 수정 사례는 평가 데이터 후보 목록에서 조회 가능하다.
- 평가 제외 상태의 사례는 고정 평가 데이터셋에 포함되지 않는다.
- 민감 정보가 포함된 후보는 승인 전 비식별화 필요 상태로 표시된다.
- 사용자 수정 저장 시간은 P95 1초 이내를 목표로 한다.

## LLMOps Notes

사용자 수정은 AI 품질 개선의 핵심 피드백이다. 다음 항목을 기록해야 한다.

- 수정 대상 메일 ID와 스레드 ID
- 수정 대상 AI 결과 ID
- 최초 AI 결과와 사용자 확정 결과
- 프롬프트 이름과 버전
- 모델명과 생성 설정
- 검색에 사용한 문서 ID와 점수
- 입력·출력 토큰 수
- 단계별 실행 시간
- 수정 사용자와 수정 시각
- 수정 사유
- 검토 완료 여부
- 평가 후보 상태와 평가 데이터셋 버전

## Open Questions

- 사용자 확정 요약, 긴급도, 핵심 정보 값을 `email_analysis_results`에 `source` 개념을 추가해 저장할지, 별도 correction 테이블을 만들지 결정해야 한다.
- review 상태를 메일 단위로 둘지, 분석 결과 단위로 둘지 결정해야 한다.
- 평가 데이터셋 테이블을 PostgreSQL에 둘지, 파일 기반 fixture와 연결할지 운영 준비 단계에서 확정해야 한다.

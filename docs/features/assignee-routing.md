# F-08 Assignee Routing

## Purpose

업무 유형, 고객, 제품, 과거 사례, 라우팅 규칙을 바탕으로 메일을 처리할 담당자 또는 담당 영역 후보를 제안하고, 사용자 확정과 전달 이력을 관리한다.

## Users

- 업무 담당자
- 업무 관리자
- AI 운영·개발 담당자

## Related Scenarios

- SC-01 신규 문의 메일 자동 분석
- SC-02 견적의뢰서 첨부 메일 분석
- SC-03 발주 메일 식별 및 담당자 연결
- SC-05 클레임 및 긴급 서비스 요청 탐지
- SC-06 AI 오분류 수정 및 평가 데이터 축적

## Input Data

- 현재 업무 분류
- 핵심 정보 추출 결과
- `routing_rules`
- 사용자와 담당 업무 정보
- 관련 메일 또는 과거 배정 검색 결과

## Output Data

- 담당자 후보 목록과 점수
- 현재 담당자 또는 담당 영역
- 라우팅 근거
- 확정, 재배정, 전달, 완료 이벤트
- 사람 검토 필요 여부

## State

| 상태 | 의미 |
|---|---|
| `pending` | 담당자 미정 |
| `assigned` | 담당자 배정됨 |
| `forwarded` | 실제 메일 전달 완료 |
| `completed` | 후속 업무 완료 |
| `cancelled` | 라우팅 취소 |

메일함과 대시보드의 업무 상태는 현재 라우팅 상태와 최신 수동 전달 알림을 함께 반영한다. `routing_assignments.status='forwarded'`이거나 최신 `manual_route_forward` 알림이 `sent`이면 배정 완료가 아니라 `전달 완료`로 표시한다.

## Normal Flow

1. 현재 업무 분류와 추출 필드를 조회한다.
2. 활성 라우팅 규칙에서 후보 담당자를 계산한다.
3. 필요하면 과거 유사 메일과 담당 이력을 검색한다.
4. 후보별 점수와 근거를 만든다.
5. 점수가 충분하면 `routing_assignments`를 생성 또는 갱신한다.
6. 배정 이벤트를 `routing_events`에 남긴다.
7. 사용자가 확정하거나 변경하면 user source 이벤트를 추가한다.

## Exception Flow

- 후보가 없으면 `pending`과 `미할당`으로 표시한다.
- 후보 점수 차이가 작으면 사람 검토 대상으로 전환한다.
- `fixed_at` 이후 규칙 변경은 기존 담당자를 자동 변경하지 않는다.
- 전달 실패는 배정 실패와 분리해 기록한다.

## Human Review Conditions

- 담당 후보가 없다.
- 최고 후보와 차순위 후보 점수 차이가 작다.
- 업무 분류 자체가 review required다.
- 긴급 메일인데 담당자가 확정되지 않았다.
- 사용자가 담당자를 변경했다.

## Settings

운영 관리자는 Settings 탭에서 자동 배정 기준을 조정할 수 있다.

| 설정 | 기본값 | 의미 |
|---|---:|---|
| 자동 배정 최소 점수 | `0.82` | 1순위 담당자 후보의 최종 점수가 이 값 이상이어야 자동 배정한다. |
| 1·2순위 최소 점수 차이 | `0.15` | 후보가 둘 이상이면 1순위와 2순위 점수 차이가 이 값 이상이어야 한다. |
| 업무유형 최소 신뢰도 | `0.78` | 업무유형 분류 신뢰도가 이 값 이상이어야 자동 배정한다. |

저장 위치는 `organization_settings.system_settings.routing_policy`이며, 저장값이 없으면 환경변수 `CORAMAIL_AUTO_ASSIGN_THRESHOLD`, `CORAMAIL_ROUTING_MIN_MARGIN`, `CORAMAIL_CLASSIFICATION_MIN_CONFIDENCE` 또는 코드 기본값을 사용한다. 변경된 기준은 다음 Mail Decision Run부터 적용된다.

## Assignee Work View

Inbox와 Dashboard 목록의 `Receiver` 칩은 담당자별 업무 화면으로 이동한다. 이 화면은 선택 담당자의 현재 배정 메일, 검토 필요 건수, 긴급 건수, 전달 완료 건수를 우선 표시하고, 같은 권한 범위의 담당자 목록을 빠르게 전환할 수 있게 한다.

현재 웹 인증은 단일 서명 쿠키 username만 제공하므로 권한은 다음 임시 규칙을 사용한다.

- `admin`과 `CORAMAIL_ADMIN_USERNAMES`에 포함된 username은 전체 담당자 업무를 조회한다.
- 담당자 계정은 로그인 username이 담당자 `user_id`, `email`, `name`, `routing_display`와 일치하는 메일을 조회한다.
- `CORAMAIL_ASSIGNEE_ACCESS_JSON`은 username별 추가 조회 허용 담당자를 JSON으로 지정한다. 값은 담당자 `user_id`, 이메일, 이름, 표시명 또는 `*`를 사용할 수 있다.
- 운영 목표는 이 임시 규칙을 `users.role`과 조직 권한 테이블 기반 정책으로 교체하는 것이다.

## API Contract

현재 구현:

- `GET /ui/assignees`
  - 담당자별 현재 업무 메일 화면을 렌더링한다.
  - Query: `assignee`, `q`, `category`
  - 권한: 관리자 전체, 담당자 본인 및 허용 담당자 범위
- `PATCH /api/emails/{email_uid}/routing`
  - `review_required` 메일을 사람이 직접 담당자에게 배정한다.
  - 요청: `assignee_user_id`
  - 저장: `routing_assignments`, `routing_events`, `audit_logs`
  - 최신 Mail Decision Run이 `review_required`이면 검토 해결로 간주해 `completed`로 닫는다.

운영 목표:

- `POST /api/emails/{email_uid}/routing/recalculate`
- `GET /api/emails/{email_uid}/routing`
- `PATCH /api/emails/{email_uid}/routing`
- `POST /api/emails/{email_uid}/routing/forward`
- `POST /api/emails/{email_uid}/routing/complete`

## Storage

- 규칙: `routing_rules`
- 현재 배정: `routing_assignments`
- 변경 이력: `routing_events`
- 사용자 변경 감사: `audit_logs`
- 검색 근거: F-07 검색 trace 또는 LLMOps trace

## Test Criteria

- 현재 라우팅 행은 이메일당 하나만 존재한다.
- 재배정은 이벤트 이력을 남긴다.
- 확정 담당자는 규칙 변경으로 자동 변경되지 않는다.
- 미할당 긴급 메일은 관리자 화면에서 조회 가능해야 한다.
- 합성 메일은 합성 담당자를 사용할 수 있지만 Gmail과 그 밖의 운영 provider는 `@coramail.invalid` 담당자를 후보로 조회하지 않는다.
- 합성 담당자 정답은 단순 순번이 아니라 고객별 고정 owner와 해당 메일의 제품, 업무 유형, 프로젝트 capability에서 결정되어야 한다.
- 최종 자동 배정이 성공하면 비차단 첨부 경고는 경고 이력으로 보존하되 terminal `review_reason`으로 남기지 않는다.

## Synthetic Evaluation Routing

- Clean v2는 `app.evaluation.synthetic_dataset`이 만든 합성 담당자 8명, 고객 12개, 제품 capability, 업무 유형 capability, 프로젝트 capability를 사용한다.
- 같은 고객의 메일은 항상 같은 합성 owner를 정답으로 사용하며, owner capability는 그 owner가 실제로 담당하는 합성 메일에서 결정적으로 파생한다.
- seed는 현재 데이터셋의 합성 담당자만 active로 만들고 이전 synthetic dataset의 사용자는 삭제하지 않고 inactive로 보존한다. 현재 담당자의 capability는 매 seed마다 canonical dataset으로 교체한다.
- 합성 담당자 이메일은 `@coramail.invalid`를 사용한다. 실제 이름, 실제 이메일, 실제 고객 관계 또는 실제 배정 이력을 포함하지 않는다.
- Settings는 표시 모드와 관계없이 현재 active 합성 담당자를 기존 담당자 관리 테이블에 `합성` 읽기 전용 행으로 표시한다. 업무 유형 capability는 담당 카테고리로 요약하지만 합성 담당자는 우선순위 배정과 Gmail 라우팅 후보에는 포함하지 않으며 화면과 서버 모두에서 수정·삭제를 차단한다.
- 합성 평가 결과는 평가 파이프라인과 라우팅 회귀 확인용이며 운영 Gmail 성능 주장이나 실제 조직 배정에 사용하지 않는다.

## LLMOps Notes

후보 점수, 선택 근거, 검색 문맥, 사용자 담당자 변경률, 업무 유형별 라우팅 정확도를 기록한다.

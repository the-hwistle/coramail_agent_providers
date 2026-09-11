# F-12 Notifications And Work Status

## Purpose

긴급 메일, 미배정 메일, 분석 실패, 처리 지연, 담당자 배정 같은 업무 상태를 사용자와 관리자에게 표시하거나 알림으로 전달한다.

## Users

- 업무 담당자
- 업무 관리자
- AI 운영·개발 담당자

## Related Scenarios

- SC-05 클레임 및 긴급 서비스 요청 탐지
- SC-07 AI 분석 실패와 안전한 대체 흐름
- SC-08 대량 메일 유입 시 우선순위 처리

## Input Data

- 메일 처리 상태
- 업무 분류와 긴급도
- 담당자 배정 상태
- CoRA 로그인 사용자와 `users.id` 연결
- 담당자의 업무 상세 확인, Gmail 회신 시작, 업무 완료 액션
- Gmail SENT metadata의 `provider_message_id`, `provider_thread_id`, `sent_at`
- 작업 실패 상태
- 사용자 알림 설정

## Output Data

- 화면 내 상태 badge
- 관리자 현황 집계
- 알림 레코드
- 발송 상태와 사용자별 메일 읽음 상태
- 담당자별 미확인, 확인함, 진행중, 회신함, 지연, 오늘 완료 집계
- Gmail outbound activity와 연결된 회신 완료 상태
- 실패 알림의 오류 원인

## State

### 알림 상태

| 상태 | 의미 |
|---|---|
| `pending` | 알림 대기 |
| `sending` | 발송 중 |
| `sent` | 발송 완료 |
| `failed` | 발송 실패 |
| `cancelled` | 발송 취소 |
| `read` | 사용자가 메일 또는 알림을 확인 |

### 업무 수행 상태

| 상태 | 의미 |
|---|---|
| `assigned` | 담당자로 배정됐지만 담당자가 아직 상세를 확인하지 않음 |
| `acknowledged` | 담당자가 상세를 확인했지만 아직 진행중으로 표시하지 않음 |
| `in_progress` | 담당자가 본인 계정에서 진행중 토글을 켰거나 Gmail 회신을 시작함 |
| `responded` | reply initiation 이후 같은 Gmail thread에서 실제 SENT 발신이 감지됨 |
| `completed` | 담당자가 업무 완료를 명시적으로 선택함 |

`overdue`는 영구 상태로 저장하지 않고 `status`, `due_at`, 현재 시각으로 계산한다.

## Normal Flow

1. 긴급, 미배정, 실패, 지연 같은 알림 조건을 평가한다.
2. 중복 발송 방지 idempotency key를 만든다.
3. `notifications`에 알림을 등록한다.
4. 웹 화면 또는 외부 채널로 전달한다.
5. 발송 성공, 실패, 읽음 상태를 갱신한다.
6. 관리자 dashboard는 현재 업무 상태를 집계한다.

## Reply Tracking Flow

1. `routing_assignments`가 담당자를 확정하면 같은 이메일에 `work_items`를 생성하거나 갱신한다.
2. 담당자 본인이 CoRA에서 메일 상세를 열면 `mail_read_states`에 사용자별 `read_at`을 idempotent하게 기록하고, `assigned` 업무는 `acknowledged`로 변경한다.
3. 담당자 본인이 진행중 토글을 켜거나 끄면 `work_items.status`를 `acknowledged`와 `in_progress` 사이에서 변경하고 `work_events.in_progress_on/off`를 기록한다. 아직 `assigned` 상태에서 토글을 켜면 바로 `in_progress`로 변경할 수 있다.
4. 담당자 본인이 `답장`을 누르면 서버가 assignee 여부를 검증한 뒤 `reply_initiated_at`과 `work_events.reply_initiated`를 기록하고 필요 시 `in_progress`로 전환한다.
5. 사용자는 공용 Gmail 화면에서 평소처럼 회신한다.
6. 별도 SENT sync가 `gmail_outbound_messages`에 최소 metadata만 저장한다.
7. 동일 Gmail thread에서 `reply_initiated_at` 이후 발신된 아직 연결되지 않은 outbound message를 찾으면 `work_items.status = responded`로 갱신하고 `work_events.response_detected`를 기록한다.
8. 담당자가 `업무 완료`를 누르면 `work_items.status = completed`와 `work_events.completed`를 기록한다.

공용 Gmail 계정에서는 Gmail 발신자 주소만으로 실제 작성자를 알 수 없다. 이번 정책은 같은 thread의 outbound message 직전 가장 최근 유효한 CoRA reply initiation actor를 수행자로 연결한다. 이 정책은 업무 추적 근거이지 Gmail 자체가 개인 작성자를 증명한다는 의미가 아니다.

## Exception Flow

- 알림 발송 실패는 업무 상태 자체를 변경하지 않는다.
- 같은 이벤트는 idempotency key로 중복 발송을 막는다.
- 수신자가 비활성 상태면 발송하지 않고 상태를 남긴다.
- 외부 채널이 없으면 web 알림 또는 dashboard 표시로 대체한다.
- SENT sync 실패는 기존 Inbox, 분석, 라우팅 상태를 변경하지 않는다.
- 담당자 본인이 아닌 사용자 또는 관리자의 상세 열람은 업무 진행 상태를 변경하지 않는다.
- `responded`, `completed` 상태는 진행중 토글로 `acknowledged`나 `assigned`로 되돌리지 않는다.
- reply initiation 이전 또는 다른 thread의 과거 SENT message는 신규 업무의 회신 완료로 연결하지 않는다.

## Human Review Conditions

- 긴급 메일이 미배정 상태다.
- 분석 실패 메일이 재시도 후에도 남아 있다.
- 담당자 확인이 SLA를 넘겼다.
- 알림 발송이 반복 실패한다.

## API Contract

운영 목표:

- `GET /api/notifications`
- `POST /api/notifications/{notification_id}/read`
- `GET /api/work-status`
- `GET /api/work-status/urgent`
- `GET /api/work-status/unassigned`
- `GET /api/work-status/failures`

현재 UI 구현:

- `POST /ui/emails/{email_ref}/work/reply-initiate`
- `POST /ui/emails/{email_ref}/work/complete`
- `POST /ui/settings/gmail/sync-outbound`

## Storage

- 알림: `notifications`
- 담당 상태: `routing_assignments`
- 업무 수행 현재 상태: `work_items`
- 업무 수행 이력: `work_events`
- Gmail 발신 활동 metadata: `gmail_outbound_messages`
- 사용자별 메일 읽음 상태: `mail_read_states`
- 작업 실패: `processing_jobs`
- 업무 분류와 긴급도: `email_category_assignments`, `email_analysis_results`

## Test Criteria

- 미배정 긴급 메일은 관리자 화면에서 누락되지 않는다.
- 같은 이벤트는 중복 알림을 만들지 않는다.
- 알림 실패는 원본 메일과 라우팅 상태를 변경하지 않는다.
- 메일 read 상태는 사용자별로 추적되고 업무 진행 상태와 독립적으로 변경된다.

## LLMOps Notes

긴급도 false negative, 미배정 지속 시간, 실패 알림 처리 시간, 담당자 최초 확인 시간을 업무 품질 지표로 기록한다.

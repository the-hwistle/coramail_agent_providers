# F-01 Mailbox Synchronization

## Purpose

메일 공급자 또는 샘플 데이터에서 이메일과 첨부파일 메타데이터를 수집해 원본 저장소에 안정적으로 적재한다. 같은 메일을 중복 저장하지 않고, AI 분석 실패와 무관하게 원본 메일 조회가 가능해야 한다.

## Users

- 업무 담당자
- 업무 관리자
- AI 운영·개발 담당자

## Related Scenarios

- SC-01 신규 문의 메일 자동 분석
- SC-02 견적의뢰서 첨부 메일 분석
- SC-03 발주 메일 식별 및 담당자 연결
- SC-05 클레임 및 긴급 서비스 요청 탐지
- SC-08 대량 메일 유입 시 우선순위 처리

## Input Data

- Demo fixture: `data/demo/*.fixture.json`
- Gmail mode: Gmail INBOX messages, recipients, snippets, body text, attachment metadata
- Operational target: provider message id, thread id, RFC message id, sender, recipients, subject, body, sent/received time, attachment metadata, sync cursor

## Output Data

- 수집 계정 상태
- 원본 이메일 레코드
- 수신자 레코드
- 첨부파일 메타데이터 레코드
- 수집 작업 상태와 실패 사유
- 중복 감지에 사용한 provider id와 content hash

## State

| 상태 | 의미 |
|---|---|
| `not_connected` | 수집 계정 인증 정보가 없음 |
| `active` | 수집 가능 |
| `syncing` | 수집 작업 실행 중 |
| `error` | 최근 수집 실패 |
| `disabled` | 수집 계정 비활성화 |

메일 처리 상태는 `received`, `processing`, `completed`, `failed`를 사용한다.

## Normal Flow

1. 수집 계정 상태와 동기화 cursor를 확인한다.
2. 공급자에서 신규 또는 변경 메일을 조회한다.
3. provider message id와 content hash로 중복 여부를 확인한다.
4. 원본 메일, 수신자, 첨부파일 메타데이터를 저장한다.
5. 첨부파일 원본 다운로드가 필요한 경우 별도 작업으로 분리한다.
6. 후속 분석, 첨부 처리, 색인 작업을 `processing_jobs`로 등록한다.
7. 수집 cursor와 마지막 정상 동기화 시각을 갱신한다.

## Exception Flow

- 공급자 API 실패는 계정 `last_error`와 `processing_jobs.error_message`에 기록한다.
- 동일 provider message id는 중복 저장하지 않는다.
- 본문 파싱 실패 시 원본 메타데이터와 snippet은 가능한 범위에서 저장한다.
- 첨부파일 다운로드 실패는 메일 저장 실패로 전파하지 않는다.
- sync cursor 손상 시 보수적인 재동기화와 중복 방지 조건을 함께 적용한다.

## Human Review Conditions

- 원본 본문이 없거나 지나치게 짧다.
- 첨부파일 메타데이터는 있지만 원본 다운로드가 실패했다.
- 같은 provider id가 다른 content hash로 감지된다.
- 수집 계정 오류가 반복된다.

## API Contract

현재 구현:

- `POST /ui/auto-sync/run`
- `GET /api/auto-sync`
- `GET /api/emails`
- `GET /api/emails/{email_index}`

상세 Gmail 설정 계약은 [Gmail Web Sync Settings](gmail-web-sync-settings.md)에 둔다.

운영 목표:

- `POST /api/mailboxes/{account_id}/sync`
- `GET /api/mailboxes/{account_id}/sync-status`
- `GET /api/emails?cursor=&limit=&status=`
- `GET /api/emails/{email_uid}`

## Storage

- 수집 계정: `email_accounts`
- 원본 메일: `email_messages`
- 수신자: `email_recipients`
- 첨부파일 메타데이터: `email_attachments`
- 작업 상태: `processing_jobs`
- 주요 변경 이력: `audit_logs`

## Test Criteria

- 같은 provider message id는 중복 저장되지 않는다.
- 수집 실패가 기존 메일 조회를 막지 않는다.
- 첨부파일 다운로드 실패와 메일 저장 실패가 구분된다.
- Gmail mode는 분석 파이프라인 없이도 목록과 상세를 표시한다.
- 수집 작업은 `success`, `failed`, 재시도 가능 상태를 기록한다.

## LLMOps Notes

이 기능은 직접 LLM을 호출하지 않지만, 후속 AI trace의 원본 기준점을 제공한다. 모든 AI 결과는 `email_messages.id`와 연결되어야 한다.


# CoRAMail PostgreSQL Schema

## 1. 문서 목적

이 문서는 CoRAMail의 PostgreSQL 데이터 모델과 테이블 관계를 정의한다.

- PostgreSQL 초기 스키마 구축
- SQLAlchemy 모델 작성
- Alembic 마이그레이션 작성
- 이메일 수집과 동기화 구현
- 첨부파일 메타데이터 관리
- 이메일 분류와 AI 분석 결과 저장
- 담당자 라우팅과 전달 이력 관리
- 알림 발송과 처리 이력 관리
- Qdrant Point와 PostgreSQL 원본 연결
- 기능 확장과 데이터 구조 변경

---

---

## 2. 설계 원칙

- PostgreSQL을 업무 데이터의 원본 저장소로 사용한다.
- Qdrant는 검색용 벡터와 검색 필터용 메타데이터만 저장한다.
- 첨부파일 원본은 파일 저장소에 두고 PostgreSQL에는 메타데이터와 저장 위치를 기록한다.
- 기본 키는 UUID를 사용한다.
- 이메일 공급자 ID와 CoRAMail 내부 ID를 분리한다.
- 사용자 수정값과 AI 분석값을 구분해 저장한다.
- 상태 변경과 담당자 변경은 현재값과 이력을 분리한다.
- 이미 전달되거나 확정된 담당자는 라우팅 규칙 변경으로 자동 변경하지 않는다.
- 시각 필드는 `TIMESTAMPTZ`를 사용하고 UTC 기준으로 저장한다.
- JSONB는 구조가 유동적인 분석 결과에만 제한적으로 사용한다.
- 검색, 조인, 고유성 보장에 필요한 값은 독립 컬럼으로 정의한다.
- 값이 없는 조건부 컬럼은 `NULL`로 저장한다.
- 스키마 변경은 Alembic 마이그레이션으로 관리한다.
- 현재 온프레미스 기능에 필요하지 않은 테이블과 컬럼은 미리 생성하지 않는다.
- 향후 기능 확장을 고려해 내부 ID, 이력 테이블, 버전 필드는 안정적으로 설계한다.

---

## 3. 필드 상태 정의

- **필수**: 레코드 생성 시 반드시 저장한다.
- **조건부**: 데이터 출처나 처리 결과가 있을 때 저장한다.
- **예약**: 향후 기능 구현을 위해 문서에 정의하지만 구현 전에는 사용하지 않는다.

---

## 4. 공통 규칙

### 명명 규칙

- 테이블명은 영문 소문자 복수형 snake_case를 사용한다.
- 기본 키 컬럼명은 `id`로 통일한다.
- 외래 키는 `<참조대상>_id` 형식을 사용한다.
- 생성 시각은 `created_at`, 수정 시각은 `updated_at`으로 통일한다.

### 공통 컬럼

- `id`
  - 타입: `UUID`
  - 의미: 레코드 고유 식별자.
  - 상태: 필수.
  - 생성 시점: INSERT 시.
  - 갱신 시점: 변경하지 않음.
  - 삭제 시점: 물리 삭제 시.

- `created_at`
  - 타입: `TIMESTAMPTZ`
  - 의미: 최초 생성 시각.
  - 상태: 필수.
  - 생성 시점: INSERT 시.
  - 갱신 시점: 변경하지 않음.
  - 삭제 시점: 레코드 삭제 시.

- `updated_at`
  - 타입: `TIMESTAMPTZ`
  - 의미: 마지막 수정 시각.
  - 상태: 필수.
  - 생성 시점: INSERT 시.
  - 갱신 시점: UPDATE 시.
  - 삭제 시점: 레코드 삭제 시.

- `deleted_at`
  - 타입: `TIMESTAMPTZ`
  - 의미: 논리 삭제 시각.
  - 상태: 조건부.
  - 생성 시점: 논리 삭제 시.
  - 갱신 시점: 복구 시 `NULL`.
  - 삭제 시점: 물리 삭제 시.

---

## 5. 핵심 관계

```text
organization_settings

users

email_accounts
 └─ email_messages
     ├─ email_recipients
     ├─ email_attachments
     │   ├─ attachment_analysis_results
     │   └─ qdrant_index_records
     ├─ email_category_assignments
     ├─ email_analysis_results
     ├─ routing_assignments
     │   └─ routing_events
     ├─ notifications
     └─ qdrant_index_records

categories
document_categories
routing_rules
processing_jobs
audit_logs
```

---

## 6. 조직 설정과 사용자

### 6.1 `organization_settings`

온프레미스 운영 조직의 기본 설정을 저장한다.

이 테이블은 한 행만 사용하는 단일 조직 설정 테이블로 운영할 수 있다.

- `id`: UUID, 설정 레코드 ID, 필수.
- `organization_name`: VARCHAR(200), 조직 표시명, 필수.
- `timezone`: VARCHAR(50), 기본 시간대, 필수, 기본값 예시 `Asia/Seoul`.
- `default_language`: VARCHAR(20), 기본 언어, 조건부.
- `notification_settings`: JSONB, 조직 공통 알림 설정, 조건부.
- `system_settings`: JSONB, 기능 플래그와 확장 설정, 조건부.
- `created_at`: TIMESTAMPTZ, 생성 시각, 필수.
- `updated_at`: TIMESTAMPTZ, 수정 시각, 필수.

### 운영 규칙

- 일반적으로 한 행만 유지한다.
- 코드에 설정값을 분산 저장하지 않고 조직 공통 설정을 이 테이블에서 관리한다.
- 비밀번호, OAuth 토큰 등 비밀정보는 저장하지 않는다.

---

### 6.2 `users`

CoRAMail 사용자와 업무 담당자를 저장한다.

- `id`: UUID, 사용자 고유 식별자, 필수.
- `email`: VARCHAR(320), 로그인 또는 알림 수신 이메일, 필수.
- `username`: VARCHAR(100), 로그인 ID, 조건부. 없으면 `email`로 로그인할 수 있다.
- `name`: VARCHAR(100), 사용자 표시명, 필수.
- `role`: VARCHAR(30), `admin`, `manager`, `member`, `viewer` 등의 권한, 필수.
- `status`: VARCHAR(30), `active`, `disabled` 등의 계정 상태, 필수.
- `password_hash`: TEXT, PBKDF2 등 평문이 아닌 비밀번호 검증값, 조건부.
- `phone_number`: VARCHAR(30), 문자 또는 전화 알림 번호, 조건부.
- `notification_preferences`: JSONB, 사용자별 알림 설정, 조건부.
- `last_login_at`: TIMESTAMPTZ, 마지막 로그인 시각, 조건부.
- `created_at`: TIMESTAMPTZ, 생성 시각, 필수.
- `updated_at`: TIMESTAMPTZ, 수정 시각, 필수.
- `deleted_at`: TIMESTAMPTZ, 논리 삭제 시각, 조건부.

### 생성과 갱신

- 생성 시점: 관리자 또는 초기 설정 과정에서 사용자 등록 시.
- 갱신 시점: 사용자 정보, 권한, 상태 또는 알림 설정 변경 시.
- 삭제 시점: 물리 삭제보다 `status = 'disabled'` 또는 논리 삭제를 권장한다.

### 제약조건과 인덱스

- `UNIQUE(email)`
- `UNIQUE(lower(username)) WHERE username IS NOT NULL AND deleted_at IS NULL`
- `INDEX(status)`
- 이메일 주소는 소문자로 정규화한 후 저장한다.

---

## 7. 이메일 수집 계정

### 7.1 `email_accounts`

Gmail, IMAP 등 이메일 수집 계정을 저장한다.

- `id`: UUID, 수집 계정 고유 식별자, 필수.
- `provider`: VARCHAR(30), `gmail`, `imap`, `microsoft` 등의 공급자, 필수.
- `email_address`: VARCHAR(320), 수집 대상 이메일 주소, 필수.
- `display_name`: VARCHAR(100), 화면 표시명, 조건부.
- `status`: VARCHAR(30), `active`, `error`, `disabled` 등의 상태, 필수.
- `credentials_reference`: VARCHAR(500), 인증정보 파일 또는 보안 저장소 참조값, 조건부.
- `sync_cursor`: VARCHAR(500), 증분 동기화 커서 또는 히스토리 ID, 조건부.
- `last_synced_at`: TIMESTAMPTZ, 마지막 정상 동기화 시각, 조건부.
- `last_error`: TEXT, 마지막 동기화 오류 요약, 조건부.
- `created_at`: TIMESTAMPTZ, 생성 시각, 필수.
- `updated_at`: TIMESTAMPTZ, 수정 시각, 필수.

### 생성과 갱신

- 생성 시점: 관리자가 수집 대상 이메일 계정을 등록할 때.
- 갱신 시점: 인증정보, 동기화 커서, 상태 또는 마지막 동기화 결과 변경 시.
- 삭제 시점: 기존 이메일 원본과 연결되어 있으면 비활성화를 권장한다.

### 제약조건과 인덱스

- `UNIQUE(provider, email_address)`
- `INDEX(status)`
- `INDEX(last_synced_at)`
- OAuth 토큰이나 비밀번호 원문을 일반 컬럼에 저장하지 않는다.

---

## 8. 이메일

### 8.1 `email_messages`

수집한 이메일 원본과 처리 상태를 저장한다.

- `id`: UUID, CoRAMail 내부 이메일 고유 식별자, 필수.
- `email_account_id`: UUID, 수집 계정, 필수, `email_accounts.id` 참조.
- `provider_message_id`: VARCHAR(255), Gmail Message ID 등 공급자 메시지 ID, 필수.
- `provider_thread_id`: VARCHAR(255), Gmail Thread ID 등 공급자 스레드 ID, 조건부.
- `rfc_message_id`: VARCHAR(998), 표준 `Message-ID`, 조건부.
- `in_reply_to`: VARCHAR(998), 답장 대상 `Message-ID`, 예약.
- `references`: TEXT[], 참조하는 이전 `Message-ID` 목록, 예약.
- `sender_name`: VARCHAR(200), 발신자 표시명, 조건부.
- `sender_address`: VARCHAR(320), 발신자 이메일 주소, 필수.
- `subject`: TEXT, 원본 이메일 제목, 필수.
- `subject_normalized`: TEXT, 답장·전달 접두사와 공백을 정리한 제목, 조건부.
- `body_text`: TEXT, 일반 텍스트 본문, 필수.
- `body_html`: TEXT, HTML 본문, 조건부.
- `snippet`: TEXT, 목록 화면용 본문 미리보기, 조건부.
- `sent_at`: TIMESTAMPTZ, 이메일 발송 시각, 필수.
- `received_at`: TIMESTAMPTZ, 수집 계정 수신 시각, 조건부.
- `has_attachment`: BOOLEAN, 표시 대상 첨부파일 존재 여부, 필수, 기본값 `FALSE`.
- `attachment_count`: INTEGER, 표시 대상 첨부파일 개수, 필수, 기본값 `0`.
- `processing_status`: VARCHAR(30), `received`, `processing`, `completed`, `failed` 등의 처리 상태, 필수.
- `content_hash`: CHAR(64), 원본 변경 감지용 SHA-256, 필수.
- `created_at`: TIMESTAMPTZ, 생성 시각, 필수.
- `updated_at`: TIMESTAMPTZ, 수정 시각, 필수.
- `deleted_at`: TIMESTAMPTZ, 논리 삭제 시각, 조건부.

### 생성과 갱신

- 생성 시점: 이메일 공급자에서 메시지 수집 완료 시.
- 갱신 시점: 원본 동기화, 첨부파일 확정, 처리 상태 변경 시.
- 삭제 시점: 이메일 삭제 정책에 따라 논리 또는 물리 삭제 시.

### 제약조건과 인덱스

- `UNIQUE(email_account_id, provider_message_id)`
- `CHECK(attachment_count >= 0)`
- `INDEX(sent_at DESC)`
- `INDEX(sender_address)`
- `INDEX(email_account_id, provider_thread_id)`
- `INDEX(processing_status)`
- `subject_normalized` 인덱스는 제목 기반 정확 일치 검색이 실제로 필요할 때만 생성한다.

### Qdrant 연결

- `email_messages.id`를 Qdrant 이메일 payload의 `email_uid`로 사용한다.

---

### 8.2 `email_recipients`

To, Cc, Bcc 수신자를 정규화해 저장한다.

- `id`: UUID, 수신자 레코드 ID, 필수.
- `email_message_id`: UUID, 대상 이메일, 필수, `email_messages.id` 참조.
- `recipient_type`: VARCHAR(10), `to`, `cc`, `bcc`, 필수.
- `name`: VARCHAR(200), 수신자 표시명, 조건부.
- `address`: VARCHAR(320), 수신자 이메일 주소, 필수.
- `created_at`: TIMESTAMPTZ, 생성 시각, 필수.

### 생성과 갱신

- 생성 시점: 이메일 헤더 파싱 시.
- 갱신 시점: 원본 이메일 재동기화 시 기존 수신자 목록과 비교해 갱신.
- 삭제 시점: 부모 이메일 삭제 시.

### 제약조건과 인덱스

- `UNIQUE(email_message_id, recipient_type, address)`
- `INDEX(address)`
- `INDEX(email_message_id, recipient_type)`

---

## 9. 첨부파일

### 9.1 `email_attachments`

첨부파일 원본의 메타데이터와 저장 위치를 관리한다.

Qdrant에서 여러 청크 Point로 나뉘어도 PostgreSQL에는 원본 파일 기준으로 한 행을 저장한다.

- `id`: UUID, 첨부파일 고유 식별자, 필수.
- `email_message_id`: UUID, 부모 이메일, 필수, `email_messages.id` 참조.
- `provider_attachment_id`: TEXT, 공급자 첨부파일 ID, 조건부. Gmail API의 opaque attachment ID는 255자를 넘을 수 있으므로 길이를 제한하지 않는다.
- `filename`: TEXT, 원본 파일명, 필수.
- `storage_uri`: TEXT, 파일 저장소 위치, 필수.
- `content_type`: VARCHAR(255), MIME 타입, 필수.
- `content_id`: TEXT, HTML 본문 `cid:` 참조와 연결하는 MIME Content-ID, 조건부.
- `content_disposition`: VARCHAR(30), MIME Content-Disposition (`inline`, `attachment` 등), 조건부.
- `file_group`: VARCHAR(30), PDF, 이미지, 문서 등 단순 파일 유형, 필수.
- `file_size`: BIGINT, 원본 파일 크기, 조건부.
- `checksum`: CHAR(64), 파일 무결성과 중복 확인용 SHA-256, 조건부.
- `is_inline`: BOOLEAN, 본문 삽입 이미지 등 인라인 첨부 여부, 필수, 기본값 `FALSE`.
- `document_category_id`: UUID, 문서 분류, 조건부, `document_categories.id` 참조.
- `processing_status`: VARCHAR(30), `pending`, `processing`, `completed`, `failed`, `unsupported`, 필수.
- `parse_error`: TEXT, 마지막 파싱 또는 분석 오류, 조건부.
- `created_at`: TIMESTAMPTZ, 생성 시각, 필수.
- `updated_at`: TIMESTAMPTZ, 수정 시각, 필수.
- `deleted_at`: TIMESTAMPTZ, 논리 삭제 시각, 조건부.

### 생성과 갱신

- 생성 시점: 첨부파일 저장 완료 시.
- 갱신 시점: 저장 위치, 분석 상태, 문서 분류 변경 시.
- 삭제 시점: 부모 이메일 삭제 또는 첨부파일 삭제 시.

### 제약조건과 인덱스

- `UNIQUE(email_message_id, provider_attachment_id)`는 공급자 ID가 있을 때 적용한다.
- `CHECK(file_size IS NULL OR file_size >= 0)`
- `INDEX(email_message_id)`
- `INDEX(processing_status)`
- `INDEX(checksum)`
- `INDEX(document_category_id)`

### Qdrant 연결

- `email_attachments.id`를 Qdrant 첨부파일 payload의 `attachment_id`로 사용한다.
- 부모 `email_messages.id`를 Qdrant payload의 `parent_email_uid`로 사용한다.

---

### 9.2 `document_categories`

첨부 문서 분류 체계를 저장한다.

- `id`: UUID, 문서 분류 ID, 필수.
- `code`: VARCHAR(100), 내부 문서 분류 코드, 필수.
- `name`: VARCHAR(100), 화면 표시명, 필수.
- `description`: TEXT, 분류 기준 설명, 조건부.
- `is_active`: BOOLEAN, 현재 사용 여부, 필수, 기본값 `TRUE`.
- `created_at`: TIMESTAMPTZ, 생성 시각, 필수.
- `updated_at`: TIMESTAMPTZ, 수정 시각, 필수.

### 제약조건과 인덱스

- `UNIQUE(code)`
- `INDEX(is_active)`

---

## 10. 이메일 분류와 AI 분석

### 10.1 `categories`

메일 분류 레이블을 저장한다.

- `id`: UUID, 분류 ID, 필수.
- `code`: VARCHAR(100), 안정적인 내부 분류 코드, 필수.
- `name`: VARCHAR(100), 화면 표시명, 필수.
- `description`: TEXT, 분류 기준 설명, 조건부.
- `is_active`: BOOLEAN, 현재 사용 여부, 필수.
- `sort_order`: INTEGER, 화면 표시 순서, 필수, 기본값 `0`.
- `created_at`: TIMESTAMPTZ, 생성 시각, 필수.
- `updated_at`: TIMESTAMPTZ, 수정 시각, 필수.

### 제약조건과 인덱스

- `UNIQUE(code)`
- `INDEX(is_active, sort_order)`

---

### 10.2 `email_category_assignments`

이메일 분류 이력과 현재 확정값을 저장한다.

- `id`: UUID, 분류 이력 ID, 필수.
- `email_message_id`: UUID, 분류 대상 이메일, 필수.
- `category_id`: UUID, 적용된 분류, 필수.
- `source`: VARCHAR(30), `ai`, `rule`, `user` 등의 결정 주체, 필수.
- `confidence`: NUMERIC(5,4), AI 또는 규칙 신뢰도, 조건부.
- `model_name`: VARCHAR(200), 분류 모델명, 조건부.
- `reason`: TEXT, 분류 근거나 수정 사유, 조건부.
- `assigned_by_user_id`: UUID, 수동 분류 사용자, 조건부.
- `is_current`: BOOLEAN, 현재 유효한 분류 여부, 필수.
- `created_at`: TIMESTAMPTZ, 생성 시각, 필수.

### 생성과 갱신

- 생성 시점: AI 분류, 규칙 분류 또는 사용자 수정 시.
- 갱신 시점: 기존 이력을 덮어쓰지 않고 새 행을 생성한다.
- 삭제 시점: 부모 이메일 물리 삭제 시.

### 제약조건과 인덱스

- 이메일별 `is_current = TRUE` 행은 하나만 존재하도록 부분 고유 인덱스를 생성한다.
- `CHECK(confidence IS NULL OR confidence BETWEEN 0 AND 1)`
- `INDEX(category_id, is_current)`
- `INDEX(email_message_id, created_at DESC)`

---

### 10.3 `email_analysis_results`

Summary, 액션 제안, 업무번호, 선박명 등 이메일 분석 결과를 저장한다.

- `id`: UUID, 분석 결과 ID, 필수.
- `email_message_id`: UUID, 분석 대상 이메일, 필수.
- `analysis_type`: VARCHAR(50), `executive_summary`, `business_refs`, `vessel_names`, `action_suggestions`, `priority` 등의 분석 종류, 필수.
- `result_text`: TEXT, 텍스트 결과, 조건부.
- `result_json`: JSONB, 목록 또는 구조화 결과, 조건부.
- `model_name`: VARCHAR(200), 분석 모델명, 필수.
- `prompt_version`: VARCHAR(100), 프롬프트 또는 파이프라인 버전, 조건부.
- `status`: VARCHAR(30), `pending`, `processing`, `success`, `failed`, 필수.
- `error_message`: TEXT, 분석 실패 원인, 조건부.
- `is_current`: BOOLEAN, 현재 사용 중인 결과 여부, 필수.
- `created_at`: TIMESTAMPTZ, 생성 시각, 필수.
- `updated_at`: TIMESTAMPTZ, 수정 시각, 필수.

### 생성과 갱신

- 생성 시점: 분석 작업 등록 또는 결과 생성 시.
- 갱신 시점: 처리 상태 변경 시.
- 새 모델 또는 프롬프트 결과는 기존 행을 덮어쓰지 않고 새 행으로 저장할 수 있다.
- 삭제 시점: 부모 이메일 물리 삭제 시.

### 제약조건과 인덱스

- 이메일과 분석 종류별 현재 결과 하나를 보장하는 부분 고유 인덱스를 생성한다.
- `INDEX(email_message_id, analysis_type, is_current)`
- `INDEX(status)`

---

### 10.4 `attachment_analysis_results`

첨부파일의 파싱, OCR, 이미지 설명, 필드 추출, 품목 추출 결과를 저장한다.

- `id`: UUID, 분석 결과 ID, 필수.
- `attachment_id`: UUID, 분석 대상 첨부파일, 필수.
- `analysis_type`: VARCHAR(50), `text_parse`, `ocr`, `image_caption`, `field_extraction`, `line_items`, 필수.
- `result_text`: TEXT, OCR 텍스트 또는 이미지 설명, 조건부.
- `result_json`: JSONB, 구조화 필드 또는 품목 목록, 조건부.
- `model_name`: VARCHAR(200), 분석 모델 또는 파서명, 조건부.
- `model_version`: VARCHAR(100), 모델 또는 파서 버전, 조건부.
- `status`: VARCHAR(30), 처리 상태, 필수.
- `error_message`: TEXT, 실패 원인, 조건부.
- `is_current`: BOOLEAN, 현재 결과 여부, 필수.
- `created_at`: TIMESTAMPTZ, 생성 시각, 필수.
- `updated_at`: TIMESTAMPTZ, 수정 시각, 필수.

### 제약조건과 인덱스

- 첨부파일과 분석 종류별 현재 결과 하나를 보장하는 부분 고유 인덱스를 생성한다.
- `INDEX(attachment_id, analysis_type, is_current)`
- `INDEX(status)`

---

## 11. 라우팅

### 11.1 `routing_rules`

메일 분류별 담당자 후보군과 신규 배정 우선순위를 정의한다.

- `id`: UUID, 규칙 ID, 필수.
- `category_id`: UUID, 적용 분류, 필수.
- `assignee_user_id`: UUID, 담당자 후보, 필수.
- `priority`: INTEGER, 후보군 내 우선순위, 필수.
- `is_active`: BOOLEAN, 신규 라우팅 사용 여부, 필수.
- `effective_from`: TIMESTAMPTZ, 적용 시작 시각, 조건부.
- `effective_to`: TIMESTAMPTZ, 적용 종료 시각, 조건부.
- `created_at`: TIMESTAMPTZ, 생성 시각, 필수.
- `updated_at`: TIMESTAMPTZ, 수정 시각, 필수.

### 규칙

- 규칙 변경은 이후 신규 라우팅에만 적용한다.
- 과거 배정 결과를 자동으로 변경하지 않는다.
- 비활성 사용자는 신규 라우팅 후보에서 제외한다.

### 제약조건과 인덱스

- `UNIQUE(category_id, assignee_user_id)`
- `CHECK(priority >= 0)`
- `INDEX(category_id, is_active, priority)`

---

### 11.2 `routing_assignments`

이메일의 현재 담당자 배정 상태를 저장한다.

- `id`: UUID, 배정 ID, 필수.
- `email_message_id`: UUID, 라우팅 대상 이메일, 필수.
- `assignee_user_id`: UUID, 현재 담당자, 조건부.
- `status`: VARCHAR(30), `pending`, `assigned`, `forwarded`, `completed`, `cancelled`, 필수.
- `assignment_source`: VARCHAR(30), `rule`, `ai`, `user` 등의 결정 방식, 필수.
- `routing_rule_id`: UUID, 적용된 자동 배정 규칙, 조건부.
- `assigned_at`: TIMESTAMPTZ, 담당자 배정 시각, 조건부.
- `forwarded_at`: TIMESTAMPTZ, 실제 전달 시각, 조건부.
- `fixed_at`: TIMESTAMPTZ, 담당자 확정 시각, 조건부.
- `completed_at`: TIMESTAMPTZ, 업무 완료 시각, 조건부.
- `created_at`: TIMESTAMPTZ, 생성 시각, 필수.
- `updated_at`: TIMESTAMPTZ, 수정 시각, 필수.

### 규칙

- 이메일당 현재 라우팅 행은 하나만 유지한다.
- `fixed_at` 이후에는 규칙 변경으로 담당자를 자동 변경하지 않는다.
- 재배정은 현재 행 갱신과 `routing_events` 이력 추가를 함께 수행한다.

### 제약조건과 인덱스

- `UNIQUE(email_message_id)`
- `INDEX(assignee_user_id, status)`
- `INDEX(status, created_at DESC)`

---

### 11.3 `routing_events`

담당자 배정, 변경, 전달, 확정, 완료 이력을 저장한다.

- `id`: UUID, 이벤트 ID, 필수.
- `routing_assignment_id`: UUID, 현재 라우팅 레코드, 필수.
- `email_message_id`: UUID, 대상 이메일, 필수.
- `event_type`: VARCHAR(30), `assigned`, `reassigned`, `forwarded`, `fixed`, `completed`, `cancelled`, 필수.
- `from_user_id`: UUID, 변경 전 담당자, 조건부.
- `to_user_id`: UUID, 변경 후 담당자, 조건부.
- `performed_by_user_id`: UUID, 작업 수행 사용자, 조건부.
- `source`: VARCHAR(30), `system`, `rule`, `ai`, `user`, 필수.
- `reason`: TEXT, 변경 사유, 조건부.
- `created_at`: TIMESTAMPTZ, 이벤트 발생 시각, 필수.

### 제약조건과 인덱스

- `INDEX(email_message_id, created_at)`
- `INDEX(routing_assignment_id, created_at)`
- `INDEX(event_type, created_at DESC)`

---

### 11.4 `work_items`

담당자 배정 이후 실제 업무 수행 상태를 저장한다. 라우팅 결과의 현재 상태인 `routing_assignments.status`와 분리한다.

- `id`: UUID, 업무 항목 ID, 필수.
- `email_message_id`: UUID, 원본 수신 이메일, 필수.
- `routing_assignment_id`: UUID, 연결된 현재 라우팅 배정, 필수.
- `assignee_user_id`: UUID, 업무 담당자, 필수.
- `status`: VARCHAR(30), `assigned`, `acknowledged`, `in_progress`, `responded`, `completed`, 필수.
- `assigned_at`: TIMESTAMPTZ, 담당자 배정 시각, 필수.
- `acknowledged_at`: TIMESTAMPTZ, 담당자가 업무 메일을 확인한 시각, 조건부. 사용자별 읽음 표시는 `mail_read_states`에도 별도로 기록한다.
- `reply_initiated_at`: TIMESTAMPTZ, 담당자가 CoRA에서 Gmail 회신 시작을 기록한 시각, 조건부.
- `first_responded_at`: TIMESTAMPTZ, 첫 Gmail outbound activity가 업무와 연결된 시각, 조건부.
- `responded_at`: TIMESTAMPTZ, 최신 Gmail outbound activity가 업무와 연결된 시각, 조건부.
- `completed_at`: TIMESTAMPTZ, 담당자가 명시적으로 업무 완료 처리한 시각, 조건부.
- `due_at`: TIMESTAMPTZ, 기본 SLA 기준 지연 판단 기준 시각, 조건부.
- `last_activity_at`: TIMESTAMPTZ, 최신 업무 활동 시각, 필수.

### 규칙

- 담당자 본인이 메일 상세를 열면 사용자별 `mail_read_states`를 갱신하고 `assigned` 상태의 업무를 `acknowledged`로 변경한다.
- 진행중 토글은 `authenticated_user.id = assignee_user_id`일 때만 `acknowledged`와 `in_progress` 사이에서 변경한다. 아직 `assigned` 상태인 업무에서 토글을 켜면 바로 `in_progress`가 될 수 있다.
- `responded`와 `completed`는 다른 상태다. Gmail 발신 감지는 회신 완료이고, 업무 완료는 담당자의 명시 액션으로 기록한다.
- 재배정 시 기존 이벤트 이력은 보존하되 현재 work item의 담당자, 확인, 회신 시작, 회신 완료, 완료 시각은 새 담당자 기준으로 초기화한다.
- 지연은 `status`, `due_at`, 현재 시각으로 계산할 수 있으므로 별도 영구 상태로 중복 저장하지 않는다.

### 제약조건과 인덱스

- `UNIQUE(routing_assignment_id)`
- `UNIQUE(email_message_id)`
- `INDEX(assignee_user_id, status, last_activity_at DESC)`

---

### 11.5 `mail_read_states`

사용자별 메일 읽음 상태를 저장한다. 업무 수행 상태와 독립적으로 관리한다.

- `email_message_id`: UUID, 원본 수신 이메일, 필수.
- `user_id`: UUID, 읽음 상태의 사용자, 필수.
- `read_at`: TIMESTAMPTZ, 최초 읽음 시각, 조건부.
- `last_opened_at`: TIMESTAMPTZ, 마지막 상세 열람 시각, 필수.
- `created_at`: TIMESTAMPTZ, 생성 시각, 필수.
- `updated_at`: TIMESTAMPTZ, 갱신 시각, 필수.

### 제약조건과 인덱스

- `PRIMARY KEY(email_message_id, user_id)`
- `INDEX(user_id, read_at DESC) WHERE read_at IS NOT NULL`

---

### 11.6 `work_events`

업무 수행 상태 변경 이력을 저장한다.

- `id`: UUID, 이벤트 ID, 필수.
- `work_item_id`: UUID, 업무 항목, 필수.
- `email_message_id`: UUID, 원본 수신 이메일, 필수.
- `routing_assignment_id`: UUID, 연결된 라우팅 배정, 조건부.
- `event_type`: VARCHAR(40), `assigned`, `in_progress_on`, `in_progress_off`, `acknowledged`, `reply_initiated`, `response_detected`, `completed`, 필수.
- `actor_user_id`: UUID, CoRA에서 액션을 수행한 사용자, 조건부.
- `provider_message_id`: VARCHAR(255), 연결된 Gmail 발신 message id, 조건부.
- `provider_thread_id`: VARCHAR(255), 연결된 Gmail thread id, 조건부.
- `metadata`: JSONB, 이벤트별 추가 정보, 조건부.
- `created_at`: TIMESTAMPTZ, 이벤트 발생 시각, 필수.

공용 Gmail 계정에서는 Gmail `From`만으로 실제 작성자를 알 수 없다. 따라서 `response_detected`의 `actor_user_id`는 같은 thread의 Gmail 발신 자체가 아니라, 해당 발신 이전 가장 최근의 유효한 CoRA `reply_initiated` 사용자에 근거한다. 이 한계는 UI와 운영 문서에서 명시해야 한다.

---

### 11.6 `gmail_outbound_messages`

SENT 메일의 최소 metadata만 저장해 업무 회신 추적에 사용한다. 이 테이블의 행은 Inbox ingestion, 첨부 분석, LLM 분석, 라우팅 대상에 포함하지 않는다.

- `id`: UUID, outbound activity ID, 필수.
- `email_account_id`: UUID, Gmail 계정, 필수.
- `provider_message_id`: VARCHAR(255), Gmail message id, 필수.
- `provider_thread_id`: VARCHAR(255), Gmail thread id, 필수.
- `rfc_message_id`: VARCHAR(998), RFC Message-ID, 조건부.
- `sender_address`: VARCHAR(320), 공용 Gmail 발신 주소, 조건부.
- `recipients`: JSONB, 수신자 metadata, 조건부.
- `subject`: TEXT, 제목, 조건부.
- `sent_at`: TIMESTAMPTZ, 실제 Gmail 발신 시각, 필수.
- `linked_work_item_id`: UUID, 연결된 업무 항목, 조건부.

### 규칙

- 동일 Gmail message는 한 번만 저장하고 한 업무 항목에만 연결한다.
- 연결 조건은 동일 `provider_thread_id`, `reply_initiated_at <= sent_at`, 아직 연결되지 않은 outbound message다.
- 업무 배정 또는 reply initiation 이전의 과거 SENT message는 신규 회신 완료로 보지 않는다.

---

## 12. 알림

### 12.1 `notifications`

메일 도착, 긴급 메일, 담당자 배정 등의 알림 발송 기록을 저장한다.

- `id`: UUID, 알림 ID, 필수.
- `email_message_id`: UUID, 관련 이메일, 조건부.
- `recipient_user_id`: UUID, 수신 사용자, 조건부.
- `channel`: VARCHAR(30), `web`, `email`, `sms`, `push` 등의 알림 채널, 필수.
- `notification_type`: VARCHAR(50), `new_email`, `urgent_email`, `assignment`, `processing_failed`, 필수.
- `title`: TEXT, 알림 제목, 필수.
- `body`: TEXT, 알림 본문, 필수.
- `status`: VARCHAR(30), `pending`, `sending`, `sent`, `failed`, `cancelled`, 필수.
- `provider_message_id`: VARCHAR(255), 외부 발송 서비스 메시지 ID, 조건부.
- `idempotency_key`: VARCHAR(255), 중복 발송 방지 키, 조건부.
- `scheduled_at`: TIMESTAMPTZ, 예약 발송 시각, 조건부.
- `sent_at`: TIMESTAMPTZ, 발송 완료 시각, 조건부.
- `read_at`: TIMESTAMPTZ, 사용자 확인 시각, 조건부.
- `error_message`: TEXT, 발송 실패 원인, 조건부.
- `created_at`: TIMESTAMPTZ, 생성 시각, 필수.
- `updated_at`: TIMESTAMPTZ, 수정 시각, 필수.

### 제약조건과 인덱스

- `UNIQUE(idempotency_key)`는 값이 있는 행에 부분 적용한다.
- `INDEX(recipient_user_id, status, created_at DESC)`
- `INDEX(status, scheduled_at)`
- `INDEX(email_message_id)`

---

## 13. Qdrant 색인 연결

### 13.1 `qdrant_index_records`

PostgreSQL 원본과 Qdrant Point의 색인 상태를 연결한다.

- `id`: UUID, 색인 레코드 ID, 필수.
- `source_type`: VARCHAR(30), `email`, `attachment_chunk`, 필수.
- `email_message_id`: UUID, 이메일 Point 원본, 조건부.
- `attachment_id`: UUID, 첨부파일 청크 Point 원본, 조건부.
- `chunk_id`: VARCHAR(255), 첨부파일 청크 식별자, 조건부.
- `chunk_index`: INTEGER, 첨부파일 청크 순번, 조건부.
- `collection_name`: VARCHAR(255), Qdrant 컬렉션명, 필수.
- `point_id`: VARCHAR(255), Qdrant Point ID, 필수.
- `schema_version`: INTEGER, Qdrant payload 스키마 버전, 필수.
- `embedding_model`: VARCHAR(200), 임베딩 모델명, 필수.
- `embedding_dimension`: INTEGER, 벡터 차원, 필수.
- `content_hash`: CHAR(64), 색인 콘텐츠 해시, 필수.
- `status`: VARCHAR(30), `pending`, `indexed`, `stale`, `failed`, `deleted`, 필수.
- `indexed_at`: TIMESTAMPTZ, 색인 성공 시각, 조건부.
- `error_message`: TEXT, 색인 실패 원인, 조건부.
- `created_at`: TIMESTAMPTZ, 생성 시각, 필수.
- `updated_at`: TIMESTAMPTZ, 수정 시각, 필수.

### 생성과 갱신

- 생성 시점: Qdrant 색인 작업 등록 시.
- 갱신 시점: 색인 성공, 실패, 원본 변경, Qdrant 삭제 시.
- 삭제 시점: 원본과 관련 색인 기록을 완전히 제거할 때.

### 제약조건과 인덱스

- `UNIQUE(collection_name, point_id)`
- 이메일 색인은 `email_message_id`가 필요하다.
- 첨부파일 청크 색인은 `attachment_id`, `chunk_id`, `chunk_index`가 필요하다.
- `INDEX(source_type, status)`
- `INDEX(email_message_id, status)`
- `INDEX(attachment_id, status)`
- `INDEX(content_hash)`

---

## 14. 비동기 작업과 감사 로그

### 14.1 `processing_jobs`

이메일 수집, 분석, 첨부파일 처리, Qdrant 색인 작업을 추적한다.

- `id`: UUID, 작업 ID, 필수.
- `job_type`: VARCHAR(50), `email_sync`, `email_analysis`, `attachment_parse`, `qdrant_index`, 필수.
- `source_type`: VARCHAR(30), 작업 대상 종류, 조건부.
- `source_id`: UUID, 작업 대상 레코드 ID, 조건부.
- `status`: VARCHAR(30), `pending`, `running`, `success`, `failed`, `cancelled`, 필수.
- `attempt_count`: INTEGER, 실행 시도 횟수, 필수, 기본값 `0`.
- `max_attempts`: INTEGER, 최대 재시도 횟수, 필수.
- `scheduled_at`: TIMESTAMPTZ, 실행 예정 시각, 조건부.
- `started_at`: TIMESTAMPTZ, 작업 시작 시각, 조건부.
- `completed_at`: TIMESTAMPTZ, 작업 종료 시각, 조건부.
- `error_message`: TEXT, 마지막 오류, 조건부.
- `metadata`: JSONB, 작업별 확장 정보, 조건부.
- `created_at`: TIMESTAMPTZ, 생성 시각, 필수.
- `updated_at`: TIMESTAMPTZ, 수정 시각, 필수.

### 제약조건과 인덱스

- `CHECK(attempt_count >= 0)`
- `CHECK(max_attempts > 0)`
- `INDEX(status, scheduled_at)`
- `INDEX(job_type, status)`
- `INDEX(source_type, source_id)`

---

### 14.2 `audit_logs`

사용자와 시스템의 주요 변경 이력을 저장한다.

- `id`: UUID, 감사 로그 ID, 필수.
- `actor_type`: VARCHAR(30), `user`, `system`, `ai`, 필수.
- `actor_user_id`: UUID, 사용자 작업인 경우 수행자, 조건부.
- `action`: VARCHAR(100), `category.changed`, `routing.reassigned`, `email.deleted` 등의 작업, 필수.
- `entity_type`: VARCHAR(50), 변경 대상 종류, 필수.
- `entity_id`: UUID, 변경 대상 ID, 필수.
- `before_data`: JSONB, 변경 전 주요 값, 조건부.
- `after_data`: JSONB, 변경 후 주요 값, 조건부.
- `request_id`: VARCHAR(100), API 요청 또는 작업 추적 ID, 조건부.
- `created_at`: TIMESTAMPTZ, 발생 시각, 필수.

### 제약조건과 인덱스

- `INDEX(entity_type, entity_id, created_at DESC)`
- `INDEX(actor_user_id, created_at DESC)`
- 감사 로그는 원칙적으로 UPDATE와 DELETE를 허용하지 않는다.

---

## 15. 삭제 정책

## 이메일

- 일반 사용자 삭제는 `deleted_at`을 이용한 논리 삭제를 권장한다.
- 물리 삭제 시 첨부파일, 분석 결과, 라우팅, 알림, Qdrant Point를 정리한다.
- Qdrant 삭제 실패 시 재시도 작업을 생성한다.

## 첨부파일

- PostgreSQL 레코드, 파일 저장소 원본, Qdrant 청크 Point를 함께 정리한다.
- 파일 삭제 실패는 비동기 재시도 작업으로 처리한다.

## 사용자

- 과거 업무 이력을 보존하기 위해 물리 삭제보다 비활성화 또는 논리 삭제를 권장한다.

## 분류와 라우팅 규칙

- 과거 기록과 연결된 분류는 물리 삭제하지 않고 `is_active = FALSE`로 변경한다.
- 규칙 비활성화는 이후 신규 라우팅에만 적용한다.
- 이미 전달 또는 확정된 담당자는 규칙 변경으로 자동 수정하지 않는다.

---

## 16. 트랜잭션 경계

## 이메일 수집

1. `email_messages` 생성
2. `email_recipients` 생성
3. `email_attachments` 생성
4. `has_attachment`, `attachment_count` 확정
5. `processing_jobs` 생성

Qdrant 색인은 외부 시스템 작업이므로 PostgreSQL 트랜잭션과 분리한다.

## 분류 변경

1. 기존 현재 분류의 `is_current` 해제
2. 새 `email_category_assignments` 생성
3. 필요 시 신규 라우팅 평가
4. `audit_logs` 생성

## 담당자 변경

1. `routing_assignments` 현재값 갱신
2. `routing_events` 생성
3. 필요 시 `notifications` 생성
4. `audit_logs` 생성

---

## 17. Qdrant 연결 규칙

- `email_messages.id`는 Qdrant 이메일 payload의 `email_uid`와 연결한다.
- `email_attachments.id`는 Qdrant 첨부파일 payload의 `attachment_id`와 연결한다.
- Qdrant 첨부파일 payload의 `parent_email_uid`는 `email_messages.id`를 가리킨다.
- PostgreSQL 원본의 `content_hash`와 Qdrant 색인 기록을 비교해 재색인 여부를 판단한다.
- Qdrant 컬렉션명, 모델명, 차원, 스키마 버전은 `qdrant_index_records`에서 추적한다.
- Qdrant는 원본 업무 상태의 최종 저장소로 사용하지 않는다.

---

## 18. 인덱스 설계 원칙

- 실제 목록 조회와 필터 조건을 기준으로 인덱스를 설계한다.
- 외래 키 조인 경로에 필요한 인덱스를 명시적으로 검토한다.
- 상태와 날짜를 함께 조회하면 복합 인덱스를 우선 검토한다.
- 고유값 비율이 높고 필터 사용이 드문 텍스트에는 무조건 인덱스를 만들지 않는다.
- JSONB는 실제 JSON 조건 검색이 확인된 뒤 GIN 인덱스를 생성한다.
- 운영 쿼리와 `EXPLAIN ANALYZE` 결과를 기준으로 인덱스를 조정한다.

---

## 19. 보안과 개인정보

- OAuth 토큰과 비밀번호 원문을 일반 컬럼에 저장하지 않는다.
- 인증정보는 환경변수, 암호화 파일 또는 별도 보안 저장소에서 관리한다.
- 이메일 본문과 첨부파일 접근은 사용자 권한에 따라 제한한다.
- 감사 로그에 이메일 본문 전체나 인증정보를 복사하지 않는다.
- 백업, 로그, 개발 데이터에도 동일한 보안 정책을 적용한다.
- 데이터베이스 서버는 외부 인터넷에 직접 노출하지 않는다.

---

## 20. 백업과 복구

- PostgreSQL 정기 백업 정책을 정의한다.
- 첨부파일 저장소와 PostgreSQL 백업 시점을 가능한 한 일치시킨다.
- Qdrant는 PostgreSQL과 파일 저장소 원본으로 재생성할 수 있어야 한다.
- 데이터베이스 복구 후 `qdrant_index_records`를 기준으로 누락된 Point를 재색인한다.
- 마이그레이션 전에는 복구 가능한 백업을 생성한다.

---

## 21. 마이그레이션 원칙

- 스키마 변경은 Alembic으로 관리한다.
- 운영 테이블을 직접 수정하지 않는다.
- 새 컬럼은 nullable 또는 안전한 기본값으로 먼저 배포한다.
- 데이터 백필 완료 후 NOT NULL 제약조건을 적용한다.
- 컬럼 이름 변경은 새 컬럼 추가, 이중 쓰기, 백필, 읽기 전환, 기존 컬럼 제거 순서로 진행한다.
- 대규모 인덱스는 `CREATE INDEX CONCURRENTLY` 사용을 검토한다.
- 데이터 제거 전 백업과 롤백 계획을 작성한다.

---

## 22. 초기 구축 우선순위

## 1단계: 이메일 원본과 검색 연동

- `organization_settings`
- `users`
- `email_accounts`
- `email_messages`
- `email_recipients`
- `email_attachments`
- `processing_jobs`
- `qdrant_index_records`

## 2단계: AI 분석과 분류

- `categories`
- `email_category_assignments`
- `email_analysis_results`
- `document_categories`
- `attachment_analysis_results`

## 3단계: 라우팅과 알림

- `routing_rules`
- `routing_assignments`
- `routing_events`
- `notifications`
- `audit_logs`

---

---

## 23. 구현 체크리스트

- [ ] 이메일 공급자 ID와 내부 UUID가 분리되어 있는가?
- [ ] 이메일 중복 수집 방지 제약조건이 있는가?
- [ ] To, Cc, Bcc 수신자가 정규화되어 있는가?
- [ ] 첨부파일 원본과 Qdrant 청크가 분리되어 있는가?
- [ ] AI 분석 결과와 사용자 확정값이 구분되어 있는가?
- [ ] 분류와 라우팅 변경 이력이 보존되는가?
- [ ] 전달 후 담당자가 규칙 변경으로 자동 변경되지 않는가?
- [ ] 알림 중복 발송을 방지할 수 있는가?
- [ ] PostgreSQL 원본으로 Qdrant 전체 재색인이 가능한가?
- [ ] Qdrant 컬렉션, 모델, 차원, 스키마 버전을 추적하는가?
- [ ] 외부 인증정보 원문을 PostgreSQL에 저장하지 않는가?
- [ ] 모든 시각이 `TIMESTAMPTZ`로 저장되는가?
- [ ] 백업과 복구 절차가 정의되어 있는가?
- [ ] 마이그레이션과 롤백 절차가 정의되어 있는가?
- [ ] 실제 조회 쿼리에 맞는 인덱스가 설계되어 있는가?

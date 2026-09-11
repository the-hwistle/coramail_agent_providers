# CoRAMail Qdrant Point Schema

## 1. 문서 목적

이 문서는 CoRAMail에서 사용하는 Qdrant 컬렉션, Point 구조, payload 필드 및 인덱스 기준을 정의한다.

- Qdrant 컬렉션 생성
- 이메일 및 첨부파일 Point 생성
- payload 필드 구성
- 검색 필터 구성
- PostgreSQL 원본 데이터 연결
- 임베딩 모델 변경 및 재색인

---

## 2. 설계 원칙

- PostgreSQL을 이메일과 첨부파일 메타데이터의 원본 저장소로 사용한다.
- 파일 저장소를 첨부파일 원본의 저장소로 사용한다.
- Qdrant에는 검색용 벡터, 원본 연결 식별자, 검색 필터, 첨부파일 청크 본문을 저장한다.
- 이메일 본문 전체는 Qdrant payload에 저장하지 않는다.
- 첨부파일은 검색 단위인 청크 본문을 payload에 저장한다.
- 값이 없는 조건부 필드는 payload에서 생략한다.
- 실제 검색 필터에 사용하는 필드에만 payload index를 생성한다.
- 서로 다른 임베딩 모델 또는 벡터 차원의 Point를 같은 컬렉션에 저장하지 않는다.
- 임베딩 모델 또는 벡터 차원이 변경되면 새 컬렉션을 생성하고 전체 재색인한다.
- Point ID는 같은 원본과 같은 청크에서 항상 같은 값이 생성되도록 결정적으로 만든다.

---

## 3. 필드 상태

- **필수**: 모든 해당 유형의 Point에 저장한다.
- **조건부**: 해당 검색 필터 또는 기능을 사용할 때 저장한다.
- **예약**: 기능 구현 전에는 저장하지 않는다.

---

## 3.1 Retrieval Isolation 공통 필드

담당자 배정용 유사 사례 retrieval은 이메일/첨부 검색과 다른 safety boundary를 가진다. 운영 routing에서 synthetic, demo, evaluation point를 similar-case evidence로 사용하면 안 된다. 따라서 Qdrant point가 routing evidence 후보가 되려면 다음 provenance 필드를 명시적으로 가져야 한다.

| 필드 | 타입 | 의미 |
|---|---|---|
| `provider` | keyword | 원본 계정 또는 corpus provider. 예: `gmail`, `synthetic` |
| `dataset_type` | keyword | `production`, `demo`, `evaluation`, `development` 중 하나 |
| `synthetic` | boolean | 합성 데이터 여부 |
| `evaluation` | boolean | 평가 corpus 여부 |
| `email_account_id` | keyword | 운영 mailbox/account scope. 운영 Gmail routing에서 사용 |
| `dataset_version` | keyword | 평가 corpus scope. evaluation retrieval에서 사용 |
| `assignment_confirmed` | boolean | 사람 또는 신뢰된 이력으로 확정된 배정 사례 여부 |

`QdrantSimilarCaseRetriever`는 planner filter와 별개로 `RetrievalScope`에서 만든 mandatory filter를 최종 Qdrant query에 합성한다. 운영 Gmail routing의 기본 scope는 `provider=gmail`, `dataset_type=production`, `synthetic=false`, `evaluation=false`, 현재 `email_account_id`, `assignment_confirmed=true`다. 이 필드가 누락된 legacy point는 운영 production evidence로 간주하지 않고 검색에서 제외한다.

Production similar-case point는 `app.retrieval.qdrant_indexing.ProductionSimilarCaseIndexer`가 PostgreSQL `email_messages`, `email_accounts`, `routing_assignments`, current `mail_facts`, current `email_analysis_results`에서 재생성한다. Production Gmail payload는 다음 값을 사용한다.

```text
provider = email_accounts.provider
dataset_type = production
synthetic = false
evaluation = false
email_account_id = email_messages.email_account_id
assignment_confirmed = routing_assignments.assignee_user_id IS NOT NULL
                       AND routing_assignments.status IN (assigned, forwarded, completed)
```

`assignment_confirmed=false` point는 Qdrant에 존재해도 routing similar-case retrieval에서 제외된다. `assigned`, `forwarded`, `completed` 상태는 확정 이력으로 본다. `review_required`는 단순 후보 또는 미확정 상태이므로 similar-case evidence가 아니다. 수동 배정, 재배정, 전달 완료는 같은 deterministic point id를 다시 upsert해 stale assignee provenance를 덮어쓴다.

Demo scope는 `provider=synthetic`, `dataset_type=demo`, `synthetic=true`, `evaluation=false`만 허용한다. Evaluation scope는 명시된 `dataset_type=evaluation`, `evaluation=true`, 필요 시 `dataset_version`으로 제한한다. Evaluation leakage detection은 dataset 생성/검증 단계의 별도 안전장치이며 runtime retrieval isolation을 대체하지 않는다.

---

## 4. 컬렉션 설정

### 환경변수

- `QDRANT_EMAIL_COLLECTION`: 이메일 컬렉션 이름
- `QDRANT_ATTACHMENT_COLLECTION`: 첨부파일 컬렉션 이름
- `EMBEDDING_MODEL`: 임베딩 모델명
- `EMBEDDING_VECTOR_SIZE`: 임베딩 벡터 차원
- `QDRANT_DISTANCE`: 벡터 거리 계산 방식
- `QDRANT_SCHEMA_VERSION`: payload 스키마 버전

```env
QDRANT_EMAIL_COLLECTION=coramail_emails_v1
QDRANT_ATTACHMENT_COLLECTION=coramail_attachments_v1

EMBEDDING_MODEL=<embedding-model-name>
EMBEDDING_VECTOR_SIZE=<model-output-dimension>
QDRANT_DISTANCE=cosine

QDRANT_SCHEMA_VERSION=1
```

### 컬렉션 변경 규칙

1. 새 임베딩 모델과 출력 차원을 확인한다.
2. 새 버전의 이메일 및 첨부파일 컬렉션을 생성한다.
3. PostgreSQL과 파일 저장소의 원본 데이터로 전체 재색인한다.
4. 검색 결과를 검증한다.
5. 애플리케이션 조회 컬렉션을 전환한다.
6. 안정화 후 기존 컬렉션을 보관하거나 삭제한다.

---

## 5. 공통 Point 구조

```python
PointStruct(
    id=point_id,
    vector=embedding_vector,
    payload=payload,
)
```

### `schema_version`

- 의미: payload 구조 버전
- 상태: 필수
- 생성 시점: Point 생성 시
- 갱신 시점: payload 구조 변경 후 재색인 시
- 삭제 시점: Point 삭제 시

---

## 6. 이메일 컬렉션

### 컬렉션명

```text
coramail_emails_v1
```

### 저장 단위

이메일 한 건을 하나의 Point로 저장한다.

### Point ID 입력값

```text
email:{email_uid}
```

위 문자열을 결정적으로 해시해 Qdrant Point ID로 사용한다.

### 임베딩 입력

- 이메일 제목
- 발신자
- 수신자
- 이메일 본문
- 첨부파일명
- 이메일 분류
- 업무 식별자
- 선박명

임베딩 입력 문자열은 벡터 생성 과정에서만 사용한다.

---

### 6.1 필수 payload

#### `schema_version`

- 타입: `integer`
- 의미: 이메일 payload 구조 버전
- 상태: 필수

#### `email_uid`

- 타입: `keyword`
- 의미: PostgreSQL `email_messages.id`와 연결하는 내부 이메일 식별자
- 상태: 필수
- 생성 시점: 이메일 Point 생성 시
- 갱신 시점: 변경하지 않음
- 삭제 시점: Point 삭제 시

---

### 6.2 조건부 payload

#### `sent_at`

- 타입: `datetime`
- 의미: 이메일 발송 시각
- 상태: 조건부
- 저장 조건: 기간 필터를 사용할 때
- 갱신 시점: 원본 발송 시각 변경 또는 재색인 시

#### `sender_address`

- 타입: `keyword`
- 의미: 정규화된 발신자 이메일 주소
- 상태: 조건부
- 저장 조건: 발신자 필터를 사용할 때
- 갱신 시점: 발신자 변경 또는 재색인 시

#### `mail_category`

- 타입: `keyword`
- 의미: 현재 이메일 분류 코드
- 상태: 조건부
- 저장 조건: 분류별 검색 필터를 사용할 때
- 갱신 시점: 재분류 또는 사용자 수정 시

#### `business_refs`

- 타입: `keyword[]`
- 의미: 발주번호, 견적번호 등 업무 식별자 목록
- 상태: 조건부
- 저장 조건: 업무 식별자 필터 또는 정확 일치 검색을 사용할 때
- 갱신 시점: 추출 결과 변경 시

#### `vessel_names`

- 타입: `keyword[]`
- 의미: 이메일에서 추출한 선박명 목록
- 상태: 조건부
- 저장 조건: 선박명 필터 또는 정확 일치 검색을 사용할 때
- 갱신 시점: 추출 결과 변경 시

#### `has_attachment`

- 타입: `boolean`
- 의미: 검색 대상 첨부파일 존재 여부
- 상태: 조건부
- 저장 조건: 첨부파일 유무 필터를 사용할 때
- 갱신 시점: 첨부파일 추가·삭제 또는 재수집 시

#### `subject_normalized`

- 타입: `keyword`
- 의미: 답장·전달 접두사와 불필요한 공백을 제거한 제목
- 상태: 예약
- 저장 조건: 제목 기반 정확 일치 검색 또는 스레드 보완 기능 구현 시
- 갱신 시점: 제목 또는 정규화 규칙 변경 시

---

### 6.3 이메일 payload 예시

```python
email_payload = {
    "schema_version": schema_version,
    "email_uid": email_uid,
}
```

조건부 필드는 기능 사용 여부와 값 존재 여부에 따라 추가한다.

```python
if sent_at is not None:
    email_payload["sent_at"] = sent_at

if sender_address:
    email_payload["sender_address"] = sender_address

if mail_category:
    email_payload["mail_category"] = mail_category

if business_refs:
    email_payload["business_refs"] = business_refs

if vessel_names:
    email_payload["vessel_names"] = vessel_names

if has_attachment_filter_enabled:
    email_payload["has_attachment"] = has_attachment
```

---

## 7. 첨부파일 컬렉션

### 컬렉션명

```text
coramail_attachments_v1
```

### 저장 단위

첨부파일에서 생성한 검색 청크 한 개를 하나의 Point로 저장한다.

- 문서 텍스트 청크
- OCR 텍스트 청크
- 이미지 설명 청크
- 표 또는 구조화 문서 섹션

### Point ID 입력값

```text
attachment:{attachment_id}:{chunk_index}:{content_hash}
```

청크 내용 또는 분할 정책이 변경되면 새 Point ID를 생성한다.

### 임베딩 입력

- 파일명
- 부모 이메일 제목
- 현재 청크 본문
- 문서 분류
- 업무 식별자
- 선박명

---

### 7.1 필수 payload

#### `schema_version`

- 타입: `integer`
- 의미: 첨부파일 payload 구조 버전
- 상태: 필수

#### `parent_email_uid`

- 타입: `keyword`
- 의미: PostgreSQL `email_messages.id`와 연결하는 부모 이메일 식별자
- 상태: 필수
- 생성 시점: 첨부파일 Point 생성 시
- 갱신 시점: 부모 이메일 연결 변경 시
- 삭제 시점: Point 삭제 시

#### `attachment_id`

- 타입: `keyword`
- 의미: PostgreSQL `email_attachments.id`와 연결하는 첨부파일 식별자
- 상태: 필수
- 생성 시점: 첨부파일 Point 생성 시
- 갱신 시점: 변경하지 않음
- 삭제 시점: 첨부파일 Point 삭제 시

#### `chunk_id`

- 타입: `keyword`
- 의미: 첨부파일 내부 청크 식별자
- 상태: 필수
- 생성 시점: 청크 생성 시
- 갱신 시점: 청크 내용 또는 분할 정책 변경 시 새 값 생성
- 삭제 시점: Point 삭제 시

#### `chunk_index`

- 타입: `integer`
- 의미: 첨부파일 내부 청크 순번
- 상태: 필수
- 생성 시점: 청크 분할 시
- 갱신 시점: 재청킹 시
- 삭제 시점: Point 삭제 시

#### `chunk_text`

- 타입: `text`
- 의미: 검색 결과와 후속 LLM 입력에 사용하는 현재 청크 본문
- 상태: 필수
- 생성 시점: 문서 파싱, OCR 또는 이미지 설명 후 청크 생성 시
- 갱신 시점: 재파싱, OCR 재실행 또는 재청킹 시
- 삭제 시점: Point 삭제 시

---

### 7.2 조건부 payload

#### `page`

- 타입: `integer`
- 의미: 현재 청크가 위치한 문서 페이지 번호
- 상태: 조건부
- 저장 조건: 페이지 정보를 제공할 수 있을 때
- 갱신 시점: 문서 재파싱 시

#### `filename`

- 타입: `keyword`
- 의미: 첨부파일 원본 파일명
- 상태: 조건부
- 저장 조건: 파일명 검색 또는 검색 결과 표시에서 사용할 때
- 갱신 시점: 파일명 변경 또는 재색인 시

#### `file_group`

- 타입: `keyword`
- 의미: PDF, 이미지, 스프레드시트 등 단순 파일 유형
- 상태: 조건부
- 저장 조건: 파일 유형별 검색 필터를 사용할 때
- 갱신 시점: 파일 유형 분류 규칙 변경 시

#### `document_category`

- 타입: `keyword`
- 의미: 첨부 문서 분류 코드
- 상태: 조건부
- 저장 조건: 문서 분류별 검색 필터를 사용할 때
- 갱신 시점: 재분류 또는 사용자 수정 시

#### `parent_email_date`

- 타입: `datetime`
- 의미: 부모 이메일 발송 시각
- 상태: 조건부
- 저장 조건: 첨부파일 검색에 이메일 기간 필터를 적용할 때
- 갱신 시점: 부모 이메일 날짜 변경 또는 재색인 시

#### `parent_email_from`

- 타입: `keyword`
- 의미: 정규화된 부모 이메일 발신자 주소
- 상태: 조건부
- 저장 조건: 첨부파일 검색에 발신자 필터를 적용할 때
- 갱신 시점: 부모 이메일 발신자 변경 또는 재색인 시

#### `business_refs`

- 타입: `keyword[]`
- 의미: 첨부파일 또는 부모 이메일에서 추출한 업무 식별자 목록
- 상태: 조건부
- 저장 조건: 업무 식별자 필터 또는 정확 일치 검색을 사용할 때
- 갱신 시점: 추출 결과 변경 시

#### `vessel_names`

- 타입: `keyword[]`
- 의미: 첨부파일 또는 부모 이메일에서 추출한 선박명 목록
- 상태: 조건부
- 저장 조건: 선박명 필터 또는 정확 일치 검색을 사용할 때
- 갱신 시점: 추출 결과 변경 시

#### `chunk_type`

- 타입: `keyword`
- 의미: `text`, `ocr_text`, `image_caption`, `table` 등의 청크 유형
- 상태: 조건부
- 저장 조건: 청크 유형별 검색 필터 또는 품질 분석을 사용할 때
- 갱신 시점: 재처리 또는 청크 유형 변경 시

---

### 7.3 첨부파일 payload 예시

```python
attachment_payload = {
    "schema_version": schema_version,
    "parent_email_uid": parent_email_uid,
    "attachment_id": attachment_id,
    "chunk_id": chunk_id,
    "chunk_index": chunk_index,
    "chunk_text": chunk_text,
}
```

조건부 필드는 기능 사용 여부와 값 존재 여부에 따라 추가한다.

```python
if page is not None:
    attachment_payload["page"] = page

if filename:
    attachment_payload["filename"] = filename

if file_group:
    attachment_payload["file_group"] = file_group

if document_category:
    attachment_payload["document_category"] = document_category

if parent_email_date is not None:
    attachment_payload["parent_email_date"] = parent_email_date

if parent_email_from:
    attachment_payload["parent_email_from"] = parent_email_from

if business_refs:
    attachment_payload["business_refs"] = business_refs

if vessel_names:
    attachment_payload["vessel_names"] = vessel_names

if chunk_type:
    attachment_payload["chunk_type"] = chunk_type
```

---

## 8. Payload Index

Payload index는 실제 필터에 사용하는 필드에만 생성한다.

### 이메일 컬렉션

| 필드 | 타입 | 생성 조건 |
|---|---|---|
| `email_uid` | keyword | payload 조건으로 원본 연결 또는 삭제할 때 |
| `sent_at` | datetime | 기간 필터를 사용할 때 |
| `sender_address` | keyword | 발신자 필터를 사용할 때 |
| `mail_category` | keyword | 분류 필터를 사용할 때 |
| `business_refs` | keyword | 업무 식별자 필터를 사용할 때 |
| `vessel_names` | keyword | 선박명 필터를 사용할 때 |
| `has_attachment` | bool | 첨부파일 유무 필터를 사용할 때 |

### 첨부파일 컬렉션

| 필드 | 타입 | 생성 조건 |
|---|---|---|
| `parent_email_uid` | keyword | 부모 이메일 기준 조회 또는 삭제 |
| `attachment_id` | keyword | 첨부파일 기준 조회 또는 삭제 |
| `page` | integer | 페이지 필터를 사용할 때 |
| `file_group` | keyword | 파일 유형 필터를 사용할 때 |
| `document_category` | keyword | 문서 분류 필터를 사용할 때 |
| `parent_email_date` | datetime | 기간 필터를 사용할 때 |
| `parent_email_from` | keyword | 발신자 필터를 사용할 때 |
| `business_refs` | keyword | 업무 식별자 필터를 사용할 때 |
| `vessel_names` | keyword | 선박명 필터를 사용할 때 |
| `chunk_type` | keyword | 청크 유형 필터를 사용할 때 |

다음 필드는 payload index를 생성하지 않는다.

- `schema_version`
- `chunk_id`
- `chunk_index`
- `chunk_text`
- `filename`

---

## 9. PostgreSQL 연결

### 이메일 Point

```text
Qdrant payload.email_uid
→ PostgreSQL email_messages.id
```

### 첨부파일 Point

```text
Qdrant payload.attachment_id
→ PostgreSQL email_attachments.id
```

```text
Qdrant payload.parent_email_uid
→ PostgreSQL email_messages.id
```

### 색인 이력

다음 정보는 PostgreSQL `qdrant_index_records`에서 관리한다.

- 컬렉션명
- Point ID
- 원본 이메일 또는 첨부파일 ID
- 청크 ID와 순번
- payload 스키마 버전
- 임베딩 모델명
- 임베딩 벡터 차원
- 임베딩 대상 콘텐츠 해시
- 색인 상태
- 색인 성공 시각
- 색인 오류

---

## 10. 삭제 규칙

### 이메일 삭제

1. `email_uid`에 해당하는 이메일 Point를 삭제한다.
2. `parent_email_uid`에 해당하는 모든 첨부파일 Point를 삭제한다.
3. PostgreSQL `qdrant_index_records`의 상태를 갱신한다.

### 첨부파일 삭제

1. `attachment_id`에 해당하는 모든 청크 Point를 삭제한다.
2. PostgreSQL `qdrant_index_records`의 상태를 갱신한다.

### 재색인

1. 원본 데이터와 현재 색인 기록의 콘텐츠 해시를 비교한다.
2. 변경된 이메일 또는 첨부파일 Point를 삭제한다.
3. 새 벡터와 payload를 생성해 upsert한다.
4. 색인 기록을 갱신한다.

### Similar-case legacy collection 교체

Provenance가 없는 기존 similar-case point는 production으로 backfill하지 않는다. 가장 안전한 기본 절차는 새 collection version을 만들고 PostgreSQL source of truth에서 전체 재색인한 뒤 `CORAMAIL_QDRANT_CASE_COLLECTION`을 새 collection으로 전환하는 것이다. 기존 collection에 production, demo, evaluation point가 섞였거나 provenance source를 신뢰할 수 없으면 in-place backfill을 금지한다.

```bash
python -m app.tools.qdrant_similar_case_index \
  --collection coramail_cases_production_v2 \
  reindex-production --provider gmail

python -m app.tools.qdrant_similar_case_index \
  --collection coramail_cases_production_v2 \
  verify
```

`verify`는 required provenance 누락, dataset/provider 분포, production인데 synthetic/evaluation인 invalid point, production account id 누락 수를 출력한다. 검증 후 애플리케이션 환경변수의 `CORAMAIL_QDRANT_CASE_COLLECTION`을 새 collection으로 바꾼다.

---

## 11. 구현 체크리스트

- [ ] 이메일 payload에 이메일 본문 전체가 저장되지 않는가?
- [ ] 첨부파일 payload에는 현재 검색 청크 본문만 저장되는가?
- [ ] 이메일 Point가 `email_uid`로 PostgreSQL 원본과 연결되는가?
- [ ] 첨부파일 Point가 `attachment_id`와 `parent_email_uid`로 연결되는가?
- [ ] 조건부 필드는 값과 실제 기능이 있을 때만 저장되는가?
- [ ] 실제 필터에 사용하는 필드에만 payload index가 생성되는가?
- [ ] 모델명, 벡터 차원, 콘텐츠 해시는 PostgreSQL 색인 기록에서 관리되는가?
- [ ] Point ID가 결정적으로 생성되는가?
- [ ] PostgreSQL과 파일 저장소 원본으로 전체 재색인이 가능한가?
- [ ] payload 구조 변경 시 `schema_version`이 갱신되는가?

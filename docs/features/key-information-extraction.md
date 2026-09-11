# F-05 Key Information Extraction

## Purpose

메일 본문과 첨부파일 분석 결과에서 업무 수행에 필요한 핵심 필드를 구조화해 추출한다. 추출 결과는 요약, 검색 필터, 담당자 라우팅, 사람 검토, 평가 데이터의 입력으로 사용한다.

## Users

- 업무 담당자
- 업무 관리자
- AI 운영·개발 담당자

## Related Scenarios

- SC-01 신규 문의 메일 자동 분석
- SC-02 견적의뢰서 첨부 메일 분석
- SC-03 발주 메일 식별 및 담당자 연결
- SC-04 기술 검토 요청 분석
- SC-06 AI 오분류 수정 및 평가 데이터 축적

## Input Data

- `email_messages`의 제목, 본문, 발신자, 수신 시각
- `email_attachments`의 파일명과 문서 유형
- `attachment_analysis_results`의 파싱, OCR, field extraction, line items
- 현재 업무 분류와 관련 검색 문맥

## Output Data

| 필드 | 예시 |
|---|---|
| `customer_name` | 고객사 또는 담당자명 |
| `business_refs` | 발주번호, 견적번호, 참조번호 |
| `vessel_names` | 선박명 |
| `product_names` | 제품명, 부품명, 모델명 |
| `quantities` | 수량과 단위 |
| `requested_due_date` | 요청 납기 |
| `requested_action` | 견적, 납기 확인, 기술 검토, 수리 요청 |
| `evidence` | 원문 또는 첨부 근거 |
| `confidence_by_field` | 필드별 신뢰도 |
| `missing_required_fields` | 필수 누락 필드 |

## State

| 상태 | 의미 |
|---|---|
| `pending` | 추출 대기 |
| `processing` | 추출 실행 중 |
| `success` | 현재 추출 결과 유효 |
| `partial_success` | 일부 필드만 추출 |
| `failed` | 추출 실패 |

## Normal Flow

1. 현재 메일과 첨부 분석 결과를 조회한다.
2. 업무 유형별 필수 필드 목록을 결정한다.
3. 본문, 첨부, 검색 문맥을 결합해 추출 입력을 구성한다.
4. 구조화 출력 schema로 필드, 근거, 신뢰도를 생성한다.
5. 필수 필드 누락과 충돌 여부를 검사한다.
6. `email_analysis_results` 또는 `attachment_analysis_results`에 현재 결과를 저장한다.
7. 누락 또는 충돌이 있으면 사람 검토 대상으로 표시한다.

## Exception Flow

- 첨부 분석이 끝나지 않았으면 본문 기반 partial result를 만들 수 있다.
- 본문과 첨부의 값이 충돌하면 하나로 확정하지 않는다.
- 날짜 형식이 모호하면 원문 값을 보존하고 정규화 상태를 별도 표시한다.
- 여러 품목과 수량의 행 연결이 불확실하면 row confidence를 낮춘다.

## Human Review Conditions

- 업무 유형별 필수 필드가 누락되었다.
- 동일 필드 후보가 여러 개이고 점수 차이가 작다.
- 본문과 첨부파일 값이 충돌한다.
- 품목과 수량의 행 연결이 불확실하다.
- 추출 결과가 사용자 업무 판단과 맞지 않아 수정되었다.

## API Contract

운영 목표:

- `POST /api/emails/{email_uid}/extracted-fields/regenerate`
- `GET /api/emails/{email_uid}/extracted-fields`
- `PATCH /api/emails/{email_uid}/extracted-fields`
- `GET /api/emails/{email_uid}/extracted-fields/history`

## Storage

- 이메일 단위 필드: `email_analysis_results`
- 첨부파일 단위 필드와 line items: `attachment_analysis_results`
- 사용자 수정: F-09 correction 저장 정책
- 작업 상태: `processing_jobs`
- 감사 로그: `audit_logs`

## Test Criteria

- 필드 결과는 값, 신뢰도, 근거를 함께 가진다.
- 누락 필드는 빈 값과 review flag로 표현한다.
- 사용자 수정은 최초 AI 추출 결과를 덮어쓰지 않는다.
- schema validation 실패는 원본 메일 조회를 막지 않는다.

## LLMOps Notes

필드별 정확도, 누락률, 사용자 수정률, 문서 유형별 추출 품질, schema validation 실패율을 기록한다.


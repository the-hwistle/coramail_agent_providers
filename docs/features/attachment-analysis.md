# F-06 Attachment Analysis

## Purpose

첨부파일의 유형, 텍스트, 이미지, 표, 핵심 필드를 분석해 메일 분류와 업무 판단에 사용할 수 있는 구조화 결과를 만든다.

## Users

- 업무 담당자
- 업무 관리자
- AI 운영·개발 담당자

## Related Scenarios

- SC-02 견적의뢰서 첨부 메일 분석
- SC-04 기술 검토 요청 분석
- SC-07 AI 분석 실패와 안전한 대체 흐름

## Input Data

- `email_attachments`의 filename, storage URI, MIME type, file size, checksum
- PDF, 이미지, 문서, 스프레드시트 원본
- 문서 분류 기준 `document_categories`

## Output Data

- 문서 유형
- 텍스트 파싱 결과
- OCR 텍스트 또는 이미지 설명
- 문서 유형별 고정 스키마에 포함된 구조화 필드
- 견적서(`quote`)와 견적의뢰서(`rfq`)의 line items와 표 행
- 페이지, chunk, 근거 위치
- 분석 상태와 오류 원인

## State

| 상태 | 의미 |
|---|---|
| `pending` | 분석 대기 |
| `processing` | 분석 실행 중 |
| `completed` | 분석 완료 |
| `failed` | 분석 실패 |
| `unsupported` | 지원하지 않는 파일 |
| `partial_success` | 일부 결과만 생성 |

## Normal Flow

1. 첨부파일 메타데이터와 원본 저장 위치를 확인한다.
2. 파일 유형과 크기 제한을 검사한다.
3. 문서 유형을 분류한다.
4. 텍스트 파싱, OCR, 이미지 설명, 표 추출 중 필요한 경로를 실행한다.
5. PaddleOCR PP-StructureV3가 로컬 런타임에 있고 `CORAMAIL_PADDLEOCR_ENABLED`가 켜져 있으면
   PDF/이미지에서 구조화 Markdown을 얻고 이를 HTML로 정규화해 `document_html`에 보존한다.
   `CORAMAIL_PADDLEOCR_MODE=auto`는 텍스트가 비었거나 OCR이 필요한 PDF 페이지와 이미지에만 사용하고,
   `always`는 PDF/이미지 첨부에 PaddleOCR 결과를 우선 사용한다. PaddleOCR 미설치 또는 실패는
   기존 parser/Vision 경로로 내려가며 실패 원인을 warning으로 남긴다. 기본 실행 장치는
   `CORAMAIL_PADDLEOCR_DEVICE=gpu`이고 Compose `web` 서비스는 GPU를 노출한다. GPU가 없는
   개발 환경에서만 명시적으로 `CORAMAIL_PADDLEOCR_DEVICE=cpu`로 낮춘다. CPU 실행에서는
   `CORAMAIL_PADDLEOCR_MKLDNN=false`를 기본으로 둬 Paddle oneDNN 런타임 호환성 문제를 피한다.
6. 파싱 텍스트가 있으면 문서 이해 모델로 문서 유형, 업무 요약, 참조번호, 금액, 납기,
   품목 같은 사용자용 필드를 추출한다.
   `document_html`이 있으면 텍스트 LLM/vLLM에는 평문 대신 HTML을 우선 전달해 표 header-cell 관계와
   페이지 구조를 유지한다.
7. 분석 결과를 `attachment_analysis_results`에 analysis type별로 저장한다.
8. 검색 대상 청크를 생성하고 F-07 색인 작업을 등록한다.
9. 메일 상세 화면의 파일별 `Details`에는 checksum, analyzer, 분석 상태 같은 내부
   메타데이터 대신 문서 유형에 맞는 정보 추출 결과를 표로 표시한다.
10. 기존 `coramail_ai`의 `document_category`/`extracted_fields` 결과와 Mail Decision의
   `document_type`/`fields` 결과를 동일한 사용자용 표 계약으로 표시한다.
11. 고정 스키마가 있는 문서 유형은 저장 전과 표시 전 모두 허용 필드명으로 필터링한다.
   모델이 `Contact Person`, `Fluemax Ref No`, `Jinhan Line Ref No`처럼 양식별 변형 라벨을
   반환하면 고정 스키마 위반으로 거부하거나 결과에서 제외한다. 비고정 필드를 다른 고정
   필드명으로 변환해 살리지 않는다. 표 데이터는 견적서와 견적의뢰서에서만 `line_items`로 유지한다.
   견적서(`quote`)의 고정 필드 풀은 `To`, `Attn`, `Your Ref No`, `Date`, `Our Ref No`,
   `In Charge`, `Tel`, `Vessel`, `Total Price`, `line_items`로 제한한다. `line_items`의 각 행은
   `Description`, `Qty`, `Unit`, `U/Price`, `Amount`만 보존한다. `No`, `Code`, `REMARK`,
   납기/포장/결제 조건 같은 견적서 부가 라벨은 시연용 추출 필드로 추가하지 않는다.
   견적의뢰서(`rfq`)의 고정 필드 풀은 `To`, `Attn`, `Email`, `Tel`, `Fax`, `Vessel`,
   `Date`, `Our Ref No`, `In Charge`, `line_items`를 우선 표시하고, `line_items`의 각 행은
   `No`, `Description`, `Code`, `Qty`, `Unit`만 보존한다. 견적의뢰서에는 가격 컬럼
   `U/Price`, `Amount`, `Total Price`를 생성하지 않는다.
   견적의뢰서 표도 `No` 컬럼의 최대 숫자를 전체 품목 수로 보고, 추출한 `line_items` 수가
   그보다 적으면 표 텍스트에서 `No` 기준으로 같은 행의 `Description`, `Code`, `Qty`, `Unit`을
   다시 복구한다. 재복구 후에도 품목 수가 부족하면
   `fixed_rfq_line_items_missing:expected=<n>,actual=<m>` warning을 남긴다.
   1차 추출 후에는 고정 필드 검증을 실행하고, 누락된 필드는 파싱 텍스트에서 결정적 재추출을
   한 번 더 수행한다. 재추출 후에도 누락된 필드는 `fixed_quote_schema_missing:<field list>`
   warning으로 기록해 사람 검토 또는 후속 재분석 근거로 남긴다.
   견적서 표에 `No` 컬럼이 있으면 `No`의 최대 숫자를 전체 품목 수로 보고, `line_items` 수가
   그보다 적을 때는 표 텍스트에서 품목 행을 다시 복구한다. 재복구 후에도 품목 수가 부족하면
   `fixed_quote_line_items_missing:expected=<n>,actual=<m>` warning을 남긴다. `No` 값은 검증에만
   사용하고 추출 field pool에는 추가하지 않는다.
12. 문서/이미지 유형 레이블은 `coramail_ai`의 기준을 따른다. 허용 카테고리는
   `quote`, `rfq`, `purchase_order`, `payment_request`, `transaction_statement`, `drawing_scan`,
   `manual_scan`, `field_photo`, `part_photo`, `document_scan`, `unknown`이다.
   PDF 텍스트의 `QUOTATION`, `INQUIRY`, `견적서`, `견적의뢰서`, `입금요청서`,
   `거래명세서`는 사전 규칙으로 먼저 분류하고, 이미지 파일은 파일명과 MIME 기준으로
   도면 스캔본, 매뉴얼 스캔본, 현장 사진, 부품 사진, JPG 스캔본 중 하나의 fallback
   레이블을 부여한다.

## Exception Flow

- 원본 파일이 없으면 metadata-only 상태로 표시한다.
- 암호화, 손상, 초과 크기 파일은 실패 또는 unsupported 상태로 저장한다.
- OCR이 실패해도 파일 메타데이터와 문서 유형 후보는 보존한다.
- 일부 페이지 실패는 전체 실패가 아니라 partial success로 저장할 수 있다.

## Human Review Conditions

- 문서 유형 신뢰도가 낮다.
- OCR 또는 파싱이 실패했다.
- 표 행 연결이 불확실하다.
- 첨부파일과 본문이 서로 다른 업무 유형을 가리킨다.
- 분석 불가 파일이 핵심 업무 판단에 필요하다.

## API Contract

현재 구현:

- `GET /api/emails/{email_index}/attachments/{attachment_index}`
- `POST /ui/emails/{email_uid}/attachments/reanalyze`
- `POST /api/emails/{email_uid}/attachments/reanalyze`
- Gmail mode는 동기화 시 원본을 `data/runtime/gmail_attachments/`에 내려받고 PostgreSQL attachment UUID와 연결한다.

운영 목표:

- `POST /api/attachments/{attachment_id}/analyze`
- `GET /api/attachments/{attachment_id}/analysis`
- `GET /api/attachments/{attachment_id}/analysis/history`
- `GET /api/attachments/{attachment_id}/file`

## Storage

- 첨부파일 메타데이터: `email_attachments`
- 문서 분류: `document_categories`
- 분석 결과: `attachment_analysis_results`
- 색인 연결: `qdrant_index_records`
- 작업 상태: `processing_jobs`

## Test Criteria

- 원본 파일이 없어도 상세 화면은 missing 상태를 표시한다.
- 분석 종류별 current 결과는 하나만 존재한다.
- 실패 원인과 재시도 가능 여부를 기록한다.
- 분석 결과는 부모 메일과 연결된다.

## LLMOps Notes

파일 유형, 페이지 수, OCR 여부, 분석 시간, 실패 원인, 문서 유형별 추출 정확도, 사용자 수정률을 기록한다.

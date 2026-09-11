# F-13 Attachment Document Type Navigation

## Purpose

첨부파일 분석 결과의 문서 유형을 기준으로 이메일을 탐색한다. 사용자는 블로그 태그처럼 문서 유형을 기준으로 업무 메일을 좁혀 보고, 견적의뢰서·견적서·발주서·도면 같은 첨부가 포함된 메일을 빠르게 확인한다.

이 기능은 새 판단을 만들지 않는다. F-06 첨부파일 분석 결과를 사용자가 검토 가능한 탐색 화면으로 노출해 첨부 기반 분류, 담당자 라우팅, 사람 검토 흐름을 보조한다.

## Users

- 업무 담당자
- 업무 관리자
- AI 운영·개발 담당자

## Input Data

- `email_messages`의 발신자, 제목, 본문 미리보기, 수신 시각, 업무 상태
- `email_attachments`의 첨부파일명과 메타데이터
- `attachment_analysis_results.result_json.document_type`
- 현재 업무 분류와 담당자 라우팅 표시값

## Output Data

화면은 문서 유형별 섹션을 제공한다.

- 문서 유형 라벨과 내부 코드
- 해당 유형이 포함된 이메일 수
- 해당 유형으로 매칭된 첨부파일 수
- 이메일별 발신자, 제목, 업무 상태, 업무 분류, 담당자
- 이메일별 매칭 첨부파일명과 분석 상태

## Document Type Scope

초기 섹션 순서는 다음을 기준으로 한다.

- `rfq`: 견적의뢰서
- `quote`: 견적서
- `purchase_order`: 발주서
- `delivery_confirmation`: 납기 확인
- `payment_request`: 입금요청서
- `transaction_statement`: 거래명세서
- `invoice`: 송장
- `drawing_scan`: 도면 스캔본
- `manual_scan`: 매뉴얼 스캔본
- `field_photo`: 현장 사진
- `part_photo`: 부품 사진
- `document_scan`: JPG 스캔본
- `unknown`: 알 수 없음

한 이메일이 여러 문서 유형 첨부를 포함하면 각 문서 유형 섹션에 각각 노출한다. 같은 유형 첨부가 여러 개 있어도 한 섹션 안의 이메일 목록에는 이메일 한 건으로 표시하고, 매칭 첨부파일 수는 별도로 집계한다.

## Normal Flow

1. 사용자가 `Documents` 탭을 연다.
2. 시스템은 현재 첨부 분석 결과를 이메일과 조인한다.
3. 문서 유형별 섹션을 만들고 이메일 수와 첨부파일 수를 계산한다.
4. 각 섹션에는 최신 수신 메일 순으로 이메일을 표시한다.
5. 사용자가 이메일 행을 선택하면 기존 Inbox 상세 화면으로 이동한다.
6. 검색어가 입력되면 발신자, 제목, 본문 미리보기, 업무 분류 기준으로 섹션을 다시 계산한다.

## Exception Flow

- 첨부 분석 결과가 없으면 `미분석` 또는 `알 수 없음`으로 분리한다.
- 분석 실패나 부분 성공 상태는 이메일을 숨기지 않고 첨부 상태로 표시한다.
- DB가 없는 데모 fixture 모드에서는 합성 기대 라벨을 사용해 동일한 화면 계약을 유지한다.

## API Contract

- `GET /ui/documents`
  - Query: optional `q`
- Response: Documents 탭 HTML
- `GET /ui/document-types`
  - Query: optional `q`
  - Response: 기존 링크 호환용 Documents 탭 HTML
- `GET /ui/document-type-sections`
  - Query: optional `q`
  - Response: 문서 유형 섹션 HTML fragment

## Storage

새 저장소는 만들지 않는다. 현재 구현은 `attachment_analysis_results`의 current `document_understanding` 결과를 읽는다. 운영 데이터가 늘어나면 `email_attachments`에 현재 문서 유형 검색용 컬럼 또는 `document_category_id` 동기화 정책을 추가할 수 있다.

## Test Criteria

- 문서 유형별 섹션이 정해진 순서로 표시된다.
- `purchase_order`와 `발주서`가 같은 문서 유형으로 정규화된다.
- 같은 이메일의 같은 유형 첨부가 여러 개 있어도 이메일 수는 1건으로 집계된다.
- 한 이메일이 여러 문서 유형 첨부를 가지면 여러 섹션에 노출된다.
- 섹션 행을 클릭하면 기존 Inbox 상세 화면으로 이동한다.

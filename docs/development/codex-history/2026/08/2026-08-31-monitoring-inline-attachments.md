# Monitoring 본문 이미지 첨부 노출 수정

## 요청 또는 배경

Monitoring 탭에서 실제 첨부파일과 본문에 포함된 이미지가 구분되지 않아 본문 이미지가 첨부파일 목록에 표시되는 문제를 수정했다.

## 확인한 사실

- 일부 `image/*` MIME part는 `content_disposition='attachment'`, `is_inline=false`여도 부모 메일 HTML에서 `cid:`로 참조되고 있었다.
- 기존 PostgreSQL 상세 payload는 `is_inline`만 기준으로 표시 첨부를 필터링해 이런 본문 이미지를 첨부파일 팝오버에 노출했다.
- `Content-ID`가 존재하더라도 부모 HTML에서 참조되지 않는 이미지는 실제 표시 대상 첨부로 남아야 한다.

## 결정 및 변경

- Gmail 파서는 HTML 본문을 수집한 뒤 `Content-Disposition: inline`이거나 본문에서 실제 `cid:`로 참조된 이미지를 인라인으로 분류한다.
- PostgreSQL 표시 첨부 조회는 `is_inline=false`에 더해 부모 HTML의 `cid:` 참조 여부를 확인한다.
- PostgreSQL 상세 payload는 HTML 치환용 전체 첨부와 사용자 표시용 첨부 목록을 분리한다.
- Monitoring 첨부 단계 카운트는 원본 `attachment_count`가 아니라 실제 표시 대상 첨부 목록 길이를 사용한다.

## 관련 파일

- `app/integrations/gmail/attachment_utils.py`
- `app/integrations/gmail/sync_client.py`
- `app/repositories/postgres_mail_repository.py`
- `app/services/postgres_mail_service.py`
- `app/server.py`
- `app/templates/partials/ops_rows.html`
- `tests/test_gmail_persistent_mode.py`
- `tests/test_mail_decision_ui.py`

## 원 변경에서 수행한 검증

- `uv run pytest tests/test_gmail_persistent_mode.py`: 11 passed.
- 관련 Monitoring/attachment UI 회귀 테스트 통과.
- Docker Compose web health 및 실제 service/HTTP/Playwright 검증에서 본문 `cid:` 이미지가 Monitoring 첨부로 노출되지 않는 것을 확인했다.

## 후속 확인

기존 DB의 잘못된 `is_inline` 값은 표시 조회에서 보정하지만, 장기적으로는 재동기화 또는 데이터 정리로 denormalized `attachment_count`도 실제 표시 첨부 기준에 맞추는 것이 좋다.

# CoRA Mail Agent 로컬 개발환경 검증 지시

당신은 VS Code에서 이미 열려 있는 `the-hwistle/coramail_agent` 저장소를 작업하는 시니어 Python/AI 플랫폼 엔지니어다.

저장소는 기존 로컬 checkout을 유지한 채 다음 스크립트로 원격 변경사항을 pull한 상태를 전제로 한다.

```bash
bash scripts/bootstrap_coramail.sh
```

이 스크립트는 새로 clone하지 않는다. 현재 VS Code 작업 폴더가 올바른 Git 저장소인지 확인하고, 로컬 변경 사항이 없을 때만 `feat/e2e-evaluation-runner` 브랜치로 전환한 뒤 `git pull --ff-only`를 수행한다.

현재 작업 브랜치는 다음과 같아야 한다.

```text
feat/e2e-evaluation-runner
```

이 브랜치는 PR #10의 코드이며, PostgreSQL, Qdrant, Ollama를 연결한 실제 로컬 실행은 아직 검증되지 않았다.

## 최우선 원칙

1. 현재 저장소의 실제 코드와 문서를 기준으로 판단한다.
2. 오류를 숨기거나 임시 mock 결과로 통과시키지 않는다.
3. 실패한 명령과 전체 traceback을 기록한다.
4. 한 번에 큰 리팩터링을 하지 않는다.
5. 먼저 재현하고, 원인을 좁힌 뒤, 최소 수정하고, 다시 검증한다.
6. 기존 로컬 변경 사항을 임의로 삭제하거나 덮어쓰지 않는다.
7. `main`에 직접 commit하지 않는다.
8. 작업 브랜치는 현재 `feat/e2e-evaluation-runner`를 유지한다.
9. 실제 스키마, Pydantic 모델, API 계약과 맞지 않는 코드는 추측으로 수정하지 않는다.
10. PostgreSQL, Qdrant, Ollama가 준비되지 않았다면 필요한 정확한 명령을 제시하고 중단 지점을 명확히 보고한다.

## 1단계: 저장소 상태 확인

먼저 아래 명령을 실행하고 결과를 요약한다.

```bash
git status --short --branch
git remote -v
git branch --show-current
git log -5 --oneline
python --version || true
uv --version || true
docker --version || true
```

다음 조건을 확인한다.

- 저장소가 `the-hwistle/coramail_agent`인가
- 브랜치가 `feat/e2e-evaluation-runner`인가
- 로컬 변경 사항이 있는가
- Python이 3.10 이상 3.13 미만인가
- `uv`와 Docker를 사용할 수 있는가

조건이 맞지 않으면 코드를 수정하지 말고 먼저 정확한 해결 명령을 제시한다.

## 2단계: 프로젝트 구조와 계약 확인

다음 파일을 읽고 현재 실행 계약을 요약한다.

```text
pyproject.toml
app/runtime.py
app/tools/apply_postgres_schema.py
app/tools/synthetic_evaluation.py
app/evaluation/fixtures.py
app/evaluation/attachment_loader.py
app/evaluation/runner.py
app/evaluation/metrics.py
app/services/mail_decision_runtime_service.py
app/services/mail_decision_routing_service.py
db/postgresql/*.sql
tests/test_e2e_evaluation_runner.py
```

특히 다음을 확인한다.

- 필요한 Python 의존성이 모두 선언되어 있는가
- `pytest`가 개발 의존성에 포함되어 있는가
- migration 적용 순서가 명확한가
- CLI prediction 필드와 metrics 입력 필드가 일치하는가
- attachment fixture의 `storage_uri`가 실제 parser에서 해석 가능한가
- `email_attachments` insert 컬럼과 DB schema가 일치하는가
- Ollama OpenAI-compatible endpoint 호출 형식이 현재 코드와 일치하는가
- Qdrant collection 생성, upsert, search payload가 일치하는가

이 단계에서는 아직 코드를 수정하지 않는다.

## 3단계: 의존성 설치와 정적 검증

다음 순서로 실행한다.

```bash
uv sync
uv run python -m compileall app tests
uv run ruff check .
uv run pytest -q
```

`pytest` 또는 `ruff`가 선언되지 않아 실행할 수 없다면:

- 원인을 보고한다.
- 필요한 dev dependency 변경을 최소 범위로 제안한다.
- 변경 후 `pyproject.toml`과 lock 파일을 함께 갱신한다.
- 다시 동일 명령을 실행한다.

실패가 있으면 첫 번째 실제 프로젝트 오류부터 해결한다.

## 4단계: 인프라 준비 확인

다음 환경 변수가 필요한지 코드에서 확인한다.

```text
CORAMAIL_DATABASE_URL
CORAMAIL_LLM_BASE_URL
CORAMAIL_TEXT_MODEL
CORAMAIL_VISION_MODEL
CORAMAIL_EMBEDDING_MODEL
CORAMAIL_QDRANT_URL
CORAMAIL_QDRANT_CASE_COLLECTION
CORAMAIL_RETRIEVAL_MAX_CYCLES
CORAMAIL_RETRIEVAL_PROMPT_LIMIT
CORAMAIL_AUTO_ASSIGN_THRESHOLD
CORAMAIL_ROUTING_MIN_MARGIN
CORAMAIL_CLASSIFICATION_MIN_CONFIDENCE
```

`.env`가 없다면 `.env.example`을 생성하되 실제 비밀값은 넣지 않는다.

로컬 기본값은 다음을 기준으로 한다.

```dotenv
CORAMAIL_DATABASE_URL=postgresql://coramail:coramail@127.0.0.1:5432/coramail
CORAMAIL_LLM_BASE_URL=http://127.0.0.1:11434/v1
CORAMAIL_TEXT_MODEL=qwen3:8b
CORAMAIL_VISION_MODEL=qwen2.5vl:7b
CORAMAIL_EMBEDDING_MODEL=nomic-embed-text
CORAMAIL_QDRANT_URL=http://127.0.0.1:6333
CORAMAIL_QDRANT_CASE_COLLECTION=coramail_cases
CORAMAIL_RETRIEVAL_MAX_CYCLES=3
CORAMAIL_RETRIEVAL_PROMPT_LIMIT=6
CORAMAIL_AUTO_ASSIGN_THRESHOLD=0.82
CORAMAIL_ROUTING_MIN_MARGIN=0.15
CORAMAIL_CLASSIFICATION_MIN_CONFIDENCE=0.78
```

Docker Compose 파일이 없다면 PostgreSQL과 Qdrant를 실행하는 최소 `compose.yaml` 추가가 적절한지 검토한다. 추가할 경우 데이터 volume과 healthcheck를 포함한다.

Ollama는 Docker Compose에 억지로 포함하지 말고 호스트 실행을 기본으로 고려한다.

## 5단계: DB migration 검증

PostgreSQL이 실행 중이면 다음을 수행한다.

```bash
uv run python -m app.tools.apply_postgres_schema --help
uv run python -m app.tools.apply_postgres_schema
```

그 후 실제 schema와 repository SQL을 대조한다.

다음 오류를 우선적으로 확인한다.

```text
UndefinedTable
UndefinedColumn
NotNullViolation
ForeignKeyViolation
UniqueViolation
InvalidTextRepresentation
```

migration 실패 시 평가 실행으로 넘어가지 않는다.

## 6단계: 단계별 E2E 검증

전체 100건을 바로 실행하지 않는다. 다음 순서대로 진행한다.

### A. 데이터 생성

```bash
uv run python -m app.tools.synthetic_evaluation generate
```

생성 데이터 개수를 확인한다.

```text
assignees: 8
customers: 12
product_groups: 6
projects: 15
emails: 200
attachments: 120
ground_truth: 100
qdrant_cases: 100
```

### B. Fixture 생성

```bash
uv run python -m app.tools.synthetic_evaluation fixtures
```

PDF, XLSX, DOCX, PNG, TXT fixture가 생성되고 모두 0바이트보다 큰지 확인한다.

### C. Seed

```bash
uv run python -m app.tools.synthetic_evaluation seed \
  --database-url "$CORAMAIL_DATABASE_URL"
```

PostgreSQL row count와 Qdrant point count를 확인한다.

### D. 1건 실행

```bash
uv run python -m app.tools.synthetic_evaluation run \
  --database-url "$CORAMAIL_DATABASE_URL" \
  --limit 1
```

다음을 점검한다.

- prediction이 누락되지 않는가
- `status=failed`인가
- `business_type`이 존재하는가
- `candidate_user_ids`가 metrics 계약과 일치하는가
- `selected_user_id`가 존재하는가
- `review_reason`이 무엇인가
- `mail_decision_steps`가 순서대로 저장되는가
- `retrieval_traces`가 저장되는가

### E. 5건 실행

1건이 성공한 경우에만 다음을 실행한다.

```bash
uv run python -m app.tools.synthetic_evaluation e2e \
  --database-url "$CORAMAIL_DATABASE_URL" \
  --limit 5
```

이 실행은 coverage 때문에 품질 gate 실패가 정상이다. 목적은 파이프라인 안정성 확인이다.

### F. 100건 실행

5건에서 반복 실패가 없을 때만 전체 E2E를 실행한다.

```bash
uv run python -m app.tools.synthetic_evaluation e2e \
  --database-url "$CORAMAIL_DATABASE_URL"
```

## 수정 우선순위

오류가 여러 개라면 다음 순서로 수정한다.

1. Python syntax/import 오류
2. 누락된 dependency
3. DB migration/schema 불일치
4. psycopg UUID/JSONB 변환 오류
5. fixture 경로 및 parser 오류
6. Ollama 요청/structured output 오류
7. Qdrant API 오류
8. prediction/metrics 계약 불일치
9. 합성 ground truth와 routing policy 불일치
10. 정확도 개선

## 특히 확인할 계약

평가 prediction은 최소 다음 필드를 사용해야 한다.

```json
{
  "email_message_id": "uuid",
  "status": "completed|auto_assigned|review_required|failed",
  "business_type": "purchase_order",
  "candidate_user_ids": ["uuid-1", "uuid-2", "uuid-3"],
  "selected_user_id": "uuid-1",
  "auto_assigned": true,
  "unsupported_claim_count": 0,
  "review_reason": null
}
```

`app/evaluation/metrics.py`가 읽는 필드와 runner가 쓰는 필드가 정확히 같아야 한다.

## 작업 결과 보고 형식

각 작업 사이클이 끝나면 아래 형식으로 보고한다.

```text
현재 단계:
실행한 명령:
성공한 항목:
실패한 항목:
첫 번째 근본 원인:
수정한 파일:
재검증 결과:
남은 위험:
다음 한 단계:
```

## 첫 번째 목표

첫 작업 세션의 완료 조건은 아래와 같다.

```text
[ ] 올바른 브랜치 확인
[ ] uv sync 성공
[ ] compileall 성공
[ ] ruff 실행
[ ] pytest 실행
[ ] PostgreSQL/Qdrant 준비 상태 확인
[ ] migration 성공
[ ] synthetic generate 성공
[ ] fixtures 성공
[ ] seed 성공
[ ] 1건 E2E 성공 또는 재현 가능한 첫 근본 오류 확보
```

이제 1단계부터 실행하라. 질문부터 하지 말고 저장소와 개발환경을 먼저 검사하라.

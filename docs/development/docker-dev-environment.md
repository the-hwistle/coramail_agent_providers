# Docker Development Environment

## 목적

이 문서는 CoRA Mail Agent 로컬 개발 환경을 재부팅 후에도 같은 상태로 복구하기 위한 Docker 기반 실행 기준을 정의한다.

현재 권장 범위는 Docker Compose가 웹 앱과 상태 저장 인프라를 함께 실행하는 방식이다. 로컬 host의 `uv run` 실행은 예외적인 디버깅 경로로만 유지한다.

```text
Docker Compose
  - web FastAPI dev server
  - startup bootstrap
  - PostgreSQL
  - Qdrant
  - Ollama optional profile
```

이 구조는 재부팅 후 PostgreSQL/Qdrant 미기동으로 웹이 깨지는 문제를 줄이고, 신규 개발자가 `docker compose up`만으로 같은 실행 환경을 재현할 수 있게 한다.

## 빠른 시작

처음 한 번 안전한 개발 기본값을 만든다.

```bash
cp .env.example .env
```

웹 앱과 개발 인프라를 함께 실행한다.

```bash
scripts/dev_up.sh
```

브라우저에서 확인한다.

```text
http://127.0.0.1:8000
```

상태 확인은 다음 endpoint를 사용한다.

```bash
curl http://127.0.0.1:8000/api/health
```

## 기본 서비스

| 서비스 | 기본 포트 | 데이터 |
|---|---:|---|
| Web | `8000` | bind mount source tree |
| PostgreSQL | `5432` | Docker volume `coramail_postgres_data` |
| Qdrant HTTP | `6333` | Docker volume `coramail_qdrant_data` |
| Qdrant gRPC | `6334` | Docker volume `coramail_qdrant_data` |
| Ollama | host `11435`, container `11434` | Docker volume `coramail_ollama_data` |

Compose container names are not pinned. Docker Compose owns the generated names under the `coramail-agent-dev` project so old stopped containers from earlier experiments do not block startup.

PostgreSQL, Qdrant, Ollama, web은 기본으로 실행한다. Ollama host port는 기존 로컬 Ollama `127.0.0.1:11434`와 충돌하지 않도록 기본 `11435`를 사용한다.

```bash
scripts/dev_pull_models.sh
```

Ollama 컨테이너를 처음 쓰면 모델은 별도로 pull해야 한다. 모델이 없으면 웹은 뜨지만 `/api/health`의 LLM 항목은 degraded로 표시된다.

## 환경 변수 기준

Compose web 컨테이너 안에서는 service name을 사용한다.

```env
CORAMAIL_DATABASE_URL=postgresql://coramail:coramail@postgres:5432/coramail
CORAMAIL_QDRANT_URL=http://qdrant:6333
CORAMAIL_LLM_BASE_URL=http://ollama:11434/v1
```

로컬 host에서 `scripts/dev_app.sh`로 직접 앱을 실행할 때만 host port를 사용한다.

```env
CORAMAIL_DATABASE_URL=postgresql://coramail:coramail@127.0.0.1:5432/coramail
CORAMAIL_QDRANT_URL=http://127.0.0.1:6333
CORAMAIL_LLM_BASE_URL=http://127.0.0.1:11434/v1
```

컨테이너 내부의 `127.0.0.1`은 호스트가 아니라 컨테이너 자신이다. 이 차이를 문서화해 둔 이유는 앱 컨테이너와 로컬 디버깅 경로의 환경 변수를 섞지 않기 위해서다.

Search/Chats 답변 생성은 `CORAMAIL_CHAT_TEXT_MODEL`로 Mail Decision 본 분석 모델과 분리할 수 있다. 값이 비어 있으면 `CORAMAIL_TEXT_MODEL`을 그대로 사용한다. 지연을 줄이기 위해 더 작은 로컬 모델을 테스트할 때는 해당 모델을 Ollama에 pull한 뒤 이 값만 바꾼다.

```env
CORAMAIL_TEXT_MODEL=llama3.2:latest
CORAMAIL_CHAT_TEXT_MODEL=llama3.2:latest
CORAMAIL_VISION_MODEL=qwen3-vl:2b
```

기존 host Ollama를 컨테이너에서 직접 쓰고 싶으면 `.env`에서 다음처럼 바꿀 수 있다. 단, host Ollama가 Docker bridge에서 접근 가능한 주소로 bind되어 있어야 한다.

```env
CORAMAIL_CONTAINER_LLM_BASE_URL=http://host.docker.internal:11434/v1
```

기본 개발/데모 provider는 Ollama다. Gemini API 같은 외부 API provider는 지연 확인용 임시 데모 경로로만 켠다. 다시 API 방식으로 전환해야 하면 로컬 `.env`에서 provider와 모델만 바꾸고, API key는 로컬 `.env` 또는 secrets store에만 둔다.

```env
CORAMAIL_LLM_PROVIDER=gemini
CORAMAIL_TEXT_MODEL=gemini-3.5-flash-lite
CORAMAIL_CHAT_TEXT_MODEL=gemini-3.5-flash-lite
CORAMAIL_VISION_MODEL=gemini-3.5-flash-lite
CORAMAIL_EMBEDDING_MODEL=gemini-embedding-001
```

## 포트 충돌

이미 로컬 PostgreSQL이나 Qdrant가 같은 포트를 사용하면 `.env`에서 host port를 바꾼다.

```env
CORAMAIL_POSTGRES_PORT=55432
CORAMAIL_DATABASE_URL=postgresql://coramail:coramail@127.0.0.1:55432/coramail
CORAMAIL_QDRANT_HTTP_PORT=6633
CORAMAIL_QDRANT_URL=http://127.0.0.1:6633
```

Compose service 내부 포트는 그대로 두고 host port만 바꾼다. 웹 포트는 `CORAMAIL_DEV_PORT`로 바꿀 수 있다.

## Schema와 Seed

`web` 컨테이너는 시작할 때마다 다음 bootstrap을 먼저 실행한 뒤 uvicorn을 시작한다.

```bash
python -m app.tools.bootstrap_dev_environment
python -m uvicorn app.server:app --host 0.0.0.0 --port 8000
```

기본 Qdrant collection은 `CORAMAIL_QDRANT_VECTOR_SIZE=768`과 Cosine distance로 생성한다. 이는 현재 기본 embedding 모델 `nomic-embed-text:latest`의 개발 기준 차원이다.

Compose의 `web` 서비스는 안정성을 위해 hot reload를 사용하지 않는다. 소스 코드, 템플릿, CSS, 문서, 테스트 파일을 수정한 뒤 컨테이너에 반영하려면 명시적으로 웹 서비스를 재시작한다.

```bash
docker compose restart web
```

자동 reload가 필요한 디버깅은 host에서 `scripts/dev_app.sh`로 실행하는 예외 경로를 사용한다. Compose에서 bind mount된 전체 작업트리를 reload 감시하면 세션 로그, 테스트, 대용량 로컬 디렉터리 변경 중에 웹 요청이 끊기거나 브라우저가 반복 reload될 수 있다.

현재 schema는 `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`를 사용하므로 반복 실행을 허용한다.

Demo seed는 deterministic UUID와 upsert를 사용한다. 같은 seed를 반복 적용해도 동일 row를 갱신한다.

수동으로 bootstrap만 다시 실행하려면 tools profile을 사용한다.

```bash
docker compose --profile tools run --rm bootstrap
```

## 중지와 초기화

컨테이너를 중지한다. Volume은 보존된다.

```bash
scripts/dev_down.sh
```

개발 DB와 Qdrant 데이터를 완전히 삭제하려면 명시 확인값이 필요하다.

```bash
CORAMAIL_DEV_RESET_CONFIRM=delete-dev-volumes scripts/dev_reset.sh
```

이 명령은 Docker volume을 삭제하므로 Gmail sync 결과, demo seed 이후 수동 변경, Qdrant index가 모두 사라진다.

## 로컬 디버깅 경로

컨테이너 밖에서 debugger를 붙이거나 특정 IDE 통합이 필요하면 인프라는 Compose로 유지하고 앱만 host에서 실행할 수 있다.

```bash
docker compose up -d postgres qdrant
docker compose --profile tools run --rm bootstrap
scripts/dev_app.sh
```

이 경로는 기본 개발 경로가 아니다. 기본은 `docker compose up` 또는 `scripts/dev_up.sh`다.

## 운영과 다른 점

- Compose 비밀번호는 로컬 개발용 기본값이다.
- `.env`에는 실제 Gmail token, API key, 고객 데이터 경로를 커밋하지 않는다.
- 운영 배포에서는 PostgreSQL, Qdrant, LLM endpoint를 별도 보안 정책과 backup 정책으로 관리한다.
- 개발 fallback은 웹 500을 막기 위한 것이며 운영 데이터 정합성을 보장하는 장치가 아니다.
- 개발 Compose는 운영 배포 구성이 아니라 재현 가능한 로컬 실행 기준이다.
- 운영 후보는 `docker-compose.prod.yml`, `config/production.env`, `scripts/prod_*`를 사용한다. 개발용 `docker-compose.yml`, `.env.example`, `scripts/dev_*`와 섞어 실행하지 않는다.

## 남은 설계 경계

다음 항목은 개발 Compose에서 의식적으로 분리하거나 후속 설계를 필요로 한다.

- Gmail OAuth token과 callback redirect URL
- 첨부파일 저장 volume과 backup 제외 정책
- Ollama 또는 vLLM GPU runtime 연결 방식
- dev/prod env 분리와 secret 주입 방식
- schema migration 도구의 운영 실행 권한

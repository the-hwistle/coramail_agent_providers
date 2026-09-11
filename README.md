# CoRA Mail Agent

CoRA Mail Agent는 공유 업무 메일과 첨부파일을 분석하고 조직 지식과 과거 확정 사례를 검색해 적절한 담당자를 근거와 함께 배정하는 온프레미스 Agentic RAG 시스템이다.

최종 성공 기준은 단순한 메일 요약이나 분류가 아니라 **정확하고 근거를 추적할 수 있는 담당자 배정**이다. 첨부파일 이해, 사실 추출, 검색, 요약, 업무 유형 분류, 후보 생성, 검증, 사람 검토는 하나의 `Mail Decision Run` 안에서 이어진다.

## 현재 구현 상태

이 저장소는 더 이상 초기 설계 단계가 아니다. 제품·아키텍처 문서 기준선 위에 실제 애플리케이션과 평가 체계가 구현되어 있으며, 현재 초점은 운영 수준 검증과 구조 안정화다.

### 구현되어 있는 주요 영역

- FastAPI 기반 웹/API 애플리케이션
- Gmail OAuth, Naver IMAP, Hiworks POP3 메일 동기화 흐름
- PostgreSQL 스키마·migration·repository
- Qdrant 유사 사례 색인과 retrieval
- PDF, 이미지, XLSX, DOCX 등 첨부파일 분석
- Fact Extraction Agent와 Decision Agent
- 결정적 Mail Decision workflow
- 담당자 후보 생성과 routing policy
- 사람 검토 및 업무 상태 추적
- 합성 평가 데이터, evaluation runner, metrics, leakage 검사
- pytest 기반 단위·통합 테스트와 Playwright UI E2E
- Docker Compose 기반 로컬 개발 환경

### 아직 운영 수준 검증이 필요한 영역

- 실제 수신 메일 분포에서의 routing 정확도와 자동 배정 precision
- 실제 조직 데이터와 합성 데이터 사이의 분포 차이
- LLM/Vision/embedding 런타임의 지연·실패·자원 사용량
- human-review 운영 루프와 사용자 수정 데이터를 이용한 회귀 평가
- 대형 웹 진입점·템플릿·스타일·UI 테스트의 모듈화

## 업무 맥락

현재 목표 고객 환경은 하나의 공유 Gmail 계정으로 하루 약 400~600건의 업무 메일을 받고 여러 직원이 수동으로 분류·전달하는 업무 흐름이다. CoRA Mail Agent의 1차 목표는 중복 전달과 누락을 줄이고 메일 확인·분류·담당자 판단의 일관성을 높이는 것이다.

2차 기능인 답변 초안, 자동 견적 폼, 후속 조치 제안, 반복 패턴 분석은 담당자 배정 흐름이 안정화된 뒤 확장한다.

## 핵심 아키텍처

```text
메일 수집
→ 첨부파일 분석
→ 본문·첨부 통합 사실 추출
→ 검색 계획
→ 정확 검색 / 규칙 검색 / Qdrant 유사 사례 검색 / 담당자 역량 검색
→ 문맥 충분성 평가와 필요 시 재검색
→ 구조화 요약·업무 유형·긴급성 판단
→ 담당자 후보 생성과 점수 계산
→ 결과 검증
→ 자동 배정 또는 사람 검토
```

상세 기준은 [`docs/architecture/agentic_rag_mail_decision_system.md`](docs/architecture/agentic_rag_mail_decision_system.md)를 따른다.

## 로컬 개발

```bash
cp .env.example .env
scripts/dev_up.sh
```

Docker Compose의 웹 서비스는 PostgreSQL schema, demo seed, Qdrant 기본 collection을 준비한 뒤 FastAPI 개발 서버를 실행한다. 호스트에서 직접 uvicorn을 실행해야 하는 디버깅 상황에서는 `scripts/dev_app.sh`를 사용한다.

이 저장소의 기본 개발 스택은 원본 `coramail_agent`와 분리되도록 `coramail-agent-providers-dev` Compose project를 사용한다. 기본 포트는 web `8030`, PostgreSQL `55452`, Qdrant `6653/6654`, Ollama `11456`이다.

메일 provider는 `CORAMAIL_MAIL_PROVIDER`로 선택한다. 기본값은 `gmail`이며, 새로 추가된 provider는 `naver`와 `hiworks`다. Naver는 `config/naver-feasibility.env.example`, Hiworks는 `config/hiworks-feasibility.env.example`를 기준으로 app password 환경변수를 설정한다. 실제 비밀번호나 `.env` 파일은 Git에 넣지 않는다.

Provider별 격리 검증 스택:

```bash
scripts/dev_naver_feasibility_up.sh
scripts/dev_hiworks_feasibility_up.sh
```

Provider별 격리 스택은 각각 `coramail-agent-providers-naver`, `coramail-agent-providers-hiworks` Compose project를 사용한다. 기본 포트는 Naver web `8010`, PostgreSQL `55432`, Qdrant `6633/6634`, Ollama `11436`; Hiworks web `8020`, PostgreSQL `55442`, Qdrant `6643/6644`, Ollama `11446`이다.

기본 정적 검증과 테스트:

```bash
uv sync --frozen
uv run python -m compileall app tests
uv run ruff check .
uv run pytest -q
```

UI E2E:

```bash
npm ci
npx playwright install chromium
npm run test:e2e:ui-smoke
```

자세한 로컬 실행 기준은 [`docs/development/docker-dev-environment.md`](docs/development/docker-dev-environment.md)를 참고한다.

## 운영 배포

개발 환경과 운영 환경은 분리되어 있다. `docker-compose.yml`과 `scripts/dev_*`는 로컬 개발 전용이며, 운영 후보는 `docker-compose.prod.yml`, `config/production.env`, `scripts/prod_*`만 사용한다.

```bash
cp config/production.env.example config/production.env
CORAMAIL_WEB_IMAGE=registry.example.com/coramail-agent:2026-09-03 scripts/prod_build.sh
scripts/prod_check.sh
scripts/prod_migrate.sh
scripts/prod_up.sh
```

운영 배포 전에는 [`docs/development/runbooks/deployment-readiness.md`](docs/development/runbooks/deployment-readiness.md)의 readiness gate와 최소 검증 명령을 통과해야 한다. `config/production.env`에는 실제 credential이 들어가므로 Git에 커밋하지 않는다.

## 저장소 구조

```text
coramail_agent/
├── AGENTS.md
├── app/
│   ├── AGENTS.md
│   ├── agents/
│   ├── api/
│   ├── document_processing/
│   ├── evaluation/
│   ├── integrations/
│   ├── llm/
│   ├── repositories/
│   ├── retrieval/
│   ├── routing/
│   ├── schemas/
│   ├── services/
│   └── workflows/
├── data/
│   └── AGENTS.md
├── db/postgresql/
├── docs/
│   ├── architecture/
│   ├── decisions/
│   ├── development/
│   ├── features/
│   └── product/
├── scripts/
├── tests/
│   └── AGENTS.md
└── notebooks/
```

## 문서 읽는 순서

1. 이 README
2. [`docs/product/README.md`](docs/product/README.md)
3. [`docs/product/data-reality-gap.md`](docs/product/data-reality-gap.md)
4. [`docs/architecture/agentic_rag_mail_decision_system.md`](docs/architecture/agentic_rag_mail_decision_system.md)
5. [`docs/development/README.md`](docs/development/README.md)
6. 관련 [`docs/features/`](docs/features/) 문서
7. 관련 [`docs/decisions/`](docs/decisions/) 문서
8. PostgreSQL/Qdrant 계약 문서

과거 Codex 작업 기록은 기본 필독 문서가 아니다. 특정 결정의 배경이 필요할 때만 `docs/development/codex-history/`에서 해당 날짜의 기록을 찾는다.

## 구현 원칙

- 문서와 데이터 계약이 동작 변화와 함께 갱신되어야 한다.
- 하나의 기능은 저장·서비스·API·화면·테스트·평가까지 이어져야 완료된 것으로 본다.
- 원본 데이터, AI 결과, 검색 근거, 사용자 수정, 실행 상태, 라우팅 상태를 구분한다.
- Agent는 구조화 추론과 제한된 도구 선택을 담당하고 업무 규칙·저장 로직은 workflow/service/repository에 둔다.
- 불확실한 담당자 배정은 억지로 확정하지 않고 사람 검토로 보낸다.
- AI 기능은 입력·출력 스키마, 모델/프롬프트 버전, 근거, 평가 기준, 사용자 수정 기록을 갖춰야 한다.

## 데이터 제약

현재 제공 데이터와 실제 운영에서 분석해야 하는 수신 메일 분포에는 차이가 있다. 따라서 합성 데이터는 기능 구현과 반복 평가에 사용하되 운영 성능 주장에 사용하지 않는다. 실제 수신 메일이 확보되면 분포 차이, prompt, retrieval, routing policy, 평가셋을 다시 검증한다.

합성 데이터와 생성 평가 산출물의 저장 기준은 `data/AGENTS.md`를 따른다.

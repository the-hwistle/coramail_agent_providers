# Evaluation data layout

이 디렉터리는 평가 입력과 재현 가능한 검증 기준을 보존하되, 매 실행마다 생성되는 결과물이 Git diff를 오염시키지 않도록 구분한다.

## Git에 추적하는 항목

### Source datasets

- `synthetic_mail_decision_dataset.json`
- 의도적으로 유지하는 버전별 synthetic dataset

평가 입력과 ground truth가 포함된 원본 데이터다. 생성 규칙과 버전이 바뀌면 코드·문서·평가 기준을 함께 검토한다.

### Deterministic fixtures

- `fixtures/`
- 의도적으로 유지하는 버전별 fixture 디렉터리

테스트와 재현 가능한 평가에 필요한 작은 첨부파일을 둔다. 동일 데이터를 결정적으로 생성할 수 있고 저장 비용이 커지는 경우에는 생성기로 대체하는 것을 우선 검토한다.

### Curated baselines

- `baselines/<baseline-name>/`
- 명시적으로 비교 기준으로 유지하는 버전 디렉터리(예: `clean-v2/`)

baseline으로 승격할 때는 dataset/workflow/model/prompt 버전, 유지 이유, 주요 지표를 설명하는 metadata를 함께 둔다. 단순히 한 번 실행했다는 이유로 baseline에 넣지 않는다.

## Git에 추적하지 않는 항목

일반 평가 실행 결과는 다음 경로에 생성한다.

```text
data/evaluation/runs/current/
├── predictions.json
├── latest_report.json
├── evaluation_report.json
├── evaluation_cases.csv
├── evaluation_trace.jsonl
└── leakage_report.json
```

`runs/`, `generated/`, `tmp/`는 `.gitignore` 대상이다. 다음과 같은 일회성 결과도 기본적으로 commit하지 않는다.

- prediction snapshots
- developer traces
- leakage reports
- 임시 benchmark exports
- 실패 디버깅 중 만든 중간 결과

## Baseline 승격 절차

1. `app.tools.synthetic_evaluation`로 평가를 실행한다.
2. dataset 버전, 실행 환경, workflow/model/prompt 버전을 확인한다.
3. 결과가 비교 기준으로 장기간 가치가 있는지 검토한다.
4. 필요한 결과만 `baselines/<name>/`으로 복사한다.
5. `baseline_metadata.json`에 승격 이유와 버전을 기록한다.
6. 재현 가능한 입력 dataset과 결과 계약이 함께 보존되는지 확인한다.

## 기본 명령

```bash
uv run python -m app.tools.synthetic_evaluation run --database-url "$CORAMAIL_DATABASE_URL"
uv run python -m app.tools.synthetic_evaluation score
```

별도 경로를 지정하지 않으면 실행 결과는 `data/evaluation/runs/current/`에 기록된다.

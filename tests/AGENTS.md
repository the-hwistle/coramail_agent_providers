# tests/AGENTS.md

These rules apply to tests under `tests/`.

## Test Layers

Prefer the following organization for new tests:

- `tests/unit/`: pure logic with no network or real database.
- `tests/contract/`: schema, prompt/output, workflow/persistence, and provider request/response contracts.
- `tests/integration/`: PostgreSQL, Qdrant, Gmail, API, and other adapter integration behavior.
- `tests/e2e/`: browser/system flows.

Existing flat tests may remain until touched. When a very large test file is modified, prefer extracting tests by feature rather than adding more unrelated cases to it.

## Mocking

- Mock external providers at their adapter boundary, not deep inside domain logic.
- Do not replace a failing project behavior with a mock merely to make a test pass.
- Prefer deterministic fixtures and explicit expected routing candidates/assignees.
- Preserve failure, partial-success, abstention, and human-review cases.

## Agentic RAG Regression Requirements

Changes to decision, retrieval, routing, or structured schemas should cover the relevant assertions:

- structured output validates;
- evidence can be traced to source data;
- candidate users come from trusted stores;
- unsupported claims are rejected or flagged;
- low confidence/conflicting context leads to review rather than fabricated certainty;
- evaluation input and prediction contracts remain aligned.

## Commands

```bash
uv run pytest -q <focused-test-path>
uv run pytest -q
npm run test:e2e:ui-smoke  # when UI behavior changes
```

# app/AGENTS.md

These rules apply to application code under `app/` in addition to the repository root `AGENTS.md`.

## Dependency Direction

Prefer this direction for new or refactored code:

```text
HTTP/API or web presentation
→ application service
→ workflow/domain policy
→ repository or integration adapter
```

Avoid adding new database SQL, external API calls, LLM calls, or routing decisions directly to `app/server.py` or template handlers.

## Responsibilities

- `agents/`: structured LLM reasoning over trusted inputs; no hidden persistence or invented organization facts.
- `workflows/`: deterministic orchestration, state transitions, retries, resumability, and node ordering.
- `services/`: application use cases and coordination across repositories/integrations.
- `repositories/`: persistence queries and storage-specific translation.
- `integrations/`: provider-specific APIs such as Gmail.
- `retrieval/`: exact/rule/vector retrieval, planning, context building, and evidence provenance.
- `routing/`: deterministic candidate scoring, thresholds, exceptions, abstention, and validation policy.
- `schemas/`: shared structured contracts. Schema changes require compatibility review across workflow, persistence, UI/API, and evaluation.
- `presentation/`: formatting and view-model logic only; no routing decisions.
- `api/`: thin transport adapters that validate request/response data and call application services.

## Large File Rule

Do not add new responsibilities to `app/server.py`. When touching an existing route or helper in that file, prefer extracting a coherent route group or helper module if it can be done without widening behavior changes. Preserve compatibility and add regression tests before deleting legacy paths.

## LLM And Retrieval Rules

- Validate structured model output before persistence or routing use.
- Store or propagate evidence references for facts used by routing.
- Treat missing or conflicting trusted context as a reason to abstain or require review, not as permission to infer organizational facts.
- Keep model-specific HTTP behavior inside the LLM gateway or an integration adapter.

## Verification

For ordinary Python changes run the smallest focused test first, then:

```bash
uv run python -m compileall app tests
uv run ruff check .
uv run pytest -q
```

For DB/Qdrant/Gmail/LLM integration changes, add or run the matching integration/contract tests and state explicitly when an external dependency prevented execution.

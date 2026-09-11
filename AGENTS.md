# AGENTS.md

## Purpose

This file defines repository-wide guidance for Codex and other coding agents working in CoRA Mail Agent. Keep this file focused on durable product, architecture, safety, and verification rules. Directory-specific guidance belongs in the nearest nested `AGENTS.md`.

## Product Goal

CoRA Mail Agent is an on-premises Agentic RAG mail decision system. Its primary success criterion is accurate, evidence-backed assignee routing. Summary, classification, retrieval, and attachment analysis are supporting stages of one `Mail Decision Run`.

The architecture baseline is `docs/architecture/agentic_rag_mail_decision_system.md`.

## Required Reading

Before meaningful changes, read only the documents relevant to the work:

- `README.md` for current maturity and repository navigation.
- `docs/architecture/agentic_rag_mail_decision_system.md` for the target workflow and invariants.
- `docs/development/README.md` for milestone and completion criteria.
- `docs/development/git-codex-workflow.md` for Git safety and publication rules.
- `DESIGN.md` before user-facing UI, interaction, visual styling, layout, or frontend component changes.
- the nearest nested `AGENTS.md` for directory-specific instructions.
- relevant files under `docs/product/`, `docs/features/`, `docs/architecture/`, and `docs/decisions/` when behavior or contracts change.

Do not load the legacy Codex history as a prerequisite for ordinary work. Search or read a specific archived entry only when historical context is needed.

## Architecture Invariants

- Use `Mail Decision Run` as the top-level unit for attachment analysis, fact extraction, retrieval, summary, classification, routing, validation, and human review.
- Keep workflow orchestration deterministic. Use agents for structured reasoning and constrained tool selection, not hidden state transitions.
- Do not allow an LLM to invent users, routing rules, customer relationships, product ownership, project ownership, or other organizational facts.
- Retrieve candidate facts from trusted stores and validate them before using them for routing.
- Keep original email data, attachment data, AI outputs, retrieved evidence, user corrections, processing state, routing state, and audit history distinguishable.
- Treat failure, retry, unsupported files, partial success, abstention, and human review as normal states.
- For AI features, preserve structured inputs/outputs, evidence links, prompt/model versions, evaluation expectations, and user correction records.
- Dates, quantities, identifiers, classifications, routing candidates, and routing reasons must be traceable to source mail, attachments, trusted rules, or retrieved cases.

## Goal-Oriented Execution

- Complete prerequisites, schemas, fixtures, tests, documentation, and migrations that are reasonably necessary to achieve the requested goal.
- When operating data is unavailable, use clearly labeled synthetic data rather than fabricating production claims.
- Remove obsolete or conflicting artifacts when they obstruct the documented target architecture.
- Do not preserve temporary deterministic demo behavior as if it were the completed AI capability.
- Record assumptions and risks when a safe synthetic substitute or explicit assumption is sufficient; ask only when a missing fact cannot be represented safely.

## Data And Security

- Never commit secrets, credentials, tokens, `.env` files, real customer personal data, raw private emails, local DB files, Qdrant runtime data, generated caches, or notebook checkpoints.
- Keep synthetic/demo data clearly separated from operating data.
- Synthetic datasets must state purpose, generation method, masking policy, expected labels, and differences from operating data.
- Generated evaluation outputs such as per-run predictions and traces are artifacts, not source datasets, unless a specific curated baseline is intentionally promoted.
- Do not present synthetic evaluation results as production performance.

## Git Safety

- Do not commit, push, merge, close, or otherwise publish repository changes unless the user explicitly requests that Git action.
- Never push directly to `main` as an implicit consequence of a code-edit request.
- Prefer a feature/fix/chore branch and a pull request for shareable work.
- Before any requested commit, inspect the relevant diff and verification result.
- Prefer `git revert` for committed rollback. Do not use `git reset --hard`, force push, or destructive deletion of tracked user work unless the user explicitly requests and approves it.

## Verification

Run the smallest relevant checks first, then the wider suite when the change warrants it.

Baseline commands:

```bash
uv sync --frozen
uv run python -m compileall app tests
uv run ruff check .
uv run pytest -q
```

For UI changes, also run the relevant Playwright smoke or E2E test. Visual changes must be checked against the rendered result and `DESIGN.md`; automated test success alone is not sufficient visual verification. For Agentic RAG changes, verify structured output validation, evidence traceability, retrieval behavior, routing candidate correctness, abstention/human-review transitions, and regression cases.

If a check cannot be run, state exactly which check was not run and why. Do not imply that unexecuted checks passed.

## Change Records

Git history is the source of truth for code and document diffs. Durable implementation context that is genuinely useful to future developers may be recorded as a small dated entry under `docs/development/codex-history/YYYY/MM/`.

Do not append every interaction to a single repository-wide session log, and do not duplicate long command output or diffs in history entries.

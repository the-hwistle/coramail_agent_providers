# Mail Attention Stabilization

## Scope

This note records the stabilization audit after `decision-agent:v3` split mail urgency and importance into independent axes.

## 2026-08-21 Product Direction Update

The independent importance axis is no longer the product-facing priority model for business mail triage. Dashboard Priority Map was removed, and the user-facing workflow should focus on urgent mail detection. Existing `importance` and `attention_quadrant` fields remain as compatibility data until the next cleanup pass removes or migrates DB/API/fixture/evaluation dependencies.

## Current Flow

```text
Email + Attachments
→ FactExtractionAgent
→ MailFacts.urgency_signals / MailFacts.importance_signals
→ DecisionAgent
→ MailUrgency / MailImportance
→ attention_quadrant_for()
→ PostgresDecisionResultRepository
→ PostgresMailboxService / DemoMailService
→ Inbox / Dashboard
```

`attention_quadrant` is deterministic application state. The LLM output field is overwritten in `DecisionAgent.decide()`, recomputed before persistence, and recomputed again in PostgreSQL UI payloads when the stored classification payload lacks a valid quadrant.

## Stabilization Findings

- `urgency_signals` should represent explicit time pressure, imminent deadlines, or a current operational interruption. A bare urgency word is not enough.
- `importance_signals` should represent business, monetary, contractual, safety, project, or operational impact. A claim type or important customer phrase alone is not enough.
- Fallback paths must not convert broad keywords such as `긴급`, `claim`, or historical `장애` into final high judgments without grounded axis-specific signals.
- Reason strings should preserve compact source phrases so a high decision can be traced back to the current email or extracted facts.
- Current-message extraction should remain ahead of quoted history. Thread history can contain high-impact terms that do not describe the new request.
- Final high judgment guards must avoid broad token matches. For example, `by next week` is not the same as `by 14:00` or `due today`, and `계약서 사본 요청` is not the same as `계약 위반` or `penalty`.
- LLM-extracted signals are treated as candidates, not final truth. `DecisionAgent` rechecks high urgency and high importance against axis-specific support patterns before calculating `attention_quadrant`.

## Priority Field Audit

`priority` has two unrelated meanings in the repository:

- Mail row UI compatibility: `DemoMailService` and `PostgresMailboxService` still emit row-level `priority` as the same value as `attention_quadrant`. This is category A, still needed for existing templates/tests that expect the row key.
- Routing capability priority: seed data, PostgreSQL schema, demo seed service, and routing capability tables use integer `priority` to rank assignee capabilities. This is category A and must not be removed as mail attention legacy.
- Older fixture labels that contain `priority: high|normal` are category B legacy. They are retained only as demo compatibility inputs and should be replaced by `urgency`, `importance`, and `attention_quadrant` when fixtures are next revised.

No `priority` use was removed in this pass because the name is still part of UI row compatibility and routing capability contracts. It must not be used as a proxy for urgency.

## Legacy `decision-agent:v2` Results

Existing `email_analysis_results` created by `decision-agent:v2` do not contain independent `urgency`, `importance`, or `attention_quadrant`.

Current PostgreSQL UI behavior is conservative: missing or invalid axis values become `normal`, and `attention_quadrant` is recalculated from those defaults. This avoids false high emphasis, but it can make unassessed legacy results look like genuinely normal messages.

Recommended operating policy:

- Do not add a schema migration only for this.
- Keep legacy rows conservative in the UI until reanalysis is available.
- Re-run `decision-agent:v3` for operating mail where attention labels matter before treating `normal` as a verified judgment.
- Add an explicit `unknown` or `unassessed` display state later only if legacy v2 rows remain operationally visible after reanalysis planning.

## Evaluation

`data/evaluation/attention_quadrant_cases.fixture.json` contains a minimal hand-written synthetic dataset for four quadrants and key boundary cases. Existing evaluation metrics now report:

- `urgency_accuracy`
- `importance_accuracy`
- `attention_quadrant_accuracy`

These metrics are populated when ground truth rows include `expected_urgency`, `expected_importance`, and `expected_attention_quadrant`.

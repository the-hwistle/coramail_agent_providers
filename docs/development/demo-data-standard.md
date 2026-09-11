# Demo Data Standard

## Purpose

Demo data must let the team demonstrate the product flow without confusing demo fixtures with production mailbox data.

The standard source for local demo emails is a fixture file under `data/demo/`. A later seed script can load that fixture into PostgreSQL and then create Qdrant points from the stored PostgreSQL records.

## Storage Layers

Use three distinct layers.

| Layer | Location | Role |
|---|---|---|
| Raw demo fixture | `data/demo/*.fixture.json` | Human-readable canonical source for demo email metadata, body text, recipients, attachment metadata, and expected labels. |
| Development organization seed | `data/demo/mail_decision_foundation.seed.json` | Synthetic fake assignees, capabilities, routing policy defaults, and routing rules for local Mail Decision routing tests. |
| Attachment files | `data/demo/attachments/` | Original demo files referenced by relative path from the fixture. |
| Runtime stores | PostgreSQL, Qdrant, local object/file storage | Generated state used by the running application. Runtime stores must be rebuildable from fixtures and attachments. |

Do not treat PostgreSQL rows or Qdrant points as the canonical source for demo data. They are seed outputs.

## Fixture Shape

Each fixture should contain:

- `fixture_version`
- `source`
- `id_policy`
- `email_account`
- `messages`
- optional `unmapped_attachments`

Each message should contain fields that map cleanly to the PostgreSQL schema:

- `email_messages`: `id`, `provider_message_id`, `provider_thread_id`, `rfc_message_id`, `sender_name`, `sender_address`, `subject`, `subject_normalized`, `body_text`, `snippet`, `sent_at`, `received_at`, `has_attachment`, `attachment_count`, `processing_status`
- `email_recipients`: nested `recipients`
- `email_attachments`: nested `attachments`
- demo evaluation hints: `expected_demo_labels`

`expected_demo_labels` are not raw email fields. They are expected outputs for demos and tests, and should later seed category assignments or evaluation datasets only when the seed script explicitly chooses to do so.

## ID Rules

- Use stable fixture IDs so local seeds are repeatable.
- UUIDv5 is recommended for demo fixtures.
- Production ingestion should not reuse the fixture namespace or fixture ID policy.
- Provider IDs in demo data should be deterministic strings such as `demo-received-quotation-001`.

## Attachment Rules

- Store files under `data/demo/attachments/`.
- Reference attachments by relative `storage_uri`.
- Include `filename`, `content_type`, `file_group`, `file_size`, `checksum_sha256`, `is_inline`, and `processing_status`.
- Record the basis for attachment-to-email mapping when it is inferred rather than supplied by a real email export.
- Keep unmatched files in `unmapped_attachments` until an email body or source mapping is available.

## AI Result Rules

- Do not store AI summaries, classifications, routing decisions, or extraction results inside the raw source fields.
- Store expected labels separately from model outputs.
- When AI analysis is implemented, persist generated results in `email_analysis_results` and `attachment_analysis_results`.
- Keep prompt version, model name, status, errors, and current-result flags with AI outputs.

## Security Rules

- Demo data must document source, generation method, masking policy, and known gaps.
- Do not commit secrets, credentials, raw private mailbox exports, local databases, Qdrant runtime files, or caches.
- Remove OS metadata sidecar files such as `Zone.Identifier` before committing demo data.
- Do not keep demo emails, attachments, filenames, company names, person names, vessel names, project names, business references, domains, message templates, item specifications, delivery dates, or amounts derived from real customer-provided email data.

## Synthetic Evaluation Organization

- Source: `app/evaluation/synthetic_dataset.py` with the fixed generator seed recorded in dataset metadata.
- Purpose: exercise Mail Decision fact extraction, classification, retrieval, candidate scoring, automatic assignment, and evaluation without using a real organization directory.
- Generation: eight UUIDv5 assignees own deterministic synthetic customers. Their customer, product, business-type, and project capabilities are derived from the synthetic emails assigned to that owner.
- Expected labels: each ground-truth row stores the expected business type and expected assignee separately from model outputs.
- Masking policy: all names are explicitly synthetic, all assignee addresses use the reserved `@coramail.invalid` domain, and no real mailbox export or customer identifier is used.
- Runtime isolation: synthetic users are eligible only when the email account provider is `synthetic`; Gmail and other operating providers exclude them.
- Seed replacement: the current synthetic dataset replaces capability rows for its users and marks older synthetic users inactive instead of deleting historical references.
- Known gap: passing synthetic routing results demonstrate deterministic pipeline behavior only. They do not measure real organization ambiguity, workload, leave schedules, or operating Gmail accuracy.

## Development Routing Organization

- Source: `data/demo/mail_decision_foundation.seed.json`.
- Purpose: provide local fake active users, assignee capabilities, and category routing rules so Mail Decision routing can be exercised before real organization data is approved.
- Masking policy: all people and relationships are synthetic. Emails use the reserved `@example.invalid` domain. User metadata includes realistic synthetic departments and positions for Settings and routing UI tests, while still marking the rows as `synthetic` with `seed_source = mail_decision_foundation.seed.json`.
- Runtime behavior: these rows are loaded by the normal demo PostgreSQL seed path and appear automatically in the Settings 담당자 관리 and 담당자 우선순위 배정 views.
- Work-status behavior: the demo seed also generates `work_items` with a fixed synthetic mix of assigned, in-progress, responded, completed, and a small overdue subset. This keeps assignee Dashboard views visually balanced for demos and must not be treated as workload or SLA performance evidence.
- General-category coverage: the development organization must include at least one assignee with `invoice`, `payment_inquiry`, or `spam` business-type capability so Settings and routing tests can exercise 기타 assignment.
- Isolation from evaluation: unlike `@coramail.invalid` synthetic evaluation users, these fake development assignees are treated as local operating assignees so Gmail-mode routing candidates can be tested. They must be replaced before production use.

## Current Demo Fixture

The current `data/demo/` fixture set intentionally keeps only synthetic external-demo data:

| Fixture | Included messages | Attachment |
|---|---|---|
| `received_quotations.fixture.json` | Four synthetic received quotation emails, `demo-received-quotation-004` through `demo-received-quotation-007` | Four quotation attachment rows using the representative `Quotation_QT-2026-0812-03.pdf` demo asset |
| `purchase_followups.fixture.json` | None; placeholder only | None |
| `specification_checks.fixture.json` | None; placeholder only | None |

This fixture covers only received quotation scenarios. Additional non-quotation scenarios must be generated from scratch as synthetic data before they are added.

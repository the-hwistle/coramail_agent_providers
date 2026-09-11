# Gmail Integration

This directory is the isolated landing zone for Gmail sync code ported from `coramail_ai`.

## Current Status

- Runtime UI can switch between fixture demo mode and Gmail mode with the `coramail_display_mode` cookie.
- Demo mode reads `data/demo/*.fixture.json` through `DemoMailRepository`.
- Gmail mode uses this package through `GmailMailboxService` and persists fetched mail into the canonical PostgreSQL mailbox tables.
- Gmail attachment bytes are downloaded into ignored local runtime storage under `data/runtime/gmail_attachments/`.
- UI routes normally use the persisted `email_messages.id` UUID; when a read-only Gmail fallback still carries a provider message ID,
  the Mail Decision API resolves it to the persisted UUID before loading the run context. Gmail message and attachment IDs remain provider identifiers only.
- Gmail OAuth can be configured from Settings; local runtime credentials are stored under `data/runtime/`.
- PostgreSQL is required for Gmail analysis, summary, attachment reanalysis, and Mail Decision execution. If it is unavailable, Gmail fetch remains a read-only in-memory fallback.
- The standalone `app.runtime:app` entrypoint loads the same project `.env` file as the UI server before initializing its repositories. If no environment file is used, start both processes with the same `CORAMAIL_DATABASE_URL`.
- In the bundled UI server, the Mail Decision API is mounted in the same process; leave `CORAMAIL_MAIL_DECISION_RUNTIME_URL` unset unless a separately managed Runtime is intentionally running.

## Porting Boundary

Use this package for:

- Gmail OAuth credential loading and refresh.
- Gmail message listing and MIME parsing.
- Attachment download into an application-controlled file store.
- Mapping Gmail message data into repository DTOs.

Do not put these responsibilities here:

- UI rendering.
- Demo fixture loading.
- Qdrant indexing.
- LLM classification or summary generation.
- Direct writes to a schema copied from `coramail_ai`.

## Source Reference

The first implementation should reference:

- `/home/ysh/workspace/coramail_ai/pipeline/gmail_postgres_fetcher.py`
- `/home/ysh/workspace/coramail_ai/pipeline/attachment_utils.py`

The old `coramail_ai` fetcher writes to a different normalized schema. This integration writes to CoRA Mail Agent's documented tables:

- `email_accounts`
- `email_messages`
- `email_recipients`
- `email_attachments`
- `processing_jobs`

## Runtime Analysis Flow

- New or content-changed Gmail messages receive persisted classification and executive-summary jobs.
- The current job worker executes those actions synchronously after sync so the Gmail inbox does not remain entirely unclassified.
- Attachment reanalysis uses the downloaded original file.
- Mail Decision receives the canonical PostgreSQL email UUID and can load the same body and attachments.
- The classification/summary worker is still `coramail-rule-v1`; it proves the operating path but is not an operating AI quality claim.

# Demo UI Porting Plan

## Purpose

This document records how the demo UI is ported from `coramail_ai` into `coramail_agent`.

The goal is to reuse the proven inbox interaction pattern while keeping `coramail_agent` aligned with its document-first architecture and fixture-based demo data.

## Decision

Do not copy `coramail_ai` as a whole application.

Copy `coramail_ai`'s Jinja templates and their matching stylesheet as-is, then create a compatibility layer in `coramail_agent`'s FastAPI server so the original UI can run against fixture-backed demo data.

## Imported Conceptual Scope

| Source concept from `coramail_ai` | Porting decision |
|---|---|
| FastAPI + Jinja2 + HTMX UI | Use directly as the UI architecture. |
| `templates/` | Copy as-is from `coramail_ai/templates`. |
| `static/app.css` | Copy as-is from `coramail_ai/static/app.css`. |
| Shell/sidebar/topbar layout | Keep original template structure. |
| Dashboard/Search/Settings/Inbox views | Keep original templates and provide fixture-backed or no-op server contexts. |
| Attachment view/download route | Recreate with fixture attachment paths. |
| Gmail sync | Keep isolated under `app/integrations/gmail/`; connect the UI through a temporary in-memory `GmailMailboxService` until PostgreSQL storage is implemented. |

## Excluded From Initial Runtime

- PostgreSQL writes.
- Qdrant indexing or search.
- LLM classification and summary regeneration.
- Celery workers.
- Login/session authentication.
- Gmail delete, send, or manual forwarding actions.
- Real Dashboard/Search/Settings persistence.

## Correction

The first UI slice was too heavily simplified and looked closer to a new static mockup than the `coramail_ai/templates` UI.
The corrected slice keeps the original Jinja template class structure and only removes actions that do not exist in the fixture demo runtime.

The later correction copies the `templates/` directory and `static/app.css` byte-for-byte from `coramail_ai`. Runtime gaps are handled in `app/server.py` through fixture-backed contexts and no-op endpoints instead of editing the UI templates.

## Current Runtime Flow

```text
CORAMAIL_DEMO_MODE=true
        |
        v
data/demo/*.fixture.json
        |
        v
DemoMailRepository
        |
        v
DemoMailService
        |
        v
FastAPI + Jinja2 + HTMX inbox UI
```

Gmail mode now uses the same UI with a cookie-selected service adapter:

```text
coramail_display_mode=gmail
        |
        v
Gmail API INBOX list/get
        |
        v
GmailMailboxService in-memory cache
        |
        v
FastAPI + Jinja2 + HTMX inbox UI
```

The temporary Gmail path requires Google API dependencies and a non-interactive token from `GOOGLE_TOKEN_JSON` or `CORAMAIL_GMAIL_TOKEN_PATH`. It does not write PostgreSQL rows, download attachment bodies, run LLM classification, or persist sync cursors yet.

## Restore Strategy

This port is intentionally one feature slice. If the result is rejected, revert the commit that introduced:

- `pyproject.toml`
- `app/server.py`
- `app/repositories/demo_mail_repository.py`
- `app/services/demo_mail_service.py`
- `app/schemas/demo_mail.py`
- `app/templates/`
- `app/static/`
- `app/integrations/gmail/`

Use `git revert <commit>` so the project history remains intact.

## Next Integration Step

After the fixture UI is accepted, implement a PostgreSQL seed/import path.

The first seed slice now converts fixture files into deterministic PostgreSQL-shaped rows without requiring a live PostgreSQL connection:

```bash
uv run python -m app.tools.export_demo_seed --check
```

Current verified row counts:

| Table target | Rows |
|---|---:|
| `email_accounts` | 1 |
| `email_messages` | 9 |
| `email_recipients` | 14 |
| `email_attachments` | 6 |
| `processing_jobs` | 9 |

The exporter can also write the generated bundle as JSON for inspection:

```bash
uv run python -m app.tools.export_demo_seed --pretty --output data/runtime/demo_postgres_seed.json
```

The JSON file under `data/runtime/` is local generated runtime data and must not be committed.

The bundle can be validated without a database write:

```bash
uv run python -m app.tools.load_demo_seed_postgres --dry-run
```

The initial PostgreSQL schema can also be validated without a database write:

```bash
uv run python -m app.tools.apply_postgres_schema --dry-run
```

When the PostgreSQL schema already exists and `psycopg` is installed in the runtime environment, the same bundle can be loaded in one transaction:

```bash
CORAMAIL_DATABASE_URL=postgresql://user:password@host:5432/coramail \
  uv run python -m app.tools.apply_postgres_schema

CORAMAIL_DATABASE_URL=postgresql://user:password@host:5432/coramail \
  uv run python -m app.tools.load_demo_seed_postgres
```

The next database-backed implementation should insert the same bundle into PostgreSQL in this order:

```text
data/demo/*.fixture.json
        |
        v
DemoSeedService seed bundle
        |
        v
email_accounts, email_messages, email_recipients, email_attachments
        |
        v
PostgreSQL-backed repository
```

The UI should keep using the service interface so the repository can switch from fixture files to PostgreSQL later.

# Demo Data

This directory stores demo fixtures used for local development and product demos.

## Files

| Path | Purpose |
|---|---|
| `purchase_followups.fixture.json` | Empty synthetic fixture reserved for future purchase order delivery follow-up emails. |
| `received_quotations.fixture.json` | Canonical demo email fixture for received quotation emails. |
| `specification_checks.fixture.json` | Empty synthetic fixture reserved for future technical specification check and recheck emails. |
| `mail_list_samples.fixture.json` | Synthetic list-display emails for Dashboard and Inbox demo rows. |
| `mail_decision_foundation.seed.json` | Synthetic development organization seed for fake assignees, capabilities, routing policy defaults, and routing rules. |
| `attachments/` | Synthetic demo attachment files referenced by the fixture. |

## Rules

- Keep demo data separate from real operating data.
- Store original email fields and attachment metadata in fixture files.
- Do not store AI-generated summaries or classifications in the original email fixture.
- Store expected demo labels separately from raw source fields so model outputs can be compared without overwriting the source.
- Keep fake organization seed data clearly marked as synthetic development data. It may be loaded into PostgreSQL for local routing tests, but it is not real customer organization data.
- Use stable IDs in fixtures so database seeds, tests, and Qdrant payloads can reference the same records repeatedly.
- Keep attachment files in `data/demo/attachments/` and reference them with relative paths.
- Do not commit credentials, tokens, raw private mailboxes, local databases, Qdrant runtime files, or cache files.
- Do not keep demo emails, attachments, filenames, company names, person names, vessel names, project names, business references, domains, message templates, item specifications, delivery dates, or amounts derived from real customer-provided email data.

## Current Scope

The current fixtures contain:

- 1,213 synthetic demo emails sent to `demo-sales@dawonict.co.kr`: four detail-ready received quotation rows, eleven curated list-display rows, and deterministic bulk volume rows for Dashboard scale screenshots.
- Dashboard scale rows plus curated fixture rows use a non-monotonic 7-day inflow pattern: 168, 142, 196, 151, 184, 207, and 165 messages from 2026-08-06 through 2026-08-12.
- The synthetic category mix keeps order and inquiry around 60% of all demo messages.
- Four synthetic quotation attachment rows. Newer received quotation rows reuse the representative synthetic PDF asset, `Quotation_QT-2026-0812-03.pdf`, while keeping distinct fixture filenames and expected quote fields.
- Empty placeholder fixtures for purchase follow-up and specification check scenarios.
- Eight fake development assignees with realistic synthetic departments, positions, customer/product/business type/fallback capabilities, and seven category routing rules, including a general-category assignee.

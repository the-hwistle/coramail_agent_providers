# Deployment Readiness Runbook

## Current Readiness

CoRA Mail Agent is not ready for direct production deployment as of this repository state. The application has real FastAPI, PostgreSQL, Qdrant, Gmail, local LLM, Mail Decision, work tracking, and UI paths, but the provided Compose stack is still a development stack and the product documents explicitly require further operating-data validation before production claims.

The highest priority is to stop local/demo defaults from being deployable by accident. Run the automated gate before any deployment candidate is promoted:

```bash
uv run python -m app.tools.check_deployment_readiness --env-file config/production.env --warnings-as-errors
```

## Environment Separation

Development and production use separate Compose projects, environment files, scripts, and Docker volumes.

| Area | Development | Production |
|---|---|---|
| Compose file | `docker-compose.yml` | `docker-compose.prod.yml` |
| Project name | `coramail-agent-dev` | `coramail-agent-prod` |
| Environment file | `.env` copied from `.env.example` | `config/production.env` copied from `config/production.env.example` |
| Scripts | `scripts/dev_*` | `scripts/prod_*` |
| Source mounting | bind-mounted `.:/app` | no source bind mount; run a tested image |
| Startup behavior | bootstrap schema and optional demo seed | app starts only after explicit migration |
| Volumes | `coramail_*` development volumes | `coramail_prod_*` production volumes |

Production startup flow:

```bash
cp config/production.env.example config/production.env
CORAMAIL_WEB_IMAGE=registry.example.com/coramail-agent:2026-09-03 scripts/prod_build.sh
scripts/prod_check.sh
scripts/prod_migrate.sh
scripts/prod_up.sh
```

Use `CORAMAIL_PROD_ENV_FILE=/path/to/production.env` when the deployment host stores the production env file outside the repository checkout.

Before a production migration or version rollout, capture a backup from the running production Compose project:

```bash
scripts/prod_backup.sh
```

The backup script runs the same readiness gate, writes a PostgreSQL custom-format `pg_dump`, creates and downloads a Qdrant collection snapshot, and stores a small manifest under `CORAMAIL_PROD_BACKUP_DIR` (default `backups/production`). This directory is ignored by Git and must be copied to the customer-approved backup location after creation. If Qdrant is protected with an API key, set `CORAMAIL_QDRANT_API_KEY` in the production environment file.

## Priority Order

1. Production configuration gate

   - `CORAMAIL_DEMO_MODE=false`
   - `CORAMAIL_LOCAL_DEV_DEFAULTS=false`
   - `CORAMAIL_DEV_SEED_DEMO=false`
   - `CORAMAIL_AUTH_ENABLED=true`
   - `CORAMAIL_AUTH_COOKIE_SECURE=true`
   - non-default `CORAMAIL_AUTH_USERNAME`, `CORAMAIL_AUTH_PASSWORD`, `CORAMAIL_AUTH_SECRET`, and `CORAMAIL_POSTGRES_PASSWORD`
   - explicit PostgreSQL, Qdrant, and LLM endpoints
   - no placeholder Gmail OAuth material
   - no unreviewed external LLM provider for on-premises operation

2. Deployment topology

   Use a production Compose, Kubernetes, or customer-managed service definition separate from `docker-compose.yml`. It must remove bind mounts, development bootstrap side effects, demo seed loading, broad host port exposure, and `:latest` image drift.

3. Secret and credential storage

   Move Gmail OAuth client credentials, refresh tokens, database credentials, and auth secrets into a customer-approved secrets store. Local `.env` and runtime token files are not an operating credential store.

4. Database migration and backup

   Replace startup-time development bootstrapping with an explicit migration runbook, least-privilege database roles, backup/restore checks, and rollback criteria. `scripts/prod_migrate.sh` applies PostgreSQL schema and ensures the configured Qdrant collection exists; it does not load demo seed data. `scripts/prod_backup.sh` captures PostgreSQL and Qdrant state before migrations or rollout changes.

5. Runtime SLO validation

   Measure real shared-mail throughput, LLM/Vision/embedding latency, failure rate, retry behavior, GPU memory, and queue backlog. The current local health endpoint proves dependencies are reachable, not that production load is acceptable.

6. Routing quality validation

   Collect real operating mail samples and user-confirmed assignments. Promotion criteria should include auto-assignment precision, Top-1/Top-3 assignment quality, review rate, unsupported attachment handling, and correction-driven regression cases.

7. Security hardening

   Review API authentication coverage, CSRF protection for mutating UI actions, role/organization authorization, audit log completeness, TLS termination, network policy, and log/trace masking for private mail content.

## Minimum Promotion Checks

```bash
uv sync --frozen
uv run python -m compileall app tests
uv run ruff check .
uv run pytest -q
npm run test:e2e:ui-smoke
uv run python -m app.tools.check_deployment_readiness --env-file config/production.env --warnings-as-errors
```

If any check cannot run in the target environment, record the exact blocker and do not treat the deployment as production-ready.

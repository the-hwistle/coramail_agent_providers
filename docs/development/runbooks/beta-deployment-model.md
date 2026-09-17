# Beta Deployment Model

## Purpose

CoRA Mail beta deployments must separate three decisions that are easy to mix up:

1. who operates the service
2. where the LLM runs
3. which mail provider is connected

The deployment owner should choose these explicitly before creating or approving a beta environment.

## Deployment Modes

| Mode | `CORAMAIL_DEPLOYMENT_MODE` | Operator | Typical customer fit |
|---|---|---|---|
| Unified setup | `setup` | undecided | first-run beta image before operator choice is finalized |
| Cloud beta | `saas` | CoRA | customers who want a fast web trial and accept hosted processing |
| Private beta | `private` | customer or customer-approved operator | customers who require mail data and AI processing inside their network |
| Hybrid beta | `hybrid` | split | customers who want private app/data with managed LLM, or hosted app with customer-controlled LLM |

## LLM Runtime Modes

| Runtime | `CORAMAIL_LLM_RUNTIME` | Meaning |
|---|---|---|
| Setup | `setup` | first-run beta state; finalize before a real customer pilot |
| Local | `local` | LLM runs in the same customer-controlled environment as the app |
| Managed | `managed` | LLM endpoint is operated by CoRA or a customer-approved managed service |
| External | `external` | LLM uses an external API provider and requires explicit approval |

Rules enforced by the readiness gate:

- `CORAMAIL_DEPLOYMENT_MODE` must be `setup`, `saas`, `private`, or `hybrid`.
- `CORAMAIL_LLM_RUNTIME` must be `setup`, `local`, `managed`, or `external`.
- `private` deployment cannot use `external` LLM runtime.
- OpenAI/Gemini-style providers require `CORAMAIL_LLM_RUNTIME=external` and `CORAMAIL_EXTERNAL_LLM_APPROVED=true`.
- Public beta requires `CORAMAIL_BETA_PUBLIC=true`, an HTTPS `CORAMAIL_BETA_BASE_URL`, and a matching `CORAMAIL_BETA_HOST`.

## Mail Provider Setup

`CORAMAIL_MAIL_PROVIDER=setup` is valid for a unified beta image. After sign-in, the UI opens the mail account setup modal and the operator selects Gmail, Naver, or Hiworks. That selection is persisted to the active env file when the deployment host allows writes.

Fixed-provider deployments should set:

- `CORAMAIL_MAIL_PROVIDER=gmail`
- `CORAMAIL_MAIL_PROVIDER=naver`
- `CORAMAIL_MAIL_PROVIDER=hiworks`

For Naver or Hiworks, app-password account variables must be present before promotion.

## Recommended Beta Tracks

### Track A: Cloud Beta

Use this when the customer wants the fastest trial.

- `CORAMAIL_DEPLOYMENT_MODE=saas`
- `CORAMAIL_LLM_RUNTIME=managed`
- `CORAMAIL_MAIL_PROVIDER=setup`
- start from `config/production.saas.env.example`
- CoRA operates app, PostgreSQL, Qdrant, backups, and LLM endpoint.
- Customer signs off on mail data processing and user access scope.

### Track B: Private Beta

Use this when the customer prioritizes data residency.

- `CORAMAIL_DEPLOYMENT_MODE=private`
- `CORAMAIL_LLM_RUNTIME=local`
- `CORAMAIL_MAIL_PROVIDER=setup`
- start from `config/production.private.env.example`
- Customer or customer-approved infrastructure hosts app, PostgreSQL, Qdrant, and LLM.
- No external LLM API is allowed.

### Track C: Hybrid Beta

Use this when the customer wants a split responsibility model.

- `CORAMAIL_DEPLOYMENT_MODE=hybrid`
- `CORAMAIL_LLM_RUNTIME=managed`, `local`, or explicitly approved `external`
- `CORAMAIL_MAIL_PROVIDER=setup`
- start from `config/production.hybrid.env.example`
- Record the exact data boundary before enabling real mailbox sync.

## Promotion Checklist

Before any customer can use a beta environment:

1. Initialize the env file with `scripts/prod_init_env.sh saas`, `scripts/prod_init_env.sh private`, or `scripts/prod_init_env.sh hybrid`.
2. Complete `config/production.env` or the external production env file.
3. Set `CORAMAIL_PROD_ENV_FILE` when the env file is outside the repository checkout.
4. Run `scripts/prod_plan.sh` and review the redacted deployment plan.
5. Run `scripts/prod_preflight.sh`.
6. Build or pull a pinned `CORAMAIL_WEB_IMAGE`.
7. Run `scripts/prod_check.sh`.
8. Run `scripts/prod_migrate.sh`.
9. Run `scripts/prod_up.sh` for a private/internal endpoint, or `scripts/prod_public_up.sh` for a direct HTTPS beta URL.
10. Run `scripts/prod_smoke.sh`.
11. Run `scripts/prod_external_smoke.sh` against `CORAMAIL_BETA_BASE_URL`.
12. Give beta users the `CORAMAIL_BETA_BASE_URL` sign-in URL and the scoped beta account.
13. Sign in and finish the initial mail provider setup.
14. Run a bounded mailbox sync first.
15. Confirm rows persist in PostgreSQL and remain visible after restart.
16. Run `scripts/prod_backup.sh` after the first successful sync.
17. Record rollback instructions for the environment.

Migration and service start are intentionally separate: `scripts/prod_migrate.sh` changes PostgreSQL/Qdrant state, while `scripts/prod_up.sh` starts the internal web service and `scripts/prod_public_up.sh` starts the web service plus the HTTPS edge profile.

For real-service SaaS beta, set DNS for `CORAMAIL_BETA_HOST` to the deployment host before `scripts/prod_public_up.sh`, and open inbound 80/443 so Caddy can issue TLS certificates. Beta users receive only the `CORAMAIL_BETA_BASE_URL` sign-in URL and a scoped beta account.

from __future__ import annotations

import os
import subprocess
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]


def test_dev_scripts_are_shell_syntax_valid_and_executable():
    scripts = [
        PROJECT_DIR / "scripts" / "dev_env.sh",
        PROJECT_DIR / "scripts" / "dev_up.sh",
        PROJECT_DIR / "scripts" / "dev_app.sh",
        PROJECT_DIR / "scripts" / "dev_down.sh",
        PROJECT_DIR / "scripts" / "dev_reset.sh",
        PROJECT_DIR / "scripts" / "dev_pull_models.sh",
    ]

    for script in scripts:
        assert script.exists()
        assert os.access(script, os.X_OK)
        subprocess.run(["bash", "-n", str(script)], check=True)


def test_prod_scripts_are_shell_syntax_valid_and_executable():
    scripts = [
        PROJECT_DIR / "scripts" / "prod_build.sh",
        PROJECT_DIR / "scripts" / "prod_init_env.sh",
        PROJECT_DIR / "scripts" / "prod_plan.sh",
        PROJECT_DIR / "scripts" / "prod_preflight.sh",
        PROJECT_DIR / "scripts" / "prod_check.sh",
        PROJECT_DIR / "scripts" / "prod_migrate.sh",
        PROJECT_DIR / "scripts" / "prod_up.sh",
        PROJECT_DIR / "scripts" / "prod_public_up.sh",
        PROJECT_DIR / "scripts" / "prod_tunnel_up.sh",
        PROJECT_DIR / "scripts" / "prod_smoke.sh",
        PROJECT_DIR / "scripts" / "prod_external_smoke.sh",
        PROJECT_DIR / "scripts" / "prod_down.sh",
        PROJECT_DIR / "scripts" / "prod_backup.sh",
    ]

    for script in scripts:
        assert script.exists()
        assert os.access(script, os.X_OK)
        subprocess.run(["bash", "-n", str(script)], check=True)


def test_compose_runs_web_by_default_and_keeps_stateful_volumes():
    compose = (PROJECT_DIR / "docker-compose.yml").read_text(encoding="utf-8")

    assert "name: coramail-agent-providers-dev" in compose
    assert "web:" in compose
    assert "python -m app.tools.bootstrap_dev_environment" in compose
    assert "python -m uvicorn app.server:app" in compose
    assert "postgres:" in compose
    assert "qdrant:" in compose
    assert "bootstrap:" in compose
    assert "- tools" in compose
    assert "ollama:" in compose
    assert "${CORAMAIL_DEV_PORT:-8030}:${CORAMAIL_DEV_PORT:-8030}" in compose
    assert "${CORAMAIL_POSTGRES_PORT:-55452}:5432" in compose
    assert "${CORAMAIL_QDRANT_HTTP_PORT:-6653}:6333" in compose
    assert "${CORAMAIL_OLLAMA_PORT:-11456}:11434" in compose
    assert "coramail_postgres_data:" in compose
    assert "coramail_qdrant_data:" in compose
    assert "coramail_ollama_data:" in compose
    assert "coramail_uv_cache:" in compose


def test_production_compose_is_independent_from_development_stack():
    compose = (PROJECT_DIR / "docker-compose.prod.yml").read_text(encoding="utf-8")

    assert "name: coramail-agent-prod" in compose
    assert "name: coramail-agent-dev" not in compose
    assert "coramail_prod_postgres_data:" in compose
    assert "coramail_prod_qdrant_data:" in compose
    assert "coramail_prod_runtime:" in compose
    assert "coramail_postgres_data:" not in compose
    assert "coramail_qdrant_data:" not in compose
    assert ".:/app" not in compose
    assert "python -m app.tools.bootstrap_dev_environment" not in compose
    assert "CORAMAIL_DEV_SEED_DEMO: \"false\"" in compose
    assert "CORAMAIL_LOCAL_DEV_DEFAULTS: \"false\"" in compose
    assert "${CORAMAIL_WEB_IMAGE:?set CORAMAIL_WEB_IMAGE" in compose
    assert "CORAMAIL_DATABASE_URL: postgresql://${CORAMAIL_POSTGRES_USER" not in compose
    assert "--proxy-headers" in compose
    assert "host.docker.internal:host-gateway" in compose
    assert "edge:" in compose
    assert "- edge" in compose
    assert "tunnel:" in compose
    assert "- tunnel" in compose
    assert "cloudflare/cloudflared:2026.9.0" in compose
    assert "CORAMAIL_CLOUDFLARE_TUNNEL_TOKEN" in compose
    assert "caddy:2.8.4-alpine" in compose
    assert "./config/Caddyfile.production:/etc/caddy/Caddyfile:ro" in compose
    assert "coramail_prod_caddy_data:" in compose
    assert "coramail_prod_caddy_config:" in compose
    assert "profiles:" in compose
    assert "- tools" in compose
    assert "python -m app.tools.apply_postgres_schema" in compose
    assert "python -m app.tools.prepare_qdrant_collection" in compose


def test_env_example_documents_host_and_container_topology():
    env_example = (PROJECT_DIR / ".env.example").read_text(encoding="utf-8")

    assert "CORAMAIL_DATABASE_URL=postgresql://coramail:coramail@127.0.0.1:55452/coramail_providers" in env_example
    assert "CORAMAIL_QDRANT_URL=http://127.0.0.1:6653" in env_example
    assert "CORAMAIL_CONTAINER_LLM_BASE_URL=http://ollama:11434/v1" in env_example
    assert "CORAMAIL_OLLAMA_PORT=11456" in env_example
    assert "CORAMAIL_QDRANT_VECTOR_SIZE=768" in env_example
    assert "CORAMAIL_VISION_MODEL=qwen3-vl:2b" in env_example
    assert "CORAMAIL_DEMO_SOURCE=postgres" in env_example
    assert "CORAMAIL_DEV_SEED_DEMO=true" in env_example
    assert "CORAMAIL_MAIL_PROVIDER=gmail" in env_example
    assert "CORAMAIL_NAVER_APP_PASSWORD=" in env_example
    assert "CORAMAIL_HIWORKS_APP_PASSWORD=" in env_example


def test_production_env_example_documents_non_dev_defaults():
    env_example = (PROJECT_DIR / "config" / "production.env.example").read_text(encoding="utf-8")

    assert "CORAMAIL_DEMO_MODE=false" in env_example
    assert "CORAMAIL_LOCAL_DEV_DEFAULTS=false" in env_example
    assert "CORAMAIL_DEV_SEED_DEMO=false" in env_example
    assert "CORAMAIL_DEPLOYMENT_MODE=setup" in env_example
    assert "CORAMAIL_BETA_PUBLIC=false" in env_example
    assert "CORAMAIL_BETA_HOST=replace-with-beta-host.example.com" in env_example
    assert "CORAMAIL_CADDY_IMAGE=caddy:2.8.4-alpine" in env_example
    assert "CORAMAIL_EDGE_HTTPS_PORT=443" in env_example
    assert "CORAMAIL_CLOUDFLARED_IMAGE=cloudflare/cloudflared:2026.9.0" in env_example
    assert "CORAMAIL_CLOUDFLARE_TUNNEL_TOKEN=" in env_example
    assert "CORAMAIL_AUTH_COOKIE_SECURE=true" in env_example
    assert "CORAMAIL_MAIL_PROVIDER=setup" in env_example
    assert "CORAMAIL_LLM_RUNTIME=setup" in env_example
    assert "CORAMAIL_EXTERNAL_LLM_APPROVED=false" in env_example
    assert "CORAMAIL_WEB_IMAGE=registry.example.com/coramail-agent:2026-09-03" in env_example
    assert "CORAMAIL_BETA_BASE_URL=https://replace-with-beta-host.example.com" in env_example
    assert "CORAMAIL_PROD_BACKUP_DIR=backups/production" in env_example
    assert "CORAMAIL_DATABASE_URL=postgresql://coramail_app:replace-with-random-postgres-password@postgres:5432/coramail" in env_example
    assert "CORAMAIL_QDRANT_URL=http://qdrant:6333" in env_example
    assert "CORAMAIL_QDRANT_API_KEY=" in env_example
    assert "GOOGLE_CREDENTIALS_JSON=" in env_example
    assert "GOOGLE_TOKEN_JSON=" in env_example
    assert "GOOGLE_SEND_TOKEN_JSON=" in env_example
    assert "CORAMAIL_NAVER_MAIL_ADDRESS=" in env_example
    assert "CORAMAIL_NAVER_APP_PASSWORD=" in env_example
    assert "CORAMAIL_HIWORKS_MAIL_ADDRESS=" in env_example
    assert "CORAMAIL_HIWORKS_APP_PASSWORD=" in env_example


def test_beta_track_env_examples_document_mode_combinations():
    examples = {
        "production.saas.env.example": ("CORAMAIL_DEPLOYMENT_MODE=saas", "CORAMAIL_LLM_RUNTIME=managed"),
        "production.private.env.example": ("CORAMAIL_DEPLOYMENT_MODE=private", "CORAMAIL_LLM_RUNTIME=local"),
        "production.hybrid.env.example": ("CORAMAIL_DEPLOYMENT_MODE=hybrid", "CORAMAIL_LLM_RUNTIME=managed"),
    }

    for filename, expected_lines in examples.items():
        env_text = (PROJECT_DIR / "config" / filename).read_text(encoding="utf-8")
        assert "CORAMAIL_MAIL_PROVIDER=setup" in env_text
        assert "CORAMAIL_WEB_IMAGE=" in env_text
        assert "CORAMAIL_BETA_BASE_URL=https://" in env_text
        assert "CORAMAIL_BETA_HOST=" in env_text
        assert "CORAMAIL_CADDY_IMAGE=caddy:2.8.4-alpine" in env_text
        assert "CORAMAIL_LLM_BASE_URL=" in env_text
        for line in expected_lines:
            assert line in env_text


def test_production_secret_file_is_gitignored():
    gitignore = (PROJECT_DIR / ".gitignore").read_text(encoding="utf-8")
    dockerignore = (PROJECT_DIR / ".dockerignore").read_text(encoding="utf-8")

    assert "config/production.env" in gitignore
    assert "config/production.env" in dockerignore
    assert "backups/" in gitignore
    assert "backups/" in dockerignore


def test_production_build_script_tags_configured_image():
    script = (PROJECT_DIR / "scripts" / "prod_build.sh").read_text(encoding="utf-8")

    assert "CORAMAIL_WEB_IMAGE" in script
    assert "git rev-parse --short HEAD" in script
    assert 'docker build -t "$CORAMAIL_WEB_IMAGE" .' in script


def test_production_init_env_script_selects_beta_track_templates():
    script = (PROJECT_DIR / "scripts" / "prod_init_env.sh").read_text(encoding="utf-8")

    assert "production.saas.env.example" in script
    assert "production.private.env.example" in script
    assert "production.hybrid.env.example" in script
    assert "CORAMAIL_PROD_ENV_FILE" in script
    assert "CORAMAIL_PROD_INIT_FORCE" in script
    assert "install -m 600" in script


def test_production_scripts_use_tmp_uv_cache_for_readiness_checks():
    for name in (
        "prod_plan.sh",
        "prod_preflight.sh",
        "prod_check.sh",
        "prod_migrate.sh",
        "prod_up.sh",
        "prod_public_up.sh",
        "prod_tunnel_up.sh",
        "prod_smoke.sh",
        "prod_external_smoke.sh",
        "prod_backup.sh",
    ):
        script = (PROJECT_DIR / "scripts" / name).read_text(encoding="utf-8")

        assert 'UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"' in script


def test_production_plan_script_renders_redacted_summary():
    script = (PROJECT_DIR / "scripts" / "prod_plan.sh").read_text(encoding="utf-8")

    assert "app.tools.render_deployment_plan" in script
    assert "CORAMAIL_PROD_ENV_FILE" in script


def test_production_preflight_script_checks_host_and_compose():
    script = (PROJECT_DIR / "scripts" / "prod_preflight.sh").read_text(encoding="utf-8")

    assert "require_command uv" in script
    assert "require_command docker" in script
    assert "stat -c '%a'" in script
    assert "docker compose version" in script
    assert "docker compose --env-file" in script
    assert "production_preflight=ok" in script


def test_deployment_readiness_runbook_documents_json_output():
    runbook = (PROJECT_DIR / "docs" / "development" / "runbooks" / "deployment-readiness.md").read_text(
        encoding="utf-8"
    )

    assert "--format json" in runbook


def test_deployment_readiness_runbook_uses_provider_dev_project_name():
    runbook = (PROJECT_DIR / "docs" / "development" / "runbooks" / "deployment-readiness.md").read_text(
        encoding="utf-8"
    )

    assert "coramail-agent-providers-dev" in runbook
    assert "| Project name | `coramail-agent-dev`" not in runbook


def test_production_up_script_does_not_run_migrations():
    script = (PROJECT_DIR / "scripts" / "prod_up.sh").read_text(encoding="utf-8")

    assert "app.tools.check_deployment_readiness" in script
    assert "--exposure internal" in script
    assert "rm -sf edge tunnel" in script
    assert "up -d web" in script
    assert "--profile tools run --rm migrate" not in script


def test_production_public_up_script_starts_edge_profile():
    script = (PROJECT_DIR / "scripts" / "prod_public_up.sh").read_text(encoding="utf-8")

    assert "app.tools.check_deployment_readiness" in script
    assert "--exposure edge" in script
    assert "rm -sf tunnel" in script
    assert "--profile edge up -d web edge" in script
    assert "CORAMAIL_PROD_COMPOSE_ENV_FILE" in script


def test_production_tunnel_up_script_starts_cloudflare_tunnel_profile():
    script = (PROJECT_DIR / "scripts" / "prod_tunnel_up.sh").read_text(encoding="utf-8")

    assert "app.tools.check_deployment_readiness" in script
    assert "--exposure tunnel" in script
    assert "rm -sf edge" in script
    assert "--profile tunnel up -d web tunnel" in script
    assert "CORAMAIL_PROD_COMPOSE_ENV_FILE" in script


def test_production_down_script_includes_all_optional_profiles():
    script = (PROJECT_DIR / "scripts" / "prod_down.sh").read_text(encoding="utf-8")

    assert "--profile edge --profile tunnel --profile tools" in script
    assert "down --remove-orphans" in script


def test_production_caddyfile_proxies_beta_host_to_web():
    caddyfile = (PROJECT_DIR / "config" / "Caddyfile.production").read_text(encoding="utf-8")

    assert "{$CORAMAIL_BETA_HOST}" in caddyfile
    assert "reverse_proxy web:8000" in caddyfile
    assert "Strict-Transport-Security" in caddyfile


def test_production_smoke_script_checks_compose_and_health_endpoint():
    script = (PROJECT_DIR / "scripts" / "prod_smoke.sh").read_text(encoding="utf-8")

    assert "docker compose --env-file" in script
    assert "exec -T web python" in script
    assert "http://127.0.0.1:8000/api/health" in script
    assert "time.monotonic() + 60" in script
    assert "urllib.error.URLError" in script
    assert "production_smoke=ok" in script
    assert "CORAMAIL_PROD_SMOKE_ALLOW_DEGRADED" in script


def test_production_external_smoke_script_checks_customer_beta_url():
    script = (PROJECT_DIR / "scripts" / "prod_external_smoke.sh").read_text(encoding="utf-8")

    assert "app.tools.check_deployment_readiness" in script
    assert "CORAMAIL_BETA_BASE_URL" in script
    assert "api/health" in script
    assert "production_external_smoke=ok" in script


def test_production_backup_script_captures_postgres_and_qdrant_state():
    script = (PROJECT_DIR / "scripts" / "prod_backup.sh").read_text(encoding="utf-8")

    assert "pg_dump" in script
    assert "--format=custom" in script
    assert 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' in script
    assert "python -m app.tools.create_qdrant_snapshot" in script
    assert 'BACKUP_DIR_ABS="$BACKUP_DIR"' in script
    assert "manifest.txt" in script


def test_dockerfile_keeps_virtualenv_outside_bind_mount():
    dockerfile = (PROJECT_DIR / "Dockerfile").read_text(encoding="utf-8")

    assert "UV_PROJECT_ENVIRONMENT=/opt/coramail-venv" in dockerfile
    assert 'PATH="/opt/coramail-venv/bin:${PATH}"' in dockerfile
    assert "uv sync --frozen --no-dev" in dockerfile


def test_bootstrap_tool_ensures_default_qdrant_collection_and_seed():
    bootstrap = (PROJECT_DIR / "app" / "tools" / "bootstrap_dev_environment.py").read_text(encoding="utf-8")

    assert "_ensure_qdrant_collection" in bootstrap
    assert "CORAMAIL_QDRANT_CASE_COLLECTION" in bootstrap
    assert "CORAMAIL_QDRANT_VECTOR_SIZE" in bootstrap
    assert "Cosine" in bootstrap
    assert "PostgresSeedWriter" in bootstrap


def test_dev_reset_requires_explicit_confirmation():
    reset_script = (PROJECT_DIR / "scripts" / "dev_reset.sh").read_text(encoding="utf-8")

    assert "CORAMAIL_DEV_RESET_CONFIRM" in reset_script
    assert "delete-dev-volumes" in reset_script
    assert "docker compose down --volumes --remove-orphans" in reset_script


def test_dev_pull_models_uses_configured_ollama_models():
    pull_script = (PROJECT_DIR / "scripts" / "dev_pull_models.sh").read_text(encoding="utf-8")

    assert "CORAMAIL_TEXT_MODEL" in pull_script
    assert "CORAMAIL_VISION_MODEL" in pull_script
    assert "CORAMAIL_EMBEDDING_MODEL" in pull_script
    assert "docker compose exec ollama ollama pull" in pull_script


def test_development_vision_model_defaults_are_consistent():
    compose = (PROJECT_DIR / "docker-compose.yml").read_text(encoding="utf-8")
    dev_env = (PROJECT_DIR / "scripts" / "dev_env.sh").read_text(encoding="utf-8")
    app_config = (PROJECT_DIR / "app" / "config.py").read_text(encoding="utf-8")
    llm_gateway = (PROJECT_DIR / "app" / "llm" / "gateway.py").read_text(encoding="utf-8")

    for source in (compose, dev_env, app_config, llm_gateway):
        assert "qwen3-vl:2b" in source
        assert "qwen2.5vl:7b" not in source

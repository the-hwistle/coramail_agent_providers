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
        PROJECT_DIR / "scripts" / "prod_check.sh",
        PROJECT_DIR / "scripts" / "prod_migrate.sh",
        PROJECT_DIR / "scripts" / "prod_up.sh",
        PROJECT_DIR / "scripts" / "prod_down.sh",
        PROJECT_DIR / "scripts" / "prod_backup.sh",
    ]

    for script in scripts:
        assert script.exists()
        assert os.access(script, os.X_OK)
        subprocess.run(["bash", "-n", str(script)], check=True)


def test_compose_runs_web_by_default_and_keeps_stateful_volumes():
    compose = (PROJECT_DIR / "docker-compose.yml").read_text(encoding="utf-8")

    assert "name: coramail-agent-dev" in compose
    assert "web:" in compose
    assert "python -m app.tools.bootstrap_dev_environment" in compose
    assert "python -m uvicorn app.server:app" in compose
    assert "postgres:" in compose
    assert "qdrant:" in compose
    assert "bootstrap:" in compose
    assert "- tools" in compose
    assert "ollama:" in compose
    assert "${CORAMAIL_OLLAMA_PORT:-11435}:11434" in compose
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
    assert "profiles:" in compose
    assert "- tools" in compose
    assert "python -m app.tools.apply_postgres_schema" in compose
    assert "python -m app.tools.prepare_qdrant_collection" in compose


def test_env_example_documents_host_and_container_topology():
    env_example = (PROJECT_DIR / ".env.example").read_text(encoding="utf-8")

    assert "CORAMAIL_DATABASE_URL=postgresql://coramail:coramail@127.0.0.1:5432/coramail" in env_example
    assert "CORAMAIL_QDRANT_URL=http://127.0.0.1:6333" in env_example
    assert "CORAMAIL_CONTAINER_LLM_BASE_URL=http://ollama:11434/v1" in env_example
    assert "CORAMAIL_OLLAMA_PORT=11435" in env_example
    assert "CORAMAIL_QDRANT_VECTOR_SIZE=768" in env_example
    assert "CORAMAIL_DEMO_SOURCE=postgres" in env_example
    assert "CORAMAIL_DEV_SEED_DEMO=true" in env_example


def test_production_env_example_documents_non_dev_defaults():
    env_example = (PROJECT_DIR / "config" / "production.env.example").read_text(encoding="utf-8")

    assert "CORAMAIL_DEMO_MODE=false" in env_example
    assert "CORAMAIL_LOCAL_DEV_DEFAULTS=false" in env_example
    assert "CORAMAIL_DEV_SEED_DEMO=false" in env_example
    assert "CORAMAIL_AUTH_COOKIE_SECURE=true" in env_example
    assert "CORAMAIL_WEB_IMAGE=registry.example.com/coramail-agent:2026-09-03" in env_example
    assert "CORAMAIL_PROD_BACKUP_DIR=backups/production" in env_example
    assert "CORAMAIL_DATABASE_URL=postgresql://coramail_app:replace-with-random-postgres-password@postgres:5432/coramail" in env_example
    assert "CORAMAIL_QDRANT_URL=http://qdrant:6333" in env_example
    assert "CORAMAIL_QDRANT_API_KEY=" in env_example
    assert "GOOGLE_CREDENTIALS_JSON=" in env_example
    assert "GOOGLE_TOKEN_JSON=" in env_example
    assert "GOOGLE_SEND_TOKEN_JSON=" in env_example


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


def test_production_scripts_use_tmp_uv_cache_for_readiness_checks():
    for name in ("prod_check.sh", "prod_migrate.sh", "prod_up.sh", "prod_backup.sh"):
        script = (PROJECT_DIR / "scripts" / name).read_text(encoding="utf-8")

        assert 'UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"' in script


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

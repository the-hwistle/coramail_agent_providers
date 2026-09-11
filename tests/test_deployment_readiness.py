from pathlib import Path

from app.tools.check_deployment_readiness import Severity, _read_env_file, deployment_readiness_issues


def test_deployment_readiness_rejects_local_defaults() -> None:
    issues = deployment_readiness_issues(
        {
            "CORAMAIL_DEMO_MODE": "true",
            "CORAMAIL_LOCAL_DEV_DEFAULTS": "true",
            "CORAMAIL_DEV_SEED_DEMO": "true",
            "CORAMAIL_AUTH_ENABLED": "true",
            "CORAMAIL_AUTH_COOKIE_SECURE": "false",
            "CORAMAIL_AUTH_USERNAME": "admin",
            "CORAMAIL_AUTH_PASSWORD": "coramail",
            "CORAMAIL_AUTH_SECRET": "replace-with-random-secret",
            "CORAMAIL_POSTGRES_PASSWORD": "coramail",
            "CORAMAIL_DATABASE_URL": "",
            "CORAMAIL_QDRANT_URL": "",
            "CORAMAIL_LLM_BASE_URL": "",
            "CORAMAIL_WEB_IMAGE": "",
            "CORAMAIL_LLM_PROVIDER": "gemini",
            "GOOGLE_CREDENTIALS_JSON": '{"client_id":"your-client-id"}',
        }
    )

    codes = {issue.code for issue in issues if issue.severity is Severity.ERROR}
    assert {
        "demo-mode",
        "local-dev-defaults",
        "demo-seed",
        "insecure-cookie",
        "default-auth-username",
        "default-auth-password",
        "weak-auth-secret",
        "default-postgres-password",
        "database-url",
        "qdrant-url",
        "llm-url",
        "web-image",
        "external-llm-provider",
        "placeholder-google_credentials_json",
    } <= codes


def test_deployment_readiness_rejects_production_template_placeholders() -> None:
    issues = deployment_readiness_issues(
        {
            "CORAMAIL_DEMO_MODE": "false",
            "CORAMAIL_LOCAL_DEV_DEFAULTS": "false",
            "CORAMAIL_DEV_SEED_DEMO": "false",
            "CORAMAIL_AUTH_ENABLED": "true",
            "CORAMAIL_AUTH_COOKIE_SECURE": "true",
            "CORAMAIL_AUTH_USERNAME": "replace-with-admin-login",
            "CORAMAIL_AUTH_PASSWORD": "replace-with-random-password",
            "CORAMAIL_AUTH_SECRET": "replace-with-at-least-32-random-characters",
            "CORAMAIL_POSTGRES_PASSWORD": "replace-with-random-postgres-password",
            "CORAMAIL_DATABASE_URL": "postgresql://coramail:secret@postgres.internal:5432/coramail",
            "CORAMAIL_QDRANT_URL": "http://qdrant.internal:6333",
            "CORAMAIL_LLM_BASE_URL": "http://vllm.internal:8000/v1",
            "CORAMAIL_WEB_IMAGE": "registry.example.com/coramail-agent:2026-09-03",
            "CORAMAIL_TEXT_MODEL": "replace-with-tested-text-model",
            "CORAMAIL_CHAT_TEXT_MODEL": "replace-with-tested-chat-model",
            "CORAMAIL_VISION_MODEL": "replace-with-tested-vision-model",
            "CORAMAIL_EMBEDDING_MODEL": "replace-with-tested-embedding-model",
            "CORAMAIL_LLM_PROVIDER": "vllm",
        }
    )

    assert {
        "default-auth-username",
        "default-auth-password",
        "weak-auth-secret",
        "default-postgres-password",
        "placeholder-web-image",
        "placeholder-text-model",
        "placeholder-chat-text-model",
        "placeholder-vision-model",
        "placeholder-embedding-model",
    } <= {issue.code for issue in issues}


def test_deployment_readiness_accepts_hardened_on_prem_config() -> None:
    issues = deployment_readiness_issues(
        {
            "CORAMAIL_DEMO_MODE": "false",
            "CORAMAIL_LOCAL_DEV_DEFAULTS": "false",
            "CORAMAIL_DEV_SEED_DEMO": "false",
            "CORAMAIL_AUTH_ENABLED": "true",
            "CORAMAIL_AUTH_COOKIE_SECURE": "true",
            "CORAMAIL_AUTH_USERNAME": "ops-admin",
            "CORAMAIL_AUTH_PASSWORD": "long-random-password-value",
            "CORAMAIL_AUTH_SECRET": "a" * 64,
            "CORAMAIL_POSTGRES_PASSWORD": "long-random-db-password",
            "CORAMAIL_DATABASE_URL": "postgresql://coramail:secret@postgres.internal:5432/coramail",
            "CORAMAIL_QDRANT_URL": "http://qdrant.internal:6333",
            "CORAMAIL_LLM_BASE_URL": "http://vllm.internal:8000/v1",
            "CORAMAIL_WEB_IMAGE": "registry.internal/coramail-agent:2026-09-03",
            "CORAMAIL_TEXT_MODEL": "qwen2.5-7b-awq",
            "CORAMAIL_CHAT_TEXT_MODEL": "qwen2.5-7b-awq",
            "CORAMAIL_VISION_MODEL": "qwen3-vl-2b",
            "CORAMAIL_EMBEDDING_MODEL": "bge-m3",
            "CORAMAIL_LLM_PROVIDER": "vllm",
        }
    )

    assert [issue for issue in issues if issue.severity is Severity.ERROR] == []


def test_deployment_readiness_warns_on_latest_images() -> None:
    issues = deployment_readiness_issues(
        {
            "CORAMAIL_DEMO_MODE": "false",
            "CORAMAIL_LOCAL_DEV_DEFAULTS": "false",
            "CORAMAIL_DEV_SEED_DEMO": "false",
            "CORAMAIL_AUTH_ENABLED": "true",
            "CORAMAIL_AUTH_COOKIE_SECURE": "true",
            "CORAMAIL_AUTH_USERNAME": "ops-admin",
            "CORAMAIL_AUTH_PASSWORD": "long-random-password-value",
            "CORAMAIL_AUTH_SECRET": "b" * 64,
            "CORAMAIL_POSTGRES_PASSWORD": "long-random-db-password",
            "CORAMAIL_DATABASE_URL": "postgresql://coramail:secret@postgres.internal:5432/coramail",
            "CORAMAIL_QDRANT_URL": "http://qdrant.internal:6333",
            "CORAMAIL_LLM_BASE_URL": "http://vllm.internal:8000/v1",
            "CORAMAIL_LLM_PROVIDER": "vllm",
            "CORAMAIL_WEB_IMAGE": "registry.internal/coramail-agent:latest",
            "CORAMAIL_TEXT_MODEL": "qwen2.5-7b-awq",
            "CORAMAIL_CHAT_TEXT_MODEL": "qwen2.5-7b-awq",
            "CORAMAIL_VISION_MODEL": "qwen3-vl-2b",
            "CORAMAIL_EMBEDDING_MODEL": "bge-m3",
            "CORAMAIL_QDRANT_IMAGE": "qdrant/qdrant:latest",
        }
    )

    assert [issue.code for issue in issues] == [
        "unpinned-coramail_web_image",
        "unpinned-coramail_qdrant_image",
    ]


def test_read_env_file_strips_quotes_and_ignores_comments(tmp_path: Path) -> None:
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        """
# comment
CORAMAIL_AUTH_USERNAME='ops-admin'
CORAMAIL_AUTH_PASSWORD="long-random-password-value"
""".strip(),
        encoding="utf-8",
    )

    assert _read_env_file(env_file) == {
        "CORAMAIL_AUTH_USERNAME": "ops-admin",
        "CORAMAIL_AUTH_PASSWORD": "long-random-password-value",
    }

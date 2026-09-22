import json
import subprocess
import sys
from pathlib import Path

from app.tools.render_deployment_plan import deployment_plan, render_markdown
from app.tools.check_deployment_readiness import (
    Severity,
    _read_env_file,
    deployment_exposure_issues,
    deployment_readiness_issues,
)


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
            "CORAMAIL_BETA_BASE_URL": "",
            "CORAMAIL_DEPLOYMENT_MODE": "",
            "CORAMAIL_LLM_RUNTIME": "",
            "CORAMAIL_MAIL_PROVIDER": "",
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
        "beta-base-url",
        "deployment-mode",
        "llm-runtime",
        "mail-provider",
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
            "CORAMAIL_BETA_BASE_URL": "https://replace-with-beta-host.example.com",
            "CORAMAIL_DEPLOYMENT_MODE": "private",
            "CORAMAIL_LLM_RUNTIME": "local",
            "CORAMAIL_MAIL_PROVIDER": "gmail",
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
        "placeholder-beta-base-url",
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
            "CORAMAIL_BETA_BASE_URL": "https://coramail-beta.internal",
            "CORAMAIL_DEPLOYMENT_MODE": "private",
            "CORAMAIL_LLM_RUNTIME": "local",
            "CORAMAIL_MAIL_PROVIDER": "gmail",
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
            "CORAMAIL_DEPLOYMENT_MODE": "saas",
            "CORAMAIL_LLM_RUNTIME": "managed",
            "CORAMAIL_MAIL_PROVIDER": "gmail",
            "CORAMAIL_WEB_IMAGE": "registry.internal/coramail-agent:latest",
            "CORAMAIL_BETA_BASE_URL": "https://coramail-beta.internal",
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


def test_deployment_readiness_rejects_unsupported_mail_provider() -> None:
    issues = deployment_readiness_issues(
        {
            "CORAMAIL_DEMO_MODE": "false",
            "CORAMAIL_LOCAL_DEV_DEFAULTS": "false",
            "CORAMAIL_DEV_SEED_DEMO": "false",
            "CORAMAIL_AUTH_ENABLED": "true",
            "CORAMAIL_AUTH_COOKIE_SECURE": "true",
            "CORAMAIL_AUTH_USERNAME": "ops-admin",
            "CORAMAIL_AUTH_PASSWORD": "long-random-password-value",
            "CORAMAIL_AUTH_SECRET": "c" * 64,
            "CORAMAIL_POSTGRES_PASSWORD": "long-random-db-password",
            "CORAMAIL_DATABASE_URL": "postgresql://coramail:secret@postgres.internal:5432/coramail",
            "CORAMAIL_QDRANT_URL": "http://qdrant.internal:6333",
            "CORAMAIL_LLM_BASE_URL": "http://vllm.internal:8000/v1",
            "CORAMAIL_WEB_IMAGE": "registry.internal/coramail-agent:2026-09-03",
            "CORAMAIL_BETA_BASE_URL": "https://coramail-beta.internal",
            "CORAMAIL_DEPLOYMENT_MODE": "saas",
            "CORAMAIL_LLM_RUNTIME": "managed",
            "CORAMAIL_TEXT_MODEL": "qwen2.5-7b-awq",
            "CORAMAIL_CHAT_TEXT_MODEL": "qwen2.5-7b-awq",
            "CORAMAIL_VISION_MODEL": "qwen3-vl-2b",
            "CORAMAIL_EMBEDDING_MODEL": "bge-m3",
            "CORAMAIL_LLM_PROVIDER": "vllm",
            "CORAMAIL_MAIL_PROVIDER": "imap",
        }
    )

    assert [issue.code for issue in issues if issue.severity is Severity.ERROR] == ["unsupported-mail-provider"]


def test_deployment_readiness_accepts_initial_provider_setup_mode() -> None:
    issues = deployment_readiness_issues(
        {
            "CORAMAIL_DEMO_MODE": "false",
            "CORAMAIL_LOCAL_DEV_DEFAULTS": "false",
            "CORAMAIL_DEV_SEED_DEMO": "false",
            "CORAMAIL_AUTH_ENABLED": "true",
            "CORAMAIL_AUTH_COOKIE_SECURE": "true",
            "CORAMAIL_AUTH_USERNAME": "ops-admin",
            "CORAMAIL_AUTH_PASSWORD": "long-random-password-value",
            "CORAMAIL_AUTH_SECRET": "f" * 64,
            "CORAMAIL_POSTGRES_PASSWORD": "long-random-db-password",
            "CORAMAIL_DATABASE_URL": "postgresql://coramail:secret@postgres.internal:5432/coramail",
            "CORAMAIL_QDRANT_URL": "http://qdrant.internal:6333",
            "CORAMAIL_LLM_BASE_URL": "http://vllm.internal:8000/v1",
            "CORAMAIL_WEB_IMAGE": "registry.internal/coramail-agent:2026-09-03",
            "CORAMAIL_BETA_BASE_URL": "https://coramail-beta.internal",
            "CORAMAIL_DEPLOYMENT_MODE": "setup",
            "CORAMAIL_LLM_RUNTIME": "setup",
            "CORAMAIL_TEXT_MODEL": "qwen2.5-7b-awq",
            "CORAMAIL_CHAT_TEXT_MODEL": "qwen2.5-7b-awq",
            "CORAMAIL_VISION_MODEL": "qwen3-vl-2b",
            "CORAMAIL_EMBEDDING_MODEL": "bge-m3",
            "CORAMAIL_LLM_PROVIDER": "vllm",
            "CORAMAIL_MAIL_PROVIDER": "setup",
        }
    )

    assert [issue for issue in issues if issue.severity is Severity.ERROR] == []


def test_deployment_readiness_requires_naver_account_material() -> None:
    issues = deployment_readiness_issues(
        {
            "CORAMAIL_DEMO_MODE": "false",
            "CORAMAIL_LOCAL_DEV_DEFAULTS": "false",
            "CORAMAIL_DEV_SEED_DEMO": "false",
            "CORAMAIL_AUTH_ENABLED": "true",
            "CORAMAIL_AUTH_COOKIE_SECURE": "true",
            "CORAMAIL_AUTH_USERNAME": "ops-admin",
            "CORAMAIL_AUTH_PASSWORD": "long-random-password-value",
            "CORAMAIL_AUTH_SECRET": "d" * 64,
            "CORAMAIL_POSTGRES_PASSWORD": "long-random-db-password",
            "CORAMAIL_DATABASE_URL": "postgresql://coramail:secret@postgres.internal:5432/coramail",
            "CORAMAIL_QDRANT_URL": "http://qdrant.internal:6333",
            "CORAMAIL_LLM_BASE_URL": "http://vllm.internal:8000/v1",
            "CORAMAIL_WEB_IMAGE": "registry.internal/coramail-agent:2026-09-03",
            "CORAMAIL_BETA_BASE_URL": "https://coramail-beta.internal",
            "CORAMAIL_DEPLOYMENT_MODE": "private",
            "CORAMAIL_LLM_RUNTIME": "local",
            "CORAMAIL_TEXT_MODEL": "qwen2.5-7b-awq",
            "CORAMAIL_CHAT_TEXT_MODEL": "qwen2.5-7b-awq",
            "CORAMAIL_VISION_MODEL": "qwen3-vl-2b",
            "CORAMAIL_EMBEDDING_MODEL": "bge-m3",
            "CORAMAIL_LLM_PROVIDER": "vllm",
            "CORAMAIL_MAIL_PROVIDER": "naver",
        }
    )

    assert {issue.code for issue in issues if issue.severity is Severity.ERROR} == {
        "naver-mail-address",
        "naver-app-password",
    }


def test_deployment_readiness_requires_hiworks_account_material() -> None:
    issues = deployment_readiness_issues(
        {
            "CORAMAIL_DEMO_MODE": "false",
            "CORAMAIL_LOCAL_DEV_DEFAULTS": "false",
            "CORAMAIL_DEV_SEED_DEMO": "false",
            "CORAMAIL_AUTH_ENABLED": "true",
            "CORAMAIL_AUTH_COOKIE_SECURE": "true",
            "CORAMAIL_AUTH_USERNAME": "ops-admin",
            "CORAMAIL_AUTH_PASSWORD": "long-random-password-value",
            "CORAMAIL_AUTH_SECRET": "e" * 64,
            "CORAMAIL_POSTGRES_PASSWORD": "long-random-db-password",
            "CORAMAIL_DATABASE_URL": "postgresql://coramail:secret@postgres.internal:5432/coramail",
            "CORAMAIL_QDRANT_URL": "http://qdrant.internal:6333",
            "CORAMAIL_LLM_BASE_URL": "http://vllm.internal:8000/v1",
            "CORAMAIL_WEB_IMAGE": "registry.internal/coramail-agent:2026-09-03",
            "CORAMAIL_BETA_BASE_URL": "https://coramail-beta.internal",
            "CORAMAIL_DEPLOYMENT_MODE": "private",
            "CORAMAIL_LLM_RUNTIME": "local",
            "CORAMAIL_TEXT_MODEL": "qwen2.5-7b-awq",
            "CORAMAIL_CHAT_TEXT_MODEL": "qwen2.5-7b-awq",
            "CORAMAIL_VISION_MODEL": "qwen3-vl-2b",
            "CORAMAIL_EMBEDDING_MODEL": "bge-m3",
            "CORAMAIL_LLM_PROVIDER": "vllm",
            "CORAMAIL_MAIL_PROVIDER": "hiworks",
        }
    )

    assert {issue.code for issue in issues if issue.severity is Severity.ERROR} == {
        "hiworks-mail-address",
        "hiworks-app-password",
    }


def test_deployment_readiness_rejects_private_external_llm_runtime() -> None:
    issues = deployment_readiness_issues(
        {
            "CORAMAIL_DEMO_MODE": "false",
            "CORAMAIL_LOCAL_DEV_DEFAULTS": "false",
            "CORAMAIL_DEV_SEED_DEMO": "false",
            "CORAMAIL_AUTH_ENABLED": "true",
            "CORAMAIL_AUTH_COOKIE_SECURE": "true",
            "CORAMAIL_AUTH_USERNAME": "ops-admin",
            "CORAMAIL_AUTH_PASSWORD": "long-random-password-value",
            "CORAMAIL_AUTH_SECRET": "g" * 64,
            "CORAMAIL_POSTGRES_PASSWORD": "long-random-db-password",
            "CORAMAIL_DATABASE_URL": "postgresql://coramail:secret@postgres.internal:5432/coramail",
            "CORAMAIL_QDRANT_URL": "http://qdrant.internal:6333",
            "CORAMAIL_LLM_BASE_URL": "http://api.openai.test/v1",
            "CORAMAIL_WEB_IMAGE": "registry.internal/coramail-agent:2026-09-03",
            "CORAMAIL_BETA_BASE_URL": "https://coramail-beta.internal",
            "CORAMAIL_DEPLOYMENT_MODE": "private",
            "CORAMAIL_LLM_RUNTIME": "external",
            "CORAMAIL_EXTERNAL_LLM_APPROVED": "true",
            "CORAMAIL_TEXT_MODEL": "gpt-4.1",
            "CORAMAIL_CHAT_TEXT_MODEL": "gpt-4.1",
            "CORAMAIL_VISION_MODEL": "gpt-4.1",
            "CORAMAIL_EMBEDDING_MODEL": "text-embedding-3-large",
            "CORAMAIL_LLM_PROVIDER": "openai",
            "CORAMAIL_MAIL_PROVIDER": "gmail",
        }
    )

    assert "private-external-llm" in {issue.code for issue in issues if issue.severity is Severity.ERROR}


def test_deployment_readiness_allows_explicit_hybrid_external_llm() -> None:
    issues = deployment_readiness_issues(
        {
            "CORAMAIL_DEMO_MODE": "false",
            "CORAMAIL_LOCAL_DEV_DEFAULTS": "false",
            "CORAMAIL_DEV_SEED_DEMO": "false",
            "CORAMAIL_AUTH_ENABLED": "true",
            "CORAMAIL_AUTH_COOKIE_SECURE": "true",
            "CORAMAIL_AUTH_USERNAME": "ops-admin",
            "CORAMAIL_AUTH_PASSWORD": "long-random-password-value",
            "CORAMAIL_AUTH_SECRET": "h" * 64,
            "CORAMAIL_POSTGRES_PASSWORD": "long-random-db-password",
            "CORAMAIL_DATABASE_URL": "postgresql://coramail:secret@postgres.internal:5432/coramail",
            "CORAMAIL_QDRANT_URL": "http://qdrant.internal:6333",
            "CORAMAIL_LLM_BASE_URL": "http://api.openai.test/v1",
            "CORAMAIL_WEB_IMAGE": "registry.internal/coramail-agent:2026-09-03",
            "CORAMAIL_BETA_BASE_URL": "https://coramail-beta.internal",
            "CORAMAIL_DEPLOYMENT_MODE": "hybrid",
            "CORAMAIL_LLM_RUNTIME": "external",
            "CORAMAIL_EXTERNAL_LLM_APPROVED": "true",
            "CORAMAIL_TEXT_MODEL": "gpt-4.1",
            "CORAMAIL_CHAT_TEXT_MODEL": "gpt-4.1",
            "CORAMAIL_VISION_MODEL": "gpt-4.1",
            "CORAMAIL_EMBEDDING_MODEL": "text-embedding-3-large",
            "CORAMAIL_LLM_PROVIDER": "openai",
            "CORAMAIL_MAIL_PROVIDER": "gmail",
        }
    )

    assert [issue for issue in issues if issue.severity is Severity.ERROR] == []


def test_deployment_readiness_requires_https_public_beta_url() -> None:
    issues = deployment_readiness_issues(
        {
            "CORAMAIL_DEMO_MODE": "false",
            "CORAMAIL_LOCAL_DEV_DEFAULTS": "false",
            "CORAMAIL_DEV_SEED_DEMO": "false",
            "CORAMAIL_AUTH_ENABLED": "true",
            "CORAMAIL_AUTH_COOKIE_SECURE": "true",
            "CORAMAIL_AUTH_USERNAME": "ops-admin",
            "CORAMAIL_AUTH_PASSWORD": "long-random-password-value",
            "CORAMAIL_AUTH_SECRET": "i" * 64,
            "CORAMAIL_POSTGRES_PASSWORD": "long-random-db-password",
            "CORAMAIL_DATABASE_URL": "postgresql://coramail:secret@postgres.internal:5432/coramail",
            "CORAMAIL_QDRANT_URL": "http://qdrant.internal:6333",
            "CORAMAIL_LLM_BASE_URL": "http://vllm.internal:8000/v1",
            "CORAMAIL_WEB_IMAGE": "registry.internal/coramail-agent:2026-09-03",
            "CORAMAIL_BETA_BASE_URL": "http://localhost:8040",
            "CORAMAIL_BETA_PUBLIC": "true",
            "CORAMAIL_BETA_HOST": "replace-with-beta-host.example.com",
            "CORAMAIL_DEPLOYMENT_MODE": "saas",
            "CORAMAIL_LLM_RUNTIME": "managed",
            "CORAMAIL_TEXT_MODEL": "qwen2.5-7b-awq",
            "CORAMAIL_CHAT_TEXT_MODEL": "qwen2.5-7b-awq",
            "CORAMAIL_VISION_MODEL": "qwen3-vl-2b",
            "CORAMAIL_EMBEDDING_MODEL": "bge-m3",
            "CORAMAIL_LLM_PROVIDER": "vllm",
            "CORAMAIL_MAIL_PROVIDER": "setup",
        }
    )

    assert {
        "public-beta-https",
        "public-beta-host",
        "placeholder-beta-host",
        "public-beta-host-mismatch",
    } <= {issue.code for issue in issues if issue.severity is Severity.ERROR}


def test_deployment_readiness_accepts_public_beta_edge_settings() -> None:
    issues = deployment_readiness_issues(
        {
            "CORAMAIL_DEMO_MODE": "false",
            "CORAMAIL_LOCAL_DEV_DEFAULTS": "false",
            "CORAMAIL_DEV_SEED_DEMO": "false",
            "CORAMAIL_AUTH_ENABLED": "true",
            "CORAMAIL_AUTH_COOKIE_SECURE": "true",
            "CORAMAIL_AUTH_USERNAME": "ops-admin",
            "CORAMAIL_AUTH_PASSWORD": "long-random-password-value",
            "CORAMAIL_AUTH_SECRET": "j" * 64,
            "CORAMAIL_POSTGRES_PASSWORD": "long-random-db-password",
            "CORAMAIL_DATABASE_URL": "postgresql://coramail:secret@postgres.internal:5432/coramail",
            "CORAMAIL_QDRANT_URL": "http://qdrant.internal:6333",
            "CORAMAIL_LLM_BASE_URL": "http://vllm.internal:8000/v1",
            "CORAMAIL_WEB_IMAGE": "registry.internal/coramail-agent:2026-09-03",
            "CORAMAIL_BETA_BASE_URL": "https://beta.coramail.test",
            "CORAMAIL_BETA_PUBLIC": "true",
            "CORAMAIL_BETA_HOST": "beta.coramail.test",
            "CORAMAIL_DEPLOYMENT_MODE": "saas",
            "CORAMAIL_LLM_RUNTIME": "managed",
            "CORAMAIL_TEXT_MODEL": "qwen2.5-7b-awq",
            "CORAMAIL_CHAT_TEXT_MODEL": "qwen2.5-7b-awq",
            "CORAMAIL_VISION_MODEL": "qwen3-vl-2b",
            "CORAMAIL_EMBEDDING_MODEL": "bge-m3",
            "CORAMAIL_LLM_PROVIDER": "vllm",
            "CORAMAIL_MAIL_PROVIDER": "setup",
        }
    )

    assert [issue for issue in issues if issue.severity is Severity.ERROR] == []


def test_deployment_readiness_rejects_public_quick_tunnel_url() -> None:
    issues = deployment_readiness_issues(
        {
            "CORAMAIL_DEMO_MODE": "false",
            "CORAMAIL_LOCAL_DEV_DEFAULTS": "false",
            "CORAMAIL_DEV_SEED_DEMO": "false",
            "CORAMAIL_AUTH_ENABLED": "true",
            "CORAMAIL_AUTH_COOKIE_SECURE": "true",
            "CORAMAIL_AUTH_USERNAME": "ops-admin",
            "CORAMAIL_AUTH_PASSWORD": "long-random-password-value",
            "CORAMAIL_AUTH_SECRET": "k" * 64,
            "CORAMAIL_POSTGRES_PASSWORD": "long-random-db-password",
            "CORAMAIL_DATABASE_URL": "postgresql://coramail:secret@postgres.internal:5432/coramail",
            "CORAMAIL_QDRANT_URL": "http://qdrant.internal:6333",
            "CORAMAIL_LLM_BASE_URL": "http://vllm.internal:8000/v1",
            "CORAMAIL_WEB_IMAGE": "registry.internal/coramail-agent:2026-09-03",
            "CORAMAIL_BETA_BASE_URL": "https://temporary-beta.trycloudflare.com",
            "CORAMAIL_BETA_PUBLIC": "true",
            "CORAMAIL_BETA_HOST": "temporary-beta.trycloudflare.com",
            "CORAMAIL_DEPLOYMENT_MODE": "saas",
            "CORAMAIL_LLM_RUNTIME": "managed",
            "CORAMAIL_TEXT_MODEL": "qwen2.5-7b-awq",
            "CORAMAIL_CHAT_TEXT_MODEL": "qwen2.5-7b-awq",
            "CORAMAIL_VISION_MODEL": "qwen3-vl-2b",
            "CORAMAIL_EMBEDDING_MODEL": "bge-m3",
            "CORAMAIL_LLM_PROVIDER": "vllm",
            "CORAMAIL_MAIL_PROVIDER": "setup",
        }
    )

    assert {
        issue.code for issue in issues if issue.severity is Severity.ERROR
    } == {"public-beta-quick-tunnel"}


def test_deployment_exposure_requires_public_mode_for_edge_and_tunnel() -> None:
    assert [issue.code for issue in deployment_exposure_issues({}, "edge")] == [
        "public-exposure-disabled"
    ]
    assert [issue.code for issue in deployment_exposure_issues({}, "tunnel")] == [
        "public-exposure-disabled",
        "cloudflare-tunnel-token",
    ]


def test_deployment_exposure_accepts_configured_paths() -> None:
    values = {
        "CORAMAIL_BETA_PUBLIC": "true",
        "CORAMAIL_CLOUDFLARE_TUNNEL_TOKEN": "configured-token",
    }

    assert deployment_exposure_issues(values, "internal") == []
    assert deployment_exposure_issues(values, "edge") == []
    assert deployment_exposure_issues(values, "tunnel") == []


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


def test_deployment_readiness_json_output_lists_actionable_issues(tmp_path: Path) -> None:
    env_file = tmp_path / "production.env"
    env_file.write_text(
        "\n".join(
            [
                "CORAMAIL_DEMO_MODE=false",
                "CORAMAIL_LOCAL_DEV_DEFAULTS=false",
                "CORAMAIL_DEV_SEED_DEMO=false",
                "CORAMAIL_AUTH_ENABLED=true",
                "CORAMAIL_AUTH_COOKIE_SECURE=true",
                "CORAMAIL_AUTH_USERNAME=replace-with-admin-login",
                "CORAMAIL_AUTH_PASSWORD=replace-with-random-password",
                "CORAMAIL_AUTH_SECRET=replace-with-at-least-32-random-characters",
                "CORAMAIL_POSTGRES_PASSWORD=replace-with-random-postgres-password",
                "CORAMAIL_DATABASE_URL=postgresql://coramail:secret@postgres.internal:5432/coramail",
                "CORAMAIL_QDRANT_URL=http://qdrant.internal:6333",
                "CORAMAIL_LLM_BASE_URL=http://vllm.internal:8000/v1",
                "CORAMAIL_WEB_IMAGE=registry.example.com/coramail-agent:2026-09-03",
                "CORAMAIL_BETA_BASE_URL=https://replace-with-beta-host.example.com",
                "CORAMAIL_DEPLOYMENT_MODE=saas",
                "CORAMAIL_LLM_RUNTIME=managed",
                "CORAMAIL_MAIL_PROVIDER=setup",
                "CORAMAIL_TEXT_MODEL=replace-with-tested-text-model",
                "CORAMAIL_CHAT_TEXT_MODEL=replace-with-tested-chat-model",
                "CORAMAIL_VISION_MODEL=replace-with-tested-vision-model",
                "CORAMAIL_EMBEDDING_MODEL=replace-with-tested-embedding-model",
                "CORAMAIL_LLM_PROVIDER=vllm",
                "CORAMAIL_CLOUDFLARE_TUNNEL_TOKEN=cf-secret-token",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.tools.check_deployment_readiness",
            "--env-file",
            str(env_file),
            "--warnings-as-errors",
            "--format",
            "json",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 1
    assert payload["deployment_readiness"] == "issues"
    assert {"severity": "error", "code": "placeholder-text-model", "message": "CORAMAIL_TEXT_MODEL must not contain placeholder values."} in payload[
        "issues"
    ]


def test_deployment_plan_redacts_secret_values(tmp_path: Path) -> None:
    env_file = tmp_path / "production.env"
    env_file.write_text(
        "\n".join(
            [
                "CORAMAIL_DEMO_MODE=false",
                "CORAMAIL_LOCAL_DEV_DEFAULTS=false",
                "CORAMAIL_DEV_SEED_DEMO=false",
                "CORAMAIL_AUTH_ENABLED=true",
                "CORAMAIL_AUTH_COOKIE_SECURE=true",
                "CORAMAIL_AUTH_USERNAME=ops-admin",
                "CORAMAIL_AUTH_PASSWORD=super-secret-password",
                "CORAMAIL_AUTH_SECRET=" + "s" * 64,
                "CORAMAIL_POSTGRES_PASSWORD=super-secret-db-password",
                "CORAMAIL_DATABASE_URL=postgresql://coramail:secret@postgres.internal:5432/coramail",
                "CORAMAIL_QDRANT_URL=http://qdrant.internal:6333",
                "CORAMAIL_LLM_BASE_URL=http://vllm.internal:8000/v1",
                "CORAMAIL_WEB_IMAGE=registry.internal/coramail-agent:2026-09-17",
                "CORAMAIL_BETA_BASE_URL=https://coramail-beta.internal",
                "CORAMAIL_BETA_PUBLIC=true",
                "CORAMAIL_BETA_HOST=coramail-beta.internal",
                "CORAMAIL_DEPLOYMENT_MODE=saas",
                "CORAMAIL_LLM_RUNTIME=managed",
                "CORAMAIL_MAIL_PROVIDER=setup",
                "CORAMAIL_TEXT_MODEL=qwen2.5-7b-awq",
                "CORAMAIL_CHAT_TEXT_MODEL=qwen2.5-7b-awq",
                "CORAMAIL_VISION_MODEL=qwen3-vl-2b",
                "CORAMAIL_EMBEDDING_MODEL=bge-m3",
                "CORAMAIL_LLM_PROVIDER=vllm",
                "CORAMAIL_CLOUDFLARE_TUNNEL_TOKEN=cf-secret-token",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    plan = deployment_plan(env_file)
    rendered = render_markdown(plan)

    assert plan["secrets"]["CORAMAIL_AUTH_PASSWORD"] == "configured"
    assert plan["secrets"]["CORAMAIL_CLOUDFLARE_TUNNEL_TOKEN"] == "configured"
    assert "super-secret-password" not in rendered
    assert "cf-secret-token" not in rendered
    assert "`CORAMAIL_DEPLOYMENT_MODE`: `saas`" in rendered
    assert "`CORAMAIL_BETA_BASE_URL`: `https://coramail-beta.internal`" in rendered
    assert "`CORAMAIL_BETA_PUBLIC`: `true`" in rendered
    assert "`CORAMAIL_BETA_HOST`: `coramail-beta.internal`" in rendered
    assert "- readiness: `ready`" in rendered

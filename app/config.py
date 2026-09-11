from __future__ import annotations

import os


LOCAL_DEV_DATABASE_URL = "postgresql://coramail:coramail@127.0.0.1:5432/coramail"


def local_dev_defaults_enabled() -> bool:
    # A hosted process normally has neither the local PostgreSQL instance nor
    # the local Qdrant/LLM services.  Falling back to 127.0.0.1 here makes the
    # first UI request fail with a database connection error instead of serving
    # the bundled demo fixtures.  Local developers can opt in explicitly.
    value = os.getenv("CORAMAIL_LOCAL_DEV_DEFAULTS", "false").strip().casefold()
    return value not in {"0", "false", "off", "no"}


def database_url() -> str:
    configured = os.getenv("CORAMAIL_DATABASE_URL", "").strip()
    if configured:
        return configured
    return LOCAL_DEV_DATABASE_URL if local_dev_defaults_enabled() else ""


def mail_provider() -> str:
    configured = os.getenv("CORAMAIL_MAIL_PROVIDER", "").strip().casefold()
    return configured if configured in {"gmail", "naver", "hiworks"} else "gmail"


def text_model() -> str:
    return os.getenv("CORAMAIL_TEXT_MODEL", "llama3.2:latest").strip() or "llama3.2:latest"


def chat_text_model() -> str:
    configured = os.getenv("CORAMAIL_CHAT_TEXT_MODEL", "").strip()
    return configured or text_model()


def vision_model() -> str:
    return os.getenv("CORAMAIL_VISION_MODEL", "qwen2.5vl:7b").strip() or "qwen2.5vl:7b"


def embedding_model() -> str:
    return os.getenv("CORAMAIL_EMBEDDING_MODEL", "nomic-embed-text:latest").strip() or "nomic-embed-text:latest"


def llm_base_url() -> str:
    return os.getenv("CORAMAIL_LLM_BASE_URL", "http://127.0.0.1:11434/v1").strip() or "http://127.0.0.1:11434/v1"


def text_llm_base_url() -> str:
    return os.getenv("CORAMAIL_TEXT_LLM_BASE_URL", "").strip() or llm_base_url()


def vision_llm_base_url() -> str:
    return os.getenv("CORAMAIL_VISION_LLM_BASE_URL", "").strip() or llm_base_url()


def embedding_base_url() -> str:
    return os.getenv("CORAMAIL_EMBEDDING_BASE_URL", "").strip() or llm_base_url()


def llm_provider() -> str:
    return os.getenv("CORAMAIL_LLM_PROVIDER", "ollama").strip().casefold() or "ollama"


def text_llm_provider() -> str:
    return os.getenv("CORAMAIL_TEXT_LLM_PROVIDER", "").strip().casefold() or llm_provider()


def vision_llm_provider() -> str:
    return os.getenv("CORAMAIL_VISION_LLM_PROVIDER", "").strip().casefold() or llm_provider()


def embedding_provider() -> str:
    return os.getenv("CORAMAIL_EMBEDDING_PROVIDER", "").strip().casefold() or llm_provider()


def llm_max_concurrency(role: str) -> int:
    role_key = role.upper().replace("-", "_")
    raw_value = os.getenv(f"CORAMAIL_{role_key}_LLM_MAX_CONCURRENCY", "").strip() or os.getenv(
        "CORAMAIL_LLM_MAX_CONCURRENCY", "4"
    ).strip()
    try:
        value = int(raw_value)
    except ValueError:
        return 4
    return max(1, value)


def llm_max_output_tokens() -> int:
    raw_value = os.getenv("CORAMAIL_LLM_MAX_OUTPUT_TOKENS", "1024").strip()
    try:
        value = int(raw_value)
    except ValueError:
        return 1024
    return max(1, value)


def qdrant_url() -> str:
    return os.getenv("CORAMAIL_QDRANT_URL", "http://127.0.0.1:6333").strip() or "http://127.0.0.1:6333"


def qdrant_case_collection() -> str:
    return os.getenv("CORAMAIL_QDRANT_CASE_COLLECTION", "coramail_cases_clean_v2").strip() or "coramail_cases_clean_v2"

from __future__ import annotations

import importlib

import app.config as config
import app.server as server


def test_database_is_not_assumed_in_a_clean_hosting_environment(monkeypatch):
    monkeypatch.delenv("CORAMAIL_DATABASE_URL", raising=False)
    monkeypatch.delenv("CORAMAIL_LOCAL_DEV_DEFAULTS", raising=False)
    reloaded = importlib.reload(config)

    assert reloaded.local_dev_defaults_enabled() is False
    assert reloaded.database_url() == ""


def test_demo_mail_service_is_selected_without_database(monkeypatch):
    monkeypatch.delenv("CORAMAIL_DATABASE_URL", raising=False)
    monkeypatch.delenv("CORAMAIL_LOCAL_DEV_DEFAULTS", raising=False)
    monkeypatch.setenv("CORAMAIL_DEMO_MODE", "true")
    monkeypatch.setattr(server, "database_url", lambda: "")

    service = server.mail_service()

    assert service.__class__.__name__ == "DemoMailService"
    assert service.list_emails()


def test_mail_rows_falls_back_to_demo_fixtures_when_configured_store_is_down(monkeypatch):
    class OperationalError(Exception):
        pass

    class FailingMailService:
        def list_emails(self, **kwargs):
            raise OperationalError("connection refused")

    monkeypatch.setattr(server, "mail_service", lambda: FailingMailService())

    rows = server.mail_rows()

    assert rows
    assert rows == server.demo_service().list_emails()


def test_health_reports_degraded_instead_of_500_when_mail_store_is_down(monkeypatch):
    class OperationalError(Exception):
        pass

    class FailingMailService:
        def list_emails(self, **kwargs):
            raise OperationalError("connection refused")

    monkeypatch.setattr(server, "mail_service", lambda: FailingMailService())
    monkeypatch.setattr(
        server,
        "local_ai_readiness",
        lambda: {
            "ready": False,
            "database": {"ready": False, "error": "connection refused"},
            "llm": {"ready": False},
            "qdrant": {"ready": False},
        },
    )

    payload = server.health()

    assert payload["status"] == "degraded"
    assert payload["demo_email_count"] > 0


def test_llm_readiness_treats_unexpected_model_payload_as_degraded(monkeypatch):
    class Gateway:
        def __init__(self, config):
            self.config = config

        def healthcheck(self):
            return {"data": None}

    monkeypatch.setattr(server, "LocalLLMGateway", Gateway)

    payload = server._llm_readiness()

    assert payload["ready"] is False
    assert payload["installed_count"] == 0
    assert payload["missing"]


def test_llm_readiness_accepts_gemini_model_payload(monkeypatch):
    class Gateway:
        def __init__(self, config):
            self.config = config

        def healthcheck(self):
            return {
                "models": [
                    {"name": "models/gemini-2.5-flash"},
                    {"name": "models/gemini-embedding-001"},
                ]
            }

    monkeypatch.setenv("CORAMAIL_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("CORAMAIL_TEXT_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("CORAMAIL_VISION_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("CORAMAIL_EMBEDDING_MODEL", "gemini-embedding-001")
    monkeypatch.setattr(server, "LocalLLMGateway", Gateway)

    payload = server._llm_readiness()

    assert payload["ready"] is True
    assert payload["installed_count"] == 2
    assert payload["missing"] == {}


def test_llm_readiness_checks_dedicated_chat_text_model(monkeypatch):
    class Gateway:
        def __init__(self, config):
            self.config = config

        def healthcheck(self):
            return {
                "data": [
                    {"id": "analysis-model"},
                    {"id": "fast-chat-model"},
                    {"id": "vision-model"},
                    {"id": "embedding-model"},
                ]
            }

    monkeypatch.setenv("CORAMAIL_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("CORAMAIL_TEXT_MODEL", "analysis-model")
    monkeypatch.setenv("CORAMAIL_CHAT_TEXT_MODEL", "fast-chat-model")
    monkeypatch.setenv("CORAMAIL_VISION_MODEL", "vision-model")
    monkeypatch.setenv("CORAMAIL_EMBEDDING_MODEL", "embedding-model")
    monkeypatch.setattr(server, "LocalLLMGateway", Gateway)

    payload = server._llm_readiness()

    assert payload["ready"] is True
    assert payload["required"]["text_model"] == "analysis-model"
    assert payload["required"]["chat_text_model"] == "fast-chat-model"
    assert payload["missing"] == {}

from __future__ import annotations

import os
from typing import Any

from app.repositories.gmail_account_repository import GmailAccountRepository
from app.services.gmail_mail_service import GmailMailboxService
from app.services.gmail_oauth_service import GmailOAuthService


class FakeCredentials:
    scopes = ["https://mail.google.com/", "https://www.googleapis.com/auth/gmail.readonly"]

    def to_json(self) -> str:
        return (
            '{"token": "issued-token", "refresh_token": "issued-refresh", '
            '"scopes": ["https://mail.google.com/", "https://www.googleapis.com/auth/gmail.readonly"]}'
        )


class FakeFlow:
    def __init__(self) -> None:
        self.credentials = FakeCredentials()
        self.authorization_kwargs: dict[str, Any] = {}
        self.relax_scope_during_fetch = ""

    def authorization_url(self, **kwargs: Any) -> tuple[str, str]:
        self.authorization_kwargs = kwargs
        return "https://accounts.google.invalid/auth", "state"

    def fetch_token(self, **kwargs: Any) -> None:
        self.relax_scope_during_fetch = os.getenv("OAUTHLIB_RELAX_TOKEN_SCOPE", "")


class ProfileFailingOAuthService(GmailOAuthService):
    def __init__(self, repository: GmailAccountRepository, flow: FakeFlow):
        super().__init__(repository)
        self.flow = flow

    def _flow(self, redirect_uri: str) -> FakeFlow:
        return self.flow

    def _profile_email(self, credentials: Any) -> str:
        return ""


def test_oauth_authorization_does_not_request_incremental_scope(tmp_path):
    repository = GmailAccountRepository(tmp_path)
    flow = FakeFlow()
    service = ProfileFailingOAuthService(repository, flow)

    service.authorization_url("http://127.0.0.1:8000/auth/gmail/callback")

    assert flow.authorization_kwargs["access_type"] == "offline"
    assert flow.authorization_kwargs["prompt"] == "consent"
    assert "include_granted_scopes" not in flow.authorization_kwargs


def test_oauth_callback_relaxes_scope_changes_and_persists_token_before_profile(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_TOKEN_JSON", raising=False)
    monkeypatch.delenv("OAUTHLIB_RELAX_TOKEN_SCOPE", raising=False)
    repository = GmailAccountRepository(tmp_path)
    flow = FakeFlow()
    service = ProfileFailingOAuthService(repository, flow)

    result = service.complete_callback(
        redirect_uri="http://127.0.0.1:8000/auth/gmail/callback",
        authorization_response="http://127.0.0.1:8000/auth/gmail/callback?code=code&state=state",
    )

    assert result == {"email_address": ""}
    assert flow.relax_scope_during_fetch == "1"
    assert os.getenv("OAUTHLIB_RELAX_TOKEN_SCOPE") is None
    assert repository.token_path.exists()
    assert repository.primary_token_info()["token"] == "issued-token"
    assert repository.connected_account()["status"] == "active"
    assert repository.connected_account()["scopes"] == FakeCredentials.scopes


def test_oauth_callback_persists_issued_token_to_active_dotenv(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("CORAMAIL_DEMO_MODE=false\n", encoding="utf-8")
    monkeypatch.setenv("CORAMAIL_ENV_FILE", str(env_path))
    monkeypatch.delenv("GOOGLE_TOKEN_JSON", raising=False)
    repository = GmailAccountRepository(tmp_path)
    flow = FakeFlow()
    service = ProfileFailingOAuthService(repository, flow)

    service.complete_callback(
        redirect_uri="http://127.0.0.1:8000/auth/gmail/callback",
        authorization_response="http://127.0.0.1:8000/auth/gmail/callback?code=code&state=state",
    )

    env_text = env_path.read_text(encoding="utf-8")
    assert "GOOGLE_TOKEN_JSON=" in env_text
    assert '"token":"issued-token"' in env_text
    assert repository.primary_token_info()["token"] == "issued-token"


def test_public_status_rereads_active_dotenv_token_after_repository_creation(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("CORAMAIL_DEMO_MODE=false\n", encoding="utf-8")
    monkeypatch.setenv("CORAMAIL_ENV_FILE", str(env_path))
    monkeypatch.delenv("GOOGLE_TOKEN_JSON", raising=False)
    repository = GmailAccountRepository(tmp_path)

    env_path.write_text(
        "CORAMAIL_DEMO_MODE=false\n"
        "GOOGLE_TOKEN_JSON='{\"token\":\"saved-token\",\"email\":\"ops@example.com\",\"scopes\":[\"https://mail.google.com/\"]}'\n",
        encoding="utf-8",
    )

    status = repository.public_status()

    assert status["connected"] is True
    assert status["email_address"] == "ops@example.com"
    assert status["token_source"] == "env"


def test_gmail_status_resolves_connected_token_account_identity(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_TOKEN_JSON", raising=False)
    repository = GmailAccountRepository(tmp_path)
    repository.save_existing_tokens(
        primary_token_json='{"token":"saved-token","scopes":["https://mail.google.com/"]}',
    )
    monkeypatch.setattr("app.services.gmail_mail_service.build_gmail_service", lambda *args, **kwargs: object())
    monkeypatch.setattr("app.services.gmail_mail_service.gmail_profile_email", lambda service: "shared@example.com")
    service = GmailMailboxService(tmp_path, repository)

    status = service.status()

    assert status["account"] == "shared@example.com"
    assert repository.public_status()["email_address"] == "shared@example.com"

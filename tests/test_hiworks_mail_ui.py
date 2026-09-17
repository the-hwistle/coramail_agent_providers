from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace

import app.server as server
from app.services.hiworks_mail_service import HiworksMailboxService
from tests.ui_test_support import request, request_with_body


def test_hiworks_provider_settings_panel_replaces_gmail_setup_copy(monkeypatch):
    monkeypatch.setattr(server, "active_mail_provider", lambda: "hiworks")
    monkeypatch.setattr(server, "active_provider_label", lambda: "하이웍스")
    monkeypatch.setattr(
        server,
        "active_mail_status",
        lambda: {
            "account": "user@example.com",
            "last_error": "",
            "last_synced_at": 0,
            "message_count": 0,
            "preview_count": 0,
            "version": "hiworks:idle",
        },
    )
    monkeypatch.setattr(
        server,
        "active_mail_public_status",
        lambda: {
            "connected": False,
            "has_client_config": True,
            "email_address": "user@example.com",
            "pop3_username": "user@example.com",
            "last_sync_error": "",
            "last_synced_at": 0,
            "pop3_host": "pop3s.hiworks.com",
            "pop3_port": 995,
            "smtp_host": "smtps.hiworks.com",
            "smtp_port": 465,
            "message_count": 0,
        },
    )

    html = server.render_mail_sync_settings(request()).body.decode("utf-8")

    assert "하이웍스 Mail 연동 준비됨" in html
    assert "하이웍스 Mail 연동 확인" in html
    assert "POP3 읽기 연결" in html
    assert "메일 전용 비밀번호 설정됨" in html
    assert "Google" not in html
    assert "OAuth" not in html
    assert "GOOGLE_TOKEN_JSON" not in html
    assert "Gmail 권한" not in html
    assert 'hx-post="/ui/settings/hiworks/account"' in html
    assert 'name="email_address"' in html
    assert 'name="pop3_username"' in html
    assert 'name="app_password"' in html
    assert "value=\"user@example.com\"" in html


def test_hiworks_settings_sync_uses_hiworks_service(monkeypatch):
    monkeypatch.setattr(
        server,
        "_hiworks_service",
        SimpleNamespace(sync=lambda: {"status": "ok", "message_count": 1000, "persisted_message_count": 20}),
    )
    monkeypatch.setattr(server, "render_mail_sync_settings", lambda request, **kwargs: kwargs)

    response = server.ui_hiworks_settings_sync(request("POST"))

    assert response["message"] == "하이웍스 받은편지함 1000건을 확인했고 20건을 Inbox에 저장했습니다."


def test_hiworks_provider_uses_hiworks_mail_service_for_inbox(monkeypatch):
    hiworks_service = SimpleNamespace(list_emails=lambda **kwargs: [{"email_uid": "hiworks-mail"}])
    gmail_service = SimpleNamespace(list_emails=lambda **kwargs: [{"email_uid": "gmail-mail"}])
    monkeypatch.setenv("CORAMAIL_MAIL_PROVIDER", "hiworks")
    monkeypatch.setattr(server, "demo_mode_enabled", lambda: False)
    monkeypatch.setattr(server, "active_mail_provider", lambda: "hiworks")
    monkeypatch.setattr(server, "_hiworks_service", hiworks_service)
    monkeypatch.setattr(server, "_gmail_service", gmail_service)

    assert server.mail_rows()[0]["email_uid"] == "hiworks-mail"


def test_hiworks_public_status_uses_persisted_success_after_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("CORAMAIL_HIWORKS_MAIL_ADDRESS", "hiworks@example.com")
    monkeypatch.setenv("CORAMAIL_HIWORKS_POP3_USERNAME", "hiworks@example.com")
    monkeypatch.setenv("CORAMAIL_HIWORKS_APP_PASSWORD", "app-password")
    service = HiworksMailboxService(
        tmp_path,
        sync_repository=SimpleNamespace(
            account_status=lambda: {
                "email_address": "hiworks@example.com",
                "status": "active",
                "last_synced_at": "2026-09-11T05:00:00+00:00",
                "last_error": "",
                "message_count": 92,
            }
        ),
    )

    status = service.public_status()

    assert status["connected"] is True
    assert status["status"] == "active"
    assert status["message_count"] == 92


def test_hiworks_account_save_updates_dotenv_and_runtime_env(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "CORAMAIL_HIWORKS_MAIL_ADDRESS='old@example.com'\n"
        "CORAMAIL_HIWORKS_APP_PASSWORD='old-password'\n"
        "CORAMAIL_NAVER_MAIL_ADDRESS='keep@example.com'\n",
        encoding="utf-8",
    )
    reset_calls: list[bool] = []
    monkeypatch.setattr(server, "ACTIVE_ENV_PATH", env_path)
    monkeypatch.setattr(server, "_hiworks_service", SimpleNamespace(reset_runtime_status=lambda: reset_calls.append(True)))
    monkeypatch.setattr(server, "render_mail_sync_settings", lambda request, **kwargs: SimpleNamespace(body=str(kwargs).encode("utf-8"), set_cookie=lambda *args, **kw: None))

    response = asyncio.run(
        server.ui_save_hiworks_account(
            request_with_body(
                "POST",
                "/ui/settings/hiworks/account",
                body=(
                    b"email_address=new%40example.com&pop3_username=login%40example.com"
                    b"&app_password=new-password&pop3_host=pop3.example.com&pop3_port=995"
                    b"&smtp_host=smtp.example.com&smtp_port=465"
                ),
            )
        )
    )

    env_text = env_path.read_text(encoding="utf-8")
    assert "CORAMAIL_HIWORKS_MAIL_ADDRESS='new@example.com'" in env_text
    assert "CORAMAIL_HIWORKS_POP3_USERNAME='login@example.com'" in env_text
    assert "CORAMAIL_HIWORKS_APP_PASSWORD='new-password'" in env_text
    assert "CORAMAIL_NAVER_MAIL_ADDRESS='keep@example.com'" in env_text
    assert os.environ["CORAMAIL_HIWORKS_MAIL_ADDRESS"] == "new@example.com"
    assert os.environ["CORAMAIL_HIWORKS_APP_PASSWORD"] == "new-password"
    assert reset_calls == [True]
    assert "하이웍스 계정 설정을 저장했습니다." in response.body.decode("utf-8")


def test_hiworks_public_status_ignores_persisted_success_for_different_account(tmp_path, monkeypatch):
    monkeypatch.setenv("CORAMAIL_HIWORKS_MAIL_ADDRESS", "new@example.com")
    monkeypatch.setenv("CORAMAIL_HIWORKS_POP3_USERNAME", "new@example.com")
    monkeypatch.setenv("CORAMAIL_HIWORKS_APP_PASSWORD", "app-password")
    service = HiworksMailboxService(
        tmp_path,
        sync_repository=SimpleNamespace(
            account_status=lambda: {
                "email_address": "old@example.com",
                "status": "active",
                "last_synced_at": "2026-09-11T05:00:00+00:00",
                "last_error": "",
                "message_count": 92,
            }
        ),
    )

    status = service.public_status()

    assert status["connected"] is False
    assert status["status"] == "ready"
    assert status["email_address"] == "new@example.com"
    assert status["last_synced_at"] == 0
    assert status["message_count"] == 0

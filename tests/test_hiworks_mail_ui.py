from __future__ import annotations

from types import SimpleNamespace

import app.server as server
from app.services.hiworks_mail_service import HiworksMailboxService
from tests.ui_test_support import request


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

from __future__ import annotations

from types import SimpleNamespace

import app.server as server
from tests.ui_test_support import request


def test_naver_provider_settings_panel_replaces_gmail_setup_copy(monkeypatch):
    monkeypatch.setattr(server, "active_mail_provider", lambda: "naver")
    monkeypatch.setattr(server, "active_provider_label", lambda: "Naver")
    monkeypatch.setattr(
        server,
        "active_mail_status",
        lambda: {
            "account": "yshui@naver.com",
            "last_error": "",
            "last_synced_at": 0,
            "message_count": 0,
            "preview_count": 0,
            "version": "naver:idle",
        },
    )
    monkeypatch.setattr(
        server,
        "active_mail_public_status",
        lambda: {
            "connected": False,
            "has_client_config": True,
            "email_address": "yshui@naver.com",
            "imap_username": "yshui",
            "last_sync_error": "",
            "last_synced_at": 0,
            "imap_host": "imap.naver.com",
            "imap_port": 993,
            "smtp_host": "smtp.naver.com",
            "smtp_port": 587,
            "message_count": 0,
        },
    )

    html = server.render_mail_sync_settings(request()).body.decode("utf-8")

    assert "Naver Mail 연동 준비됨" in html
    assert "Naver Mail 연동 확인" in html
    assert "IMAP 읽기 연결" in html
    assert "앱 비밀번호 설정됨" in html
    assert "Google" not in html
    assert "OAuth" not in html
    assert "GOOGLE_TOKEN_JSON" not in html
    assert "Gmail 권한" not in html


def test_naver_settings_sync_uses_naver_service(monkeypatch):
    monkeypatch.setattr(
        server,
        "_naver_service",
        SimpleNamespace(sync=lambda: {"status": "ok", "message_count": 1000, "persisted_message_count": 20}),
    )
    monkeypatch.setattr(server, "render_mail_sync_settings", lambda request, **kwargs: kwargs)

    response = server.ui_naver_settings_sync(request("POST"))

    assert response["message"] == "Naver INBOX 1000건을 확인했고 20건을 Inbox에 저장했습니다."


def test_naver_provider_uses_naver_mail_service_for_inbox(monkeypatch):
    naver_service = SimpleNamespace(list_emails=lambda **kwargs: [{"email_uid": "naver-mail"}])
    gmail_service = SimpleNamespace(list_emails=lambda **kwargs: [{"email_uid": "gmail-mail"}])
    monkeypatch.setattr(server, "demo_mode_enabled", lambda: False)
    monkeypatch.setattr(server, "active_mail_provider", lambda: "naver")
    monkeypatch.setattr(server, "_naver_service", naver_service)
    monkeypatch.setattr(server, "_gmail_service", gmail_service)

    assert server.mail_rows()[0]["email_uid"] == "naver-mail"

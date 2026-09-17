from __future__ import annotations

import asyncio
from types import SimpleNamespace

import app.server as server
from app.services.naver_mail_service import NaverMailboxService
from tests.ui_test_support import request, request_with_body


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
    monkeypatch.setenv("CORAMAIL_MAIL_PROVIDER", "naver")
    monkeypatch.setattr(server, "demo_mode_enabled", lambda: False)
    monkeypatch.setattr(server, "active_mail_provider", lambda: "naver")
    monkeypatch.setattr(server, "_naver_service", naver_service)
    monkeypatch.setattr(server, "_gmail_service", gmail_service)

    assert server.mail_rows()[0]["email_uid"] == "naver-mail"


def test_configured_provider_still_uses_selected_mail_service(monkeypatch):
    naver_service = SimpleNamespace(list_emails=lambda **kwargs: [{"email_uid": "naver-mail"}])
    monkeypatch.setenv("CORAMAIL_MAIL_PROVIDER", "naver")
    monkeypatch.setattr(server, "demo_mode_enabled", lambda: False)
    monkeypatch.setattr(server, "_naver_service", naver_service)

    assert server.mail_rows()[0]["email_uid"] == "naver-mail"


def test_mail_provider_settings_panel_renders_provider_choices(monkeypatch):
    monkeypatch.setattr(server, "active_mail_provider", lambda: "gmail")
    monkeypatch.setattr(server, "active_provider_label", lambda: "Gmail")
    monkeypatch.setattr(server, "active_mail_provider_source", lambda: "environment")
    monkeypatch.setattr(
        server,
        "active_mail_public_status",
        lambda: {
            "connected": False,
            "has_client_config": False,
            "email_address": "",
            "last_sync_error": "",
            "last_synced_at": 0,
        },
    )

    html = server.render_mail_sync_settings(request()).body.decode("utf-8")

    assert 'hx-post="/ui/settings/mail-provider"' in html
    assert 'class="mail-provider-options" role="group" aria-label="메일 provider" data-sliding-tabs' in html
    assert 'class="mail-provider-option-pill" data-sliding-tabs-pill aria-hidden="true"' in html
    assert '{"provider":"gmail"}' in html
    assert '{"provider":"naver"}' in html
    assert '{"provider":"hiworks"}' in html
    assert "<small>" not in html
    assert ">API<" not in html
    assert ">IMAP<" not in html
    assert ">POP3<" not in html
    assert "환경 설정 기준" in html


def test_mail_provider_settings_post_switches_runtime_provider(monkeypatch):
    env_values: dict[str, str] = {}
    monkeypatch.setattr(server, "_mail_provider_override", None)
    monkeypatch.setattr(server, "_persist_env_values", lambda path, values: env_values.update(values))
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
            "message_count": 0,
        },
    )

    response = asyncio.run(
        server.ui_settings_mail_provider(
            request_with_body("POST", "/ui/settings/mail-provider", body=b"provider=naver")
        )
    )
    html = response.body.decode("utf-8")

    assert server.active_mail_provider() == "naver"
    assert env_values == {"CORAMAIL_MAIL_PROVIDER": "naver"}
    assert "Naver Mail을 기본 연동으로 저장했습니다." in html
    assert "환경 설정 기준" in html


def test_initial_provider_setup_state_opens_mail_settings_modal(monkeypatch):
    monkeypatch.setenv("CORAMAIL_MAIL_PROVIDER", "setup")
    html = server.templates.get_template("shell.html").render(
        **server.ui_globals(),
        request=request(),
        active_view="dashboard",
        initial_view_template="views/dashboard.html",
        summary={
            "email_count": 0,
            "today_email_count": 0,
            "classified_count": 0,
            "routed_count": 0,
            "attachment_count": 0,
            "mail_categories": {},
            "business_labels": {},
        },
        emails=[],
        mail_rows_mode="dashboard",
        category_timeline={"labels": [], "datasets": {}},
        routing_overview={
            "total": 0,
            "loaded_count": 0,
            "loaded_percent": 0,
            "unassigned_count": 0,
            "unassigned_percent": 0,
            "assignee_labels": [],
            "assignee_counts": [],
            "palette": [],
        },
    )

    assert "초기 메일 연동 설정" in html
    assert "통합 베타에서 사용할 provider를 선택하세요" in html
    assert "openGmailSettingsModal();" in html


def test_initial_provider_setup_state_does_not_probe_gmail(monkeypatch):
    monkeypatch.setenv("CORAMAIL_MAIL_PROVIDER", "setup")
    monkeypatch.setattr(server, "demo_mode_enabled", lambda: False)
    monkeypatch.setattr(
        server,
        "_gmail_service",
        SimpleNamespace(list_emails=lambda **kwargs: (_ for _ in ()).throw(AssertionError("gmail probed"))),
    )

    assert server.mail_rows() == []

    status = server.active_mail_status()
    assert status["last_error"] == ""
    assert status["version"] == "gmail:setup"


def test_display_mode_cookie_selects_naver_provider():
    response = server.ui_display_mode_toggle(request("POST"), display_mode="naver")

    assert response.status_code == 204
    assert "coramail_display_mode=naver" in response.headers["set-cookie"]

    cookie_request = request_with_body("GET", "/", headers=[(b"cookie", b"coramail_display_mode=naver")])

    assert server.request_display_mode(cookie_request) == "naver"
    assert server.request_mail_provider(cookie_request) == "naver"


def test_display_mode_cookie_selects_hiworks_provider():
    cookie_request = request_with_body("GET", "/", headers=[(b"cookie", b"coramail_display_mode=hiworks")])

    assert server.request_display_mode(cookie_request) == "hiworks"
    assert server.request_mail_provider(cookie_request) == "hiworks"


def test_naver_public_status_uses_persisted_success_after_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("CORAMAIL_NAVER_MAIL_ADDRESS", "naver@example.com")
    monkeypatch.setenv("CORAMAIL_NAVER_IMAP_USERNAME", "naver")
    monkeypatch.setenv("CORAMAIL_NAVER_APP_PASSWORD", "app-password")
    service = NaverMailboxService(
        tmp_path,
        sync_repository=SimpleNamespace(
            account_status=lambda: {
                "email_address": "naver@example.com",
                "status": "active",
                "last_synced_at": "2026-09-11T05:00:00+00:00",
                "last_error": "",
                "message_count": 1000,
            }
        ),
    )

    status = service.public_status()

    assert status["connected"] is True
    assert status["status"] == "active"
    assert status["message_count"] == 1000

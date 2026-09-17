from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.ui.mail_display import build_mail_display_ui_router, render_email_detail, render_mail_rows


class TemplatesStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def TemplateResponse(self, request: Request, template_name: str, context: dict[str, object]):  # noqa: N802
        self.calls.append((template_name, context))
        return SimpleNamespace(template_name=template_name, context=context, headers={})


def _request(method: str = "GET") -> Request:
    return Request({"type": "http", "method": method, "path": "/", "headers": []})


def _router(templates: TemplatesStub | None = None):
    templates = templates or TemplatesStub()
    return build_mail_display_ui_router(
        parse_form=lambda _body: {},
        mail_rows=lambda **_kwargs: [],
        dashboard_rows=lambda _request, rows: rows,
        visible_rows=lambda _request, rows: rows,
        status_matches=lambda _row, _status: True,
        dashboard_reference_date=lambda _rows: date(2026, 8, 31),
        ui_globals=lambda *_args: {},
        templates=templates,
        email_detail=lambda _ref: {"email_uid": "mail-1"},
        ensure_can_view=lambda *_args: None,
        mark_mail_read=lambda *_args: None,
        related_emails=lambda _email: [],
    )


def test_mail_display_router_registers_expected_paths() -> None:
    router = _router()
    paths = {(route.path, method) for route in router.routes for method in route.methods}
    assert ("/ui/mail-rows", "GET") in paths
    assert ("/ui/mail-rows", "POST") in paths
    assert ("/ui/emails/{email_ref}", "GET") in paths
    assert ("/ui/emails/{email_ref}", "POST") in paths


def test_render_mail_rows_preserves_dashboard_mode_and_selection() -> None:
    templates = TemplatesStub()
    rows = [{"email_uid": "mail-1"}]
    render_mail_rows(
        _request(),
        q="rfq",
        category="문의",
        limit=5,
        view="dashboard",
        status="review_required",
        selected_email_index=2,
        selected_email_uid="mail-1",
        mail_rows=lambda **_kwargs: rows,
        dashboard_rows=lambda _request, values: values,
        visible_rows=lambda _request, values: values,
        status_matches=lambda _row, _status: True,
        dashboard_reference_date=lambda _rows: date(2026, 8, 31),
        ui_globals=lambda *_args: {"asset_version": "v1"},
        templates=templates,
    )
    template_name, context = templates.calls[-1]
    assert template_name == "partials/mail_rows.html"
    assert context["mail_rows_mode"] == "dashboard"
    assert context["dashboard_reference_day"] == "2026-08-31"
    assert context["selected_email_index"] == 2
    assert context["selected_email_uid"] == "mail-1"


def test_render_mail_rows_filters_inbox_rows_by_visibility() -> None:
    templates = TemplatesStub()
    rows = [
        {"email_uid": "mail-1", "subject": "Hidden"},
        {"email_uid": "mail-2", "subject": "Visible"},
    ]
    render_mail_rows(
        _request(),
        q="",
        category="",
        limit=None,
        view="inbox",
        status="",
        selected_email_index=None,
        selected_email_uid="",
        mail_rows=lambda **_kwargs: rows,
        dashboard_rows=lambda _request, values: values,
        visible_rows=lambda _request, values: [row for row in values if row["email_uid"] == "mail-2"],
        status_matches=lambda _row, _status: True,
        dashboard_reference_date=lambda _rows: date(2026, 8, 31),
        ui_globals=lambda *_args: {},
        templates=templates,
    )

    assert templates.calls[-1][1]["emails"] == [rows[1]]


def test_render_email_detail_maps_missing_email_to_404() -> None:
    with pytest.raises(HTTPException) as exc_info:
        render_email_detail(
            _request(),
            "missing",
            email_detail=lambda _ref: None,
            ensure_can_view=lambda *_args: None,
            mark_mail_read=lambda *_args: None,
            ui_globals=lambda *_args: {},
            related_emails=lambda _email: [],
            templates=TemplatesStub(),
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "이메일을 찾을 수 없습니다."


def test_render_email_detail_emits_read_state_trigger() -> None:
    templates = TemplatesStub()
    email = {"email_uid": "mail-1"}
    response = render_email_detail(
        _request(),
        "mail-1",
        email_detail=lambda _ref: email,
        ensure_can_view=lambda *_args: None,
        mark_mail_read=lambda *_args: {"was_unread": True},
        ui_globals=lambda *_args: {},
        related_emails=lambda _email: [],
        templates=templates,
    )
    assert templates.calls[-1][0] == "partials/email_detail.html"
    assert "mail-read-state-changed" in response.headers["HX-Trigger"]


def test_render_email_detail_skips_second_detail_lookup_when_read_state_does_not_change() -> None:
    templates = TemplatesStub()
    email = {"email_uid": "mail-1", "work_status": "acknowledged"}
    calls = []

    response = render_email_detail(
        _request(),
        "mail-1",
        email_detail=lambda _ref: calls.append(_ref) or email,
        ensure_can_view=lambda *_args: None,
        mark_mail_read=lambda *_args: {"was_unread": False},
        ui_globals=lambda *_args: {},
        related_emails=lambda _email: [],
        templates=templates,
    )

    assert calls == ["mail-1"]
    assert response.headers == {}


def test_render_email_detail_refreshes_detail_when_work_status_changes() -> None:
    templates = TemplatesStub()
    calls = []

    def email_detail(_ref):
        calls.append(_ref)
        if len(calls) == 1:
            return {"email_uid": "mail-1", "work_status": "assigned"}
        return {"email_uid": "mail-1", "work_status": "acknowledged"}

    response = render_email_detail(
        _request(),
        "mail-1",
        email_detail=email_detail,
        ensure_can_view=lambda *_args: None,
        mark_mail_read=lambda *_args: {"was_unread": True, "work_status_changed": True, "work_status": "acknowledged"},
        ui_globals=lambda *_args: {},
        related_emails=lambda _email: [],
        templates=templates,
    )

    assert calls == ["mail-1", "mail-1"]
    assert templates.calls[-1][1]["email"]["work_status"] == "acknowledged"
    assert "work-item-status-changed" in response.headers["HX-Trigger"]

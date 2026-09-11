from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.ui.monitoring import build_monitoring_ui_router


class TemplatesStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def TemplateResponse(self, request: Request, template_name: str, context: dict[str, object]):  # noqa: N802
        self.calls.append((template_name, context))
        return SimpleNamespace(template_name=template_name, context=context)


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


def test_monitoring_router_registers_expected_paths() -> None:
    router = build_monitoring_ui_router(
        ops_console_context=lambda *_args, **_kwargs: {},
        render_view=lambda *_args, **_kwargs: SimpleNamespace(),
        templates=TemplatesStub(),
        email_detail=lambda _ref: {},
        ensure_can_view=lambda *_args: None,
        ui_globals=lambda *_args: {},
        related_emails=lambda _email: [],
    )
    paths = {(route.path, method) for route in router.routes for method in route.methods}
    assert ("/ui/monitoring", "GET") in paths
    assert ("/ui/monitoring", "POST") in paths
    assert ("/ui/ops", "GET") in paths
    assert ("/ui/monitoring-rows", "GET") in paths
    assert ("/ui/ops-rows", "GET") in paths
    assert ("/ui/monitoring/emails/{email_ref}", "GET") in paths


def test_monitoring_inspector_maps_missing_email_to_404() -> None:
    router = build_monitoring_ui_router(
        ops_console_context=lambda *_args, **_kwargs: {},
        render_view=lambda *_args, **_kwargs: SimpleNamespace(),
        templates=TemplatesStub(),
        email_detail=lambda _ref: None,
        ensure_can_view=lambda *_args: None,
        ui_globals=lambda *_args: {},
        related_emails=lambda _email: [],
    )
    endpoint = next(route.endpoint for route in router.routes if route.path == "/ui/monitoring/emails/{email_ref}")
    with pytest.raises(HTTPException) as exc_info:
        endpoint(_request(), "missing")
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "이메일을 찾을 수 없습니다."


def test_monitoring_inspector_preserves_template_context() -> None:
    templates = TemplatesStub()
    email = {"email_uid": "mail-1"}
    router = build_monitoring_ui_router(
        ops_console_context=lambda *_args, **_kwargs: {},
        render_view=lambda *_args, **_kwargs: SimpleNamespace(),
        templates=templates,
        email_detail=lambda _ref: email,
        ensure_can_view=lambda *_args: None,
        ui_globals=lambda *_args: {"asset_version": "v1"},
        related_emails=lambda _email: [{"email_uid": "mail-2"}],
    )
    endpoint = next(route.endpoint for route in router.routes if route.path == "/ui/monitoring/emails/{email_ref}")
    endpoint(_request(), "mail-1")
    template_name, context = templates.calls[-1]
    assert template_name == "partials/ops_email_inspector.html"
    assert context["email"] == email
    assert context["related_emails"] == [{"email_uid": "mail-2"}]
    assert context["classify_regenerate_state"] == "ready"

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.ui.inbox import build_inbox_ui_router


def request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/ui/inbox", "headers": [], "query_string": b""})


def test_inbox_ui_router_registers_get_and_post() -> None:
    router = build_inbox_ui_router(
        mail_rows=lambda **_: [],
        status_matches=lambda row, status: True,
        resolve_selected_index=lambda rows, index, uid: None,
        visible_rows=lambda _request, rows: rows,
        inbox_context=lambda *args, **kwargs: {},
        render_view=lambda *args, **kwargs: HTMLResponse("ok"),
    )
    paths = {(route.path, method) for route in router.routes for method in route.methods}
    assert ("/ui/inbox", "GET") in paths
    assert ("/ui/inbox", "POST") in paths


def test_inbox_ui_router_preserves_selection_and_filters() -> None:
    captured: dict[str, object] = {}
    rows = [
        {"email_uid": "mail-1", "work_status": "assigned"},
        {"email_uid": "mail-2", "work_status": "completed"},
    ]

    def inbox_context(request: Request, **kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"emails": rows}

    def render_view(request: Request, template_name: str, context: dict[str, object], *, active_view: str) -> HTMLResponse:
        captured["template_name"] = template_name
        captured["active_view"] = active_view
        return HTMLResponse("ok")

    router = build_inbox_ui_router(
        mail_rows=lambda **_: rows,
        status_matches=lambda row, status: row.get("work_status") == status,
        resolve_selected_index=lambda filtered, index, uid: 0 if filtered else None,
        visible_rows=lambda _request, filtered: filtered,
        inbox_context=inbox_context,
        render_view=render_view,
    )
    route = next(route for route in router.routes if route.path == "/ui/inbox" and "GET" in route.methods)
    response = route.endpoint(request(), email_uid="mail-2", status="completed")
    assert response.body == b"ok"
    assert captured["selected_index"] == 0
    assert captured["selected_email_uid"] == "mail-2"
    assert captured["status"] == "completed"
    assert captured["template_name"] == "views/inbox.html"
    assert captured["active_view"] == "inbox"


def test_inbox_ui_router_applies_visibility_before_selection() -> None:
    captured: dict[str, object] = {}
    rows = [
        {"email_uid": "mail-1", "work_status": "assigned", "assignee_email": "other@example.com"},
        {"email_uid": "mail-2", "work_status": "assigned", "assignee_email": "me@example.com"},
    ]

    def visible_rows(_request: Request, source_rows: list[dict[str, object]]) -> list[dict[str, object]]:
        return [row for row in source_rows if row.get("assignee_email") == "me@example.com"]

    def inbox_context(request: Request, **kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"emails": [rows[1]]}

    router = build_inbox_ui_router(
        mail_rows=lambda **_: rows,
        status_matches=lambda row, status: row.get("work_status") == status,
        resolve_selected_index=lambda filtered, index, uid: 0 if filtered else None,
        visible_rows=visible_rows,
        inbox_context=inbox_context,
        render_view=lambda *args, **kwargs: HTMLResponse("ok"),
    )
    route = next(route for route in router.routes if route.path == "/ui/inbox" and "GET" in route.methods)
    route.endpoint(request(), email_uid="mail-1", status="assigned")

    assert captured["selected_email_uid"] == "mail-2"

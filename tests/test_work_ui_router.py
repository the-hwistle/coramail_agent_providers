from fastapi import Request
from fastapi.responses import HTMLResponse

from app.ui.work import build_work_ui_router


def request(path: str) -> Request:
    return Request({"type": "http", "method": "GET", "path": path, "headers": [], "query_string": b""})


def test_work_ui_router_registers_assignees_and_my_work() -> None:
    router = build_work_ui_router(
        assignee_work_context=lambda *args, **kwargs: {},
        render_view=lambda *args, **kwargs: HTMLResponse("ok"),
    )
    paths = {(route.path, method) for route in router.routes for method in route.methods}
    assert ("/ui/assignees", "GET") in paths
    assert ("/ui/assignees", "POST") in paths
    assert ("/ui/my-work", "GET") in paths
    assert ("/ui/my-work", "POST") in paths


def test_my_work_preserves_view_specific_context() -> None:
    captured: dict[str, object] = {}

    def context(request: Request, **kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"rows": []}

    def render_view(request: Request, template_name: str, context: dict[str, object], *, active_view: str) -> HTMLResponse:
        captured["template_name"] = template_name
        captured["active_view"] = active_view
        return HTMLResponse("ok")

    router = build_work_ui_router(assignee_work_context=context, render_view=render_view)
    route = next(route for route in router.routes if route.path == "/ui/my-work" and "GET" in route.methods)
    response = route.endpoint(request("/ui/my-work"), assignee="owner", status="assigned", selected_email_uid="mail-1")
    assert response.body == b"ok"
    assert captured["assignee"] == "owner"
    assert captured["status"] == "assigned"
    assert captured["selected_email_uid"] == "mail-1"
    assert captured["work_view_name"] == "my-work"
    assert captured["work_endpoint"] == "/ui/my-work"
    assert captured["work_title"] == "My Work"
    assert captured["template_name"] == "views/assignee_work.html"
    assert captured["active_view"] == "my-work"

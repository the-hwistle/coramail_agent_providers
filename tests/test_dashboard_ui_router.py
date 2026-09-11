from fastapi import Request
from fastapi.responses import HTMLResponse

from app.ui.dashboard import build_dashboard_ui_router


def request(path: str = "/ui/dashboard") -> Request:
    return Request({"type": "http", "method": "GET", "path": path, "headers": [], "query_string": b""})


class FakeTemplates:
    def TemplateResponse(self, request: Request, name: str, context: dict[str, object]) -> HTMLResponse:
        return HTMLResponse(name)


def test_dashboard_ui_router_registers_expected_paths() -> None:
    router = build_dashboard_ui_router(
        render_view=lambda *args, **kwargs: HTMLResponse("dashboard"),
        dashboard_context=lambda *args, **kwargs: {},
        templates=FakeTemplates(),
    )
    paths = {(route.path, method) for route in router.routes for method in route.methods}
    assert ("/ui/dashboard", "GET") in paths
    assert ("/ui/dashboard", "POST") in paths
    assert ("/ui/stats", "GET") in paths
    assert ("/ui/dashboard-distribution", "GET") in paths
    assert ("/ui/dashboard-category-timeline", "GET") in paths
    assert ("/ui/dashboard-routing-overview", "GET") in paths


def test_dashboard_routing_overview_preserves_work_scope_template() -> None:
    router = build_dashboard_ui_router(
        render_view=lambda *args, **kwargs: HTMLResponse("dashboard"),
        dashboard_context=lambda *args, **kwargs: {"dashboard_work_scope": True},
        templates=FakeTemplates(),
    )
    route = next(route for route in router.routes if route.path == "/ui/dashboard-routing-overview")
    response = route.endpoint(request("/ui/dashboard-routing-overview"))
    assert response.body.decode() == "partials/dashboard_my_work_aging.html"


def test_dashboard_route_delegates_to_render_view() -> None:
    calls: list[tuple[str, str]] = []

    def render_view(request: Request, template_name: str, context: dict[str, object], *, active_view: str) -> HTMLResponse:
        calls.append((template_name, active_view))
        return HTMLResponse("ok")

    router = build_dashboard_ui_router(
        render_view=render_view,
        dashboard_context=lambda *args, **kwargs: {"summary": "ok"},
        templates=FakeTemplates(),
    )
    route = next(route for route in router.routes if route.path == "/ui/dashboard" and "GET" in route.methods)
    response = route.endpoint(request())
    assert response.body == b"ok"
    assert calls == [("views/dashboard.html", "dashboard")]

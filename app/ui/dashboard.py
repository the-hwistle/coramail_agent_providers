from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse


DashboardContext = Callable[..., dict[str, object]]
RenderView = Callable[..., HTMLResponse]


class Templates(Protocol):
    def TemplateResponse(
        self,
        request: Request,
        name: str,
        context: dict[str, object],
    ) -> HTMLResponse: ...


def build_dashboard_ui_router(
    *,
    render_view: RenderView,
    dashboard_context: DashboardContext,
    templates: Templates,
) -> APIRouter:
    router = APIRouter()

    @router.post("/ui/dashboard", response_class=HTMLResponse)
    @router.get("/ui/dashboard", response_class=HTMLResponse)
    def dashboard(request: Request, status: str = "") -> HTMLResponse:
        return render_view(
            request,
            "views/dashboard.html",
            {**dashboard_context(request, status=status), "request": request},
            active_view="dashboard",
        )

    @router.get("/ui/stats", response_class=HTMLResponse)
    def stats(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "partials/stats.html",
            {**dashboard_context(request), "request": request},
        )

    @router.get("/ui/dashboard-distribution", response_class=HTMLResponse)
    def distribution(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "partials/dashboard_distribution.html",
            {**dashboard_context(request), "request": request},
        )

    @router.get("/ui/dashboard-category-timeline", response_class=HTMLResponse)
    def category_timeline(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "partials/dashboard_category_timeline.html",
            {**dashboard_context(request), "request": request},
        )

    @router.get("/ui/dashboard-routing-overview", response_class=HTMLResponse)
    def routing_overview(request: Request) -> HTMLResponse:
        context = dashboard_context(request)
        template_name = (
            "partials/dashboard_my_work_aging.html"
            if context.get("dashboard_work_scope")
            else "partials/dashboard_routing_overview.html"
        )
        return templates.TemplateResponse(
            request,
            template_name,
            {**context, "request": request},
        )

    return router

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse


OpsConsoleContext = Callable[..., dict[str, object]]
RenderView = Callable[..., HTMLResponse]
EmailDetail = Callable[[str], dict[str, object] | None]
EnsureCanView = Callable[[Request | None, dict[str, object]], None]
UiGlobals = Callable[[Request | None], dict[str, object]]
RelatedEmails = Callable[[dict[str, object]], list[dict[str, object]]]


def render_monitoring(
    request: Request,
    *,
    q: str = "",
    category: str = "",
    status: str = "",
    ops_console_context: OpsConsoleContext,
    render_view: RenderView,
) -> HTMLResponse:
    return render_view(
        request,
        "views/ops.html",
        {**ops_console_context(request, q=q, category=category, status=status), "request": request},
        active_view="monitoring",
    )


def render_monitoring_rows(
    request: Request,
    *,
    q: str = "",
    category: str = "",
    status: str = "",
    ops_console_context: OpsConsoleContext,
    templates: Any,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "partials/ops_rows.html",
        {**ops_console_context(request, q=q, category=category, status=status), "request": request},
    )


def render_monitoring_email_inspector(
    request: Request,
    email_ref: str,
    *,
    templates: Any,
    email_detail: EmailDetail,
    ensure_can_view: EnsureCanView,
    ui_globals: UiGlobals,
    related_emails: RelatedEmails,
) -> HTMLResponse:
    email = email_detail(email_ref)
    if email is None:
        raise HTTPException(status_code=404, detail="이메일을 찾을 수 없습니다.")
    ensure_can_view(request, email)
    return templates.TemplateResponse(
        request,
        "partials/ops_email_inspector.html",
        {
            **ui_globals(request),
            "email": email,
            "related_emails": related_emails(email),
            "customer_history": [],
            "classify_regenerate_state": "ready",
            "classification_regeneration": {},
            "summary_regenerate_state": "ready",
            "summary_regeneration": {},
            "attachment_reanalysis": {},
        },
    )


def build_monitoring_ui_router(
    *,
    ops_console_context: OpsConsoleContext,
    render_view: RenderView,
    templates: Any,
    email_detail: EmailDetail,
    ensure_can_view: EnsureCanView,
    ui_globals: UiGlobals,
    related_emails: RelatedEmails,
) -> APIRouter:
    router = APIRouter()

    @router.post("/ui/monitoring", response_class=HTMLResponse)
    @router.get("/ui/monitoring", response_class=HTMLResponse)
    def monitoring(
        request: Request,
        q: str = "",
        category: str = "",
        status: str = "",
    ) -> HTMLResponse:
        return render_monitoring(
            request,
            q=q,
            category=category,
            status=status,
            ops_console_context=ops_console_context,
            render_view=render_view,
        )

    @router.get("/ui/ops", response_class=HTMLResponse)
    def ops(request: Request, q: str = "", category: str = "") -> HTMLResponse:
        return render_monitoring(
            request,
            q=q,
            category=category,
            ops_console_context=ops_console_context,
            render_view=render_view,
        )

    @router.get("/ui/monitoring-rows", response_class=HTMLResponse)
    def monitoring_rows(
        request: Request,
        q: str = "",
        category: str = "",
        status: str = "",
    ) -> HTMLResponse:
        return render_monitoring_rows(
            request,
            q=q,
            category=category,
            status=status,
            ops_console_context=ops_console_context,
            templates=templates,
        )

    @router.get("/ui/ops-rows", response_class=HTMLResponse)
    def ops_rows(request: Request, q: str = "", category: str = "") -> HTMLResponse:
        return render_monitoring_rows(
            request,
            q=q,
            category=category,
            ops_console_context=ops_console_context,
            templates=templates,
        )

    @router.get("/ui/monitoring/emails/{email_ref}", response_class=HTMLResponse)
    def monitoring_email_inspector(request: Request, email_ref: str) -> HTMLResponse:
        return render_monitoring_email_inspector(
            request,
            email_ref,
            templates=templates,
            email_detail=email_detail,
            ensure_can_view=ensure_can_view,
            ui_globals=ui_globals,
            related_emails=related_emails,
        )

    return router

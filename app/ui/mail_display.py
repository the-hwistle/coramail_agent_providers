from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from typing import Any, Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse


FormParser = Callable[[bytes], dict[str, str]]
MailRows = Callable[..., list[dict[str, Any]]]
DashboardRows = Callable[[Request, list[dict[str, Any]]], list[dict[str, Any]]]
StatusMatches = Callable[[dict[str, object], str], bool]
VisibleRows = Callable[[Request | None, list[dict[str, object]]], list[dict[str, object]]]
UiGlobals = Callable[[Request | None], dict[str, object]]
DashboardReferenceDate = Callable[[list[dict[str, Any]]], date]
EmailDetail = Callable[[str], dict[str, object] | None]
EnsureCanView = Callable[[Request | None, dict[str, object]], None]
MarkMailRead = Callable[[Request, dict[str, object]], dict[str, object] | None]
RelatedEmails = Callable[[dict[str, object]], list[dict[str, object]]]


def render_mail_rows(
    request: Request,
    *,
    q: str,
    category: str,
    limit: int | None,
    view: str,
    status: str,
    selected_email_index: int | None,
    selected_email_uid: str,
    mail_rows: MailRows,
    dashboard_rows: DashboardRows,
    visible_rows: VisibleRows,
    status_matches: StatusMatches,
    dashboard_reference_date: DashboardReferenceDate,
    ui_globals: UiGlobals,
    templates: Any,
) -> HTMLResponse:
    rows = mail_rows(q=q, category=category, limit=limit)
    if view == "dashboard":
        rows = dashboard_rows(request, rows)
    elif view == "inbox":
        rows = visible_rows(request, rows)
    rows = [row for row in rows if status_matches(row, status.strip())]
    return templates.TemplateResponse(
        request,
        "partials/mail_rows.html",
        {
            **ui_globals(request),
            "emails": rows,
            "mail_rows_mode": "dashboard" if view == "dashboard" else "inbox",
            "dashboard_reference_day": dashboard_reference_date(rows).isoformat(),
            "selected_email_index": selected_email_index,
            "selected_email_uid": selected_email_uid,
        },
    )


def render_email_detail(
    request: Request,
    email_ref: str,
    *,
    template_name: str = "partials/email_detail.html",
    email_detail: EmailDetail,
    ensure_can_view: EnsureCanView,
    mark_mail_read: MarkMailRead,
    ui_globals: UiGlobals,
    related_emails: RelatedEmails,
    templates: Any,
) -> HTMLResponse:
    email = email_detail(email_ref)
    if email is None:
        raise HTTPException(status_code=404, detail="이메일을 찾을 수 없습니다.")
    ensure_can_view(request, email)
    read_result = mark_mail_read(request, email)
    if read_result and (read_result.get("was_unread") or read_result.get("work_status_changed")):
        email = email_detail(email_ref) or email
    response = templates.TemplateResponse(
        request,
        template_name,
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
    if read_result:
        email_uid = str(email.get("email_uid") or email_ref)
        triggers: dict[str, object] = {}
        if read_result.get("was_unread"):
            triggers["mail-read-state-changed"] = {"email_uid": email_uid}
        if read_result.get("work_status_changed"):
            triggers["work-item-status-changed"] = {
                "email_uid": email_uid,
                "work_status": str(read_result.get("work_status") or ""),
            }
        if triggers:
            response.headers["HX-Trigger"] = json.dumps(triggers, ensure_ascii=True)
    return response


def build_mail_display_ui_router(
    *,
    parse_form: FormParser,
    mail_rows: MailRows,
    dashboard_rows: DashboardRows,
    visible_rows: VisibleRows,
    status_matches: StatusMatches,
    dashboard_reference_date: DashboardReferenceDate,
    ui_globals: UiGlobals,
    templates: Any,
    email_detail: EmailDetail,
    ensure_can_view: EnsureCanView,
    mark_mail_read: MarkMailRead,
    related_emails: RelatedEmails,
) -> APIRouter:
    router = APIRouter()

    @router.post("/ui/mail-rows", response_class=HTMLResponse)
    @router.get("/ui/mail-rows", response_class=HTMLResponse)
    async def mail_rows_view(
        request: Request,
        q: str = "",
        category: str = "",
        limit: Annotated[int | None, Query(ge=1)] = None,
        view: str = "inbox",
        dashboard_mail_filter: str = "",
        status: str = "",
        selected_email_index: int | None = None,
        selected_email_uid: str = "",
    ) -> HTMLResponse:
        del dashboard_mail_filter
        if request.method == "POST":
            form = parse_form(await request.body())
            q = form.get("q", q)
            category = form.get("category", category)
            view = form.get("view", view)
            status = form.get("status", status)
            selected_email_uid = form.get("selected_email_uid", selected_email_uid)
            selected_index_value = form.get("selected_email_index", "")
            if selected_index_value:
                try:
                    selected_email_index = int(selected_index_value)
                except ValueError:
                    selected_email_index = None
            limit_value = form.get("limit", "")
            if limit_value:
                try:
                    limit = max(1, int(limit_value))
                except ValueError:
                    limit = None
        return render_mail_rows(
            request,
            q=q,
            category=category,
            limit=limit,
            view=view,
            status=status,
            selected_email_index=selected_email_index,
            selected_email_uid=selected_email_uid,
            mail_rows=mail_rows,
            dashboard_rows=dashboard_rows,
            visible_rows=visible_rows,
            status_matches=status_matches,
            dashboard_reference_date=dashboard_reference_date,
            ui_globals=ui_globals,
            templates=templates,
        )

    @router.post("/ui/emails/{email_ref}", response_class=HTMLResponse)
    @router.get("/ui/emails/{email_ref}", response_class=HTMLResponse)
    def email_detail_view(request: Request, email_ref: str) -> HTMLResponse:
        return render_email_detail(
            request,
            email_ref,
            email_detail=email_detail,
            ensure_can_view=ensure_can_view,
            mark_mail_read=mark_mail_read,
            ui_globals=ui_globals,
            related_emails=related_emails,
            templates=templates,
        )

    return router

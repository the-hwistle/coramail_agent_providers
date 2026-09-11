from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse


MailRows = Callable[..., list[dict[str, Any]]]
StatusMatches = Callable[[dict[str, object], str], bool]
ResolveSelectedIndex = Callable[[list[dict[str, object]], int, str], int | None]
VisibleRows = Callable[[Request | None, list[dict[str, object]]], list[dict[str, object]]]
InboxContext = Callable[..., dict[str, object]]
RenderView = Callable[..., HTMLResponse]


def render_inbox(
    request: Request,
    *,
    mail_rows: MailRows,
    status_matches: StatusMatches,
    resolve_selected_index: ResolveSelectedIndex,
    visible_rows: VisibleRows,
    inbox_context: InboxContext,
    render_view: RenderView,
    email_index: int = 0,
    email_uid: str = "",
    q: str = "",
    category: str = "",
    status: str = "",
) -> HTMLResponse:
    rows = [
        row
        for row in mail_rows(q=q, category=category)
        if status_matches(row, status.strip())
    ]
    rows = visible_rows(request, rows)
    selected_index = resolve_selected_index(rows, email_index, email_uid)
    context = {
        **inbox_context(
            request,
            selected_index=selected_index,
            selected_email_uid=rows[selected_index]["email_uid"] if selected_index is not None else "",
            q=q,
            category=category,
            status=status,
        ),
        "request": request,
    }
    return render_view(request, "views/inbox.html", context, active_view="inbox")


def build_inbox_ui_router(
    *,
    mail_rows: MailRows,
    status_matches: StatusMatches,
    resolve_selected_index: ResolveSelectedIndex,
    visible_rows: VisibleRows,
    inbox_context: InboxContext,
    render_view: RenderView,
) -> APIRouter:
    router = APIRouter()

    @router.post("/ui/inbox", response_class=HTMLResponse)
    @router.get("/ui/inbox", response_class=HTMLResponse)
    def inbox(
        request: Request,
        email_index: int = 0,
        email_uid: str = "",
        q: str = "",
        category: str = "",
        status: str = "",
    ) -> HTMLResponse:
        return render_inbox(
            request,
            mail_rows=mail_rows,
            status_matches=status_matches,
            resolve_selected_index=resolve_selected_index,
            visible_rows=visible_rows,
            inbox_context=inbox_context,
            render_view=render_view,
            email_index=email_index,
            email_uid=email_uid,
            q=q,
            category=category,
            status=status,
        )

    return router

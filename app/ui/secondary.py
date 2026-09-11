from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response


RenderView = Callable[..., HTMLResponse]
UiGlobals = Callable[[], dict[str, object]]
EmailDetail = Callable[[str], dict[str, object] | None]
EnsureCanView = Callable[[Request | None, dict[str, object]], None]
MarkMailRead = Callable[[Request, dict[str, object]], dict[str, object] | None]
RelatedEmails = Callable[[dict[str, object]], list[dict[str, object]]]


def render_evaluation(
    request: Request,
    report: str,
    *,
    render_view: RenderView,
    ui_globals: UiGlobals,
    dashboard_view: Callable[[str], dict[str, object]],
) -> HTMLResponse:
    return render_view(
        request,
        "views/evaluation.html",
        {**ui_globals(), "request": request, "evaluation": dashboard_view(report)},
        active_view="evaluation",
    )


def render_evaluation_case(
    request: Request,
    email_message_id: str,
    report: str,
    *,
    render_view: RenderView,
    ui_globals: UiGlobals,
    case_view: Callable[[str, str], dict[str, object]],
) -> HTMLResponse:
    view = case_view(email_message_id, report)
    if not view.get("available"):
        raise HTTPException(status_code=404, detail="평가 케이스를 찾을 수 없습니다.")
    return render_view(
        request,
        "views/evaluation_case.html",
        {**ui_globals(), "request": request, "evaluation_case": view},
        active_view="evaluation",
    )


def render_evaluation_trace(
    request: Request,
    email_message_id: str,
    report: str,
    *,
    ui_globals: UiGlobals,
    case_view: Callable[[str, str], dict[str, object]],
    templates: Any,
) -> HTMLResponse:
    view = case_view(email_message_id, report)
    if not view.get("available"):
        raise HTTPException(status_code=404, detail="평가 trace를 찾을 수 없습니다.")
    return templates.TemplateResponse(
        request,
        "partials/evaluation_trace.html",
        {**ui_globals(), "request": request, "evaluation_case": view},
    )


def render_search(
    request: Request,
    q: str,
    limit: int,
    *,
    render_view: RenderView,
    search_context: Callable[[str, int], dict[str, object]],
) -> HTMLResponse:
    return render_view(
        request,
        "views/search.html",
        {**search_context(q, limit), "request": request},
        active_view="search",
    )


def render_search_results(
    request: Request,
    q: str,
    limit: int,
    *,
    is_htmx_request: Callable[[Request], bool],
    request_demo_mode: Callable[[Request], bool],
    normalize_search_query: Callable[[str], str],
    mail_search_service: Callable[[], Any],
    ui_globals: UiGlobals,
    templates: Any,
    logger: Any,
) -> Response:
    if not is_htmx_request(request):
        location = "/ui/search" if request_demo_mode(request) else "/?view=search"
        normalized_for_redirect = normalize_search_query(q)
        if normalized_for_redirect:
            separator = "&" if "?" in location else "?"
            location = f"{location}{separator}q={quote(normalized_for_redirect)}&limit={limit}"
        return RedirectResponse(location, status_code=303)
    normalized_query = normalize_search_query(q)
    error = ""
    result = None
    if normalized_query:
        try:
            result = mail_search_service().search(normalized_query, limit=limit)
        except Exception as exc:  # noqa: BLE001
            logger.exception("mail search failed")
            error = f"검색 저장소를 조회하지 못했습니다: {exc}"
    return templates.TemplateResponse(
        request,
        "partials/search_results.html",
        {
            **ui_globals(),
            "request": request,
            "query": normalized_query,
            "limit": limit,
            "result": result,
            "error": error,
            "loading": False,
            "answer": str((result or {}).get("answer") or ""),
        },
    )


def render_chats(
    request: Request,
    q: str,
    limit: int,
    session_id: str,
    *,
    render_view: RenderView,
    chats_context: Callable[[str, int, str], dict[str, object]],
) -> HTMLResponse:
    return render_view(
        request,
        "views/chats.html",
        {**chats_context(q, limit, session_id), "request": request},
        active_view="chats",
    )


def render_chats_results(
    request: Request,
    q: str,
    limit: int,
    session_id: str,
    chat_history: list[dict[str, object]],
    *,
    is_htmx_request: Callable[[Request], bool],
    request_demo_mode: Callable[[Request], bool],
    normalize_search_query: Callable[[str], str],
    mail_chat_service: Any,
    mail_search_service: Callable[[], Any],
    ui_globals: UiGlobals,
    templates: Any,
) -> Response:
    if not is_htmx_request(request):
        location = "/ui/chats" if request_demo_mode(request) else "/?view=chats"
        safe_session_id = str(session_id or "").strip()
        if safe_session_id:
            separator = "&" if "?" in location else "?"
            location = f"{location}{separator}session_id={quote(safe_session_id)}"
        normalized_for_redirect = normalize_search_query(q)
        if normalized_for_redirect:
            separator = "&" if "?" in location else "?"
            location = f"{location}{separator}q={quote(normalized_for_redirect)}&limit={limit}"
        return RedirectResponse(location, status_code=303)
    normalized_query = normalize_search_query(q)
    chat_context = mail_chat_service.ask(
        session_id=session_id,
        query=normalized_query,
        search_service=mail_search_service(),
        limit=limit,
        compact_history=chat_history,
    )
    return templates.TemplateResponse(
        request,
        "partials/chats_results.html",
        {
            **ui_globals(),
            "request": request,
            "query": normalized_query,
            "limit": limit,
            "loading": False,
            **chat_context,
            "include_session_oob": True,
        },
    )


def render_chat_email_drawer(
    request: Request,
    email_ref: str,
    *,
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
    email = email_detail(email_ref) or email
    response = templates.TemplateResponse(
        request,
        "partials/chat_email_drawer.html",
        {
            **ui_globals(),
            "request": request,
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

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response


EmailDetail = Callable[[str], dict[str, object] | None]
EnsureCanView = Callable[[Request | None, dict[str, object]], None]
MarkMailRead = Callable[[Request, dict[str, object]], dict[str, object] | None]
UiGlobals = Callable[[Request | None], dict[str, object]]
RelatedEmails = Callable[[dict[str, object]], list[dict[str, object]]]
AuthenticatedUserId = Callable[[Request], UUID | None]
GmailThreadUrl = Callable[[str], str]


def render_my_work_email_drawer(
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
        "partials/assignee_email_drawer.html",
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


def toggle_work_in_progress(
    request: Request,
    email_ref: str,
    *,
    active: bool,
    email_detail: EmailDetail,
    authenticated_user_id: AuthenticatedUserId,
    work_tracking_repository: Any,
) -> Response:
    email = email_detail(email_ref)
    if email is None:
        raise HTTPException(status_code=404, detail="이메일을 찾을 수 없습니다.")
    actor_user_id = authenticated_user_id(request)
    if actor_user_id is None:
        raise HTTPException(status_code=403, detail="DB 사용자로 로그인한 담당자만 진행중 상태를 변경할 수 있습니다.")
    try:
        work_item = work_tracking_repository.set_in_progress(
            email_message_id=UUID(str(email.get("email_uid") or "")),
            actor_user_id=actor_user_id,
            active=active,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    response = Response(status_code=204)
    response.headers["HX-Trigger"] = json.dumps(
        {
            "work-item-status-changed": {
                "email_uid": email_ref,
                "work_status": str(work_item.get("status") or ""),
            }
        },
        ensure_ascii=True,
    )
    return response


def initiate_work_reply(
    request: Request,
    email_ref: str,
    *,
    email_detail: EmailDetail,
    authenticated_user_id: AuthenticatedUserId,
    work_tracking_repository: Any,
    gmail_thread_url: GmailThreadUrl,
) -> Response:
    email = email_detail(email_ref)
    if email is None:
        raise HTTPException(status_code=404, detail="이메일을 찾을 수 없습니다.")
    actor_user_id = authenticated_user_id(request)
    if actor_user_id is None:
        raise HTTPException(status_code=403, detail="DB 사용자로 로그인한 담당자만 회신 시작을 기록할 수 있습니다.")
    try:
        work_item = work_tracking_repository.initiate_reply(
            email_message_id=UUID(str(email.get("email_uid") or "")),
            actor_user_id=actor_user_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    gmail_url = gmail_thread_url(str(work_item.get("provider_thread_id") or ""))
    if request.headers.get("HX-Request", "").casefold() != "true":
        return RedirectResponse(gmail_url or "/ui/inbox", status_code=303)
    response = Response(status_code=204)
    response.headers["HX-Redirect"] = gmail_url or "/ui/inbox"
    return response


def complete_work_item(
    request: Request,
    email_ref: str,
    *,
    email_detail: EmailDetail,
    authenticated_user_id: AuthenticatedUserId,
    work_tracking_repository: Any,
) -> Response:
    email = email_detail(email_ref)
    if email is None:
        raise HTTPException(status_code=404, detail="이메일을 찾을 수 없습니다.")
    actor_user_id = authenticated_user_id(request)
    if actor_user_id is None:
        raise HTTPException(status_code=403, detail="DB 사용자로 로그인한 담당자만 업무를 완료할 수 있습니다.")
    try:
        work_tracking_repository.complete(
            email_message_id=UUID(str(email.get("email_uid") or "")),
            actor_user_id=actor_user_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    response = Response(status_code=204, headers={"HX-Refresh": "true"})
    response.headers["HX-Trigger"] = json.dumps(
        {"work-item-completed": {"email_uid": email_ref}}, ensure_ascii=True
    )
    return response

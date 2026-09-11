from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from app.services.mail_decision_runtime_client import MailDecisionRuntimeClientError


EmailDetail = Callable[[str], dict[str, object] | None]
RuntimeClientFactory = Callable[[Request], Any]
RenderPanel = Callable[..., HTMLResponse]
RuntimeUserMessage = Callable[[MailDecisionRuntimeClientError], str]


def create_mail_decision_run(
    request: Request,
    email_ref: str,
    *,
    email_detail: EmailDetail,
    runtime_client: RuntimeClientFactory,
    render_panel: RenderPanel,
    runtime_user_message: RuntimeUserMessage,
    logger: Any,
) -> HTMLResponse:
    email = email_detail(email_ref)
    if email is None:
        return render_panel(
            request,
            error="해당 메일을 찾을 수 없습니다.",
            error_title="Mail Decision 실행 불가",
            email_ref=email_ref,
        )
    try:
        client = runtime_client(request)
        run = client.create_run(str(email["email_uid"]))
        steps = client.get_steps(str(run["run_id"]))
    except MailDecisionRuntimeClientError as exc:
        logger.warning("Mail Decision UI create failed: %s: %s", type(exc).__name__, exc)
        return render_panel(request, error=runtime_user_message(exc), email_ref=email_ref)
    response = render_panel(request, run=run, steps=steps, email_ref=email_ref)
    response.headers["HX-Trigger"] = json.dumps(
        {"mail-decision-run-created": {"email_uid": str(email["email_uid"])}},
        ensure_ascii=True,
    )
    return response


def latest_mail_decision_run(
    request: Request,
    email_ref: str,
    *,
    email_detail: EmailDetail,
    runtime_client: RuntimeClientFactory,
    render_panel: RenderPanel,
    demo_mode_enabled: Callable[[], bool],
    database_url: Callable[[], str],
    demo_service: Callable[[], Any],
    logger: Any,
) -> HTMLResponse:
    email = email_detail(email_ref)
    if email is None:
        return render_panel(
            request,
            error="해당 메일을 찾을 수 없습니다.",
            error_title="Mail Decision 조회 불가",
            email_ref=email_ref,
        )
    service = demo_service()
    if demo_mode_enabled() and not database_url() and hasattr(service, "mail_decision_run_by_uid"):
        run = service.mail_decision_run_by_uid(str(email["email_uid"]))
        return render_panel(request, run=run, steps=[], email_ref=email_ref)
    try:
        client = runtime_client(request)
        run = client.get_latest_run_for_email(str(email["email_uid"]))
        steps: list[dict[str, object]] = []
        steps_error = ""
        if run is not None:
            try:
                steps = client.get_steps(str(run["run_id"]))
            except MailDecisionRuntimeClientError as exc:
                logger.warning("Mail Decision UI latest steps lookup failed: %s: %s", type(exc).__name__, exc)
                steps_error = "실행 단계를 불러올 수 없습니다."
    except MailDecisionRuntimeClientError as exc:
        logger.warning("Mail Decision UI latest lookup failed: %s: %s", type(exc).__name__, exc)
        return render_panel(
            request,
            error="Mail Decision 결과를 불러올 수 없습니다.",
            error_title="Mail Decision 조회 실패",
            email_ref=email_ref,
        )
    return render_panel(request, run=run, steps=steps, steps_error=steps_error, email_ref=email_ref)


def mail_decision_run(
    request: Request,
    run_id: str,
    *,
    runtime_client: RuntimeClientFactory,
    render_panel: RenderPanel,
    runtime_user_message: RuntimeUserMessage,
    logger: Any,
) -> HTMLResponse:
    try:
        client = runtime_client(request)
        run = client.get_run(run_id)
        steps = client.get_steps(run_id)
    except MailDecisionRuntimeClientError as exc:
        logger.warning("Mail Decision UI lookup failed: %s: %s", type(exc).__name__, exc)
        return render_panel(request, error=runtime_user_message(exc))
    return render_panel(request, run=run, steps=steps)


def mail_decision_steps(
    request: Request,
    run_id: str,
    *,
    runtime_client: RuntimeClientFactory,
    runtime_user_message: RuntimeUserMessage,
    steps_view: Callable[[list[dict[str, object]]], list[dict[str, object]]],
    templates: Any,
    logger: Any,
) -> HTMLResponse:
    try:
        steps = runtime_client(request).get_steps(run_id)
    except MailDecisionRuntimeClientError as exc:
        logger.warning("Mail Decision UI steps lookup failed: %s: %s", type(exc).__name__, exc)
        return templates.TemplateResponse(
            request,
            "partials/mail_decision_steps.html",
            {"steps": [], "error": runtime_user_message(exc), "request": request},
        )
    return templates.TemplateResponse(
        request,
        "partials/mail_decision_steps.html",
        {"steps": steps_view(steps), "request": request},
    )


async def manual_assign_review_email(
    request: Request,
    email_ref: str,
    *,
    parse_form: Callable[[bytes], dict[str, str]],
    latest_run_for_panel: Callable[[Request, str], dict[str, object] | None],
    manual_assign: Callable[..., dict[str, object]],
    auth_cookie_username: Callable[[str | None], str],
    auth_cookie_name: str,
    auth_username: str,
    render_panel: RenderPanel,
    email_detail: EmailDetail,
    logger: Any,
) -> HTMLResponse:
    form = parse_form(await request.body())
    assignee_user_id = str(form.get("assignee_user_id") or "").strip()
    if not assignee_user_id:
        return render_panel(
            request,
            run=latest_run_for_panel(request, email_ref),
            error="담당자를 선택하세요.",
            error_title="수동 배정 실패",
            email_ref=email_ref,
        )
    try:
        assignment = manual_assign(
            email_ref=email_ref,
            assignee_user_id=UUID(assignee_user_id),
            actor_label=auth_cookie_username(request.cookies.get(auth_cookie_name)) or auth_username,
        )
    except ValueError as exc:
        return render_panel(
            request,
            run=latest_run_for_panel(request, email_ref),
            error=str(exc),
            error_title="수동 배정 실패",
            email_ref=email_ref,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("manual review assignment failed")
        return render_panel(
            request,
            run=latest_run_for_panel(request, email_ref),
            error=f"담당자 배정을 저장하지 못했습니다: {exc}",
            error_title="수동 배정 실패",
            email_ref=email_ref,
        )
    email = email_detail(email_ref)
    response = render_panel(
        request,
        run=latest_run_for_panel(request, email_ref),
        email_ref=email_ref,
    )
    trigger = {
        "mail-manual-assignment-completed": {
            "email_index": email.get("index") if isinstance(email, dict) else None,
            "email_uid": email.get("email_uid") if isinstance(email, dict) else email_ref,
            "assignee_user_id": assignee_user_id,
            "assignee_name": assignment.get("assignee_name") or "",
        }
    }
    response.headers["HX-Trigger"] = json.dumps(trigger, ensure_ascii=True)
    return response


def confirm_top_review_candidate(
    request: Request,
    email_ref: str,
    *,
    manual_assign_top: Callable[..., dict[str, object]],
    auth_cookie_username: Callable[[str | None], str],
    auth_cookie_name: str,
    auth_username: str,
    email_detail: EmailDetail,
) -> Response:
    try:
        assignment = manual_assign_top(
            email_ref=email_ref,
            actor_label=auth_cookie_username(request.cookies.get(auth_cookie_name)) or auth_username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    email = email_detail(email_ref)
    trigger = {
        "mail-manual-assignment-completed": {
            "email_index": email.get("index") if isinstance(email, dict) else None,
            "email_uid": email.get("email_uid") if isinstance(email, dict) else email_ref,
            "assignee_user_id": str(assignment.get("assignee_user_id") or ""),
            "assignee_name": assignment.get("assignee_name") or "",
        }
    }
    return Response(status_code=204, headers={"HX-Trigger": json.dumps(trigger, ensure_ascii=True)})

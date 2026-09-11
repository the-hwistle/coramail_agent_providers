from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, quote
from uuid import UUID

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response


@dataclass(frozen=True)
class SettingsHandlers:
    render_view: Any
    settings_context: Any
    render_gmail_sync_settings: Any
    parse_form: Any
    gmail_account_repository: Any
    gmail_oauth_service: Any
    gmail_callback_redirect: Any
    gmail_service: Any
    active_mail_provider: Any
    active_provider_label: Any
    active_provider_service: Any
    active_mail_public_status: Any
    request_demo_mode: Any
    duplicate_latest_demo_mail: Any
    start_received_demo_mail_processing: Any
    display_mode_cookie_name: str
    gmail_oauth_state_cookie_name: str
    auth_cookie_secure: bool
    templates: Any
    render_auto_assignment_policy: Any
    demo_mode_enabled: Any
    logger: Any
    assignee_admin_repository: Any
    routing_table_response: Any
    routing_policy_settings_repository: Any

    def settings(self, request: Request) -> HTMLResponse:
        return self.render_view(
            request,
            "views/settings.html",
            {**self.settings_context(), "request": request},
            active_view="settings",
        )

    def gmail_sync_settings(self, request: Request) -> HTMLResponse:
        return self.render_gmail_sync_settings(request)

    async def save_gmail_client_config(self, request: Request) -> HTMLResponse:
        form = self.parse_form(await request.body())
        raw_config = str(form.get("client_config_json") or "").strip()
        if not raw_config:
            return self.render_gmail_sync_settings(request, error="Google OAuth client JSON을 입력하세요.")
        try:
            self.gmail_account_repository.save_client_config(raw_config)
        except json.JSONDecodeError:
            return self.render_gmail_sync_settings(request, error="Google OAuth client JSON 형식이 올바르지 않습니다.")
        except ValueError as exc:
            return self.render_gmail_sync_settings(request, error=str(exc))
        return self.render_gmail_sync_settings(request, message="Gmail OAuth client JSON을 저장했습니다.")

    async def save_gmail_tokens(self, request: Request) -> HTMLResponse:
        form = self.parse_form(await request.body())
        primary_token_json = str(form.get("primary_token_json") or "").strip()
        send_token_json = str(form.get("send_token_json") or "").strip()
        if not primary_token_json:
            return self.render_gmail_sync_settings(request, error="GOOGLE_TOKEN_JSON을 입력하세요.")
        try:
            self.gmail_account_repository.save_existing_tokens(
                primary_token_json=primary_token_json,
                send_token_json=send_token_json,
            )
        except ValueError as exc:
            return self.render_gmail_sync_settings(request, error=str(exc))
        return self.render_gmail_sync_settings(
            request,
            message="Gmail token을 저장했습니다. 이제 Gmail 모드에서 동기화를 실행할 수 있습니다.",
        )

    def gmail_connect(self, request: Request) -> RedirectResponse:
        try:
            redirect_uri = str(request.url_for("gmail_oauth_callback"))
            authorization_url, state = self.gmail_oauth_service.authorization_url(redirect_uri)
        except Exception as exc:  # noqa: BLE001
            response = RedirectResponse("/ui/settings", status_code=303)
            response.headers["X-CoRA-Gmail-Connect-Error"] = str(exc)
            return response
        response = RedirectResponse(authorization_url, status_code=303)
        response.set_cookie(
            self.gmail_oauth_state_cookie_name,
            state,
            max_age=10 * 60,
            httponly=True,
            samesite="lax",
        )
        return response

    def gmail_oauth_callback(self, request: Request, state: str = "", error: str = "") -> RedirectResponse:
        expected_state = str(request.cookies.get(self.gmail_oauth_state_cookie_name) or "")
        if error:
            return self.gmail_callback_redirect(error=f"Gmail OAuth가 취소되거나 실패했습니다: {error}")
        if not expected_state or state != expected_state:
            return self.gmail_callback_redirect(error="Gmail OAuth state가 일치하지 않습니다. 다시 연결하세요.")
        try:
            redirect_uri = str(request.url_for("gmail_oauth_callback"))
            self.gmail_oauth_service.complete_callback(
                redirect_uri=redirect_uri,
                authorization_response=str(request.url),
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("Gmail OAuth callback failed")
            self.gmail_account_repository.record_oauth_error(str(exc))
            return self.gmail_callback_redirect(error=str(exc))
        return self.gmail_callback_redirect(message="Gmail 계정이 연결되었습니다.", display_mode="gmail")

    def gmail_disconnect(self, request: Request) -> HTMLResponse:
        self.gmail_account_repository.disconnect()
        return self.render_gmail_sync_settings(request, message="Gmail 연결을 해제했습니다.")

    def gmail_sync(self, request: Request) -> HTMLResponse:
        result = self.gmail_service.sync()
        if result.get("status") == "ok":
            return self.render_gmail_sync_settings(
                request,
                message=f"{result.get('message_count', 0)}건을 동기화했습니다.",
            )
        return self.render_gmail_sync_settings(
            request,
            error=str(result.get("message") or "Gmail 동기화 실패"),
        )

    def gmail_sync_outbound(self, request: Request) -> HTMLResponse:
        result = self.gmail_service.sync_outbound_activity()
        if result.get("status") == "ok":
            return self.render_gmail_sync_settings(
                request,
                message=(
                    f"SENT 활동 {result.get('outbound_message_count', 0)}건을 확인했고 "
                    f"{result.get('linked_work_item_count', 0)}건을 업무 회신으로 연결했습니다."
                ),
            )
        return self.render_gmail_sync_settings(
            request,
            error=str(result.get("message") or "Gmail 발신 활동 동기화 실패"),
        )

    def receive_latest_duplicate_demo_mail(self, request: Request) -> RedirectResponse:
        if not self.request_demo_mode(request):
            raise HTTPException(status_code=400, detail="Demo mode is required.")
        new_email_uid = self.duplicate_latest_demo_mail()
        self.start_received_demo_mail_processing(new_email_uid)
        response = RedirectResponse(f"/?view=inbox&email_uid={quote(new_email_uid)}", status_code=303)
        response.set_cookie(
            self.display_mode_cookie_name,
            "demo",
            max_age=60 * 60 * 24 * 365,
            httponly=False,
            secure=self.auth_cookie_secure,
            samesite="lax",
        )
        return response

    def routing_table(self, request: Request) -> HTMLResponse:
        return self.templates.TemplateResponse(
            request,
            "partials/routing_table.html",
            {**self.settings_context(), "request": request},
        )

    def routing_summary(self, request: Request) -> HTMLResponse:
        return self.templates.TemplateResponse(
            request,
            "partials/routing_summary.html",
            {**self.settings_context(), "request": request},
        )

    def auto_assignment_policy(self, request: Request) -> HTMLResponse:
        return self.render_auto_assignment_policy(request)

    def display_mode_toggle(self, request: Request, display_mode: str = "") -> Response:
        selected_mode = str(display_mode or request.query_params.get("display_mode") or "").strip().casefold()
        if selected_mode not in {"demo", "gmail", "naver", "hiworks"}:
            selected_mode = "demo" if not self.request_demo_mode(request) else "gmail"
        response = Response(status_code=204, headers={"HX-Refresh": "true"})
        response.set_cookie(
            self.display_mode_cookie_name,
            selected_mode,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            samesite="lax",
        )
        return response

    def auto_sync_run(self) -> Response:
        if self.demo_mode_enabled():
            return Response(status_code=204, headers={"HX-Trigger": "coramail-demo-noop"})
        provider = self.active_mail_provider()
        service = self.active_provider_service()
        result = service.sync()
        if result.get("status") == "ok":
            if provider == "gmail":
                outbound_result = self.gmail_service.sync_outbound_activity()
                if outbound_result.get("status") not in {"ok", "skipped"}:
                    self.logger.warning(
                        "Gmail outbound sync failed during auto sync: %s",
                        outbound_result.get("message"),
                    )
            return Response(status_code=204, headers={"HX-Refresh": "true"})
        trigger = {
            "mail-delete-warning": {
                "message": str(result.get("message") or f"{self.active_provider_label()} Mail 동기화 실패")
            }
        }
        return Response(
            status_code=204,
            headers={"HX-Trigger": json.dumps(trigger, ensure_ascii=True)},
        )

    def auto_sync_status(self) -> dict[str, object]:
        status = self.active_provider_service().status()
        account_status = self.active_mail_public_status()
        last_error = str(status.get("last_error") or account_status.get("last_sync_error") or "")
        return {
            "enabled": not self.demo_mode_enabled(),
            "running": False,
            "last_exit_code": 0 if not last_error else 1,
            "last_error": last_error,
            "last_synced_at": status.get("last_synced_at") or account_status.get("last_synced_at") or 0,
            "message_count": status.get("message_count") or 0,
            "account": status.get("account") or "",
        }

    async def create_assignee(self, request: Request) -> HTMLResponse:
        form = self.parse_form(await request.body())
        name = str(form.get("assignee_name") or "").strip()
        email = str(form.get("email_address") or "").strip()
        if name and email:
            self.assignee_admin_repository.create(
                name=name,
                email=email,
                department=str(form.get("department") or "").strip(),
                position=str(form.get("position") or "").strip(),
                category=str(form.get("mail_category") or "기타").strip(),
            )
        return self.routing_table_response(request)

    async def update_assignee(self, request: Request, assignee_id: UUID) -> Response:
        form = self.parse_form(await request.body())
        self.assignee_admin_repository.update(
            assignee_id,
            name=str(form.get("assignee_name") or "").strip(),
            email=str(form.get("email_address") or "").strip(),
            department=str(form.get("department") or "").strip(),
            position=str(form.get("position") or "").strip(),
            category=str(form.get("mail_category") or "").strip(),
        )
        return Response(status_code=204)

    async def toggle_assignee(self, request: Request, assignee_id: UUID) -> HTMLResponse:
        self.assignee_admin_repository.toggle_active(assignee_id)
        return self.templates.TemplateResponse(
            request,
            "partials/routing_summary.html",
            {**self.settings_context(), "request": request},
        )

    async def deactivate_assignee(self, request: Request, assignee_id: UUID) -> HTMLResponse:
        self.assignee_admin_repository.set_active(assignee_id, False)
        return self.routing_table_response(request)

    async def delete_assignee(self, request: Request, assignee_id: UUID) -> HTMLResponse:
        self.assignee_admin_repository.delete(assignee_id)
        return self.routing_table_response(request)

    async def routing_reorder(self, request: Request) -> HTMLResponse:
        form = parse_qs((await request.body()).decode("utf-8", errors="replace"), keep_blank_values=True)
        category = str((form.get("category") or [""])[-1]).strip()
        assignee_ids = []
        for raw_id in form.get("assignee_ids") or []:
            try:
                assignee_ids.append(UUID(str(raw_id)))
            except ValueError:
                continue
        if category and assignee_ids:
            self.assignee_admin_repository.reorder_category_assignees(category, assignee_ids)
        return self.templates.TemplateResponse(
            request,
            "partials/routing_summary.html",
            {**self.settings_context(), "request": request},
        )

    async def save_auto_assignment_policy(self, request: Request) -> HTMLResponse:
        form = self.parse_form(await request.body())
        try:
            self.routing_policy_settings_repository.save(
                auto_assign_threshold=float(str(form.get("auto_assign_threshold") or "")),
                minimum_margin=float(str(form.get("minimum_margin") or "")),
                minimum_classification_confidence=float(
                    str(form.get("minimum_classification_confidence") or "")
                ),
            )
        except ValueError:
            return self.render_auto_assignment_policy(request, error="0과 1 사이의 숫자로 입력하세요.")
        return self.render_auto_assignment_policy(request, message="자동 배정 기준을 저장했습니다.")

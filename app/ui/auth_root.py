from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse


@dataclass(frozen=True)
class AuthRootHandlers:
    is_authenticated: Callable[[Request], bool]
    login_response: Callable[..., HTMLResponse]
    parse_form: Callable[[bytes], dict[str, str]]
    authenticate_login: Callable[[str, str], dict[str, Any] | None]
    auth_cookie_value: Callable[[str], str]
    auth_cookie_name: str
    auth_session_seconds: int
    auth_cookie_secure: bool
    mail_rows: Callable[..., list[dict[str, Any]]]
    status_matches: Callable[[dict[str, Any], str], bool]
    resolve_selected_index: Callable[..., int | None]
    inbox_context: Callable[..., dict[str, Any]]
    document_types_context: Callable[..., dict[str, Any]]
    address_book_context: Callable[..., dict[str, Any]]
    assignee_work_context: Callable[..., dict[str, Any]]
    ops_console_context: Callable[..., dict[str, Any]]
    search_context: Callable[..., dict[str, Any]]
    chats_context: Callable[..., dict[str, Any]]
    settings_context: Callable[..., dict[str, Any]]
    dashboard_context: Callable[..., dict[str, Any]]
    templates: Any

    @staticmethod
    def safe_next(next_path: str) -> str:
        safe_next = next_path if next_path.startswith("/") and not next_path.startswith("//") else "/"
        return "/" if safe_next.startswith("/ui/") else safe_next

    def login_form(self, request: Request, next_path: str = "/") -> Response:
        safe_next = self.safe_next(next_path)
        if self.is_authenticated(request):
            return RedirectResponse(safe_next, status_code=303)
        return self.login_response(request, next_path=safe_next)

    async def login_submit(self, request: Request, next_path: str = "/") -> Response:
        form = self.parse_form(await request.body())
        username = str(form.get("username") or "").strip()
        password = str(form.get("password") or "")
        safe_next = self.safe_next(next_path)
        identity = self.authenticate_login(username, password)
        if identity:
            response = RedirectResponse(safe_next, status_code=303)
            response.set_cookie(
                self.auth_cookie_name,
                self.auth_cookie_value(identity["username"]),
                max_age=self.auth_session_seconds,
                httponly=True,
                secure=self.auth_cookie_secure,
                samesite="lax",
            )
            return response
        return self.login_response(request, error="아이디 또는 비밀번호가 올바르지 않습니다.", next_path=safe_next)

    def logout_submit(self) -> RedirectResponse:
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(self.auth_cookie_name)
        return response

    def root(
        self,
        request: Request,
        view: str = "dashboard",
        q: str = "",
        category: str = "",
        limit: int = 5,
        email_index: int = 0,
        email_uid: str = "",
        selected_email_uid: str = "",
        assignee: str = "",
        status: str = "",
        session_id: str = "",
        organization: str = "",
    ) -> HTMLResponse:
        context = self.shell_context(
            request,
            view=view,
            q=q,
            category=category,
            limit=limit,
            email_index=email_index,
            email_uid=email_uid,
            selected_email_uid=selected_email_uid,
            assignee=assignee,
            status=status,
            session_id=session_id,
            organization=organization,
        )
        return self.templates.TemplateResponse(request, "shell.html", context)

    def shell_context(
        self,
        request: Request,
        view: str = "dashboard",
        q: str = "",
        category: str = "",
        limit: int = 5,
        email_index: int = 0,
        email_uid: str = "",
        selected_email_uid: str = "",
        assignee: str = "",
        status: str = "",
        session_id: str = "",
        organization: str = "",
    ) -> dict[str, Any]:
        active_view = view if view in {"dashboard", "inbox", "monitoring", "ops", "assignees", "my-work", "documents", "address-book", "search", "chats", "settings"} else "dashboard"
        if active_view == "inbox":
            rows = [row for row in self.mail_rows(q=q, category=category) if self.status_matches(row, status.strip())]
            selected_index = self.resolve_selected_index(rows, email_index, email_uid)
            context = {
                **self.inbox_context(
                    request,
                    selected_index=selected_index,
                    selected_email_uid=rows[selected_index]["email_uid"] if selected_index is not None else "",
                    q=q,
                    category=category,
                    status=status,
                ),
                "request": request,
                "active_view": active_view,
                "initial_view_template": "views/inbox.html",
            }
        elif active_view == "documents":
            context = {**self.document_types_context(q=q), "request": request, "active_view": active_view, "initial_view_template": "views/document_types.html"}
        elif active_view == "address-book":
            context = {**self.address_book_context(q=q, organization=organization), "request": request, "active_view": active_view, "initial_view_template": "views/address_book.html"}
        elif active_view == "assignees":
            context = {**self.assignee_work_context(request, assignee=assignee, q=q, category=category, status=status, selected_email_uid=selected_email_uid), "request": request, "active_view": active_view, "initial_view_template": "views/assignee_work.html"}
        elif active_view == "my-work":
            context = {**self.assignee_work_context(request, assignee=assignee, q=q, category=category, status=status, selected_email_uid=selected_email_uid, work_view_name="my-work", work_endpoint="/ui/my-work", work_title="My Work"), "request": request, "active_view": active_view, "initial_view_template": "views/assignee_work.html"}
        elif active_view in {"monitoring", "ops"}:
            context = {**self.ops_console_context(request, q=q, category=category, status=status), "request": request, "active_view": "monitoring", "initial_view_template": "views/ops.html"}
        elif active_view == "search":
            context = {**self.search_context(q, limit), "request": request, "active_view": active_view, "initial_view_template": "views/search.html"}
        elif active_view == "chats":
            context = {**self.chats_context(q, limit, session_id), "request": request, "active_view": active_view, "initial_view_template": "views/chats.html"}
        elif active_view == "settings":
            context = {**self.settings_context(), "request": request, "active_view": active_view, "initial_view_template": "views/settings.html"}
        else:
            context = {**self.dashboard_context(request, status=status), "request": request, "active_view": "dashboard", "initial_view_template": "views/dashboard.html"}
        return context

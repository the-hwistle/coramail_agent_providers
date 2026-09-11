from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse


AssigneeWorkContext = Callable[..., dict[str, object]]
RenderView = Callable[..., HTMLResponse]


def build_work_ui_router(
    *,
    assignee_work_context: AssigneeWorkContext,
    render_view: RenderView,
) -> APIRouter:
    router = APIRouter()

    @router.post("/ui/assignees", response_class=HTMLResponse)
    @router.get("/ui/assignees", response_class=HTMLResponse)
    def assignees(
        request: Request,
        assignee: str = "",
        q: str = "",
        category: str = "",
        status: str = "",
        selected_email_uid: str = "",
    ) -> HTMLResponse:
        return render_view(
            request,
            "views/assignee_work.html",
            {
                **assignee_work_context(
                    request,
                    assignee=assignee,
                    q=q,
                    category=category,
                    status=status,
                    selected_email_uid=selected_email_uid,
                ),
                "request": request,
            },
            active_view="assignees",
        )

    @router.post("/ui/my-work", response_class=HTMLResponse)
    @router.get("/ui/my-work", response_class=HTMLResponse)
    def my_work(
        request: Request,
        assignee: str = "",
        q: str = "",
        category: str = "",
        status: str = "",
        selected_email_uid: str = "",
    ) -> HTMLResponse:
        return render_view(
            request,
            "views/assignee_work.html",
            {
                **assignee_work_context(
                    request,
                    assignee=assignee,
                    q=q,
                    category=category,
                    status=status,
                    selected_email_uid=selected_email_uid,
                    work_view_name="my-work",
                    work_endpoint="/ui/my-work",
                    work_title="My Work",
                ),
                "request": request,
            },
            active_view="my-work",
        )

    return router

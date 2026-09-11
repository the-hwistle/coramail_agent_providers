from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse


@dataclass(frozen=True)
class MailActionHandlers:
    run_analysis_job: Callable[[str, str], dict[str, Any] | None]
    reanalyze_attachments: Callable[[str], dict[str, Any] | None]
    request_demo_mode: Callable[[Request], bool]
    gmail_service: Any
    render_inbox: Callable[..., HTMLResponse]
    mail_rows: Callable[..., list[dict[str, Any]]]
    status_matches: Callable[[dict[str, Any], str], bool]
    resolve_selected_index: Callable[..., int | None]
    inbox_context: Callable[..., dict[str, Any]]
    render_view: Callable[..., HTMLResponse]
    email_detail: Callable[[str], dict[str, Any] | None]
    start_demo_manual_route_delivery: Callable[[str], dict[str, Any]]
    dashboard_context: Callable[[Request], dict[str, Any]]
    templates: Any
    demo_service: Callable[[], Any]
    logger: logging.Logger

    def classification_regenerate(self, email_ref: str) -> Response:
        return self._regenerate(email_ref, "classification", "mail-classification-regenerated")

    def summary_regenerate(self, email_ref: str) -> Response:
        return self._regenerate(email_ref, "executive_summary", "mail-summary-regenerated")

    def _regenerate(self, email_ref: str, job_kind: str, event_name: str) -> Response:
        processed = self.run_analysis_job(email_ref, job_kind)
        if processed is None:
            return Response(status_code=204, headers={"HX-Trigger": "coramail-demo-noop"})
        email = processed["email"]
        job = processed["job"]
        trigger = {
            event_name: {
                "email_index": email["index"],
                "email_uid": email["email_uid"],
                "processing_job_id": str(job["id"]),
                "status": processed["status"],
            }
        }
        return Response(status_code=204, headers={"HX-Trigger": json.dumps(trigger, ensure_ascii=True)})

    def attachments_reanalyze(self, email_ref: str) -> Response:
        result = self.reanalyze_attachments(email_ref)
        if result is None:
            return Response(status_code=204, headers={"HX-Trigger": "coramail-demo-noop"})
        email = result["email"]
        trigger = {
            "mail-attachments-reanalyzed": {
                "email_index": email["index"],
                "email_uid": email["email_uid"],
                "status": result["status"],
                "attachment_count": result["attachment_count"],
            }
        }
        return Response(status_code=204, headers={"HX-Trigger": json.dumps(trigger, ensure_ascii=True)})

    def trash_email(self, request: Request, email_ref: str) -> HTMLResponse:
        if not self.request_demo_mode(request):
            try:
                self.gmail_service.trash_email(email_ref)
            except Exception as exc:
                self.logger.warning("Gmail trash failed: %s: %s", type(exc).__name__, exc)
        return self.render_inbox(
            request,
            mail_rows=self.mail_rows,
            status_matches=self.status_matches,
            resolve_selected_index=self.resolve_selected_index,
            inbox_context=self.inbox_context,
            render_view=self.render_view,
        )

    def route_email_manual(self, request: Request, email_ref: str) -> HTMLResponse:
        email = self.email_detail(email_ref)
        if self.request_demo_mode(request):
            try:
                self.start_demo_manual_route_delivery(email_ref)
            except RuntimeError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        else:
            try:
                self.gmail_service.start_manual_route_delivery(email_ref)
            except RuntimeError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        dashboard = self.dashboard_context(request)
        response = self.templates.TemplateResponse(
            request,
            "partials/mail_rows.html",
            {
                **dashboard,
                "request": request,
                "emails": dashboard["emails"],
                "mail_rows_mode": "dashboard",
                "selected_email_index": email["index"] if email else None,
                "selected_email_uid": email["email_uid"] if email else "",
            },
        )
        if email:
            response.headers["HX-Trigger"] = json.dumps(
                {"mail-manual-route-started": {"email_uid": str(email["email_uid"])}}, ensure_ascii=True
            )
        return response

    def demo_attachment(self, email_index: int, attachment_index: int, download: bool = False) -> FileResponse:
        resolved = self.demo_service().attachment_path(email_index, attachment_index)
        if resolved is None:
            raise HTTPException(status_code=404, detail="첨부파일을 찾을 수 없습니다.")
        path, filename, media_type = resolved
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="첨부파일 원본이 존재하지 않습니다.")
        return FileResponse(
            path=path,
            media_type=media_type,
            filename=filename,
            content_disposition_type="attachment" if download else "inline",
            headers={"Cache-Control": "no-store"},
        )

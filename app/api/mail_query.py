from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException


DashboardSummary = Callable[[], dict[str, object]]
MailRows = Callable[[], list[dict[str, Any]]]
EmailDetail = Callable[[str], dict[str, object] | None]
JobsEnabled = Callable[[], bool]
JobsForEmail = Callable[[str], list[dict[str, Any]]]
PublicJob = Callable[[dict[str, Any]], dict[str, object]]


def build_mail_query_router(
    *,
    dashboard_summary: DashboardSummary,
    mail_rows: MailRows,
    email_detail: EmailDetail,
    jobs_enabled: JobsEnabled,
    jobs_for_email: JobsForEmail,
    public_job: PublicJob,
) -> APIRouter:
    """Build read-only mail API routes without importing application wiring."""
    router = APIRouter()

    @router.get("/api/summary")
    def summary() -> dict[str, object]:
        return dashboard_summary()

    @router.get("/api/emails")
    def emails() -> dict[str, object]:
        return {"emails": mail_rows()}

    @router.get("/api/emails/{email_ref}/jobs")
    def email_jobs(email_ref: str) -> dict[str, object]:
        email = email_detail(email_ref)
        if email is None:
            raise HTTPException(status_code=404, detail="이메일을 찾을 수 없습니다.")
        if not jobs_enabled():
            return {"email_uid": email["email_uid"], "jobs": []}
        return {
            "email_uid": email["email_uid"],
            "jobs": [public_job(job) for job in jobs_for_email(str(email["email_uid"]))],
        }

    @router.get("/api/emails/{email_ref}")
    def email(email_ref: str) -> dict[str, object]:
        item = email_detail(email_ref)
        if item is None:
            raise HTTPException(status_code=404, detail="이메일을 찾을 수 없습니다.")
        return {"email": item}

    return router

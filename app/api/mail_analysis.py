from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException


ProcessAnalysisJob = Callable[[str, str], dict[str, Any]]
ReanalyzeAttachments = Callable[[str], dict[str, object] | None]
EmailDetail = Callable[[str], dict[str, object] | None]
PublicJob = Callable[[dict[str, Any]], dict[str, object]]


def build_mail_analysis_router(
    *,
    process_analysis_job: ProcessAnalysisJob,
    reanalyze_attachments: ReanalyzeAttachments,
    email_detail: EmailDetail,
    public_job: PublicJob,
) -> APIRouter:
    """Build mail-analysis mutation routes without importing application wiring."""
    router = APIRouter(prefix="/api/emails/{email_ref}")

    def process(email_ref: str, analysis_type: str) -> dict[str, object]:
        processed = process_analysis_job(email_ref, analysis_type)
        return {
            "email_uid": processed["email"]["email_uid"],
            "processing_job": public_job(processed["job"]),
            "worker_result": processed["worker_result"],
            "status": processed["status"],
        }

    @router.post("/classification/regenerate")
    def classification_regenerate(email_ref: str) -> dict[str, object]:
        return process(email_ref, "classification")

    @router.post("/summary/regenerate")
    def summary_regenerate(email_ref: str) -> dict[str, object]:
        return process(email_ref, "executive_summary")

    @router.post("/attachments/reanalyze")
    def attachments_reanalyze(email_ref: str) -> dict[str, object]:
        result = reanalyze_attachments(email_ref)
        if result is not None:
            return result
        if email_detail(email_ref) is None:
            raise HTTPException(status_code=404, detail="이메일을 찾을 수 없습니다.")
        raise HTTPException(status_code=503, detail="PostgreSQL 메일 저장소가 설정되지 않았습니다.")

    return router

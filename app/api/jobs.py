from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query


JobsEnabled = Callable[[], bool]
ListJobs = Callable[..., list[dict[str, Any]]]
JobById = Callable[[str], dict[str, Any] | None]
RunPendingJobs = Callable[..., dict[str, object]]
PublicJob = Callable[[dict[str, Any]], dict[str, object]]


def build_jobs_router(
    *,
    jobs_enabled: JobsEnabled,
    list_jobs: ListJobs,
    job_by_id: JobById,
    run_pending: RunPendingJobs,
    public_job: PublicJob,
) -> APIRouter:
    """Build the job HTTP boundary without importing application wiring."""
    router = APIRouter(prefix="/api/jobs")

    @router.get("")
    def jobs(
        status: str = "",
        job_type: str = "",
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> dict[str, object]:
        if not jobs_enabled():
            return {"jobs": []}
        return {
            "jobs": [
                public_job(job)
                for job in list_jobs(status=status, job_type=job_type, limit=limit)
            ]
        }

    @router.post("/run-pending")
    def run_pending_jobs(limit: Annotated[int, Query(ge=1, le=100)] = 10) -> dict[str, object]:
        if not jobs_enabled():
            raise HTTPException(status_code=503, detail="PostgreSQL 작업 저장소가 설정되지 않았습니다.")
        return run_pending(limit=limit)

    @router.get("/{job_id}")
    def job_detail(job_id: str) -> dict[str, object]:
        if not jobs_enabled():
            raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
        job = job_by_id(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
        return {"job": public_job(job)}

    return router

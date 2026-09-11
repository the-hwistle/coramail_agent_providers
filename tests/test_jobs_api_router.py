from fastapi import FastAPI

from app.api.jobs import build_jobs_router


def test_jobs_router_registers_expected_paths() -> None:
    router = build_jobs_router(
        jobs_enabled=lambda: True,
        list_jobs=lambda **_: [],
        job_by_id=lambda _job_id: None,
        run_pending=lambda **_: {"processed": 0},
        public_job=lambda job: job,
    )
    app = FastAPI()
    app.include_router(router)

    paths = set(app.openapi()["paths"])
    assert paths == {"/api/jobs", "/api/jobs/{job_id}", "/api/jobs/run-pending"}

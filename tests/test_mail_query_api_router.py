from fastapi import FastAPI

from app.api.mail_query import build_mail_query_router


def test_mail_query_router_registers_expected_paths() -> None:
    router = build_mail_query_router(
        dashboard_summary=lambda: {},
        mail_rows=lambda: [],
        email_detail=lambda _email_ref: None,
        jobs_enabled=lambda: False,
        jobs_for_email=lambda _email_uid: [],
        public_job=lambda job: job,
    )
    app = FastAPI()
    app.include_router(router)

    assert set(app.openapi()["paths"]) == {
        "/api/summary",
        "/api/emails",
        "/api/emails/{email_ref}/jobs",
        "/api/emails/{email_ref}",
    }


def test_mail_query_router_keeps_specific_email_jobs_route_before_email_detail() -> None:
    router = build_mail_query_router(
        dashboard_summary=lambda: {},
        mail_rows=lambda: [],
        email_detail=lambda email_ref: {"email_uid": email_ref},
        jobs_enabled=lambda: False,
        jobs_for_email=lambda _email_uid: [],
        public_job=lambda job: job,
    )
    paths = [getattr(route, "path", "") for route in router.routes]

    assert paths.index("/api/emails/{email_ref}/jobs") < paths.index("/api/emails/{email_ref}")

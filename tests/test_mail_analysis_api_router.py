from fastapi import FastAPI

from app.api.mail_analysis import build_mail_analysis_router


def test_mail_analysis_router_registers_expected_paths() -> None:
    router = build_mail_analysis_router(
        process_analysis_job=lambda _email_ref, _analysis_type: {},
        reanalyze_attachments=lambda _email_ref: {},
        email_detail=lambda _email_ref: None,
        public_job=lambda job: job,
    )
    app = FastAPI()
    app.include_router(router)

    assert set(app.openapi()["paths"]) == {
        "/api/emails/{email_ref}/classification/regenerate",
        "/api/emails/{email_ref}/summary/regenerate",
        "/api/emails/{email_ref}/attachments/reanalyze",
    }

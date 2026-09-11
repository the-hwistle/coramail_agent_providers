from app.web.runtime import build_server_runtime


def test_build_server_runtime_without_persistent_database(monkeypatch, tmp_path):
    monkeypatch.setenv("CORAMAIL_DATABASE_URL", "")
    monkeypatch.setenv("CORAMAIL_LOCAL_DEV_DEFAULTS", "false")
    monkeypatch.setenv("CORAMAIL_WORK_OVERDUE_HOURS", "18")

    runtime = build_server_runtime(tmp_path)

    assert runtime.production_case_indexer is None
    assert runtime.postgres_routing_repository.assignment_indexer is None
    assert runtime.postgres_work_tracking_repository.overdue_hours == 18
    assert runtime.gmail_service.account_repository is runtime.gmail_account_repository
    assert runtime.gmail_service.postgres_mailbox is None
    assert runtime.gmail_service.routing_repository is runtime.postgres_routing_repository
    assert runtime.gmail_service.job_repository is runtime.postgres_job_repository
    assert runtime.gmail_service.analysis_worker is runtime.postgres_email_analysis_worker
    assert runtime.gmail_service.work_tracking_repository is runtime.postgres_work_tracking_repository
    assert runtime.mail_search_embedding_cache == {}

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.repositories.postgres_mail_decision_repository import PostgresMailDecisionRepository
from app.schemas.mail_decision import MailDecisionRunState, MailDecisionStatus


class RecordingCursor:
    rowcount = 1

    def __init__(self, row=None) -> None:
        self.sql = ""
        self.params = {}
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchone(self):
        return self.row


class RecordingConnection:
    def __init__(self, cursor: RecordingCursor) -> None:
        self.recording_cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def transaction(self):
        return self

    def cursor(self):
        return self.recording_cursor


def test_save_run_uses_boolean_running_parameter(monkeypatch) -> None:
    cursor = RecordingCursor()

    class PsycopgStub:
        @staticmethod
        def connect(database_url):
            assert database_url == "postgresql://example.invalid/coramail"
            return RecordingConnection(cursor)

    monkeypatch.setitem(__import__("sys").modules, "psycopg", PsycopgStub)

    state = MailDecisionRunState(
        run_id=uuid4(),
        email_message_id=uuid4(),
        workflow_version="test-workflow",
        status=MailDecisionStatus.RUNNING,
    )

    PostgresMailDecisionRepository("postgresql://example.invalid/coramail").save_run(state)

    assert "SET status = %(status)s" in cursor.sql
    assert "%(status)s = 'running'" not in cursor.sql
    assert "AND %(is_running)s" in cursor.sql
    assert cursor.params["status"] == "running"
    assert cursor.params["is_running"] is True
    assert state.started_at is not None


def test_save_run_sets_completed_at_for_existing_terminal_states(monkeypatch) -> None:
    cursor = RecordingCursor()

    class PsycopgStub:
        @staticmethod
        def connect(database_url):
            return RecordingConnection(cursor)

    monkeypatch.setitem(__import__("sys").modules, "psycopg", PsycopgStub)

    state = MailDecisionRunState(
        run_id=uuid4(),
        email_message_id=uuid4(),
        workflow_version="test-workflow",
        status=MailDecisionStatus.COMPLETED,
    )

    PostgresMailDecisionRepository("postgresql://example.invalid/coramail").save_run(state)

    assert cursor.params["status"] == "completed"
    assert cursor.params["is_running"] is False
    assert state.completed_at is not None


def run_row(*, run_id, email_id, status="review_required", created_at=None):
    return {
        "id": run_id,
        "email_message_id": email_id,
        "workflow_version": "test-workflow",
        "status": status,
        "current_node": None,
        "started_at": None,
        "completed_at": None,
        "created_at": created_at or datetime.now(timezone.utc),
        "state_json": {},
    }


def test_get_latest_run_for_email_returns_none_when_email_has_no_runs(monkeypatch) -> None:
    cursor = RecordingCursor(row=None)

    class PsycopgStub:
        @staticmethod
        def connect(database_url, row_factory=None):
            return RecordingConnection(cursor)

    monkeypatch.setitem(__import__("sys").modules, "psycopg", PsycopgStub)

    email_id = uuid4()
    state = PostgresMailDecisionRepository("postgresql://example.invalid/coramail").get_latest_run_for_email(email_id)

    assert state is None
    assert "WHERE email_message_id = %(email_message_id)s" in cursor.sql
    assert "ORDER BY created_at DESC, id DESC" in cursor.sql
    assert cursor.params == {"email_message_id": email_id}


def test_get_latest_run_for_email_reuses_state_mapping_for_terminal_and_running_runs(monkeypatch) -> None:
    email_id = uuid4()
    latest_run_id = uuid4()
    cursor = RecordingCursor(row=run_row(run_id=latest_run_id, email_id=email_id, status="failed"))

    class PsycopgStub:
        @staticmethod
        def connect(database_url, row_factory=None):
            return RecordingConnection(cursor)

    monkeypatch.setitem(__import__("sys").modules, "psycopg", PsycopgStub)

    state = PostgresMailDecisionRepository("postgresql://example.invalid/coramail").get_latest_run_for_email(email_id)

    assert state is not None
    assert state.run_id == latest_run_id
    assert state.email_message_id == email_id
    assert state.status == MailDecisionStatus.FAILED


def test_get_latest_run_for_email_accepts_running_as_latest(monkeypatch) -> None:
    email_id = uuid4()
    latest_run_id = uuid4()
    cursor = RecordingCursor(row=run_row(run_id=latest_run_id, email_id=email_id, status="running"))

    class PsycopgStub:
        @staticmethod
        def connect(database_url, row_factory=None):
            return RecordingConnection(cursor)

    monkeypatch.setitem(__import__("sys").modules, "psycopg", PsycopgStub)

    state = PostgresMailDecisionRepository("postgresql://example.invalid/coramail").get_latest_run_for_email(email_id)

    assert state is not None
    assert state.run_id == latest_run_id
    assert state.status == MailDecisionStatus.RUNNING


def test_resolve_email_message_id_maps_gmail_provider_id_to_canonical_uuid(monkeypatch) -> None:
    email_id = uuid4()
    cursor = RecordingCursor(row={"id": email_id})

    class PsycopgStub:
        @staticmethod
        def connect(database_url, row_factory=None):
            return RecordingConnection(cursor)

    monkeypatch.setitem(__import__("sys").modules, "psycopg", PsycopgStub)

    repository = PostgresMailDecisionRepository("postgresql://example.invalid/coramail")
    assert repository.resolve_email_message_id("19bef463b6aee06d") == email_id
    assert "account.provider = 'gmail'" in cursor.sql
    assert cursor.params == {"provider_message_id": "19bef463b6aee06d"}


def test_resolve_email_message_id_keeps_canonical_uuid_without_database_lookup() -> None:
    email_id = uuid4()
    repository = PostgresMailDecisionRepository("")

    assert repository.resolve_email_message_id(email_id) == email_id

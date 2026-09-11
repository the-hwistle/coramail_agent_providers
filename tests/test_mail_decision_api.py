from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

import app.api.mail_decision as api
from app.runtime import app as runtime_app
from app.schemas.mail_decision import MailDecisionRunState, MailDecisionStatus


class FakeRepository:
    def __init__(self, state=None, *, enabled=True):
        self.state = state
        self.enabled = enabled
        self.latest_email_id = None

    def get_latest_run_for_email(self, email_message_id):
        self.latest_email_id = email_message_id
        return self.state

    def resolve_email_message_id(self, email_ref):
        return UUID(str(email_ref))


def test_latest_mail_decision_run_returns_existing_run(monkeypatch):
    email_id = uuid4()
    state = MailDecisionRunState(
        run_id=uuid4(),
        email_message_id=email_id,
        workflow_version="test-workflow",
        status=MailDecisionStatus.REVIEW_REQUIRED,
        context={"review_reason": "retrieval_context_insufficient"},
    )
    repository = FakeRepository(state)
    monkeypatch.setattr(api, "_repository", repository)

    response = api.get_latest_mail_decision_run_for_email(email_id)

    assert response["run"]["run_id"] == str(state.run_id)
    assert response["run"] == api.get_latest_mail_decision_run_for_email(email_id)["run"]
    assert repository.latest_email_id == email_id


def test_latest_mail_decision_run_returns_null_when_absent(monkeypatch):
    monkeypatch.setattr(api, "_repository", FakeRepository(None))

    assert api.get_latest_mail_decision_run_for_email(uuid4()) == {"run": None}


def test_latest_mail_decision_run_returns_503_when_repository_disabled(monkeypatch):
    monkeypatch.setattr(api, "_repository", FakeRepository(None, enabled=False))

    with pytest.raises(HTTPException) as exc:
        api.get_latest_mail_decision_run_for_email(uuid4())

    assert exc.value.status_code == 503


def test_mail_decision_repository_refreshes_after_environment_load(monkeypatch):
    monkeypatch.setenv("CORAMAIL_DATABASE_URL", "postgresql://example.invalid/coramail")
    monkeypatch.setattr(api, "_repository", api.PostgresMailDecisionRepository(""))
    monkeypatch.setattr(api, "_service", None)

    repository = api._repository_for_current_config()

    assert repository.enabled is True
    assert repository.database_url == "postgresql://example.invalid/coramail"


def test_latest_mail_decision_run_path_accepts_provider_or_canonical_reference():
    openapi = runtime_app.openapi()
    parameter = openapi["paths"]["/api/emails/{email_message_id}/mail-decision-runs/latest"]["get"]["parameters"][0]

    assert parameter["name"] == "email_message_id"
    assert parameter["schema"]["type"] == "string"


def test_latest_mail_decision_run_resolves_gmail_provider_message_id(monkeypatch):
    email_id = uuid4()
    repository = FakeRepository(None)
    repository.resolve_email_message_id = lambda email_ref: email_id if email_ref == "19bef463b6aee06d" else None
    monkeypatch.setattr(api, "_repository", repository)

    assert api.get_latest_mail_decision_run_for_email("19bef463b6aee06d") == {"run": None}
    assert repository.latest_email_id == email_id


def test_latest_mail_decision_run_rejects_unknown_provider_message_id(monkeypatch):
    repository = FakeRepository(None)
    repository.resolve_email_message_id = lambda email_ref: None
    monkeypatch.setattr(api, "_repository", repository)

    with pytest.raises(HTTPException) as exc:
        api.get_latest_mail_decision_run_for_email("unknown-gmail-id")

    assert exc.value.status_code == 404


def test_create_mail_decision_run_resolves_gmail_provider_message_id(monkeypatch):
    email_id = uuid4()
    state = MailDecisionRunState(
        run_id=uuid4(),
        email_message_id=email_id,
        workflow_version="test-workflow",
        status=MailDecisionStatus.REVIEW_REQUIRED,
    )
    repository = FakeRepository(None)
    repository.resolve_email_message_id = lambda email_ref: email_id if email_ref == "19bef463b6aee06d" else None

    class FakeService:
        def create_and_run(self, resolved_email_id):
            assert resolved_email_id == email_id
            return state

    monkeypatch.setattr(api, "_repository", repository)
    monkeypatch.setattr(api, "_service", FakeService())

    response = api.create_mail_decision_run("19bef463b6aee06d")

    assert response["run"]["email_message_id"] == str(email_id)

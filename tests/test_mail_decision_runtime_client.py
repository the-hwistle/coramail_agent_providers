from __future__ import annotations

import json

import pytest
import requests

from app.services.mail_decision_runtime_client import (
    MailDecisionRuntimeClient,
    MailDecisionRuntimeClientConfig,
    MailDecisionRuntimeConnectionError,
    MailDecisionRuntimeInvalidResponseError,
    MailDecisionRuntimeNotFoundError,
    MailDecisionRuntimeServerError,
    MailDecisionRuntimeTimeoutError,
)


RUN_PAYLOAD = {
    "run_id": "5df8b829-b235-4ecd-a0b7-66dfd90c30de",
    "email_message_id": "e9105ba1-da36-5ef8-9471-7bcee37b48e4",
    "workflow_version": "mail-decision-decision-agent-v1",
    "status": "review_required",
    "context": {"review_reason": "retrieval_context_insufficient"},
}


class FakeSession:
    def __init__(self, responses=None, exc=None):
        self.responses = list(responses or [])
        self.exc = exc
        self.calls = []

    def request(self, method, url, timeout):
        self.calls.append((method, url, timeout))
        if self.exc:
            raise self.exc
        return self.responses.pop(0)


def response(status_code: int, payload=None, text: str = ""):
    item = requests.Response()
    item.status_code = status_code
    item._content = json.dumps(payload).encode("utf-8") if payload is not None else text.encode("utf-8")
    item.headers["Content-Type"] = "application/json"
    return item


def client(session):
    return MailDecisionRuntimeClient(
        MailDecisionRuntimeClientConfig(base_url="http://runtime.test", timeout_seconds=321),
        session=session,
    )


def test_runtime_client_create_get_and_steps_success():
    session = FakeSession(
        [
            response(200, {"run": RUN_PAYLOAD}),
            response(200, {"run": RUN_PAYLOAD}),
            response(200, {"steps": [{"node_name": "load_mail_context", "status": "completed"}]}),
        ]
    )
    runtime = client(session)

    assert runtime.create_run(RUN_PAYLOAD["email_message_id"])["status"] == "review_required"
    assert runtime.get_run(RUN_PAYLOAD["run_id"])["run_id"] == RUN_PAYLOAD["run_id"]
    assert runtime.get_steps(RUN_PAYLOAD["run_id"])[0]["node_name"] == "load_mail_context"
    assert session.calls[0] == (
        "POST",
        f"http://runtime.test/api/emails/{RUN_PAYLOAD['email_message_id']}/mail-decision-runs",
        321,
    )


def test_runtime_client_latest_run_success_and_absent():
    session = FakeSession(
        [
            response(200, {"run": RUN_PAYLOAD}),
            response(200, {"run": None}),
        ]
    )
    runtime = client(session)

    assert runtime.get_latest_run_for_email(RUN_PAYLOAD["email_message_id"])["run_id"] == RUN_PAYLOAD["run_id"]
    assert runtime.get_latest_run_for_email(RUN_PAYLOAD["email_message_id"]) is None
    assert session.calls[0] == (
        "GET",
        f"http://runtime.test/api/emails/{RUN_PAYLOAD['email_message_id']}/mail-decision-runs/latest",
        321,
    )


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (requests.ConnectionError("refused"), MailDecisionRuntimeConnectionError),
        (requests.Timeout("slow"), MailDecisionRuntimeTimeoutError),
    ],
)
def test_runtime_client_connection_and_timeout_errors(exc, expected):
    with pytest.raises(expected):
        client(FakeSession(exc=exc)).create_run(RUN_PAYLOAD["email_message_id"])


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (404, MailDecisionRuntimeNotFoundError),
        (500, MailDecisionRuntimeServerError),
    ],
)
def test_runtime_client_http_errors(status_code, expected):
    with pytest.raises(expected):
        client(FakeSession([response(status_code, {"detail": "error"})])).get_run(RUN_PAYLOAD["run_id"])


def test_runtime_client_rejects_invalid_json_and_schema():
    with pytest.raises(MailDecisionRuntimeInvalidResponseError):
        client(FakeSession([response(200, text="not json")])).get_run(RUN_PAYLOAD["run_id"])
    with pytest.raises(MailDecisionRuntimeInvalidResponseError):
        client(FakeSession([response(200, {"run": {"status": "completed"}})])).get_run(RUN_PAYLOAD["run_id"])
    with pytest.raises(MailDecisionRuntimeInvalidResponseError):
        client(FakeSession([response(200, {"run": []})])).get_latest_run_for_email(RUN_PAYLOAD["email_message_id"])

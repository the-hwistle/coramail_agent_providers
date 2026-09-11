from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import requests


logger = logging.getLogger(__name__)


class MailDecisionRuntimeClientError(Exception):
    user_message = "Mail Decision Runtime에 연결할 수 없습니다."


class MailDecisionRuntimeConnectionError(MailDecisionRuntimeClientError):
    user_message = "Mail Decision Runtime에 연결할 수 없습니다."


class MailDecisionRuntimeTimeoutError(MailDecisionRuntimeClientError):
    user_message = "Mail Decision 실행 시간이 초과되었습니다."


class MailDecisionRuntimeNotFoundError(MailDecisionRuntimeClientError):
    user_message = "해당 메일을 찾을 수 없습니다."


class MailDecisionRuntimeValidationError(MailDecisionRuntimeClientError):
    user_message = "Mail Decision 요청 형식이 올바르지 않습니다."


class MailDecisionRuntimeServerError(MailDecisionRuntimeClientError):
    user_message = "Mail Decision 실행 중 서버 오류가 발생했습니다."


class MailDecisionRuntimeInvalidResponseError(MailDecisionRuntimeClientError):
    user_message = "Mail Decision Runtime 응답을 해석할 수 없습니다."


@dataclass(frozen=True)
class MailDecisionRuntimeClientConfig:
    base_url: str = "http://127.0.0.1:8001"
    timeout_seconds: float = 600.0

    @classmethod
    def from_env(cls) -> "MailDecisionRuntimeClientConfig":
        raw_timeout = os.getenv("CORAMAIL_MAIL_DECISION_RUNTIME_TIMEOUT_SECONDS", "600")
        try:
            timeout = float(raw_timeout)
        except ValueError:
            timeout = 600.0
        return cls(
            base_url=os.getenv("CORAMAIL_MAIL_DECISION_RUNTIME_URL", cls.base_url).strip() or cls.base_url,
            timeout_seconds=max(1.0, timeout),
        )


class MailDecisionRuntimeClient:
    def __init__(
        self,
        config: MailDecisionRuntimeClientConfig | None = None,
        *,
        session: requests.Session | None = None,
    ):
        self.config = config or MailDecisionRuntimeClientConfig.from_env()
        self.session = session or requests.Session()

    def create_run(self, email_message_id: UUID | str) -> dict[str, Any]:
        return self._request_run("POST", f"/api/emails/{email_message_id}/mail-decision-runs")

    def get_run(self, run_id: UUID | str) -> dict[str, Any]:
        return self._request_run("GET", f"/api/mail-decision-runs/{run_id}")

    def get_latest_run_for_email(self, email_message_id: UUID | str) -> dict[str, Any] | None:
        payload = self._request("GET", f"/api/emails/{email_message_id}/mail-decision-runs/latest")
        run = payload.get("run")
        if run is None:
            return None
        if not isinstance(run, dict):
            raise MailDecisionRuntimeInvalidResponseError("runtime response run must be an object or null")
        self._validate_run(run)
        return run

    def get_steps(self, run_id: UUID | str) -> list[dict[str, Any]]:
        payload = self._request("GET", f"/api/mail-decision-runs/{run_id}/steps")
        steps = payload.get("steps")
        if not isinstance(steps, list):
            raise MailDecisionRuntimeInvalidResponseError("runtime response missing steps list")
        return [step for step in steps if isinstance(step, dict)]

    def resume_run(self, run_id: UUID | str) -> dict[str, Any]:
        return self._request_run("POST", f"/api/mail-decision-runs/{run_id}/resume")

    def _request_run(self, method: str, path: str) -> dict[str, Any]:
        payload = self._request(method, path)
        run = payload.get("run")
        if not isinstance(run, dict):
            raise MailDecisionRuntimeInvalidResponseError("runtime response missing run object")
        self._validate_run(run)
        return run

    @staticmethod
    def _validate_run(run: dict[str, Any]) -> None:
        required = {"run_id", "email_message_id", "status", "context"}
        missing = sorted(required - set(run))
        if missing:
            raise MailDecisionRuntimeInvalidResponseError(f"runtime run response missing keys: {missing}")

    def _request(self, method: str, path: str) -> dict[str, Any]:
        url = f"{self.config.base_url.rstrip('/')}/{path.lstrip('/')}"
        try:
            response = self.session.request(method, url, timeout=self.config.timeout_seconds)
        except requests.Timeout as exc:
            logger.warning("Mail Decision Runtime timeout: %s", type(exc).__name__)
            raise MailDecisionRuntimeTimeoutError(str(exc)) from exc
        except requests.ConnectionError as exc:
            logger.warning("Mail Decision Runtime connection failure: %s", type(exc).__name__)
            raise MailDecisionRuntimeConnectionError(str(exc)) from exc
        except requests.RequestException as exc:
            logger.warning("Mail Decision Runtime request failure: %s: %s", type(exc).__name__, exc)
            raise MailDecisionRuntimeConnectionError(str(exc)) from exc

        if response.status_code == 404:
            raise MailDecisionRuntimeNotFoundError(response.text)
        if response.status_code == 422:
            raise MailDecisionRuntimeValidationError(response.text)
        if response.status_code >= 500:
            raise MailDecisionRuntimeServerError(response.text)
        if response.status_code >= 400:
            raise MailDecisionRuntimeClientError(response.text)

        try:
            payload = response.json()
        except ValueError as exc:
            raise MailDecisionRuntimeInvalidResponseError("runtime returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise MailDecisionRuntimeInvalidResponseError("runtime returned non-object JSON")
        return payload

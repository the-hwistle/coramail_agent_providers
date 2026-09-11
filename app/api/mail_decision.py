from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.config import database_url
from app.repositories.postgres_mail_decision_repository import PostgresMailDecisionRepository
from app.services.mail_decision_routing_service import MailDecisionRoutingService


router = APIRouter(prefix="/api", tags=["mail-decision"])
_repository: PostgresMailDecisionRepository | object | None = None
_service: MailDecisionRoutingService | object | None = None


def _repository_for_current_config() -> PostgresMailDecisionRepository:
    global _repository, _service

    current_database_url = database_url()
    repository_database_url = getattr(_repository, "database_url", current_database_url)
    if _repository is None or repository_database_url != current_database_url:
        _repository = PostgresMailDecisionRepository(current_database_url)
        _service = MailDecisionRoutingService(_repository)
    return _repository  # type: ignore[return-value]


def _service_for_current_config() -> MailDecisionRoutingService:
    _repository_for_current_config()
    if _service is None:
        raise RuntimeError("Mail Decision service was not initialized")
    return _service  # type: ignore[return-value]


def _require_database(repository: PostgresMailDecisionRepository) -> None:
    if not repository.enabled:
        raise HTTPException(status_code=503, detail="CORAMAIL_DATABASE_URL is not configured")


def _resolve_email_message_id(repository: PostgresMailDecisionRepository, email_ref: str) -> UUID:
    email_message_id = repository.resolve_email_message_id(email_ref)
    if email_message_id is None:
        raise HTTPException(status_code=404, detail=f"email not found: {email_ref}")
    return email_message_id


@router.post("/emails/{email_message_id}/mail-decision-runs")
def create_mail_decision_run(email_message_id: str) -> dict[str, object]:
    repository = _repository_for_current_config()
    _require_database(repository)
    canonical_email_message_id = _resolve_email_message_id(repository, email_message_id)
    try:
        state = _service_for_current_config().create_and_run(canonical_email_message_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"run": state.model_dump(mode="json")}


@router.get("/mail-decision-runs/{run_id}")
def get_mail_decision_run(run_id: UUID) -> dict[str, object]:
    repository = _repository_for_current_config()
    _require_database(repository)
    state = repository.get_run(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"mail decision run not found: {run_id}")
    return {"run": state.model_dump(mode="json")}


@router.get("/emails/{email_message_id}/mail-decision-runs/latest")
def get_latest_mail_decision_run_for_email(email_message_id: str) -> dict[str, object]:
    repository = _repository_for_current_config()
    _require_database(repository)
    canonical_email_message_id = _resolve_email_message_id(repository, email_message_id)
    state = repository.get_latest_run_for_email(canonical_email_message_id)
    return {"run": None if state is None else state.model_dump(mode="json")}


@router.get("/mail-decision-runs/{run_id}/steps")
def get_mail_decision_steps(run_id: UUID) -> dict[str, object]:
    repository = _repository_for_current_config()
    _require_database(repository)
    if repository.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail=f"mail decision run not found: {run_id}")
    return {"steps": repository.list_steps(run_id)}


@router.post("/mail-decision-runs/{run_id}/resume")
def resume_mail_decision_run(run_id: UUID) -> dict[str, object]:
    repository = _repository_for_current_config()
    _require_database(repository)
    try:
        state = _service_for_current_config().resume(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"run": state.model_dump(mode="json")}

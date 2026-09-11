from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from app.repositories.postgres_mail_decision_repository import PostgresMailDecisionRepository
from app.services.mail_decision_routing_service import MailDecisionRoutingService


class EndToEndEvaluationRunner:
    """Runs ground-truth emails through the real Mail Decision service and emits predictions."""

    def __init__(self, database_url: str):
        self.repository = PostgresMailDecisionRepository(database_url)
        self.service = MailDecisionRoutingService(self.repository)

    def run(
        self,
        dataset: dict[str, Any],
        *,
        limit: int | None = None,
        email_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        truth_rows = list(dataset.get("ground_truth") or [])
        raw_metadata = dataset.get("metadata")
        metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
        selected_ids = {str(item) for item in email_ids or []}
        if selected_ids:
            truth_rows = [row for row in truth_rows if str(row.get("email_message_id")) in selected_ids]
        if limit is not None:
            truth_rows = truth_rows[: max(0, limit)]
        predictions: list[dict[str, Any]] = []
        for truth in truth_rows:
            email_id = UUID(str(truth["email_message_id"]))
            started = datetime.now(timezone.utc)
            try:
                state = self.service.create_and_run(email_id)
                prediction = self._prediction(email_id, state.model_dump(mode="json"))
            except Exception as exc:
                prediction = {
                    "email_message_id": str(email_id),
                    "status": "failed",
                    "business_type": None,
                    "candidate_user_ids": [],
                    "selected_user_id": None,
                    "auto_assigned": False,
                    "unsupported_claim_count": 1,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            completed = datetime.now(timezone.utc)
            prediction["started_at"] = started.isoformat()
            prediction["completed_at"] = completed.isoformat()
            prediction["latency_ms"] = int((completed - started).total_seconds() * 1000)
            prediction["dataset_version"] = metadata.get("dataset_version")
            prediction["qdrant_collection"] = os.getenv("CORAMAIL_QDRANT_CASE_COLLECTION", "")
            print(
                json.dumps(
                    {
                        "email_message_id": str(email_id),
                        "started_at": prediction["started_at"],
                        "completed_at": prediction["completed_at"],
                        "latency_ms": prediction["latency_ms"],
                        "status": prediction.get("status"),
                        "run_id": prediction.get("run_id"),
                        "review_reason": prediction.get("review_reason"),
                        "failure_stage": prediction.get("primary_failure_stage"),
                        "error": prediction.get("error"),
                    },
                    ensure_ascii=False,
                )
            )
            predictions.append(prediction)
        return predictions

    @staticmethod
    def _prediction(email_id: UUID, state: dict[str, Any]) -> dict[str, Any]:
        context = dict(state.get("context") or {})
        decision = dict(context.get("decision_output") or {})
        classification = dict(decision.get("classification") or {})
        urgency = dict(decision.get("urgency") or {})
        importance = dict(decision.get("importance") or {})
        routing = dict(context.get("routing_decision") or {})
        facts = dict(state.get("facts") or {})
        candidates = list(routing.get("candidates") or [])
        candidate_user_ids = [str(item.get("user_id")) for item in candidates if item.get("user_id")]
        selected = routing.get("selected_user_id") or context.get("assigned_user_id")
        unsupported_claims = list(decision.get("unsupported_claims") or [])
        mail = dict(context.get("mail") or {})
        retrieval_context = context.get("retrieval_context")
        return {
            "email_message_id": str(email_id),
            "status": state.get("status"),
            "business_type": classification.get("primary_type"),
            "urgency": urgency.get("level"),
            "importance": importance.get("level"),
            "attention_quadrant": decision.get("attention_quadrant"),
            "candidate_user_ids": candidate_user_ids,
            "selected_user_id": str(selected) if selected else None,
            "auto_assigned": routing.get("decision") == "auto_assign",
            "unsupported_claim_count": len(unsupported_claims),
            "unsupported_claims": unsupported_claims,
            "review_reason": context.get("review_reason"),
            "run_id": state.get("run_id"),
            "facts": facts,
            "attachment_analysis": context.get("attachment_analysis_results") or [],
            "retrieval_context": retrieval_context or {},
            "sufficiency": {
                "unresolved_context": context.get("retrieval_missing_context") or [],
                "sufficient": bool(retrieval_context.get("sufficient")) if isinstance(retrieval_context, dict) else False,
                "review_reason": context.get("review_reason"),
            },
            "decision_output": decision,
            "routing_decision": routing,
            "workflow_version": state.get("workflow_version"),
            "model_name": context.get("model_name"),
            "input": {
                "subject": mail.get("subject"),
                "body_length": len(str(mail.get("body_text") or "")),
            },
        }

    @staticmethod
    def write(predictions: list[dict[str, Any]], path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(predictions, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

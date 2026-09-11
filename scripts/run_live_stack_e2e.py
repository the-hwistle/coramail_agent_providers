from __future__ import annotations

import json
import os
from typing import Literal
from uuid import UUID

import psycopg
from pydantic import BaseModel

from app.config import (
    database_url,
    embedding_model,
    llm_base_url,
    llm_provider,
    qdrant_case_collection,
    qdrant_url,
    text_model,
)
from app.llm.gateway import LocalLLMConfig, LocalLLMGateway
from app.repositories.postgres_mail_decision_repository import PostgresMailDecisionRepository
from app.retrieval.qdrant_indexing import QdrantCaseIndexClient
from app.schemas.mail_decision import MailDecisionStatus
from app.services.mail_decision_routing_service import MailDecisionRoutingService


class LiveProbe(BaseModel):
    verdict: Literal["ok"]
    detail: str


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required for live-stack E2E")
    return value


def _select_seed_email(db_url: str) -> UUID:
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT m.id
                FROM email_messages m
                JOIN email_accounts account ON account.id = m.email_account_id
                WHERE account.provider = 'synthetic'
                  AND m.deleted_at IS NULL
                  AND m.attachment_count = 0
                ORDER BY m.received_at DESC NULLS LAST, m.created_at DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
    if not row:
        raise RuntimeError("demo seed contains no attachment-free synthetic email for live-stack E2E")
    return UUID(str(row[0]))


def _gateway() -> LocalLLMGateway:
    provider = llm_provider().strip().casefold()
    if provider == "gemini":
        _required("GEMINI_API_KEY")
    return LocalLLMGateway(
        LocalLLMConfig(
            base_url=llm_base_url(),
            text_model=text_model(),
            embedding_model=embedding_model(),
            provider=provider,
            text_provider=os.getenv("CORAMAIL_TEXT_LLM_PROVIDER", "").strip(),
            embedding_provider=os.getenv("CORAMAIL_EMBEDDING_PROVIDER", "").strip(),
            timeout_seconds=float(os.getenv("CORAMAIL_LIVE_E2E_LLM_TIMEOUT_SECONDS", "120")),
            max_output_tokens=int(os.getenv("CORAMAIL_LLM_MAX_OUTPUT_TOKENS", "1024")),
        )
    )


def main() -> int:
    db_url = _required("CORAMAIL_DATABASE_URL") or database_url()
    _required("CORAMAIL_QDRANT_URL")
    gateway = _gateway()

    health = gateway.healthcheck()
    if not health:
        raise RuntimeError("real LLM healthcheck returned an empty response")

    probe = gateway.generate_structured(
        system_prompt="You are a deterministic live integration probe.",
        user_prompt='Return verdict "ok" and a short detail confirming the request was processed.',
        output_schema=LiveProbe,
        temperature=0.0,
    )
    if probe.verdict != "ok":
        raise RuntimeError(f"unexpected real LLM probe verdict: {probe.verdict}")

    vectors = gateway.embed(["CoRA Mail live stack Qdrant integration probe"])
    if len(vectors) != 1 or not vectors[0]:
        raise RuntimeError("real embedding provider returned no vector")

    qdrant = QdrantCaseIndexClient(base_url=qdrant_url(), collection=qdrant_case_collection())
    qdrant.ensure_collection(len(vectors[0]))
    counts = qdrant.verification_counts()

    email_message_id = _select_seed_email(db_url)
    repository = PostgresMailDecisionRepository(db_url)
    service = MailDecisionRoutingService(repository)
    state = service.create_and_run(email_message_id)

    if state.status not in {
        MailDecisionStatus.REVIEW_REQUIRED,
        MailDecisionStatus.AUTO_ASSIGNED,
        MailDecisionStatus.COMPLETED,
    }:
        raise RuntimeError(f"mail decision did not reach an accepted terminal state: {state.status.value}")
    if not state.context.get("retrieval_context"):
        raise RuntimeError("mail decision run did not persist retrieval_context")
    if not state.context.get("decision_output"):
        raise RuntimeError("mail decision run did not persist decision_output from the real LLM path")

    steps = repository.list_steps(state.run_id)
    if not steps:
        raise RuntimeError("mail decision run persisted no workflow steps")

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM mail_decision_runs WHERE id = %s", (state.run_id,))
            persisted = int(cursor.fetchone()[0])
    if persisted != 1:
        raise RuntimeError("mail decision run was not persisted in PostgreSQL")

    print(
        json.dumps(
            {
                "status": "ok",
                "postgres": {"mail_decision_run_persisted": True},
                "qdrant": {
                    "url": qdrant_url(),
                    "collection": qdrant_case_collection(),
                    "embedding_dimension": len(vectors[0]),
                    "verification_counts": counts,
                },
                "llm": {
                    "provider": llm_provider(),
                    "text_model": text_model(),
                    "embedding_model": embedding_model(),
                    "probe": probe.model_dump(mode="json"),
                },
                "mail_decision": {
                    "email_message_id": str(email_message_id),
                    "run_id": str(state.run_id),
                    "status": state.status.value,
                    "retrieval_cycle": state.retrieval_cycle,
                    "step_count": len(steps),
                    "review_reason": state.context.get("review_reason"),
                },
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

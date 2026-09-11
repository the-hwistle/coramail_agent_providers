from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid5

from psycopg.rows import dict_row

from app.agents.decision_agent import DecisionAgentOutput
from app.repositories.postgres_mail_decision_repository import PostgresMailDecisionRepository
from app.services.mail_decision_routing_service import MailDecisionRoutingService


CATEGORY_NAMESPACE = UUID("7f3b1189-41f7-5aac-87e4-bfc8de62cf81")

CATEGORIES = {
    "order": {"name": "발주", "sort_order": 10, "keywords": ["purchase", "order", "po", "delivery", "납기", "발주"]},
    "inquiry": {"name": "문의", "sort_order": 20, "keywords": ["quotation", "quote", "rfq", "inquiry", "견적", "문의"]},
    "service": {"name": "서비스", "sort_order": 30, "keywords": ["service", "claim", "failure", "urgent", "긴급", "수리", "클레임"]},
    "technical": {"name": "기술", "sort_order": 40, "keywords": ["spec", "drawing", "technical", "사양", "도면", "기술"]},
    "general": {"name": "기타", "sort_order": 50, "keywords": []},
    "unclassified": {"name": "미분류", "sort_order": 60, "keywords": []},
}


class PostgresEmailAnalysisWorker:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def run_pending(self, *, limit: int = 10) -> dict[str, Any]:
        import psycopg

        processed: list[dict[str, Any]] = []
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            self._ensure_categories(conn)
            self._recover_stale_jobs(conn)
            for _ in range(max(1, min(limit, 100))):
                job = self._claim_next_job(conn)
                if job is None:
                    break
                processed.append(self._process_job(conn, job))
        return {
            "status": "ok",
            "processed_count": len(processed),
            "processed_jobs": processed,
        }

    @staticmethod
    def _recover_stale_jobs(conn: Any) -> None:
        stale_seconds = max(60, int(os.getenv("CORAMAIL_ANALYSIS_STALE_SECONDS", "300")))
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_seconds)
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE processing_jobs
                    SET status = 'pending',
                        started_at = NULL,
                        error_message = 'Recovered after interrupted worker',
                        updated_at = %(updated_at)s
                    WHERE job_type = 'email_analysis'
                      AND status = 'running'
                      AND started_at < %(cutoff)s
                      AND attempt_count < max_attempts
                    """,
                    {"cutoff": cutoff, "updated_at": datetime.now(timezone.utc)},
                )

    def run_one(self, job_id: str) -> dict[str, Any]:
        import psycopg

        processed: list[dict[str, Any]] = []
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            self._ensure_categories(conn)
            self._recover_stale_jobs(conn)
            job = self._claim_next_job(conn, job_id=job_id)
            if job is not None:
                processed.append(self._process_job(conn, job))
        return {
            "status": "ok",
            "processed_count": len(processed),
            "processed_jobs": processed,
        }

    def _claim_next_job(self, conn: Any, *, job_id: str | None = None) -> dict[str, Any] | None:
        timestamp = datetime.now(timezone.utc)
        job_filter = "AND id = %(job_id)s" if job_id else ""
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT *
                    FROM processing_jobs
                    WHERE job_type = 'email_analysis'
                      AND status = 'pending'
                      AND COALESCE(scheduled_at, created_at) <= %(now)s
                      AND metadata ->> 'analysis_type' IN ('classification', 'executive_summary', 'mail_decision')
                      {job_filter}
                    ORDER BY COALESCE(scheduled_at, created_at), created_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                    """,
                    {"now": timestamp, "job_id": job_id},
                )
                job = cursor.fetchone()
                if job is None:
                    return None
                cursor.execute(
                    """
                    UPDATE processing_jobs
                    SET status = 'running',
                        attempt_count = attempt_count + 1,
                        started_at = %(started_at)s,
                        updated_at = %(updated_at)s
                    WHERE id = %(id)s
                    RETURNING *
                    """,
                    {"id": job["id"], "started_at": timestamp, "updated_at": timestamp},
                )
                return dict(cursor.fetchone())

    def _process_job(self, conn: Any, job: dict[str, Any]) -> dict[str, Any]:
        analysis_type = str((job.get("metadata") or {}).get("analysis_type") or "")
        try:
            if analysis_type == "classification":
                result = self._process_classification(conn, job)
            elif analysis_type == "executive_summary":
                result = self._process_summary(conn, job)
            elif analysis_type == "mail_decision":
                result = self._process_mail_decision(job)
            else:
                raise ValueError(f"unsupported analysis_type={analysis_type}")
            self._mark_job_success(conn, str(job["id"]))
            return {"id": str(job["id"]), "analysis_type": analysis_type, "status": "success", **result}
        except Exception as exc:
            self._mark_analysis_failed(
                conn,
                email_uid=str(job["source_id"]),
                analysis_type=analysis_type,
                error_message=f"{type(exc).__name__}: {exc}",
            )
            self._mark_job_failed(conn, str(job["id"]), f"{type(exc).__name__}: {exc}")
            return {"id": str(job["id"]), "analysis_type": analysis_type, "status": "failed", "error": str(exc)}

    def _process_classification(self, conn: Any, job: dict[str, Any]) -> dict[str, Any]:
        payload = self._current_ai_result(conn, str(job["source_id"]), "classification")
        if payload is None:
            output = self._run_mail_decision(str(job["source_id"]))
            payload = output.classification.model_dump(mode="json")
            payload["category_name"] = _category_name(output.classification.primary_type)
        return {
            "category": payload.get("category_name") or payload.get("primary_type"),
            "confidence": float(payload.get("confidence") or 0),
            "source": "mail_decision",
        }

    def _process_summary(self, conn: Any, job: dict[str, Any]) -> dict[str, Any]:
        payload = self._current_ai_result(conn, str(job["source_id"]), "executive_summary")
        if payload is None:
            output = self._run_mail_decision(str(job["source_id"]))
            summary_text = output.summary.one_line_summary
        else:
            summary_text = str(payload.get("summary_text") or payload.get("one_line_summary") or "")
        return {"summary_text": summary_text, "source": "mail_decision"}

    def _process_mail_decision(self, job: dict[str, Any]) -> dict[str, Any]:
        output = self._run_mail_decision(str(job["source_id"]))
        return {
            "category": _category_name(output.classification.primary_type),
            "confidence": output.classification.confidence,
            "source": "mail_decision",
        }

    def _run_mail_decision(self, email_uid: str) -> DecisionAgentOutput:
        repository = PostgresMailDecisionRepository(self.database_url)
        state = MailDecisionRoutingService(repository).create_and_run(UUID(email_uid))
        payload = state.context.get("decision_output")
        if not isinstance(payload, dict):
            reason = str(state.context.get("review_reason") or state.context.get("failure_message") or state.status.value)
            raise RuntimeError(f"Mail Decision did not produce an AI result: {reason}")
        return DecisionAgentOutput.model_validate(payload)

    @staticmethod
    def _current_ai_result(conn: Any, email_uid: str, analysis_type: str) -> dict[str, Any] | None:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT result_json
                FROM email_analysis_results
                WHERE email_message_id = %(email_message_id)s
                  AND analysis_type = %(analysis_type)s
                  AND status = 'success'
                  AND is_current IS TRUE
                  AND prompt_version IN ('decision-agent:v3', 'decision-agent:v2')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                {"email_message_id": email_uid, "analysis_type": analysis_type},
            )
            row = cursor.fetchone()
            return dict(row["result_json"] or {}) if row is not None else None

    def _ensure_categories(self, conn: Any) -> None:
        timestamp = datetime.now(timezone.utc)
        with conn.transaction():
            with conn.cursor() as cursor:
                for code, payload in CATEGORIES.items():
                    category_id = str(uuid5(CATEGORY_NAMESPACE, code))
                    cursor.execute(
                        """
                        UPDATE categories
                        SET code = %(code)s,
                            name = %(name)s,
                            description = %(description)s,
                            is_active = TRUE,
                            sort_order = %(sort_order)s,
                            updated_at = %(updated_at)s
                        WHERE id = %(id)s
                           OR code = %(code)s
                        """,
                        {
                            "id": category_id,
                            "code": code,
                            "name": payload["name"],
                            "description": f"CoRA Mail default category: {payload['name']}",
                            "sort_order": payload["sort_order"],
                            "created_at": timestamp,
                            "updated_at": timestamp,
                        },
                    )
                    if cursor.rowcount:
                        continue
                    cursor.execute(
                        """
                        INSERT INTO categories (id, code, name, description, is_active, sort_order, created_at, updated_at)
                        VALUES (%(id)s, %(code)s, %(name)s, %(description)s, TRUE, %(sort_order)s, %(created_at)s, %(updated_at)s)
                        """,
                        {
                            "id": category_id,
                            "code": code,
                            "name": payload["name"],
                            "description": f"CoRA Mail default category: {payload['name']}",
                            "sort_order": payload["sort_order"],
                            "created_at": timestamp,
                            "updated_at": timestamp,
                        },
                    )

    def _mark_job_success(self, conn: Any, job_id: str) -> None:
        timestamp = datetime.now(timezone.utc)
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE processing_jobs
                    SET status = 'success', completed_at = %(completed_at)s, updated_at = %(updated_at)s
                    WHERE id = %(id)s
                    """,
                    {"id": job_id, "completed_at": timestamp, "updated_at": timestamp},
                )

    def _mark_job_failed(self, conn: Any, job_id: str, error_message: str) -> None:
        timestamp = datetime.now(timezone.utc)
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE processing_jobs
                    SET status = 'failed',
                        error_message = %(error_message)s,
                        completed_at = %(completed_at)s,
                        updated_at = %(updated_at)s
                    WHERE id = %(id)s
                    """,
                    {
                        "id": job_id,
                        "error_message": error_message[:2000],
                        "completed_at": timestamp,
                        "updated_at": timestamp,
                    },
                )

    @staticmethod
    def _mark_analysis_failed(
        conn: Any, *, email_uid: str, analysis_type: str, error_message: str
    ) -> None:
        timestamp = datetime.now(timezone.utc)
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE email_analysis_results
                    SET status = 'failed',
                        error_message = %(error_message)s,
                        updated_at = %(updated_at)s
                    WHERE email_message_id = %(email_message_id)s
                      AND analysis_type = %(analysis_type)s
                      AND is_current IS TRUE
                      AND status IN ('pending', 'processing')
                    """,
                    {
                        "email_message_id": email_uid,
                        "analysis_type": analysis_type,
                        "error_message": error_message[:2000],
                        "updated_at": timestamp,
                    },
                )

def _category_name(primary_type: str) -> str:
    if primary_type in {"purchase_order", "order_change", "order_cancellation", "delivery_confirmation", "delivery_delay"}:
        return "발주"
    if primary_type in {"quotation_request", "quotation_followup", "general_inquiry", "certificate_request"}:
        return "문의"
    if primary_type in {"service_request", "repair_request", "claim", "urgent_failure"}:
        return "서비스"
    if primary_type in {"technical_inquiry", "drawing_review", "specification_review", "compatibility_check"}:
        return "기술"
    return "기타"

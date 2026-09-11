from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class PostgresJobRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def create_email_analysis_job(self, email_uid: str, analysis_type: str, *, requested_by: str = "ui") -> dict[str, Any]:
        email_id = str(UUID(email_uid))
        timestamp = datetime.now(timezone.utc)
        metadata = {
            "analysis_type": analysis_type,
            "requested_by": requested_by,
            "request_source": "coramail_agent",
            "pipeline_version": "job-registration-v1",
        }

        import psycopg

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT id
                        FROM email_messages
                        WHERE id = %(id)s
                        FOR UPDATE
                        """,
                        {"id": email_id},
                    )
                    existing = self._active_email_analysis_job(conn, email_id, analysis_type)
                    if existing is not None:
                        return dict(existing)

                    job_id = str(uuid4())
                    analysis_result_id = str(uuid4())
                    cursor.execute(
                        """
                        INSERT INTO processing_jobs (
                            id, job_type, source_type, source_id, status, attempt_count, max_attempts,
                            scheduled_at, started_at, completed_at, error_message, metadata, created_at, updated_at
                        )
                        VALUES (
                            %(id)s, 'email_analysis', 'email', %(source_id)s, 'pending', 0, 3,
                            %(scheduled_at)s, NULL, NULL, NULL, %(metadata)s, %(created_at)s, %(updated_at)s
                        )
                        RETURNING *
                        """,
                        {
                            "id": job_id,
                            "source_id": email_id,
                            "scheduled_at": timestamp,
                            "metadata": Jsonb(metadata),
                            "created_at": timestamp,
                            "updated_at": timestamp,
                        },
                    )
                    job = dict(cursor.fetchone())
                    cursor.execute(
                        """
                        UPDATE email_analysis_results
                        SET is_current = FALSE, updated_at = %(updated_at)s
                        WHERE email_message_id = %(email_message_id)s
                          AND analysis_type = %(analysis_type)s
                          AND is_current IS TRUE
                        """,
                        {
                            "email_message_id": email_id,
                            "analysis_type": analysis_type,
                            "updated_at": timestamp,
                        },
                    )
                    cursor.execute(
                        """
                        INSERT INTO email_analysis_results (
                            id, email_message_id, analysis_type, result_text, result_json,
                            model_name, prompt_version, status, error_message, is_current, created_at, updated_at
                        )
                        VALUES (
                            %(id)s, %(email_message_id)s, %(analysis_type)s, NULL, %(result_json)s,
                            %(model_name)s, %(prompt_version)s, 'pending', NULL, TRUE, %(created_at)s, %(updated_at)s
                        )
                        """,
                        {
                            "id": analysis_result_id,
                            "email_message_id": email_id,
                            "analysis_type": analysis_type,
                            "result_json": Jsonb({"processing_job_id": job_id, **metadata}),
                            "model_name": "pending-worker",
                            "prompt_version": f"{analysis_type}:pending-v1",
                            "created_at": timestamp,
                            "updated_at": timestamp,
                        },
                    )
                return job

    def list_jobs(
        self,
        *,
        status: str = "",
        job_type: str = "",
        source_id: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: dict[str, Any] = {"limit": max(1, min(limit, 200))}
        if status:
            clauses.append("status = %(status)s")
            params["status"] = status
        if job_type:
            clauses.append("job_type = %(job_type)s")
            params["job_type"] = job_type
        if source_id:
            clauses.append("source_id = %(source_id)s")
            params["source_id"] = str(UUID(source_id))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT *
            FROM processing_jobs
            {where}
            ORDER BY created_at DESC
            LIMIT %(limit)s
        """
        return self._fetch_all(sql, params)

    def job_by_id(self, job_id: str) -> dict[str, Any] | None:
        rows = self._fetch_all("SELECT * FROM processing_jobs WHERE id = %(id)s", {"id": str(UUID(job_id))})
        return rows[0] if rows else None

    def jobs_for_email(self, email_uid: str) -> list[dict[str, Any]]:
        return self.list_jobs(source_id=email_uid)

    def _active_email_analysis_job(self, conn: Any, email_uid: str, analysis_type: str) -> dict[str, Any] | None:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM processing_jobs
                WHERE job_type = 'email_analysis'
                  AND source_type = 'email'
                  AND source_id = %(source_id)s
                  AND status IN ('pending', 'running')
                  AND metadata ->> 'analysis_type' = %(analysis_type)s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                {"source_id": email_uid, "analysis_type": analysis_type},
            )
            row = cursor.fetchone()
            return dict(row) if row is not None else None

    def _fetch_all(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        import psycopg

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return [dict(row) for row in cursor.fetchall()]

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.schemas.mail_decision import MailDecisionNode, MailDecisionRunState, MailDecisionStatus


class PostgresMailDecisionRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url.strip()

    @property
    def enabled(self) -> bool:
        return bool(self.database_url)

    def create_or_get_active_run(self, *, email_message_id: UUID, workflow_version: str) -> MailDecisionRunState:
        self._require_enabled()
        import psycopg

        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT *
                        FROM mail_decision_runs
                        WHERE email_message_id = %(email_message_id)s
                          AND status IN ('queued', 'running', 'review_required')
                        ORDER BY created_at DESC
                        LIMIT 1
                        FOR UPDATE
                        """,
                        {"email_message_id": email_message_id},
                    )
                    row = cursor.fetchone()
                    if row is not None:
                        return self._state_from_row(row)

                    cursor.execute(
                        """
                        SELECT id, content_hash
                        FROM email_messages
                        WHERE id = %(email_message_id)s
                          AND deleted_at IS NULL
                        """,
                        {"email_message_id": email_message_id},
                    )
                    email = cursor.fetchone()
                    if email is None:
                        raise LookupError(f"email not found: {email_message_id}")

                    run_id = uuid4()
                    input_hash = hashlib.sha256(
                        f"{email['content_hash']}:{workflow_version}".encode("utf-8")
                    ).hexdigest()
                    state = MailDecisionRunState(
                        run_id=run_id,
                        email_message_id=email_message_id,
                        workflow_version=workflow_version,
                        status=MailDecisionStatus.QUEUED,
                    )
                    cursor.execute(
                        """
                        INSERT INTO mail_decision_runs (
                            id, email_message_id, workflow_version, status, current_node,
                            input_hash, attempt_count, review_required, state_json,
                            created_at, updated_at
                        )
                        VALUES (
                            %(id)s, %(email_message_id)s, %(workflow_version)s, %(status)s, NULL,
                            %(input_hash)s, 0, FALSE, %(state_json)s,
                            %(created_at)s, %(updated_at)s
                        )
                        """,
                        {
                            "id": run_id,
                            "email_message_id": email_message_id,
                            "workflow_version": workflow_version,
                            "status": state.status.value,
                            "input_hash": input_hash,
                            "state_json": Jsonb(state.model_dump(mode="json")),
                            "created_at": now,
                            "updated_at": now,
                        },
                    )
                    return state

    def get_run(self, run_id: UUID) -> MailDecisionRunState | None:
        self._require_enabled()
        import psycopg

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM mail_decision_runs WHERE id = %(id)s", {"id": run_id})
                row = cursor.fetchone()
                return None if row is None else self._state_from_row(row)

    def get_latest_run_for_email(self, email_message_id: UUID) -> MailDecisionRunState | None:
        self._require_enabled()
        import psycopg

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM mail_decision_runs
                    WHERE email_message_id = %(email_message_id)s
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                    """,
                    {"email_message_id": email_message_id},
                )
                row = cursor.fetchone()
                return None if row is None else self._state_from_row(row)

    def resolve_email_message_id(self, email_ref: str | UUID) -> UUID | None:
        """Resolve a canonical UUID or a Gmail provider message ID to the mailbox UUID."""
        try:
            return UUID(str(email_ref))
        except (TypeError, ValueError, AttributeError):
            provider_message_id = str(email_ref or "").strip()
            if not provider_message_id:
                return None

        self._require_enabled()
        import psycopg

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT m.id
                    FROM email_messages m
                    JOIN email_accounts account ON account.id = m.email_account_id
                    WHERE account.provider = 'gmail'
                      AND m.provider_message_id = %(provider_message_id)s
                      AND m.deleted_at IS NULL
                    ORDER BY m.updated_at DESC, m.id DESC
                    LIMIT 1
                    """,
                    {"provider_message_id": provider_message_id},
                )
                row = cursor.fetchone()
                return UUID(str(row["id"])) if row is not None else None

    def list_steps(self, run_id: UUID) -> list[dict[str, Any]]:
        self._require_enabled()
        import psycopg

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, node_name, attempt_number, status, input_json, output_json,
                           model_name, prompt_version, latency_ms, input_tokens, output_tokens,
                           error_message, started_at, completed_at, created_at
                    FROM mail_decision_steps
                    WHERE mail_decision_run_id = %(run_id)s
                    ORDER BY created_at, attempt_number
                    """,
                    {"run_id": run_id},
                )
                return [dict(row) for row in cursor.fetchall()]

    def load_email_context(self, email_message_id: UUID) -> dict[str, Any]:
        self._require_enabled()
        import psycopg

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT m.id, m.email_account_id, m.sender_name, m.sender_address, m.subject, m.body_text, m.snippet,
                           provider_thread_id, sent_at, received_at, has_attachment, attachment_count,
                           content_hash, account.provider AS account_provider
                    FROM email_messages m
                    JOIN email_accounts account ON account.id = m.email_account_id
                    WHERE m.id = %(id)s AND m.deleted_at IS NULL
                    """,
                    {"id": email_message_id},
                )
                email = cursor.fetchone()
                if email is None:
                    raise LookupError(f"email not found: {email_message_id}")
                cursor.execute(
                    """
                    SELECT id, filename, storage_uri, content_type, file_group, file_size,
                           checksum, processing_status, parse_error
                    FROM email_attachments
                    WHERE email_message_id = %(email_message_id)s
                      AND deleted_at IS NULL
                      AND is_inline IS FALSE
                    ORDER BY created_at
                    """,
                    {"email_message_id": email_message_id},
                )
                return {"email": dict(email), "attachments": [dict(row) for row in cursor.fetchall()]}

    def save_run(self, state: MailDecisionRunState) -> None:
        self._require_enabled()
        import psycopg

        now = datetime.now(timezone.utc)
        started_at = state.started_at
        if state.status == MailDecisionStatus.RUNNING and started_at is None:
            started_at = now
            state.started_at = started_at
        completed_at = state.completed_at
        if state.status in {MailDecisionStatus.COMPLETED, MailDecisionStatus.FAILED} and completed_at is None:
            completed_at = now
            state.completed_at = completed_at

        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE mail_decision_runs
                        SET status = %(status)s,
                            current_node = %(current_node)s,
                            attempt_count = CASE
                                WHEN status = 'queued' AND %(is_running)s THEN attempt_count + 1
                                ELSE attempt_count
                            END,
                            review_required = %(review_required)s,
                            failure_code = %(failure_code)s,
                            failure_message = %(failure_message)s,
                            started_at = COALESCE(started_at, %(started_at)s),
                            completed_at = %(completed_at)s,
                            state_json = %(state_json)s,
                            updated_at = %(updated_at)s
                        WHERE id = %(id)s
                        """,
                        {
                            "id": state.run_id,
                            "status": state.status.value,
                            "is_running": state.status == MailDecisionStatus.RUNNING,
                            "current_node": state.current_node.value if state.current_node else None,
                            "review_required": state.status == MailDecisionStatus.REVIEW_REQUIRED,
                            "failure_code": state.context.get("failure_code"),
                            "failure_message": state.context.get("failure_message"),
                            "started_at": started_at,
                            "completed_at": completed_at,
                            "state_json": Jsonb(state.model_dump(mode="json")),
                            "updated_at": now,
                        },
                    )
                    if cursor.rowcount != 1:
                        raise LookupError(f"mail decision run not found: {state.run_id}")

    def start_step(self, state: MailDecisionRunState, node: MailDecisionNode) -> None:
        self._require_enabled()
        import psycopg

        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT COALESCE(MAX(attempt_number), 0) + 1
                        FROM mail_decision_steps
                        WHERE mail_decision_run_id = %(run_id)s AND node_name = %(node_name)s
                        """,
                        {"run_id": state.run_id, "node_name": node.value},
                    )
                    attempt_number = int(cursor.fetchone()[0])
                    cursor.execute(
                        """
                        INSERT INTO mail_decision_steps (
                            id, mail_decision_run_id, node_name, attempt_number, status,
                            input_json, started_at, created_at
                        )
                        VALUES (
                            %(id)s, %(run_id)s, %(node_name)s, %(attempt_number)s, 'running',
                            %(input_json)s, %(started_at)s, %(created_at)s
                        )
                        """,
                        {
                            "id": uuid4(),
                            "run_id": state.run_id,
                            "node_name": node.value,
                            "attempt_number": attempt_number,
                            "input_json": Jsonb(state.model_dump(mode="json")),
                            "started_at": now,
                            "created_at": now,
                        },
                    )

    def complete_step(self, state: MailDecisionRunState, node: MailDecisionNode) -> None:
        self._finish_step(state, node, status="completed", error_message=None)

    def fail_step(self, state: MailDecisionRunState, node: MailDecisionNode, error: Exception) -> None:
        state.context["failure_code"] = type(error).__name__
        state.context["failure_message"] = str(error)
        self._finish_step(state, node, status="failed", error_message=f"{type(error).__name__}: {error}")

    def _finish_step(
        self,
        state: MailDecisionRunState,
        node: MailDecisionNode,
        *,
        status: str,
        error_message: str | None,
    ) -> None:
        self._require_enabled()
        import psycopg

        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE mail_decision_steps
                        SET status = %(status)s,
                            output_json = %(output_json)s,
                            error_message = %(error_message)s,
                            completed_at = %(completed_at)s,
                            latency_ms = GREATEST(
                                0,
                                FLOOR(EXTRACT(EPOCH FROM (%(completed_at)s - started_at)) * 1000)::INTEGER
                            )
                        WHERE id = (
                            SELECT id
                            FROM mail_decision_steps
                            WHERE mail_decision_run_id = %(run_id)s
                              AND node_name = %(node_name)s
                              AND status = 'running'
                            ORDER BY attempt_number DESC
                            LIMIT 1
                        )
                        """,
                        {
                            "status": status,
                            "output_json": Jsonb(state.model_dump(mode="json")),
                            "error_message": error_message,
                            "completed_at": now,
                            "run_id": state.run_id,
                            "node_name": node.value,
                        },
                    )

    @staticmethod
    def _state_from_row(row: dict[str, Any]) -> MailDecisionRunState:
        payload = dict(row.get("state_json") or {})
        if payload:
            return MailDecisionRunState.model_validate(payload)
        return MailDecisionRunState(
            run_id=row["id"],
            email_message_id=row["email_message_id"],
            workflow_version=row["workflow_version"],
            status=MailDecisionStatus(row["status"]),
            current_node=MailDecisionNode(row["current_node"]) if row.get("current_node") else None,
            started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
        )

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise RuntimeError("CORAMAIL_DATABASE_URL is not configured")

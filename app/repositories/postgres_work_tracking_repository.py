from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class PostgresWorkTrackingRepository:
    def __init__(self, database_url: str, *, overdue_hours: int = 24):
        self.database_url = database_url.strip()
        self.overdue_hours = max(1, overdue_hours)

    @property
    def enabled(self) -> bool:
        return bool(self.database_url)

    def ensure_for_assignment(
        self,
        *,
        email_message_id: UUID,
        routing_assignment_id: UUID,
        assignee_user_id: UUID | None,
        assigned_at: datetime | None,
        actor_user_id: UUID | None = None,
        reason: str = "",
    ) -> dict[str, Any] | None:
        if assignee_user_id is None:
            return None
        import psycopg

        now = datetime.now(timezone.utc)
        assigned_at = assigned_at or now
        due_at = assigned_at + timedelta(hours=self.overdue_hours)
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    row = self._ensure_for_assignment_cursor(
                        cursor,
                        email_message_id=email_message_id,
                        routing_assignment_id=routing_assignment_id,
                        assignee_user_id=assignee_user_id,
                        assigned_at=assigned_at,
                        due_at=due_at,
                    )
                    self._append_event_cursor(
                        cursor,
                        work_item_id=UUID(str(row["id"])),
                        email_message_id=email_message_id,
                        routing_assignment_id=routing_assignment_id,
                        event_type="assigned",
                        actor_user_id=actor_user_id,
                        metadata={"reason": reason} if reason else {},
                        created_at=now,
                    )
                    return dict(row)

    def acknowledge_if_assignee(self, *, email_message_id: UUID, actor_user_id: UUID | None) -> dict[str, Any] | None:
        if actor_user_id is None:
            return self.current_by_email(email_message_id)
        import psycopg

        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT *
                        FROM work_items
                        WHERE email_message_id = %(email_message_id)s
                        FOR UPDATE
                        """,
                        {"email_message_id": email_message_id},
                    )
                    row = cursor.fetchone()
                    if not row:
                        return None
                    if str(row["assignee_user_id"]) != str(actor_user_id):
                        return dict(row)
                    if str(row.get("status") or "") == "assigned" or row.get("acknowledged_at") is None:
                        cursor.execute(
                            """
                            UPDATE work_items
                            SET status = CASE WHEN status = 'assigned' THEN 'acknowledged' ELSE status END,
                                acknowledged_at = COALESCE(acknowledged_at, %(now)s),
                                last_activity_at = %(now)s,
                                updated_at = %(now)s
                            WHERE id = %(id)s
                            RETURNING *
                            """,
                            {"id": row["id"], "now": now},
                        )
                        row = cursor.fetchone()
                        self._append_event_cursor(
                            cursor,
                            work_item_id=UUID(str(row["id"])),
                            email_message_id=email_message_id,
                            routing_assignment_id=UUID(str(row["routing_assignment_id"])),
                            event_type="acknowledged",
                            actor_user_id=actor_user_id,
                            created_at=now,
                        )
                    return dict(row)

    def set_in_progress(
        self,
        *,
        email_message_id: UUID,
        actor_user_id: UUID,
        active: bool,
    ) -> dict[str, Any]:
        import psycopg

        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    row = self._lock_assignee_work(cursor, email_message_id, actor_user_id)
                    status = str(row.get("status") or "")
                    if status not in {"assigned", "acknowledged", "in_progress"}:
                        raise ValueError("회신함 또는 완료 상태는 진행중 토글로 되돌릴 수 없습니다.")
                    next_status = "in_progress" if active else ("acknowledged" if status == "in_progress" else status)
                    if status == next_status:
                        return dict(row)
                    cursor.execute(
                        """
                        UPDATE work_items
                        SET status = %(status)s,
                            acknowledged_at = COALESCE(acknowledged_at, %(now)s),
                            last_activity_at = %(now)s,
                            updated_at = %(now)s
                        WHERE id = %(id)s
                        RETURNING *
                        """,
                        {"id": row["id"], "status": next_status, "now": now},
                    )
                    row = cursor.fetchone()
                    self._append_event_cursor(
                        cursor,
                        work_item_id=UUID(str(row["id"])),
                        email_message_id=email_message_id,
                        routing_assignment_id=UUID(str(row["routing_assignment_id"])),
                        event_type="in_progress_on" if active else "in_progress_off",
                        actor_user_id=actor_user_id,
                        created_at=now,
                    )
                    return dict(row)

    def initiate_reply(self, *, email_message_id: UUID, actor_user_id: UUID) -> dict[str, Any]:
        import psycopg

        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    row = self._lock_assignee_work(cursor, email_message_id, actor_user_id)
                    cursor.execute(
                        """
                        SELECT provider_thread_id
                        FROM email_messages
                        WHERE id = %(email_message_id)s
                        """,
                        {"email_message_id": email_message_id},
                    )
                    email = cursor.fetchone()
                    provider_thread_id = str((email or {}).get("provider_thread_id") or "")
                    if not provider_thread_id:
                        raise ValueError("Gmail thread id가 없어 회신 추적을 시작할 수 없습니다.")
                    cursor.execute(
                        """
                        UPDATE work_items
                        SET status = CASE WHEN status IN ('assigned', 'acknowledged') THEN 'in_progress' ELSE status END,
                            acknowledged_at = COALESCE(acknowledged_at, %(now)s),
                            reply_initiated_at = %(now)s,
                            last_activity_at = %(now)s,
                            updated_at = %(now)s
                        WHERE id = %(id)s
                        RETURNING *
                        """,
                        {"id": row["id"], "now": now},
                    )
                    row = cursor.fetchone()
                    self._append_event_cursor(
                        cursor,
                        work_item_id=UUID(str(row["id"])),
                        email_message_id=email_message_id,
                        routing_assignment_id=UUID(str(row["routing_assignment_id"])),
                        event_type="reply_initiated",
                        actor_user_id=actor_user_id,
                        provider_thread_id=provider_thread_id,
                        created_at=now,
                    )
                    return dict(row) | {"provider_thread_id": provider_thread_id}

    def complete(self, *, email_message_id: UUID, actor_user_id: UUID) -> dict[str, Any]:
        import psycopg

        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    row = self._lock_assignee_work(cursor, email_message_id, actor_user_id)
                    cursor.execute(
                        """
                        UPDATE work_items
                        SET status = 'completed',
                            completed_at = COALESCE(completed_at, %(now)s),
                            last_activity_at = %(now)s,
                            updated_at = %(now)s
                        WHERE id = %(id)s
                        RETURNING *
                        """,
                        {"id": row["id"], "now": now},
                    )
                    row = cursor.fetchone()
                    self._append_event_cursor(
                        cursor,
                        work_item_id=UUID(str(row["id"])),
                        email_message_id=email_message_id,
                        routing_assignment_id=UUID(str(row["routing_assignment_id"])),
                        event_type="completed",
                        actor_user_id=actor_user_id,
                        created_at=now,
                    )
                    return dict(row)

    def write_outbound_and_link(
        self,
        *,
        account_email: str,
        outbound_messages: list[Any],
    ) -> dict[str, int]:
        if not outbound_messages:
            return {"outbound_count": 0, "linked_count": 0}
        import psycopg

        now = datetime.now(timezone.utc)
        linked_count = 0
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    account_id = self._gmail_account_id(cursor, account_email, now)
                    for message in outbound_messages:
                        sent_at = _parse_datetime(getattr(message, "sent_at", ""), now)
                        outbound_id = uuid4()
                        cursor.execute(
                            """
                            INSERT INTO gmail_outbound_messages (
                                id, email_account_id, provider_message_id, provider_thread_id,
                                rfc_message_id, sender_address, recipients, subject, sent_at,
                                linked_work_item_id, created_at, updated_at
                            ) VALUES (
                                %(id)s, %(email_account_id)s, %(provider_message_id)s, %(provider_thread_id)s,
                                %(rfc_message_id)s, %(sender_address)s, %(recipients)s, %(subject)s, %(sent_at)s,
                                NULL, %(created_at)s, %(updated_at)s
                            )
                            ON CONFLICT (email_account_id, provider_message_id) DO UPDATE SET
                                provider_thread_id = EXCLUDED.provider_thread_id,
                                rfc_message_id = EXCLUDED.rfc_message_id,
                                sender_address = EXCLUDED.sender_address,
                                recipients = EXCLUDED.recipients,
                                subject = EXCLUDED.subject,
                                sent_at = EXCLUDED.sent_at,
                                updated_at = EXCLUDED.updated_at
                            RETURNING id, linked_work_item_id
                            """,
                            {
                                "id": outbound_id,
                                "email_account_id": account_id,
                                "provider_message_id": message.provider_message_id,
                                "provider_thread_id": message.provider_thread_id,
                                "rfc_message_id": message.rfc_message_id or None,
                                "sender_address": message.sender_address or None,
                                "recipients": Jsonb(
                                    {
                                        "to": [item.address for item in message.recipients_to],
                                        "cc": [item.address for item in message.recipients_cc],
                                    }
                                ),
                                "subject": message.subject or None,
                                "sent_at": sent_at,
                                "created_at": now,
                                "updated_at": now,
                            },
                        )
                        outbound = cursor.fetchone()
                        if outbound and outbound.get("linked_work_item_id"):
                            continue
                        linked_count += self._link_outbound_cursor(
                            cursor,
                            outbound_id=UUID(str(outbound["id"])),
                            provider_message_id=str(message.provider_message_id),
                            provider_thread_id=str(message.provider_thread_id),
                            sent_at=sent_at,
                            now=now,
                        )
        return {"outbound_count": len(outbound_messages), "linked_count": linked_count}

    def current_by_email(self, email_message_id: UUID) -> dict[str, Any] | None:
        import psycopg

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM work_items WHERE email_message_id = %(id)s", {"id": email_message_id})
                row = cursor.fetchone()
        return dict(row) if row else None

    def _ensure_for_assignment_cursor(
        self,
        cursor: Any,
        *,
        email_message_id: UUID,
        routing_assignment_id: UUID,
        assignee_user_id: UUID,
        assigned_at: datetime,
        due_at: datetime,
    ) -> dict[str, Any]:
        cursor.execute(
            """
            INSERT INTO work_items (
                id, email_message_id, routing_assignment_id, assignee_user_id, status,
                assigned_at, due_at, last_activity_at, created_at, updated_at
            ) VALUES (
                %(id)s, %(email_message_id)s, %(routing_assignment_id)s, %(assignee_user_id)s, 'assigned',
                %(assigned_at)s, %(due_at)s, %(assigned_at)s, %(created_at)s, %(updated_at)s
            )
            ON CONFLICT (email_message_id) DO UPDATE SET
                routing_assignment_id = EXCLUDED.routing_assignment_id,
                status = CASE
                    WHEN work_items.assignee_user_id <> EXCLUDED.assignee_user_id THEN 'assigned'
                    ELSE work_items.status
                END,
                assignee_user_id = EXCLUDED.assignee_user_id,
                assigned_at = EXCLUDED.assigned_at,
                due_at = EXCLUDED.due_at,
                acknowledged_at = CASE
                    WHEN work_items.assignee_user_id <> EXCLUDED.assignee_user_id THEN NULL
                    ELSE work_items.acknowledged_at
                END,
                reply_initiated_at = CASE
                    WHEN work_items.assignee_user_id <> EXCLUDED.assignee_user_id THEN NULL
                    ELSE work_items.reply_initiated_at
                END,
                first_responded_at = CASE
                    WHEN work_items.assignee_user_id <> EXCLUDED.assignee_user_id THEN NULL
                    ELSE work_items.first_responded_at
                END,
                responded_at = CASE
                    WHEN work_items.assignee_user_id <> EXCLUDED.assignee_user_id THEN NULL
                    ELSE work_items.responded_at
                END,
                completed_at = CASE
                    WHEN work_items.assignee_user_id <> EXCLUDED.assignee_user_id THEN NULL
                    ELSE work_items.completed_at
                END,
                last_activity_at = EXCLUDED.assigned_at,
                updated_at = EXCLUDED.updated_at
            RETURNING *
            """,
            {
                "id": uuid4(),
                "email_message_id": email_message_id,
                "routing_assignment_id": routing_assignment_id,
                "assignee_user_id": assignee_user_id,
                "assigned_at": assigned_at,
                "due_at": due_at,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            },
        )
        return dict(cursor.fetchone())

    def _lock_assignee_work(self, cursor: Any, email_message_id: UUID, actor_user_id: UUID) -> dict[str, Any]:
        cursor.execute(
            """
            SELECT *
            FROM work_items
            WHERE email_message_id = %(email_message_id)s
            FOR UPDATE
            """,
            {"email_message_id": email_message_id},
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError("배정된 업무가 없습니다.")
        if str(row["assignee_user_id"]) != str(actor_user_id):
            raise PermissionError("담당자 본인만 업무 상태를 변경할 수 있습니다.")
        return dict(row)

    def _link_outbound_cursor(
        self,
        cursor: Any,
        *,
        outbound_id: UUID,
        provider_message_id: str,
        provider_thread_id: str,
        sent_at: datetime,
        now: datetime,
    ) -> int:
        cursor.execute(
            """
            SELECT wi.*
            FROM work_items wi
            JOIN email_messages m ON m.id = wi.email_message_id
            WHERE m.provider_thread_id = %(provider_thread_id)s
              AND wi.reply_initiated_at IS NOT NULL
              AND wi.reply_initiated_at <= %(sent_at)s
              AND wi.status <> 'completed'
            ORDER BY wi.reply_initiated_at DESC, wi.updated_at DESC
            LIMIT 1
            FOR UPDATE OF wi
            """,
            {"provider_thread_id": provider_thread_id, "sent_at": sent_at},
        )
        row = cursor.fetchone()
        if not row:
            return 0
        cursor.execute(
            """
            UPDATE gmail_outbound_messages
            SET linked_work_item_id = %(work_item_id)s,
                updated_at = %(updated_at)s
            WHERE id = %(outbound_id)s
              AND linked_work_item_id IS NULL
            """,
            {"outbound_id": outbound_id, "work_item_id": row["id"], "updated_at": now},
        )
        if cursor.rowcount != 1:
            return 0
        cursor.execute(
            """
            UPDATE work_items
            SET status = CASE WHEN status = 'completed' THEN status ELSE 'responded' END,
                first_responded_at = COALESCE(first_responded_at, %(sent_at)s),
                responded_at = %(sent_at)s,
                last_activity_at = %(sent_at)s,
                updated_at = %(updated_at)s
            WHERE id = %(id)s
            """,
            {"id": row["id"], "sent_at": sent_at, "updated_at": now},
        )
        self._append_event_cursor(
            cursor,
            work_item_id=UUID(str(row["id"])),
            email_message_id=UUID(str(row["email_message_id"])),
            routing_assignment_id=UUID(str(row["routing_assignment_id"])),
            event_type="response_detected",
            actor_user_id=UUID(str(row["assignee_user_id"])),
            provider_message_id=provider_message_id,
            provider_thread_id=provider_thread_id,
            metadata={"sent_at": sent_at.isoformat()},
            created_at=now,
        )
        return 1

    @staticmethod
    def _append_event_cursor(
        cursor: Any,
        *,
        work_item_id: UUID,
        email_message_id: UUID,
        routing_assignment_id: UUID | None,
        event_type: str,
        actor_user_id: UUID | None = None,
        provider_message_id: str = "",
        provider_thread_id: str = "",
        metadata: dict[str, Any] | None = None,
        created_at: datetime,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO work_events (
                id, work_item_id, email_message_id, routing_assignment_id, event_type,
                actor_user_id, provider_message_id, provider_thread_id, metadata, created_at
            ) VALUES (
                %(id)s, %(work_item_id)s, %(email_message_id)s, %(routing_assignment_id)s, %(event_type)s,
                %(actor_user_id)s, NULLIF(%(provider_message_id)s, ''), NULLIF(%(provider_thread_id)s, ''),
                %(metadata)s, %(created_at)s
            )
            ON CONFLICT DO NOTHING
            """,
            {
                "id": uuid4(),
                "work_item_id": work_item_id,
                "email_message_id": email_message_id,
                "routing_assignment_id": routing_assignment_id,
                "event_type": event_type,
                "actor_user_id": actor_user_id,
                "provider_message_id": provider_message_id,
                "provider_thread_id": provider_thread_id,
                "metadata": Jsonb(metadata or {}),
                "created_at": created_at,
            },
        )

    @staticmethod
    def _gmail_account_id(cursor: Any, account_email: str, now: datetime) -> UUID:
        from app.repositories.postgres_gmail_sync_repository import PostgresGmailSyncRepository

        return UUID(str(PostgresGmailSyncRepository._upsert_account(cursor, account_email, now)))


def _parse_datetime(value: str, default: datetime) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value or ""))
    except ValueError:
        return default
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

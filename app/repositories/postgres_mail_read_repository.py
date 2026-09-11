from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row


class PostgresMailReadRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url.strip()

    @property
    def enabled(self) -> bool:
        return bool(self.database_url)

    def mark_read(self, *, email_message_id: UUID, user_id: UUID | None) -> dict[str, Any] | None:
        if user_id is None or not self.database_url:
            return None
        import psycopg

        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT *
                        FROM mail_read_states
                        WHERE email_message_id = %(email_message_id)s
                          AND user_id = %(user_id)s
                        FOR UPDATE
                        """,
                        {"email_message_id": email_message_id, "user_id": user_id},
                    )
                    existing = cursor.fetchone()
                    was_unread = not existing or existing.get("read_at") is None
                    cursor.execute(
                        """
                        INSERT INTO mail_read_states (
                            email_message_id, user_id, read_at, last_opened_at, created_at, updated_at
                        ) VALUES (
                            %(email_message_id)s, %(user_id)s, %(now)s, %(now)s, %(now)s, %(now)s
                        )
                        ON CONFLICT (email_message_id, user_id) DO UPDATE
                        SET read_at = COALESCE(mail_read_states.read_at, EXCLUDED.read_at),
                            last_opened_at = EXCLUDED.last_opened_at,
                            updated_at = EXCLUDED.updated_at
                        RETURNING *
                        """,
                        {"email_message_id": email_message_id, "user_id": user_id, "now": now},
                    )
                    row = cursor.fetchone()
                    return (dict(row) | {"was_unread": was_unread}) if row else None

    def read_states_for_user(self, *, email_message_ids: list[UUID], user_id: UUID | None) -> dict[str, str]:
        if user_id is None or not email_message_ids or not self.database_url:
            return {}
        import psycopg

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT email_message_id, read_at
                    FROM mail_read_states
                    WHERE user_id = %(user_id)s
                      AND email_message_id = ANY(%(email_message_ids)s::uuid[])
                      AND read_at IS NOT NULL
                    """,
                    {"user_id": user_id, "email_message_ids": email_message_ids},
                )
                return {
                    str(row["email_message_id"]): row["read_at"].isoformat()
                    for row in cursor.fetchall()
                    if row.get("read_at") is not None
                }

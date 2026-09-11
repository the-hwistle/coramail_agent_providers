from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from app.schemas.mail_decision import MailFacts


class PostgresMailFactsRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url.strip()

    def save(self, *, email_message_id: UUID, run_id: UUID, facts: MailFacts, confidence: float | None = None) -> None:
        if not self.database_url:
            raise RuntimeError("CORAMAIL_DATABASE_URL is not configured")
        import psycopg

        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE mail_facts
                        SET is_current = FALSE
                        WHERE email_message_id = %(email_message_id)s AND is_current IS TRUE
                        """,
                        {"email_message_id": email_message_id},
                    )
                    cursor.execute(
                        """
                        INSERT INTO mail_facts (
                            id, email_message_id, mail_decision_run_id, facts_json,
                            confidence, is_current, created_at
                        ) VALUES (
                            %(id)s, %(email_message_id)s, %(run_id)s, %(facts_json)s,
                            %(confidence)s, TRUE, %(created_at)s
                        )
                        """,
                        {
                            "id": uuid4(),
                            "email_message_id": email_message_id,
                            "run_id": run_id,
                            "facts_json": Jsonb(facts.model_dump(mode="json")),
                            "confidence": confidence,
                            "created_at": now,
                        },
                    )

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def file_group_for_fixture(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    groups = {
        ".pdf": "pdf",
        ".xlsx": "spreadsheet",
        ".docx": "document",
        ".png": "image",
        ".txt": "text",
    }
    try:
        return groups[suffix]
    except KeyError as exc:
        raise ValueError(f"unsupported attachment fixture extension: {suffix or '<none>'}") from exc


class SyntheticAttachmentLoader:
    def __init__(self, database_url: str):
        self.database_url = database_url.strip()

    def load(self, dataset: dict[str, Any]) -> int:
        import psycopg

        rows = list(dataset.get("attachments") or [])
        now = datetime.now(timezone.utc)
        by_email: dict[str, int] = {}
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    for attachment in rows:
                        storage_uri = str(attachment.get("storage_uri") or "")
                        if not storage_uri:
                            raise ValueError(f"fixture storage_uri missing: {attachment['id']}")
                        cursor.execute(
                            """
                            INSERT INTO email_attachments (
                                id, email_message_id, filename, file_group, storage_uri, content_type,
                                file_size, processing_status, created_at, updated_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s)
                            ON CONFLICT (id) DO UPDATE SET
                                filename = EXCLUDED.filename,
                                file_group = EXCLUDED.file_group,
                                storage_uri = EXCLUDED.storage_uri,
                                content_type = EXCLUDED.content_type,
                                file_size = EXCLUDED.file_size,
                                processing_status = 'pending',
                                parse_error = NULL,
                                updated_at = EXCLUDED.updated_at
                            """,
                            (
                                attachment["id"],
                                attachment["email_message_id"],
                                attachment["filename"],
                                file_group_for_fixture(str(attachment["filename"])),
                                storage_uri,
                                attachment["content_type"],
                                int(attachment.get("file_size") or 0),
                                now,
                                now,
                            ),
                        )
                        email_id = str(attachment["email_message_id"])
                        by_email[email_id] = by_email.get(email_id, 0) + 1
                    for email_id, count in by_email.items():
                        cursor.execute(
                            """
                            UPDATE email_messages
                            SET has_attachment = TRUE, attachment_count = %s, updated_at = %s
                            WHERE id = %s
                            """,
                            (count, now, email_id),
                        )
        return len(rows)

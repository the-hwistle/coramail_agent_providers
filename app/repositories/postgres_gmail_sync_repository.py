from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from app.integrations.gmail.sync_client import GmailMessageDraft


GMAIL_NAMESPACE = UUID("bf073886-66b8-53d5-88e7-af3c73cd8b93")


@dataclass(frozen=True)
class GmailAttachmentArtifact:
    storage_uri: str
    checksum: str
    error_message: str = ""


@dataclass(frozen=True)
class GmailSyncWriteResult:
    account_id: str
    message_ids: list[str]
    changed_message_ids: list[str]
    message_count: int
    attachment_count: int


class PostgresGmailSyncRepository:
    """Persist Gmail provider data using the canonical mailbox UUID contract."""

    def __init__(
        self,
        database_url: str,
        project_dir: Path,
        *,
        provider: str = "gmail",
        credentials_reference: str = "runtime:gmail-token",
        namespace: UUID = GMAIL_NAMESPACE,
    ):
        self.database_url = database_url
        self.project_dir = project_dir
        self.provider = provider.strip().casefold() or "gmail"
        self.credentials_reference = credentials_reference.strip() or f"runtime:{self.provider}"
        self.namespace = namespace

    @property
    def enabled(self) -> bool:
        return bool(self.database_url)

    def account_status(self) -> dict[str, Any]:
        if not self.enabled:
            return {}

        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        account.id,
                        account.email_address,
                        account.status,
                        account.last_synced_at,
                        account.last_error,
                        COUNT(message.id) FILTER (WHERE message.deleted_at IS NULL) AS message_count
                    FROM email_accounts account
                    LEFT JOIN email_messages message
                      ON message.email_account_id = account.id
                    WHERE account.provider = %(provider)s
                    GROUP BY account.id
                    ORDER BY account.last_synced_at DESC NULLS LAST, account.updated_at DESC
                    LIMIT 1
                    """,
                    {"provider": self.provider},
                )
                row = cursor.fetchone()
        return dict(row) if row else {}

    def write_messages(
        self,
        *,
        account_email: str,
        messages: list[GmailMessageDraft],
        artifacts: dict[tuple[str, str], GmailAttachmentArtifact],
    ) -> GmailSyncWriteResult:
        if not self.enabled:
            raise RuntimeError("PostgreSQL Gmail persistence is not configured")

        import psycopg
        from psycopg.rows import dict_row

        now = datetime.now(timezone.utc)
        message_ids: list[str] = []
        changed_message_ids: list[str] = []
        attachment_count = 0
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    account_id = self._upsert_account(cursor, account_email, now)
                    for message in messages:
                        message_id, changed = self._upsert_message(cursor, account_id, message, now)
                        message_ids.append(message_id)
                        if changed:
                            changed_message_ids.append(message_id)
                        self._replace_recipients(cursor, message_id, message, now)
                        attachment_count += self._upsert_attachments(cursor, message_id, message, artifacts, now)
                    cursor.execute(
                        """
                        UPDATE email_accounts
                        SET status = 'active',
                            last_synced_at = %(last_synced_at)s,
                            last_error = NULL,
                            updated_at = %(updated_at)s
                        WHERE id = %(id)s
                        """,
                        {"id": account_id, "last_synced_at": now, "updated_at": now},
                    )
        return GmailSyncWriteResult(
            account_id=account_id,
            message_ids=message_ids,
            changed_message_ids=changed_message_ids,
            message_count=len(message_ids),
            attachment_count=attachment_count,
        )

    def message_ids_needing_attachment_analysis(self, message_ids: list[str]) -> list[str]:
        if not message_ids:
            return []
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT a.email_message_id
                    FROM email_attachments a
                    LEFT JOIN attachment_analysis_results ar
                      ON ar.attachment_id = a.id
                     AND ar.analysis_type = 'document_understanding'
                     AND ar.is_current IS TRUE
                    WHERE a.email_message_id = ANY(%(message_ids)s::uuid[])
                      AND a.deleted_at IS NULL
                      AND a.is_inline IS FALSE
                      AND a.processing_status = 'downloaded'
                      AND ar.id IS NULL
                    """,
                    {"message_ids": message_ids},
                )
                return [str(row["email_message_id"]) for row in cursor.fetchall()]

    def _upsert_account(self, cursor: Any, account_email: str, now: datetime) -> str:
        proposed_id = str(uuid5(self.namespace, f"account:{self.provider}:{account_email.casefold()}"))
        cursor.execute(
            """
            INSERT INTO email_accounts (
                id, provider, email_address, display_name, status, credentials_reference,
                sync_cursor, last_synced_at, last_error, created_at, updated_at
            )
            VALUES (
                %(id)s, %(provider)s, %(email_address)s, %(display_name)s, 'active',
                %(credentials_reference)s, NULL, %(last_synced_at)s, NULL, %(created_at)s, %(updated_at)s
            )
            ON CONFLICT (provider, email_address) DO UPDATE
            SET status = 'active',
                credentials_reference = EXCLUDED.credentials_reference,
                last_synced_at = EXCLUDED.last_synced_at,
                last_error = NULL,
                updated_at = EXCLUDED.updated_at
            RETURNING id
            """,
            {
                "id": proposed_id,
                "provider": self.provider,
                "email_address": account_email,
                "display_name": account_email,
                "credentials_reference": self.credentials_reference,
                "last_synced_at": now,
                "created_at": now,
                "updated_at": now,
            },
        )
        return str(cursor.fetchone()["id"])

    def _upsert_message(
        self,
        cursor: Any,
        account_id: str,
        message: GmailMessageDraft,
        now: datetime,
    ) -> tuple[str, bool]:
        content_hash = self._message_hash(message)
        visible_attachments = [attachment for attachment in message.attachments if not attachment.is_inline]
        cursor.execute(
            """
            SELECT id, content_hash
            FROM email_messages
            WHERE email_account_id = %(email_account_id)s
              AND provider_message_id = %(provider_message_id)s
            """,
            {"email_account_id": account_id, "provider_message_id": message.provider_message_id},
        )
        existing = cursor.fetchone()
        message_id = (
            str(existing["id"])
            if existing is not None
            else str(uuid5(self.namespace, f"message:{account_id}:{message.provider_message_id}"))
        )
        changed = existing is None or str(existing["content_hash"]) != content_hash
        sent_at = self._datetime_or_now(message.sent_at, now)
        received_at = self._datetime_or_now(message.received_at, sent_at)
        cursor.execute(
            """
            INSERT INTO email_messages (
                id, email_account_id, provider_message_id, provider_thread_id, rfc_message_id,
                in_reply_to, "references", sender_name, sender_address, subject, subject_normalized,
                body_text, body_html, snippet, sent_at, received_at, has_attachment, attachment_count,
                processing_status, content_hash, created_at, updated_at, deleted_at
            )
            VALUES (
                %(id)s, %(email_account_id)s, %(provider_message_id)s, %(provider_thread_id)s,
                %(rfc_message_id)s, NULL, NULL, %(sender_name)s, %(sender_address)s, %(subject)s,
                %(subject_normalized)s, %(body_text)s, %(body_html)s, %(snippet)s, %(sent_at)s,
                %(received_at)s, %(has_attachment)s, %(attachment_count)s, 'received',
                %(content_hash)s, %(created_at)s, %(updated_at)s, NULL
            )
            ON CONFLICT (email_account_id, provider_message_id) DO UPDATE
            SET provider_thread_id = EXCLUDED.provider_thread_id,
                rfc_message_id = EXCLUDED.rfc_message_id,
                sender_name = EXCLUDED.sender_name,
                sender_address = EXCLUDED.sender_address,
                subject = EXCLUDED.subject,
                subject_normalized = EXCLUDED.subject_normalized,
                body_text = EXCLUDED.body_text,
                body_html = EXCLUDED.body_html,
                snippet = EXCLUDED.snippet,
                sent_at = EXCLUDED.sent_at,
                received_at = EXCLUDED.received_at,
                has_attachment = EXCLUDED.has_attachment,
                attachment_count = EXCLUDED.attachment_count,
                processing_status = CASE
                    WHEN email_messages.content_hash <> EXCLUDED.content_hash THEN 'received'
                    ELSE email_messages.processing_status
                END,
                content_hash = EXCLUDED.content_hash,
                updated_at = EXCLUDED.updated_at,
                deleted_at = NULL
            """,
            {
                "id": message_id,
                "email_account_id": account_id,
                "provider_message_id": message.provider_message_id,
                "provider_thread_id": message.provider_thread_id or None,
                "rfc_message_id": message.rfc_message_id or None,
                "sender_name": message.sender_name or None,
                "sender_address": message.sender_address or "unknown@invalid.local",
                "subject": message.subject or "(제목 없음)",
                "subject_normalized": " ".join((message.subject or "").split()).casefold(),
                "body_text": message.body_text or message.snippet or "",
                "body_html": message.body_html or None,
                "snippet": message.snippet or None,
                "sent_at": sent_at,
                "received_at": received_at,
                "has_attachment": bool(visible_attachments),
                "attachment_count": len(visible_attachments),
                "content_hash": content_hash,
                "created_at": now,
                "updated_at": now,
            },
        )
        return message_id, changed

    def _replace_recipients(self, cursor: Any, message_id: str, message: GmailMessageDraft, now: datetime) -> None:
        current_keys: set[tuple[str, str]] = set()
        for recipient_type, recipients in (("to", message.recipients_to), ("cc", message.recipients_cc)):
            for recipient in recipients:
                address = recipient.address.strip()
                if not address:
                    continue
                key = (recipient_type, address.casefold())
                if key in current_keys:
                    continue
                current_keys.add(key)
                recipient_id = str(uuid5(self.namespace, f"recipient:{message_id}:{recipient_type}:{address.casefold()}"))
                cursor.execute(
                    """
                    INSERT INTO email_recipients (
                        id, email_message_id, recipient_type, name, address, created_at
                    )
                    VALUES (%(id)s, %(email_message_id)s, %(recipient_type)s, %(name)s, %(address)s, %(created_at)s)
                    ON CONFLICT (email_message_id, recipient_type, address) DO UPDATE
                    SET name = EXCLUDED.name
                    """,
                    {
                        "id": recipient_id,
                        "email_message_id": message_id,
                        "recipient_type": recipient_type,
                        "name": recipient.name or None,
                        "address": address,
                        "created_at": now,
                    },
                )

    def _upsert_attachments(
        self,
        cursor: Any,
        message_id: str,
        message: GmailMessageDraft,
        artifacts: dict[tuple[str, str], GmailAttachmentArtifact],
        now: datetime,
    ) -> int:
        active_attachment_ids: list[str] = []
        for index, attachment in enumerate(message.attachments):
            provider_key = attachment.provider_attachment_id or f"inline-{index}"
            artifact = artifacts.get((message.provider_message_id, provider_key))
            attachment_id = str(uuid5(self.namespace, f"attachment:{message_id}:{provider_key}"))
            active_attachment_ids.append(attachment_id)
            storage_uri = artifact.storage_uri if artifact else ""
            checksum = artifact.checksum if artifact and artifact.checksum else None
            error_message = artifact.error_message if artifact else "attachment download result missing"
            cursor.execute(
                """
                INSERT INTO email_attachments (
                    id, email_message_id, provider_attachment_id, filename, storage_uri, content_type,
                    content_id, content_disposition, file_group, file_size, checksum, is_inline,
                    document_category_id, processing_status, parse_error, created_at, updated_at, deleted_at
                )
                VALUES (
                    %(id)s, %(email_message_id)s, %(provider_attachment_id)s, %(filename)s, %(storage_uri)s,
                    %(content_type)s, %(content_id)s, %(content_disposition)s, %(file_group)s, %(file_size)s,
                    %(checksum)s, %(is_inline)s, NULL, %(processing_status)s, %(parse_error)s,
                    %(created_at)s, %(updated_at)s, NULL
                )
                ON CONFLICT (id) DO UPDATE
                SET filename = EXCLUDED.filename,
                    storage_uri = EXCLUDED.storage_uri,
                    content_type = EXCLUDED.content_type,
                    content_id = EXCLUDED.content_id,
                    content_disposition = EXCLUDED.content_disposition,
                    file_group = EXCLUDED.file_group,
                    file_size = EXCLUDED.file_size,
                    checksum = EXCLUDED.checksum,
                    is_inline = EXCLUDED.is_inline,
                    processing_status = EXCLUDED.processing_status,
                    parse_error = EXCLUDED.parse_error,
                    updated_at = EXCLUDED.updated_at,
                    deleted_at = NULL
                """,
                {
                    "id": attachment_id,
                    "email_message_id": message_id,
                    "provider_attachment_id": attachment.provider_attachment_id or None,
                    "filename": Path(attachment.filename).name or "attachment",
                    "storage_uri": storage_uri,
                    "content_type": attachment.content_type or "application/octet-stream",
                    "content_id": attachment.content_id or None,
                    "content_disposition": attachment.content_disposition or None,
                    "file_group": self._file_group(attachment.content_type, attachment.filename),
                    "file_size": attachment.file_size,
                    "checksum": checksum,
                    "is_inline": attachment.is_inline,
                    "processing_status": "downloaded" if artifact and not error_message else "failed",
                    "parse_error": error_message or None,
                    "created_at": now,
                    "updated_at": now,
                },
            )
        if active_attachment_ids:
            cursor.execute(
                """
                UPDATE email_attachments
                SET deleted_at = %(deleted_at)s,
                    processing_status = 'superseded',
                    updated_at = %(updated_at)s
                WHERE email_message_id = %(email_message_id)s
                  AND deleted_at IS NULL
                  AND NOT (id = ANY(%(active_attachment_ids)s::uuid[]))
                """,
                {
                    "email_message_id": message_id,
                    "active_attachment_ids": active_attachment_ids,
                    "deleted_at": now,
                    "updated_at": now,
                },
            )
        else:
            cursor.execute(
                """
                UPDATE email_attachments
                SET deleted_at = %(deleted_at)s,
                    processing_status = 'superseded',
                    updated_at = %(updated_at)s
                WHERE email_message_id = %(email_message_id)s
                  AND deleted_at IS NULL
                """,
                {"email_message_id": message_id, "deleted_at": now, "updated_at": now},
            )
        return len(message.attachments)

    @staticmethod
    def _message_hash(message: GmailMessageDraft) -> str:
        raw = "\n".join(
            [
                message.provider_message_id,
                message.provider_thread_id,
                message.rfc_message_id,
                message.sender_address,
                message.subject,
                message.body_text,
                message.body_html,
                message.snippet,
                message.sent_at,
                "|".join(
                    (
                        f"{item.provider_attachment_id}:{item.filename}:{item.file_size}:"
                        f"{item.is_inline}:{item.content_id}:{item.content_disposition}"
                    )
                    for item in message.attachments
                ),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()

    @staticmethod
    def _datetime_or_now(value: str, fallback: datetime) -> datetime:
        try:
            parsed = datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return fallback
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)

    @staticmethod
    def _file_group(content_type: str, filename: str) -> str:
        suffix = Path(filename).suffix.casefold()
        if content_type == "application/pdf" or suffix == ".pdf":
            return "pdf"
        if content_type.startswith("image/"):
            return "image"
        if suffix in {".xlsx", ".xlsm", ".xls"}:
            return "spreadsheet"
        if suffix in {".docx", ".doc"}:
            return "document"
        if content_type.startswith("text/"):
            return "text"
        return "other"

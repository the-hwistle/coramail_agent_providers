from __future__ import annotations

import time
import hashlib
import re
from pathlib import Path
from threading import Lock
from typing import Any

from app.integrations.naver.sync_client import NaverImapConfig, NaverSyncError, fetch_inbox_message_drafts, probe_inbox
from app.repositories.postgres_gmail_sync_repository import GmailAttachmentArtifact, PostgresGmailSyncRepository


class NaverMailboxService:
    """Synchronize Naver Mail into the provider-isolated PostgreSQL mailbox."""

    def __init__(
        self,
        project_dir: Path,
        *,
        postgres_mailbox: Any | None = None,
        sync_repository: PostgresGmailSyncRepository | None = None,
    ) -> None:
        self.project_dir = project_dir
        self.postgres_mailbox = postgres_mailbox
        self.sync_repository = sync_repository
        self._lock = Lock()
        self._last_error = ""
        self._last_synced_at = 0.0
        self._message_count = 0
        self._preview_count = 0
        self._version = "naver:idle"

    def list_emails(self, *, q: str = "", category: str = "", limit: int | None = None) -> list[dict[str, Any]]:
        if self.postgres_mailbox is None:
            return []
        return self.postgres_mailbox.list_emails(q=q, category=category, limit=limit)

    def category_order(self) -> list[str]:
        return ["발주", "문의", "서비스", "기술", "기타", "미분류"]

    def search_documents(self) -> list[dict[str, Any]]:
        if self.postgres_mailbox is None:
            return []
        return self.postgres_mailbox.search_documents()

    def document_type_sections(self, *, q: str = "", limit_per_section: int = 8) -> list[dict[str, Any]]:
        if self.postgres_mailbox is None:
            return []
        return self.postgres_mailbox.document_type_sections(q=q, limit_per_section=limit_per_section)

    def email_detail(self, index: int) -> dict[str, Any] | None:
        if self.postgres_mailbox is None:
            return None
        return self.postgres_mailbox.email_detail(index)

    def email_detail_by_uid(self, email_uid: str) -> dict[str, Any] | None:
        if self.postgres_mailbox is None:
            return None
        return self.postgres_mailbox.email_detail_by_uid(email_uid)

    def attachment_path(self, email_index: int, attachment_index: int) -> tuple[Path, str, str] | None:
        if self.postgres_mailbox is None:
            return None
        return self.postgres_mailbox.attachment_path(email_index, attachment_index)

    def attachment_path_by_uid(
        self,
        email_uid: str,
        attachment_index: int,
        *,
        include_inline: bool = False,
    ) -> tuple[Path, str, str] | None:
        if self.postgres_mailbox is None:
            return None
        return self.postgres_mailbox.attachment_path_by_uid(email_uid, attachment_index, include_inline=include_inline)

    def sync(self) -> dict[str, Any]:
        started_at = time.time()
        config = NaverImapConfig.from_env()
        try:
            result = fetch_inbox_message_drafts(config)
            messages = list(result.get("messages") or [])
            persisted = self._persist_messages(config.email_address, messages)
        except NaverSyncError as exc:
            return self._record_failure(str(exc))
        except Exception as exc:
            return self._record_failure(f"{type(exc).__name__}: {exc}")
        with self._lock:
            self._last_error = ""
            self._last_synced_at = time.time()
            self._message_count = int(result.get("matched_message_count") or 0)
            self._preview_count = len(messages)
            self._version = f"naver:ok:{int(self._last_synced_at * 1000)}"
        return {
            "status": "ok",
            "message_count": self._message_count,
            "preview_count": self._preview_count,
            "persisted_message_count": persisted.get("message_count", 0),
            "changed_message_count": persisted.get("changed_message_count", 0),
            "attachment_count": persisted.get("attachment_count", 0),
            "account": config.email_address,
            "elapsed_ms": round((time.time() - started_at) * 1000),
        }

    def probe(self) -> dict[str, Any]:
        config = NaverImapConfig.from_env()
        return probe_inbox(config)

    def status(self) -> dict[str, Any]:
        config = NaverImapConfig.from_env()
        with self._lock:
            return {
                "account": config.email_address or "Naver Mail 계정 미설정",
                "last_error": self._last_error,
                "last_synced_at": self._last_synced_at,
                "message_count": self._message_count,
                "preview_count": self._preview_count,
                "version": self._version,
            }

    def public_status(self) -> dict[str, Any]:
        config = NaverImapConfig.from_env()
        status = self.status()
        configured = bool(config.email_address and config.app_password)
        connected = configured and not status["last_error"] and status["version"].startswith("naver:ok:")
        return {
            "connected": connected,
            "has_client_config": configured,
            "email_address": config.email_address,
            "imap_username": config.login_username if config.email_address else "",
            "status": "active" if connected else "ready" if configured else "not_connected",
            "last_synced_at": status["last_synced_at"],
            "last_sync_status": "ok" if connected else "ready" if configured else "",
            "last_sync_error": status["last_error"],
            "token_source": "app-password" if configured else "",
            "has_send_token": configured,
            "can_disconnect": False,
            "imap_host": config.imap_host,
            "imap_port": config.imap_port,
            "smtp_host": config.smtp_host,
            "smtp_port": config.smtp_port,
            "message_count": status["message_count"],
            "preview_count": status["preview_count"],
        }

    def _record_failure(self, message: str) -> dict[str, Any]:
        with self._lock:
            self._last_error = message
            self._version = f"naver:error:{int(time.time() * 1000)}"
        return {"status": "error", "message": message}

    def _persist_messages(self, account: str, messages: list[Any]) -> dict[str, int]:
        if self.sync_repository is None or not self.sync_repository.enabled:
            return {"message_count": 0, "changed_message_count": 0, "attachment_count": 0}
        artifacts = self._store_attachments(messages)
        write_result = self.sync_repository.write_messages(
            account_email=account,
            messages=messages,
            artifacts=artifacts,
        )
        return {
            "message_count": write_result.message_count,
            "changed_message_count": len(write_result.changed_message_ids),
            "attachment_count": write_result.attachment_count,
        }

    def _store_attachments(self, messages: list[Any]) -> dict[tuple[str, str], GmailAttachmentArtifact]:
        artifacts: dict[tuple[str, str], GmailAttachmentArtifact] = {}
        root = self.project_dir / "data" / "runtime" / "naver_attachments"
        for message in messages:
            message_dir = root / hashlib.sha256(message.provider_message_id.encode("utf-8")).hexdigest()[:20]
            for index, attachment in enumerate(message.attachments):
                provider_key = attachment.provider_attachment_id or f"inline-{index}"
                key = (message.provider_message_id, provider_key)
                safe_name = self._safe_filename(attachment.filename)
                prefix = hashlib.sha256(provider_key.encode("utf-8")).hexdigest()[:16]
                path = message_dir / f"{prefix}-{safe_name}"
                relative_path = path.relative_to(self.project_dir).as_posix()
                content = attachment.content_bytes or b""
                if not content:
                    artifacts[key] = GmailAttachmentArtifact(
                        storage_uri=relative_path,
                        checksum="",
                        error_message="Naver IMAP attachment payload is empty.",
                    )
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix(path.suffix + ".part")
                temporary.write_bytes(content)
                temporary.replace(path)
                artifacts[key] = GmailAttachmentArtifact(
                    storage_uri=relative_path,
                    checksum=hashlib.sha256(content).hexdigest(),
                )
        return artifacts

    @staticmethod
    def _safe_filename(filename: str) -> str:
        name = Path(filename).name.strip() or "attachment"
        safe = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", name)
        return safe[:180] or "attachment"

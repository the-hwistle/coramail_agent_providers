from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import textwrap
import time
from pathlib import Path
from threading import Lock, Thread
from typing import Any
from uuid import UUID

from app.integrations.gmail.sync_client import (
    GmailMessageDraft,
    GmailSyncConfig,
    GmailSyncUnavailable,
    build_gmail_service,
    fetch_attachment_bytes,
    fetch_inbox_messages,
    fetch_sent_messages,
    gmail_profile_email,
    send_gmail_message,
)
from app.integrations.gmail.attachment_utils import is_visible_attachment
from app.mail_content import email_body_srcdoc, plain_email_body_srcdoc
from app.repositories.gmail_account_repository import GmailAccountRepository
from app.repositories.postgres_gmail_sync_repository import (
    GmailAttachmentArtifact,
    PostgresGmailSyncRepository,
)
from app.services.demo_mail_service import DemoMailService


logger = logging.getLogger(__name__)


class GmailMailboxService:
    """Synchronize Gmail into the canonical mailbox and expose the shared UI contract."""

    def __init__(
        self,
        project_dir: Path,
        account_repository: GmailAccountRepository | None = None,
        *,
        postgres_mailbox: Any | None = None,
        sync_repository: PostgresGmailSyncRepository | None = None,
        routing_repository: Any | None = None,
        job_repository: Any | None = None,
        analysis_worker: Any | None = None,
        work_tracking_repository: Any | None = None,
    ):
        self.project_dir = project_dir
        self.account_repository = account_repository or GmailAccountRepository(project_dir)
        self.postgres_mailbox = postgres_mailbox
        self.sync_repository = sync_repository
        self.routing_repository = routing_repository
        self.job_repository = job_repository
        self.analysis_worker = analysis_worker
        self.work_tracking_repository = work_tracking_repository
        self._lock = Lock()
        self._messages: list[GmailMessageDraft] = []
        self._synced_at = 0.0
        self._last_error = ""
        self._account = ""
        self._version = "gmail:empty"
        self._analysis_thread: Thread | None = None
        self._auto_analysis_lock = Lock()

    def list_emails(self, *, q: str = "", category: str = "", limit: int | None = None) -> list[dict[str, Any]]:
        if self.postgres_mailbox is not None:
            rows = self.postgres_mailbox.list_emails(q=q, category=category, limit=limit)
            if rows or self._last_error:
                self._run_missing_attachment_analysis_for_rows(rows)
                return rows
        if not self.account_repository.public_status().get("connected"):
            return []
        if not self._messages and not self._last_error:
            self.sync()
        if self.postgres_mailbox is not None:
            rows = self.postgres_mailbox.list_emails(q=q, category=category, limit=limit)
            self._run_missing_attachment_analysis_for_rows(rows)
            return rows
        with self._lock:
            rows = [self._message_row(message, index) for index, message in enumerate(self._messages)]
        query = " ".join(q.split()).casefold()
        if query:
            rows = [
                row
                for row in rows
                if query
                in " ".join(
                    [
                        str(row.get("sender_name", "")),
                        str(row.get("sender_address", "")),
                        str(row.get("subject", "")),
                        str(row.get("body_preview", "")),
                    ]
                ).casefold()
            ]
        if category:
            rows = [row for row in rows if row.get("mail_category") == category]
        return rows[:limit] if limit else rows

    def category_order(self) -> list[str]:
        return ["발주", "문의", "서비스", "기술", "기타", "미분류"]

    def search_documents(self) -> list[dict[str, Any]]:
        if self.postgres_mailbox is not None:
            return self.postgres_mailbox.search_documents()
        documents: list[dict[str, Any]] = []
        for row in self.list_emails():
            detail = self.email_detail_by_uid(str(row.get("email_uid") or ""))
            if detail is None:
                continue
            documents.append(
                {
                    "email_uid": row.get("email_uid"),
                    "source_type": "mail",
                    "source": row.get("subject") or "(제목 없음)",
                    "title": row.get("subject") or "",
                    "category": row.get("mail_category") or "",
                    "document_category": "",
                    "preview": detail.get("body") or row.get("body_preview") or "",
                    "sender": f"{row.get('sender_name') or ''} {row.get('sender_address') or ''}",
                    "business_refs": [],
                    "vessel_names": [],
                    "received_at": row.get("received_at") or "",
                    "detail_url": f"/ui/inbox?email_uid={row.get('email_uid') or ''}",
                }
            )
        return documents

    def document_type_sections(self, *, q: str = "", limit_per_section: int = 8) -> list[dict[str, Any]]:
        if self.postgres_mailbox is not None:
            return self.postgres_mailbox.document_type_sections(q=q, limit_per_section=limit_per_section)
        return []

    def attachments_for_messages_payload(self, email_uids: list[str]) -> dict[str, list[dict[str, Any]]]:
        if self.postgres_mailbox is not None and hasattr(self.postgres_mailbox, "attachments_for_messages_payload"):
            return self.postgres_mailbox.attachments_for_messages_payload(email_uids)
        return {email_uid: [] for email_uid in email_uids}

    def email_detail(self, index: int) -> dict[str, Any] | None:
        if self.postgres_mailbox is not None:
            return self.postgres_mailbox.email_detail(index)
        with self._lock:
            if index < 0 or index >= len(self._messages):
                return None
            message = self._messages[index]
        return self._email_detail_payload(message, index)

    def email_detail_by_uid(self, email_uid: str) -> dict[str, Any] | None:
        if self.postgres_mailbox is not None:
            return self.postgres_mailbox.email_detail_by_uid(email_uid)
        if not self._messages and not self._last_error:
            self.sync()
        with self._lock:
            for index, message in enumerate(self._messages):
                if message.provider_message_id == email_uid:
                    return self._email_detail_payload(message, index)
        return None

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
        return self.postgres_mailbox.attachment_path_by_uid(
            email_uid,
            attachment_index,
            include_inline=include_inline,
        )

    def trash_email(self, email_uid: str) -> bool:
        if self.postgres_mailbox is None:
            return False
        provider_message_id = self.postgres_mailbox.repository.provider_message_id(email_uid)
        if not provider_message_id:
            return False
        service = build_gmail_service(self._config(), allow_interactive_auth=False)
        service.users().messages().trash(userId="me", id=provider_message_id).execute()
        self.postgres_mailbox.repository.mark_trashed(email_uid)
        return True

    def start_manual_route_delivery(self, email_uid: str) -> dict[str, Any]:
        if self.postgres_mailbox is None or self.routing_repository is None:
            raise RuntimeError("수동 라우팅은 PostgreSQL Gmail 메일함에서만 사용할 수 있습니다.")
        email = self.postgres_mailbox.email_detail_by_uid(email_uid)
        if email is None:
            raise RuntimeError("이메일을 찾을 수 없습니다.")
        email_message_id = UUID(str(email.get("email_uid") or ""))
        assignment = self.routing_repository.current_assignment(email_message_id)
        if not assignment or not assignment.get("assignee_user_id") or not assignment.get("assignee_email"):
            raise RuntimeError("담당자 이메일이 확정되지 않아 수동 라우팅을 시작할 수 없습니다.")
        latest = self.routing_repository.latest_manual_forward_notification(email_message_id)
        if str(latest.get("status") or "") == "pending":
            return {"status": "pending", "notification_id": str(latest.get("id") or "")}

        subject = self._manual_forward_subject(email)
        body = self._manual_forward_body(email)
        assignee_user_id = UUID(str(assignment["assignee_user_id"]))
        notification_id = self.routing_repository.create_manual_forward_notification(
            email_message_id=email_message_id,
            recipient_user_id=assignee_user_id,
            title=subject,
            body=body[:10000],
            idempotency_key=f"manual-route:{email_message_id}:{int(time.time() * 1000000)}",
        )
        worker = Thread(
            target=self._manual_route_worker,
            name=f"manual-route-{email_message_id}",
            args=(notification_id, email_message_id, assignee_user_id, str(assignment["assignee_email"]), subject, body, email),
            daemon=True,
        )
        worker.start()
        return {"status": "pending", "notification_id": str(notification_id)}

    def _manual_route_worker(
        self,
        notification_id: UUID,
        email_message_id: UUID,
        assignee_user_id: UUID,
        assignee_email: str,
        subject: str,
        body: str,
        email: dict[str, Any],
    ) -> None:
        try:
            service = build_gmail_service(self._config(), allow_interactive_auth=False)
            response = send_gmail_message(
                service,
                assignee_email,
                subject,
                body,
                attachments=self._manual_forward_attachments(email),
            )
            self.routing_repository.mark_manual_forward_sent(
                notification_id=notification_id,
                email_message_id=email_message_id,
                assignee_user_id=assignee_user_id,
                provider_message_id=str(response.get("id") or ""),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Manual route delivery failed. email_uid=%s", email_message_id)
            self.routing_repository.mark_manual_forward_failed(
                notification_id=notification_id,
                error_message=f"{type(exc).__name__}: {exc}",
            )

    @staticmethod
    def _manual_forward_subject(email: dict[str, Any]) -> str:
        subject = str(email.get("subject") or "").strip() or "(no subject)"
        return f"Fwd: {subject}"

    @staticmethod
    def _manual_forward_body(email: dict[str, Any]) -> str:
        classification = email.get("classification") if isinstance(email.get("classification"), dict) else {}
        business_refs = classification.get("business_refs") if isinstance(classification.get("business_refs"), list) else []
        vessel_names = classification.get("vessel_names") if isinstance(classification.get("vessel_names"), list) else []
        return textwrap.dedent(
            f"""
            전달 대상: {email.get('assignee_name') or email.get('assignee_email') or '-'}
            라우팅 근거: {classification.get('reasoning_summary') or classification.get('routing_resolution') or '-'}

            ---------- Forwarded message ----------
            From: {email.get('sender_name') or email.get('sender_address') or '-'}
            Date: {email.get('date') or email.get('received_at') or email.get('created_at') or '-'}
            Subject: {email.get('subject') or '(no subject)'}
            To: {email.get('to') or '-'}
            Ref No.: {', '.join(str(ref) for ref in business_refs[:8]) or '-'}
            Vessel: {', '.join(str(vessel) for vessel in vessel_names[:6]) or '-'}

            {email.get('body') or email.get('body_preview') or '(본문 없음)'}
            """
        ).strip()

    @staticmethod
    def _manual_forward_attachments(email: dict[str, Any]) -> list[dict[str, Any]]:
        attachments: list[dict[str, Any]] = []
        for attachment in email.get("attachments") or []:
            if not isinstance(attachment, dict):
                continue
            path = attachment.get("path")
            if not path:
                continue
            attachments.append(
                {
                    "path": str(path),
                    "filename": str(attachment.get("filename") or "attachment"),
                    "content_type": str(attachment.get("content_type") or ""),
                }
            )
        return attachments

    def _email_detail_payload(self, message: GmailMessageDraft, index: int) -> dict[str, Any]:
        row = self._message_row(message, index)
        visible_attachments = [attachment for attachment in message.attachments if is_visible_attachment(attachment)]
        row.update(
            {
                "body": message.body_text,
                "body_html_srcdoc": self._body_html_srcdoc(message),
                "attachments": [
                    self._attachment_payload(attachment, index, attachment_index)
                    for attachment_index, attachment in enumerate(visible_attachments)
                ],
                "classification": self._classification_payload(message),
                "executive_summary_sections": [],
            }
        )
        return row

    def sync(self) -> dict[str, Any]:
        started_at = time.time()
        try:
            service = build_gmail_service(self._config(), allow_interactive_auth=False)
            account = gmail_profile_email(service)
            messages = fetch_inbox_messages(
                service,
                max_results=self._max_results(),
                query=os.getenv("CORAMAIL_GMAIL_QUERY", "").strip(),
                max_body_length=self._config().max_body_length,
            )
            persisted = self._persist_messages(service, account, messages)
        except GmailSyncUnavailable as exc:
            return self._record_failure(str(exc))
        except Exception as exc:
            return self._record_failure(f"{type(exc).__name__}: {exc}")

        with self._lock:
            self._messages = messages
            self._account = account
            self._synced_at = time.time()
            self._last_error = ""
            self._version = f"gmail:{int(self._synced_at * 1000)}:{len(messages)}"
        self.account_repository.update_sync_result(ok=True)
        return {
            "status": "ok",
            "message_count": len(messages),
            "persisted_message_count": persisted.get("message_count", 0),
            "changed_message_count": persisted.get("changed_message_count", 0),
            "attachment_count": persisted.get("attachment_count", 0),
            "analysis_job_count": persisted.get("analysis_job_count", 0),
            "account": account,
            "elapsed_ms": round((time.time() - started_at) * 1000),
        }

    def sync_outbound_activity(self) -> dict[str, Any]:
        started_at = time.time()
        if self.work_tracking_repository is None:
            return {"status": "skipped", "message": "work tracking repository is not configured"}
        try:
            service = build_gmail_service(self._config(), allow_interactive_auth=False)
            account = gmail_profile_email(service)
            query = os.getenv("CORAMAIL_GMAIL_SENT_QUERY", "").strip()
            messages = fetch_sent_messages(
                service,
                max_results=self._sent_max_results(),
                query=query,
                max_body_length=500,
            )
            result = self.work_tracking_repository.write_outbound_and_link(
                account_email=account,
                outbound_messages=messages,
            )
        except GmailSyncUnavailable as exc:
            return self._record_failure(str(exc))
        except Exception as exc:
            return self._record_failure(f"{type(exc).__name__}: {exc}")
        return {
            "status": "ok",
            "outbound_message_count": result.get("outbound_count", 0),
            "linked_work_item_count": result.get("linked_count", 0),
            "account": account,
            "elapsed_ms": round((time.time() - started_at) * 1000),
        }

    def _persist_messages(
        self,
        service: Any,
        account: str,
        messages: list[GmailMessageDraft],
    ) -> dict[str, int]:
        if self.sync_repository is None or not self.sync_repository.enabled:
            return {
                "message_count": 0,
                "changed_message_count": 0,
                "attachment_count": 0,
                "analysis_job_count": 0,
            }
        artifacts = self._download_attachments(service, messages)
        write_result = self.sync_repository.write_messages(
            account_email=account,
            messages=messages,
            artifacts=artifacts,
        )
        changed_message_ids = list(dict.fromkeys(write_result.changed_message_ids))
        missing_attachment_ids: list[str] = []
        if hasattr(self.sync_repository, "message_ids_needing_attachment_analysis"):
            missing_attachment_ids = list(
                dict.fromkeys(self.sync_repository.message_ids_needing_attachment_analysis(write_result.message_ids))
            )
        analysis_job_count = self._run_analysis(
            changed_message_ids,
            analysis_types=("mail_decision", "classification", "executive_summary"),
        )
        backfill_ids = [message_id for message_id in missing_attachment_ids if message_id not in changed_message_ids]
        analysis_job_count += self._run_analysis(backfill_ids, analysis_types=("mail_decision",))
        return {
            "message_count": write_result.message_count,
            "changed_message_count": len(write_result.changed_message_ids),
            "attachment_count": write_result.attachment_count,
            "analysis_job_count": analysis_job_count,
        }

    def _download_attachments(
        self,
        service: Any,
        messages: list[GmailMessageDraft],
    ) -> dict[tuple[str, str], GmailAttachmentArtifact]:
        artifacts: dict[tuple[str, str], GmailAttachmentArtifact] = {}
        root = self.project_dir / "data" / "runtime" / "gmail_attachments"
        for message in messages:
            message_dir = root / hashlib.sha256(message.provider_message_id.encode("utf-8")).hexdigest()[:20]
            for index, attachment in enumerate(message.attachments):
                provider_key = attachment.provider_attachment_id or f"inline-{index}"
                key = (message.provider_message_id, provider_key)
                safe_name = self._safe_filename(attachment.filename)
                prefix = hashlib.sha256(provider_key.encode("utf-8")).hexdigest()[:16]
                path = message_dir / f"{prefix}-{safe_name}"
                relative_path = path.relative_to(self.project_dir).as_posix()
                try:
                    content = fetch_attachment_bytes(service, message.provider_message_id, attachment)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_suffix(path.suffix + ".part")
                    temporary.write_bytes(content)
                    temporary.replace(path)
                    artifacts[key] = GmailAttachmentArtifact(
                        storage_uri=relative_path,
                        checksum=hashlib.sha256(content).hexdigest(),
                    )
                except Exception as exc:
                    artifacts[key] = GmailAttachmentArtifact(
                        storage_uri=relative_path,
                        checksum="",
                        error_message=f"{type(exc).__name__}: {exc}",
                    )
        return artifacts

    def _run_initial_analysis(self, message_ids: list[str]) -> int:
        return self._run_analysis(
            message_ids,
            analysis_types=("mail_decision", "classification", "executive_summary"),
        )

    def _run_missing_attachment_analysis_for_rows(self, rows: list[dict[str, Any]]) -> int:
        if self.sync_repository is None or self.job_repository is None or self.analysis_worker is None:
            return 0
        if not hasattr(self.sync_repository, "message_ids_needing_attachment_analysis"):
            return 0
        if not self._auto_analysis_lock.acquire(blocking=False):
            return 0
        try:
            return self._run_missing_attachment_analysis_for_rows_locked(rows)
        finally:
            self._auto_analysis_lock.release()

    def _run_missing_attachment_analysis_for_rows_locked(self, rows: list[dict[str, Any]]) -> int:
        message_ids = [
            str(row.get("email_uid") or "")
            for row in rows
            if str(row.get("email_uid") or "") and (row.get("has_attachment") or int(row.get("attachment_count") or 0) > 0)
        ]
        if not message_ids:
            return 0
        try:
            missing_ids = self.sync_repository.message_ids_needing_attachment_analysis(list(dict.fromkeys(message_ids)))
            return self._run_analysis(
                list(dict.fromkeys(missing_ids)),
                analysis_types=("mail_decision",),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("automatic attachment analysis enqueue failed: %s", exc)
            return 0

    def _run_analysis(self, message_ids: list[str], *, analysis_types: tuple[str, ...]) -> int:
        if not message_ids or self.job_repository is None or self.analysis_worker is None:
            return 0
        jobs: list[dict[str, Any]] = []
        for message_id in message_ids:
            for analysis_type in analysis_types:
                jobs.append(
                    self.job_repository.create_email_analysis_job(
                        message_id,
                        analysis_type,
                        requested_by="gmail_sync",
                    )
                )
        if hasattr(self.analysis_worker, "run_one") and hasattr(self.analysis_worker, "run_pending"):
            if self._analysis_thread is not None and self._analysis_thread.is_alive():
                return len(jobs)
            self._analysis_thread = Thread(
                target=self._drain_analysis_jobs_by_id,
                name="coramail-gmail-analysis",
                args=([str(job["id"]) for job in jobs],),
                daemon=True,
            )
            self._analysis_thread.start()
            return len(jobs)
        if hasattr(self.analysis_worker, "run_pending"):
            if self._analysis_thread is None or not self._analysis_thread.is_alive():
                self._analysis_thread = Thread(
                    target=self._drain_analysis_jobs,
                    name="coramail-gmail-analysis",
                    daemon=True,
                )
                self._analysis_thread.start()
            return len(jobs)

        processed_count = 0
        for job in jobs:
            if hasattr(self.analysis_worker, "run_one"):
                result = self.analysis_worker.run_one(str(job["id"]))
                processed_count += int(result.get("processed_count") or 0)
        return processed_count

    def _drain_analysis_jobs_by_id(self, job_ids: list[str]) -> None:
        for job_id in job_ids:
            try:
                self.analysis_worker.run_one(job_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Gmail analysis job failed. job_id=%s error=%s", job_id, exc)

    def _drain_analysis_jobs(self) -> None:
        while True:
            result = self.analysis_worker.run_pending(limit=100)
            if int(result.get("processed_count") or 0) == 0:
                return

    @staticmethod
    def _safe_filename(filename: str) -> str:
        name = Path(filename).name.strip() or "attachment"
        safe = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", name)
        return safe[:180] or "attachment"

    def status(self) -> dict[str, Any]:
        public_account = self.account_repository.public_status()
        account_label = str(public_account.get("email_address") or "")
        with self._lock:
            cached_account = self._account
        if not cached_account and not account_label and public_account.get("connected"):
            account_label = self._resolve_connected_account_email()
        with self._lock:
            return {
                "account": self._account
                or account_label
                or self._account_fallback()
                or "Gmail 계정 미확인",
                "last_error": self._last_error,
                "last_synced_at": self._synced_at,
                "message_count": len(self._messages),
                "version": self._version,
            }

    def version(self) -> str:
        return str(self.status()["version"])

    def _config(self) -> GmailSyncConfig:
        credentials_path = self._path_env("CORAMAIL_GMAIL_CREDENTIALS_PATH")
        token_path = self._path_env("CORAMAIL_GMAIL_TOKEN_PATH") or self.account_repository.token_path
        return GmailSyncConfig(
            credentials_path=credentials_path,
            token_path=token_path,
            env_path=self._path_env("CORAMAIL_ENV_FILE") or (self.project_dir / ".env"),
            max_body_length=self._max_body_length(),
        )

    def _path_env(self, name: str) -> Path | None:
        value = os.getenv(name, "").strip()
        if not value:
            return None
        path = Path(value).expanduser()
        return path if path.is_absolute() else (self.project_dir / path).resolve()

    def _max_results(self) -> int | None:
        return self._optional_int_env("CORAMAIL_GMAIL_MAX_RESULTS", minimum=1, maximum=100000)

    def _sent_max_results(self) -> int | None:
        return self._optional_int_env("CORAMAIL_GMAIL_SENT_MAX_RESULTS", minimum=1, maximum=100000) or 500

    def _max_body_length(self) -> int:
        return self._int_env("CORAMAIL_GMAIL_MAX_BODY_LENGTH", 100000, minimum=500, maximum=500000)

    @staticmethod
    def _int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
        try:
            value = int(os.getenv(name, str(default)))
        except ValueError:
            value = default
        return min(max(value, minimum), maximum)

    @staticmethod
    def _optional_int_env(name: str, *, minimum: int, maximum: int) -> int | None:
        raw_value = os.getenv(name, "").strip()
        if not raw_value or raw_value.casefold() in {"all", "none", "unlimited", "0"}:
            return None
        try:
            value = int(raw_value)
        except ValueError:
            return None
        return min(max(value, minimum), maximum)

    def _record_failure(self, message: str) -> dict[str, Any]:
        with self._lock:
            self._last_error = message
            self._version = f"gmail:error:{int(time.time() * 1000)}"
        self.account_repository.update_sync_result(ok=False, error=message)
        return {"status": "error", "message": message, "message_count": len(self._messages)}

    def _message_row(self, message: GmailMessageDraft, index: int) -> dict[str, Any]:
        attachment_count = sum(1 for attachment in message.attachments if is_visible_attachment(attachment))
        return {
            "index": index,
            "email_uid": message.provider_message_id,
            "gmail_message_id": message.provider_message_id,
            "sender_name": message.sender_name or message.sender_address,
            "sender_address": message.sender_address,
            "subject": message.subject,
            "body_preview": message.snippet or message.body_text[:180],
            "date": message.received_at or message.sent_at,
            "received_at": message.received_at or message.sent_at,
            "cc": ", ".join(item.address for item in message.recipients_cc),
            "has_attachment": attachment_count > 0,
            "attachment_count": attachment_count,
            "classification_state": "unclassified",
            "classification_state_label": "Gmail",
            "mail_category": "미분류",
            "business_label": "미분류",
            "routing_display": "미할당",
            "routing_target_label": "미할당",
            "classification": self._classification_payload(message),
        }

    def _classification_payload(self, message: GmailMessageDraft) -> dict[str, Any]:
        return {
            "business_label": "미분류",
            "mail_category": "미분류",
            "urgency": "",
            "routing_display": "미할당",
            "business_refs": [],
            "vessel_names": [],
            "summary": "",
            "confidence": 0,
        }

    def _attachment_payload(self, attachment: Any, email_index: int, attachment_index: int) -> dict[str, Any]:
        return {
            "attachment_uid": attachment.provider_attachment_id or f"gmail-{email_index}-{attachment_index}",
            "index": attachment_index,
            "filename": attachment.filename,
            "content_type": attachment.content_type,
            "size_label": DemoMailService._size_label(attachment.file_size),
            "exists": False,
            "view_url": "",
            "download_url": "",
            "preview_kind": "pdf" if attachment.content_type == "application/pdf" else "file",
            "parse_status": "metadata_only",
            "analysis_rows": [],
        }

    @staticmethod
    def _body_html_srcdoc(message: GmailMessageDraft) -> str:
        if message.body_html:
            return email_body_srcdoc(message.body_html, [])
        return plain_email_body_srcdoc(message.body_text)

    def _resolve_connected_account_email(self) -> str:
        try:
            service = build_gmail_service(self._config(), allow_interactive_auth=False)
            email_address = gmail_profile_email(service).strip()
        except Exception as exc:
            logger.debug("Gmail account identity lookup failed: %s", exc)
            return ""
        if not email_address:
            return ""
        self.account_repository.save_account_identity(email_address=email_address)
        with self._lock:
            self._account = email_address
        return email_address

    @staticmethod
    def _account_fallback() -> str:
        raw_value = os.getenv("GOOGLE_TOKEN_JSON", "").strip()
        if not raw_value:
            return ""
        try:
            token_info = json.loads(raw_value)
        except json.JSONDecodeError:
            return ""
        return str(
            token_info.get("account")
            or token_info.get("email")
            or token_info.get("email_address")
            or ""
        ).strip()

from __future__ import annotations

import base64
import os
from pathlib import Path

from app.integrations.gmail.sync_client import (
    GmailAddress,
    GmailAttachmentDraft,
    GmailMessageDraft,
    GmailSyncConfig,
    fetch_attachment_bytes,
    fetch_inbox_messages,
    fetch_sent_messages,
    parse_gmail_message,
    send_gmail_message,
    _persist_token,
    _read_json_env_value,
)
from app.repositories.postgres_gmail_sync_repository import GmailSyncWriteResult
from app.services import gmail_mail_service as gmail_module
from app.services.gmail_mail_service import GmailMailboxService


def gmail_message(*, with_attachment: bool = False) -> GmailMessageDraft:
    attachments = []
    if with_attachment:
        attachments.append(
            GmailAttachmentDraft(
                provider_attachment_id="attachment-1",
                filename="../../purchase order.pdf",
                content_type="application/pdf",
                file_size=7,
                is_inline=False,
            )
        )
    return GmailMessageDraft(
        provider_message_id="gmail-message-1",
        provider_thread_id="gmail-thread-1",
        rfc_message_id="<gmail-message-1@example.invalid>",
        sender_name="Buyer",
        sender_address="buyer@example.invalid",
        recipients_to=[GmailAddress(name="Sales", address="sales@example.invalid")],
        recipients_cc=[],
        subject="Purchase order",
        body_text="Please process PO-1001.",
        body_html="",
        snippet="Please process PO-1001.",
        sent_at="2026-07-31T01:00:00+00:00",
        received_at="2026-07-31T01:00:00+00:00",
        attachments=attachments,
    )


class FakeAccountRepository:
    token_path = Path("/tmp/not-used-gmail-token.json")

    def __init__(self):
        self.results = []

    def update_sync_result(self, *, ok, error=""):
        self.results.append((ok, error))

    def public_status(self):
        return {"connected": True, "email_address": "mailbox@example.invalid"}


class FakeDisconnectedAccountRepository(FakeAccountRepository):
    def public_status(self):
        return {"connected": False, "email_address": "", "last_sync_error": ""}


class FakePostgresMailbox:
    def __init__(self):
        self.rows = []
        self.attachments_by_uid = {}

    def list_emails(self, **kwargs):
        return list(self.rows)

    def attachments_for_messages_payload(self, email_uids):
        return {email_uid: list(self.attachments_by_uid.get(email_uid, [])) for email_uid in email_uids}

    def email_detail(self, index):
        return self.rows[index] if 0 <= index < len(self.rows) else None

    def email_detail_by_uid(self, email_uid):
        return next((row for row in self.rows if row["email_uid"] == email_uid), None)


class FakeSyncRepository:
    enabled = True

    def __init__(self, mailbox):
        self.mailbox = mailbox
        self.artifacts = {}
        self.needs_attachment_analysis = []
        self.changed_message_ids = ["5d76f02d-a9a1-5a66-9d12-b7564a184a02"]

    def write_messages(self, *, account_email, messages, artifacts):
        assert account_email == "mailbox@example.invalid"
        self.artifacts = artifacts
        self.mailbox.rows = [{"email_uid": "5d76f02d-a9a1-5a66-9d12-b7564a184a02", "subject": messages[0].subject}]
        return GmailSyncWriteResult(
            account_id="8b12d529-0bef-54bd-9cbd-219ddb956749",
            message_ids=[self.mailbox.rows[0]["email_uid"]],
            changed_message_ids=list(self.changed_message_ids),
            message_count=1,
            attachment_count=len(artifacts),
        )

    def message_ids_needing_attachment_analysis(self, message_ids):
        assert message_ids == ["5d76f02d-a9a1-5a66-9d12-b7564a184a02"]
        return list(self.needs_attachment_analysis)


class FakeJobRepository:
    def __init__(self):
        self.created = []

    def create_email_analysis_job(self, message_id, analysis_type, *, requested_by):
        self.created.append((message_id, analysis_type, requested_by))
        return {"id": f"job-{analysis_type}"}


class FakeWorker:
    def __init__(self):
        self.runs = []

    def run_one(self, job_id):
        self.runs.append(job_id)
        return {"processed_count": 1}


class FakePendingWorker(FakeWorker):
    def __init__(self):
        super().__init__()
        self.pending_runs = 0

    def run_pending(self, *, limit):
        self.pending_runs += 1
        return {"processed_count": 0}


class FakeGmailExecute:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class FakePaginatedGmailMessages:
    def __init__(self):
        self.list_calls = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        page_token = kwargs.get("pageToken", "")
        if not page_token:
            return FakeGmailExecute(
                {
                    "messages": [{"id": "message-1"}, {"id": "message-2"}],
                    "nextPageToken": "page-2",
                }
            )
        return FakeGmailExecute({"messages": [{"id": "message-3"}]})

    def get(self, **kwargs):
        message_id = kwargs["id"]
        return FakeGmailExecute(
            {
                "id": message_id,
                "threadId": f"thread-{message_id}",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "buyer@example.invalid"},
                        {"name": "Subject", "value": message_id},
                    ]
                },
            }
        )


class FakePaginatedGmailUsers:
    def __init__(self, messages):
        self._messages = messages

    def messages(self):
        return self._messages


class FakePaginatedGmailService:
    def __init__(self):
        self.messages_resource = FakePaginatedGmailMessages()

    def users(self):
        return FakePaginatedGmailUsers(self.messages_resource)


class FakeSendExecute:
    def __init__(self, response):
        self.response = response

    def execute(self):
        return self.response


class FakeSendMessages:
    def __init__(self):
        self.sent = []

    def send(self, **kwargs):
        self.sent.append(kwargs)
        return FakeSendExecute({"id": "sent-message-1"})


class FakeSendUsers:
    def __init__(self, messages):
        self._messages = messages

    def messages(self):
        return self._messages


class FakeSendGmailService:
    def __init__(self):
        self.messages_resource = FakeSendMessages()

    def users(self):
        return FakeSendUsers(self.messages_resource)


def test_gmail_sync_persists_uuid_rows_downloads_attachments_and_runs_initial_analysis(monkeypatch, tmp_path):
    message = gmail_message(with_attachment=True)
    mailbox = FakePostgresMailbox()
    sync_repository = FakeSyncRepository(mailbox)
    jobs = FakeJobRepository()
    worker = FakeWorker()
    account_repository = FakeAccountRepository()
    monkeypatch.setattr(gmail_module, "build_gmail_service", lambda config, allow_interactive_auth: object())
    monkeypatch.setattr(gmail_module, "gmail_profile_email", lambda service: "mailbox@example.invalid")
    monkeypatch.setattr(gmail_module, "fetch_inbox_messages", lambda *args, **kwargs: [message])
    monkeypatch.setattr(gmail_module, "fetch_attachment_bytes", lambda *args, **kwargs: b"pdfdata")

    service = GmailMailboxService(
        tmp_path,
        account_repository,
        postgres_mailbox=mailbox,
        sync_repository=sync_repository,
        job_repository=jobs,
        analysis_worker=worker,
    )

    rows = service.list_emails()

    assert rows[0]["email_uid"] == "5d76f02d-a9a1-5a66-9d12-b7564a184a02"
    assert [item[1] for item in jobs.created] == ["mail_decision", "classification", "executive_summary"]
    assert all(item[2] == "gmail_sync" for item in jobs.created)
    assert worker.runs == ["job-mail_decision", "job-classification", "job-executive_summary"]
    artifact = sync_repository.artifacts[("gmail-message-1", "attachment-1")]
    assert ".." not in artifact.storage_uri
    assert artifact.storage_uri.endswith("-purchase_order.pdf")
    assert (tmp_path / artifact.storage_uri).read_bytes() == b"pdfdata"
    assert account_repository.results == [(True, "")]


def test_gmail_list_emails_does_not_sync_before_account_connection(monkeypatch, tmp_path):
    mailbox = FakePostgresMailbox()
    sync_called: list[bool] = []
    monkeypatch.setattr(
        gmail_module,
        "build_gmail_service",
        lambda *args, **kwargs: sync_called.append(True) or object(),
    )

    service = GmailMailboxService(
        tmp_path,
        FakeDisconnectedAccountRepository(),
        postgres_mailbox=mailbox,
    )

    assert service.list_emails() == []
    assert sync_called == []


def test_gmail_sync_backfills_existing_unanalyzed_attachments(monkeypatch, tmp_path):
    message = gmail_message(with_attachment=True)
    mailbox = FakePostgresMailbox()
    sync_repository = FakeSyncRepository(mailbox)
    sync_repository.changed_message_ids = []
    sync_repository.needs_attachment_analysis = ["5d76f02d-a9a1-5a66-9d12-b7564a184a02"]
    jobs = FakeJobRepository()
    worker = FakeWorker()
    account_repository = FakeAccountRepository()
    monkeypatch.setattr(gmail_module, "build_gmail_service", lambda config, allow_interactive_auth: object())
    monkeypatch.setattr(gmail_module, "gmail_profile_email", lambda service: "mailbox@example.invalid")
    monkeypatch.setattr(gmail_module, "fetch_inbox_messages", lambda *args, **kwargs: [message])
    monkeypatch.setattr(gmail_module, "fetch_attachment_bytes", lambda *args, **kwargs: b"pdfdata")

    service = GmailMailboxService(
        tmp_path,
        account_repository,
        postgres_mailbox=mailbox,
        sync_repository=sync_repository,
        job_repository=jobs,
        analysis_worker=worker,
    )

    service.list_emails()

    assert [item[1] for item in jobs.created] == ["mail_decision"]
    assert worker.runs == ["job-mail_decision"]


def test_gmail_list_emails_auto_runs_attachment_analysis_for_existing_rows(tmp_path):
    mailbox = FakePostgresMailbox()
    mailbox.rows = [
        {
            "email_uid": "5d76f02d-a9a1-5a66-9d12-b7564a184a02",
            "subject": "Purchase order",
            "has_attachment": True,
            "attachment_count": 1,
        }
    ]
    sync_repository = FakeSyncRepository(mailbox)
    sync_repository.changed_message_ids = []
    sync_repository.needs_attachment_analysis = ["5d76f02d-a9a1-5a66-9d12-b7564a184a02"]
    jobs = FakeJobRepository()
    worker = FakeWorker()

    service = GmailMailboxService(
        tmp_path,
        FakeAccountRepository(),
        postgres_mailbox=mailbox,
        sync_repository=sync_repository,
        job_repository=jobs,
        analysis_worker=worker,
    )

    rows = service.list_emails()

    assert rows == mailbox.rows
    assert [item[1] for item in jobs.created] == ["mail_decision"]
    assert worker.runs == ["job-mail_decision"]


def test_gmail_service_exposes_postgres_bulk_attachment_lookup(tmp_path):
    mailbox = FakePostgresMailbox()
    mailbox.attachments_by_uid = {
        "mail-1": [{"filename": "purchase-order.pdf", "parse_status": "completed"}],
    }
    service = GmailMailboxService(
        tmp_path,
        FakeAccountRepository(),
        postgres_mailbox=mailbox,
    )

    attachments = service.attachments_for_messages_payload(["mail-1", "mail-2"])

    assert attachments == {
        "mail-1": [{"filename": "purchase-order.pdf", "parse_status": "completed"}],
        "mail-2": [],
    }


def test_gmail_analysis_uses_created_job_ids_instead_of_old_pending_queue(tmp_path):
    service = GmailMailboxService(
        tmp_path,
        FakeAccountRepository(),
        job_repository=FakeJobRepository(),
        analysis_worker=FakePendingWorker(),
    )

    count = service._run_analysis(["5d76f02d-a9a1-5a66-9d12-b7564a184a02"], analysis_types=("mail_decision",))
    service._analysis_thread.join(timeout=1) if service._analysis_thread is not None else None

    assert count == 1
    assert service.analysis_worker.runs == ["job-mail_decision"]
    assert service.analysis_worker.pending_runs == 0


def test_send_gmail_message_attaches_existing_files_and_skips_missing(tmp_path):
    attachment_path = tmp_path / "quote.pdf"
    attachment_path.write_bytes(b"pdfdata")
    service = FakeSendGmailService()

    response = send_gmail_message(
        service,
        "assignee@example.invalid",
        "Fwd: RFQ",
        "forward body",
        attachments=[
            {"path": str(attachment_path), "filename": "quote.pdf", "content_type": "application/pdf"},
            {"path": str(tmp_path / "missing.pdf"), "filename": "missing.pdf", "content_type": "application/pdf"},
        ],
    )

    assert response == {"id": "sent-message-1"}
    raw = service.messages_resource.sent[0]["body"]["raw"]
    payload = base64.urlsafe_b64decode(raw.encode("ascii"))
    assert b"assignee@example.invalid" in payload
    assert b"Fwd: RFQ" in payload
    assert b"quote.pdf" in payload
    assert b"missing.pdf" not in payload


def test_fetch_inbox_messages_reads_all_gmail_pages_by_default():
    service = FakePaginatedGmailService()

    messages = fetch_inbox_messages(service)

    assert [message.provider_message_id for message in messages] == ["message-1", "message-2", "message-3"]
    assert service.messages_resource.list_calls == [
        {"userId": "me", "labelIds": ["INBOX"], "maxResults": 500},
        {"userId": "me", "labelIds": ["INBOX"], "maxResults": 500, "pageToken": "page-2"},
    ]


def test_fetch_inbox_messages_honors_explicit_max_results_across_pages():
    service = FakePaginatedGmailService()

    messages = fetch_inbox_messages(service, max_results=2)

    assert [message.provider_message_id for message in messages] == ["message-1", "message-2"]
    assert service.messages_resource.list_calls == [
        {"userId": "me", "labelIds": ["INBOX"], "maxResults": 2},
    ]


def test_fetch_sent_messages_uses_sent_label_without_inbox_ingestion():
    service = FakePaginatedGmailService()

    messages = fetch_sent_messages(service, max_results=2)

    assert [message.provider_message_id for message in messages] == ["message-1", "message-2"]
    assert service.messages_resource.list_calls == [
        {"userId": "me", "labelIds": ["SENT"], "maxResults": 2},
    ]
    assert messages[0].provider_thread_id == "thread-message-1"


def test_inline_gmail_attachment_keeps_embedded_bytes_without_api_request():
    encoded = base64.urlsafe_b64encode(b"inline-data").decode("ascii").rstrip("=")
    raw = {
        "id": "message-1",
        "threadId": "thread-1",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [{"name": "From", "value": "buyer@example.invalid"}],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "filename": "note.txt",
                    "headers": [{"name": "Content-Disposition", "value": "attachment"}],
                    "body": {"data": encoded, "size": 11},
                }
            ],
        },
    }

    message = parse_gmail_message(raw)
    attachment = message.attachments[0]

    assert attachment.provider_attachment_id == ""
    assert attachment.content_bytes == b"inline-data"
    assert fetch_attachment_bytes(object(), "message-1", attachment) == b"inline-data"


def test_content_id_image_without_attachment_disposition_is_marked_inline():
    encoded = base64.urlsafe_b64encode(b"image-data").decode("ascii").rstrip("=")
    html = base64.urlsafe_b64encode(b'<p>Regards</p><img src="cid:signature-image">').decode("ascii").rstrip("=")
    raw = {
        "id": "message-inline",
        "threadId": "thread-inline",
        "payload": {
            "mimeType": "multipart/related",
            "headers": [{"name": "From", "value": "buyer@example.invalid"}],
            "parts": [
                {
                    "mimeType": "text/html",
                    "body": {"data": html},
                },
                {
                    "mimeType": "image/png",
                    "filename": "signature.png",
                    "headers": [{"name": "Content-ID", "value": "<signature-image>"}],
                    "body": {"data": encoded, "size": 10},
                }
            ],
        },
    }

    attachment = parse_gmail_message(raw).attachments[0]

    assert attachment.is_inline is True
    assert attachment.content_id == "signature-image"
    assert attachment.content_disposition == ""


def test_content_id_jpg_attachment_not_referenced_by_html_stays_visible():
    html = base64.urlsafe_b64encode(b"<p>Please review attached site photo.</p>").decode("ascii").rstrip("=")
    raw = {
        "id": "message-jpg",
        "threadId": "thread-jpg",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [{"name": "From", "value": "buyer@example.invalid"}],
            "parts": [
                {
                    "mimeType": "text/html",
                    "body": {"data": html},
                },
                {
                    "mimeType": "image/jpeg",
                    "filename": "site-photo.jpg",
                    "headers": [{"name": "Content-ID", "value": "<site-photo>"}],
                    "body": {"attachmentId": "jpg-attachment-1", "size": 8},
                },
            ],
        },
    }

    message = parse_gmail_message(raw)
    attachment = message.attachments[0]

    assert message.body_html == "<p>Please review attached site photo.</p>"
    assert attachment.filename == "site-photo.jpg"
    assert attachment.provider_attachment_id == "jpg-attachment-1"
    assert attachment.is_inline is False


def test_content_id_jpg_referenced_by_html_is_inline_even_with_attachment_disposition():
    html = base64.urlsafe_b64encode(b'<p>Photo below</p><img src="cid:body-photo">').decode("ascii").rstrip("=")
    raw = {
        "id": "message-body-image",
        "threadId": "thread-body-image",
        "payload": {
            "mimeType": "multipart/related",
            "headers": [{"name": "From", "value": "buyer@example.invalid"}],
            "parts": [
                {
                    "mimeType": "text/html",
                    "body": {"data": html},
                },
                {
                    "mimeType": "image/jpeg",
                    "filename": "body-photo.jpg",
                    "headers": [
                        {"name": "Content-ID", "value": "<body-photo>"},
                        {"name": "Content-Disposition", "value": "attachment; filename=body-photo.jpg"},
                    ],
                    "body": {"attachmentId": "body-image-1", "size": 8},
                },
            ],
        },
    }

    attachment = parse_gmail_message(raw).attachments[0]

    assert attachment.filename == "body-photo.jpg"
    assert attachment.content_disposition == "attachment"
    assert attachment.is_inline is True


def test_gmail_sync_reads_json_env_values_from_active_dotenv(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "GOOGLE_CREDENTIALS_JSON='{\"installed\":{\"client_id\":\"client-id\"}}'\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("GOOGLE_CREDENTIALS_JSON", raising=False)

    value = _read_json_env_value("GOOGLE_CREDENTIALS_JSON", env_path)

    assert value == '{"installed":{"client_id":"client-id"}}'
    assert "client-id" in value


def test_gmail_sync_persists_refreshed_token_to_runtime_file_and_dotenv(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    token_path = tmp_path / "runtime" / "gmail_token.json"
    env_path.write_text("CORAMAIL_DEMO_MODE=false\n", encoding="utf-8")
    monkeypatch.delenv("GOOGLE_TOKEN_JSON", raising=False)

    _persist_token(
        GmailSyncConfig(token_path=token_path, env_path=env_path),
        '{"token":"refreshed","scopes":["https://mail.google.com/"]}',
    )

    assert token_path.exists()
    assert token_path.read_text(encoding="utf-8") == '{"token":"refreshed","scopes":["https://mail.google.com/"]}'
    env_text = env_path.read_text(encoding="utf-8")
    assert "GOOGLE_TOKEN_JSON=" in env_text
    assert '"token":"refreshed"' in env_text
    os.environ.pop("GOOGLE_TOKEN_JSON", None)

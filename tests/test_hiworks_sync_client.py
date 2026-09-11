from __future__ import annotations

from email.message import EmailMessage

from app.integrations.hiworks.sync_client import (
    HiworksPop3Config,
    fetch_inbox_message_drafts,
    parse_message_draft,
    parse_message_preview,
    probe_inbox,
)


class FakePop3:
    def __init__(self, raw_message: bytes):
        self.raw_message = raw_message
        self.calls = []

    def user(self, user: str):
        self.calls.append(("user", user))
        return b"+OK user accepted"

    def pass_(self, password: str):
        self.calls.append(("pass", password))
        return b"+OK authenticated"

    def list(self, which: int | None = None):
        self.calls.append(("list", which))
        return b"+OK 3 messages", [b"1 100", b"2 100", b"3 100"], 300

    def uidl(self, which: int | None = None):
        self.calls.append(("uidl", which))
        return b"+OK", [b"1 uid-1", b"2 uid-2", b"3 uid-3"], 0

    def retr(self, which: int):
        self.calls.append(("retr", which))
        return b"+OK", self.raw_message.splitlines(), len(self.raw_message)

    def quit(self):
        self.calls.append(("quit",))
        return b"+OK bye"


def test_probe_inbox_logs_in_with_app_password_and_fetches_bounded_preview():
    raw = (
        b"From: Sender <sender@example.invalid>\r\n"
        b"Subject: Test mail\r\n"
        b"Message-ID: <message-3@example.invalid>\r\n"
        b"Date: Tue, 01 Sep 2026 10:00:00 +0900\r\n"
        b"\r\n"
        b"Body"
    )
    client = FakePop3(raw)
    config = HiworksPop3Config(
        email_address="user@hiworks.com",
        pop3_username="user@hiworks.com",
        app_password="app-password",
        max_results=1,
    )

    result = probe_inbox(config, client=client)

    assert result["status"] == "ok"
    assert result["matched_message_count"] == 3
    assert result["preview_count"] == 1
    assert result["previews"][0].provider_uid == "uid-3"
    assert client.calls[:2] == [("user", "user@hiworks.com"), ("pass", "app-password")]


def test_fetch_inbox_message_drafts_fetches_all_messages_when_unbounded():
    raw = b"From: Sender <sender@example.invalid>\r\nSubject: Test mail\r\n\r\nBody"
    client = FakePop3(raw)
    config = HiworksPop3Config(
        email_address="user@hiworks.com",
        app_password="app-password",
        max_results=None,
    )

    result = fetch_inbox_message_drafts(config, client=client)

    assert result["matched_message_count"] == 3
    assert result["message_count"] == 3
    assert [call[1] for call in client.calls if call[0] == "retr"] == [1, 2, 3]


def test_probe_inbox_uses_full_email_address_for_login_by_default():
    client = FakePop3(b"Subject: Test\r\n\r\nBody")
    config = HiworksPop3Config(
        email_address="user@hiworks.com",
        app_password="app-password",
        max_results=1,
    )

    probe_inbox(config, client=client)

    assert client.calls[0] == ("user", "user@hiworks.com")


def test_probe_inbox_uses_explicit_pop3_username_when_configured():
    client = FakePop3(b"Subject: Test\r\n\r\nBody")
    config = HiworksPop3Config(
        email_address="alias@example.com",
        pop3_username="hiworks-id",
        app_password="app-password",
        max_results=1,
    )

    probe_inbox(config, client=client)

    assert client.calls[0] == ("user", "hiworks-id")


def test_parse_message_preview_counts_attachments():
    message = EmailMessage()
    message["From"] = "Sender <sender@example.invalid>"
    message["Subject"] = "With attachment"
    message["Message-ID"] = "<message@example.invalid>"
    message.set_content("Body")
    message.add_attachment(b"pdfdata", maintype="application", subtype="pdf", filename="quote.pdf")

    preview = parse_message_preview("42", message)

    assert preview.provider_uid == "42"
    assert preview.message_id == "<message@example.invalid>"
    assert preview.subject == "With attachment"
    assert preview.sender == "sender@example.invalid"
    assert preview.attachment_count == 1


def test_parse_message_draft_maps_pop3_message_to_inbox_contract():
    message = EmailMessage()
    message["From"] = "Buyer <buyer@example.invalid>"
    message["To"] = "Sales <sales@example.invalid>"
    message["Subject"] = "Hiworks purchase order"
    message["Date"] = "Fri, 31 Jul 2026 10:00:00 +0900"
    message["Message-ID"] = "<hiworks-message-42@example.invalid>"
    message.set_content("Please process PO-1001.")

    draft = parse_message_draft("42", message)

    assert draft.provider_message_id == "hiworks:42"
    assert draft.provider_thread_id == "<hiworks-message-42@example.invalid>"
    assert draft.sender_address == "buyer@example.invalid"
    assert draft.recipients_to[0].address == "sales@example.invalid"
    assert draft.subject == "Hiworks purchase order"
    assert draft.body_text.strip() == "Please process PO-1001."
    assert draft.snippet == "Please process PO-1001."


def test_parse_message_draft_removes_nul_bytes_from_postgres_text_fields():
    message = EmailMessage()
    message["From"] = "Buyer <buyer@example.invalid>"
    message["To"] = "Sales <sales@example.invalid>"
    message["Subject"] = "Hiworks\x00 purchase order"
    message.set_content("Please\x00 process PO-1001.")

    draft = parse_message_draft("42", message)

    assert "\x00" not in draft.subject
    assert "\x00" not in draft.body_text
    assert "\x00" not in draft.snippet

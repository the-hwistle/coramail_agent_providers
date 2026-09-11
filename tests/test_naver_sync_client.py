from __future__ import annotations

from email.message import EmailMessage

from app.integrations.naver.sync_client import (
    NaverImapConfig,
    fetch_inbox_message_drafts,
    parse_message_draft,
    parse_message_preview,
    probe_inbox,
)


class FakeImap:
    def __init__(self, raw_message: bytes):
        self.raw_message = raw_message
        self.calls = []

    def login(self, user: str, password: str):
        self.calls.append(("login", user, password))
        return "OK", [b"authenticated"]

    def select(self, mailbox: str, readonly: bool = False):
        self.calls.append(("select", mailbox, readonly))
        return "OK", [b"3"]

    def uid(self, command: str, *args: str):
        self.calls.append(("uid", command, args))
        if command == "SEARCH":
            return "OK", [b"1 2 3"]
        return "OK", [(b"3 (BODY[] {1}", self.raw_message)]

    def logout(self):
        self.calls.append(("logout",))
        return "OK", [b"bye"]


def test_probe_inbox_logs_in_with_app_password_and_fetches_bounded_preview():
    raw = (
        b"From: Sender <sender@example.invalid>\r\n"
        b"Subject: Test mail\r\n"
        b"Message-ID: <message-3@example.invalid>\r\n"
        b"Date: Tue, 01 Sep 2026 10:00:00 +0900\r\n"
        b"\r\n"
        b"Body"
    )
    client = FakeImap(raw)
    config = NaverImapConfig(
        email_address="user@naver.com",
        imap_username="user@naver.com",
        app_password="app-password",
        max_results=1,
    )

    result = probe_inbox(config, client=client)

    assert result["status"] == "ok"
    assert result["matched_message_count"] == 3
    assert result["preview_count"] == 1
    assert result["previews"][0].provider_uid == "3"
    assert client.calls[0] == ("login", "user@naver.com", "app-password")


def test_fetch_inbox_message_drafts_fetches_all_messages_when_unbounded():
    raw = b"From: Sender <sender@example.invalid>\r\nSubject: Test mail\r\n\r\nBody"
    client = FakeImap(raw)
    config = NaverImapConfig(
        email_address="user@naver.com",
        app_password="app-password",
        max_results=None,
    )

    result = fetch_inbox_message_drafts(config, client=client)

    fetched_uids = [call[2][0] for call in client.calls if call[:2] == ("uid", "FETCH")]
    assert result["matched_message_count"] == 3
    assert result["message_count"] == 3
    assert fetched_uids == ["1", "2", "3"]


def test_probe_inbox_uses_naver_id_for_login_when_email_address_is_naver_domain():
    client = FakeImap(b"Subject: Test\r\n\r\nBody")
    config = NaverImapConfig(
        email_address="user@naver.com",
        app_password="app-password",
        max_results=1,
    )

    probe_inbox(config, client=client)

    assert client.calls[0] == ("login", "user", "app-password")


def test_probe_inbox_uses_explicit_imap_username_when_configured():
    client = FakeImap(b"Subject: Test\r\n\r\nBody")
    config = NaverImapConfig(
        email_address="alias@example.com",
        imap_username="naver-id",
        app_password="app-password",
        max_results=1,
    )

    probe_inbox(config, client=client)

    assert client.calls[0] == ("login", "naver-id", "app-password")


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


def test_parse_message_draft_maps_imap_message_to_inbox_contract():
    message = EmailMessage()
    message["From"] = "Buyer <buyer@example.invalid>"
    message["To"] = "Sales <sales@example.invalid>"
    message["Subject"] = "Naver purchase order"
    message["Date"] = "Fri, 31 Jul 2026 10:00:00 +0900"
    message["Message-ID"] = "<naver-message-42@example.invalid>"
    message.set_content("Please process PO-1001.")

    draft = parse_message_draft("42", message)

    assert draft.provider_message_id == "naver:42"
    assert draft.provider_thread_id == "<naver-message-42@example.invalid>"
    assert draft.sender_address == "buyer@example.invalid"
    assert draft.recipients_to[0].address == "sales@example.invalid"
    assert draft.subject == "Naver purchase order"
    assert draft.body_text.strip() == "Please process PO-1001."
    assert draft.snippet == "Please process PO-1001."


def test_parse_message_draft_removes_nul_bytes_from_postgres_text_fields():
    message = EmailMessage()
    message["From"] = "Buyer <buyer@example.invalid>"
    message["To"] = "Sales <sales@example.invalid>"
    message["Subject"] = "Naver\x00 purchase order"
    message.set_content("Please\x00 process PO-1001.")

    draft = parse_message_draft("42", message)

    assert "\x00" not in draft.subject
    assert "\x00" not in draft.body_text
    assert "\x00" not in draft.snippet

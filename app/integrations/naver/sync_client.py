from __future__ import annotations

import imaplib
import mimetypes
import os
import socket
from dataclasses import dataclass
from email import policy
from email.headerregistry import Address
from email.message import EmailMessage
from email.parser import BytesParser
from email.header import decode_header
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from typing import Any, Protocol

from app.integrations.gmail.attachment_utils import is_inline_image_part
from app.integrations.gmail.sync_client import GmailAddress, GmailAttachmentDraft, GmailMessageDraft


class NaverSyncError(RuntimeError):
    """Raised when Naver IMAP feasibility checks cannot complete."""


@dataclass(frozen=True, slots=True)
class NaverImapConfig:
    email_address: str
    app_password: str
    imap_username: str = ""
    imap_host: str = "imap.naver.com"
    imap_port: int = 993
    smtp_host: str = "smtp.naver.com"
    smtp_port: int = 587
    max_results: int | None = None

    @classmethod
    def from_env(cls) -> "NaverImapConfig":
        return cls(
            email_address=os.getenv("CORAMAIL_NAVER_MAIL_ADDRESS", "").strip(),
            app_password=os.getenv("CORAMAIL_NAVER_APP_PASSWORD", "").strip(),
            imap_username=os.getenv("CORAMAIL_NAVER_IMAP_USERNAME", "").strip(),
            imap_host=os.getenv("CORAMAIL_NAVER_IMAP_HOST", "imap.naver.com").strip() or "imap.naver.com",
            imap_port=_int_env("CORAMAIL_NAVER_IMAP_PORT", 993, minimum=1, maximum=65535),
            smtp_host=os.getenv("CORAMAIL_NAVER_SMTP_HOST", "smtp.naver.com").strip() or "smtp.naver.com",
            smtp_port=_int_env("CORAMAIL_NAVER_SMTP_PORT", 587, minimum=1, maximum=65535),
            max_results=_max_results_env("CORAMAIL_NAVER_MAX_RESULTS"),
        )

    @property
    def login_username(self) -> str:
        if self.imap_username:
            return self.imap_username
        if self.email_address.casefold().endswith("@naver.com"):
            return self.email_address.split("@", 1)[0]
        return self.email_address

    def validate(self) -> None:
        if not self.email_address:
            raise NaverSyncError("CORAMAIL_NAVER_MAIL_ADDRESS is required.")
        if not self.app_password:
            raise NaverSyncError("CORAMAIL_NAVER_APP_PASSWORD is required.")


@dataclass(frozen=True, slots=True)
class NaverMessagePreview:
    provider_uid: str
    message_id: str
    subject: str
    sender: str
    sent_at: str
    attachment_count: int


class ImapClient(Protocol):
    def login(self, user: str, password: str) -> tuple[str, list[bytes]]: ...

    def select(self, mailbox: str, readonly: bool = False) -> tuple[str, list[bytes]]: ...

    def uid(self, command: str, *args: str) -> tuple[str, list[bytes]]: ...

    def logout(self) -> tuple[str, list[bytes]]: ...


def probe_inbox(config: NaverImapConfig, *, client: ImapClient | None = None) -> dict[str, Any]:
    config.validate()
    try:
        imap = client or imaplib.IMAP4_SSL(config.imap_host, config.imap_port)
    except (OSError, socket.gaierror) as exc:
        raise NaverSyncError(f"IMAP connection failed: {exc}") from exc
    try:
        _expect_ok("login", imap.login(config.login_username, config.app_password))
        _expect_ok("select INBOX", imap.select("INBOX", readonly=True))
        uids = _search_uids(imap)
        selected_uids = _select_latest_uids(uids, config.max_results)
        previews = [_fetch_preview(imap, uid) for uid in selected_uids]
        return {
            "status": "ok",
            "account": config.email_address,
            "imap_host": config.imap_host,
            "imap_port": config.imap_port,
            "matched_message_count": len(uids),
            "preview_count": len(previews),
            "previews": previews,
        }
    except imaplib.IMAP4.error as exc:
        raise NaverSyncError(f"IMAP authentication or command failed: {exc}") from exc
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def fetch_inbox_message_drafts(config: NaverImapConfig, *, client: ImapClient | None = None) -> dict[str, Any]:
    config.validate()
    try:
        imap = client or imaplib.IMAP4_SSL(config.imap_host, config.imap_port)
    except (OSError, socket.gaierror) as exc:
        raise NaverSyncError(f"IMAP connection failed: {exc}") from exc
    try:
        _expect_ok("login", imap.login(config.login_username, config.app_password))
        _expect_ok("select INBOX", imap.select("INBOX", readonly=True))
        uids = _search_uids(imap)
        selected_uids = _select_latest_uids(uids, config.max_results)
        messages = [_fetch_message_draft(imap, uid) for uid in selected_uids]
        return {
            "status": "ok",
            "account": config.email_address,
            "imap_host": config.imap_host,
            "imap_port": config.imap_port,
            "matched_message_count": len(uids),
            "message_count": len(messages),
            "messages": messages,
        }
    except imaplib.IMAP4.error as exc:
        raise NaverSyncError(f"IMAP authentication or command failed: {exc}") from exc
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def _search_uids(imap: ImapClient) -> list[str]:
    status, data = imap.uid("SEARCH", None, "ALL")
    _expect_ok("uid SEARCH", (status, data))
    if not data:
        return []
    raw = data[0] if isinstance(data[0], bytes) else b""
    return [item.decode("ascii", errors="ignore") for item in raw.split() if item]


def _select_latest_uids(uids: list[str], max_results: int | None) -> list[str]:
    if max_results is None:
        return list(uids)
    return uids[-max_results:]


def _fetch_preview(imap: ImapClient, uid: str) -> NaverMessagePreview:
    status, data = imap.uid("FETCH", uid, "(BODY.PEEK[])")
    _expect_ok("uid FETCH", (status, data))
    message = BytesParser(policy=policy.default).parsebytes(_first_message_bytes(data))
    return parse_message_preview(uid, message)


def _fetch_message_draft(imap: ImapClient, uid: str) -> GmailMessageDraft:
    status, data = imap.uid("FETCH", uid, "(BODY.PEEK[])")
    _expect_ok("uid FETCH", (status, data))
    message = BytesParser(policy=policy.default).parsebytes(_first_message_bytes(data))
    return parse_message_draft(uid, message)


def parse_message_preview(provider_uid: str, message: EmailMessage) -> NaverMessagePreview:
    return NaverMessagePreview(
        provider_uid=provider_uid,
        message_id=str(message.get("Message-ID", "")).strip(),
        subject=str(message.get("Subject", "")).strip(),
        sender=_address_header(message.get("From")),
        sent_at=_date_header(message.get("Date")),
        attachment_count=_attachment_count(message),
    )


def parse_message_draft(provider_uid: str, message: EmailMessage, *, max_body_length: int = 100000) -> GmailMessageDraft:
    sender_name, sender_address = parseaddr(str(message.get("From", "")))
    body_text, body_html, attachments = _walk_message_parts(message, provider_uid=provider_uid)
    sent_at = _date_header(message.get("Date"))
    provider_message_id = f"naver:{provider_uid}"
    subject = _clean_text(_decode_header_value(str(message.get("Subject", ""))))
    cleaned_body_text = _clean_text(body_text)
    cleaned_body_html = _clean_text(body_html)
    return GmailMessageDraft(
        provider_message_id=provider_message_id,
        provider_thread_id=_clean_text(str(message.get("Message-ID", "")).strip()) or provider_message_id,
        rfc_message_id=_clean_text(str(message.get("Message-ID", "")).strip()),
        sender_name=_clean_text(_decode_header_value(sender_name)),
        sender_address=_clean_text(sender_address),
        recipients_to=_parse_addresses(str(message.get("To", ""))),
        recipients_cc=_parse_addresses(str(message.get("Cc", ""))),
        subject=subject,
        body_text=cleaned_body_text[:max_body_length],
        body_html=cleaned_body_html,
        snippet=(cleaned_body_text or _strip_html(cleaned_body_html))[:300],
        sent_at=sent_at,
        received_at=sent_at,
        attachments=attachments,
    )


def _first_message_bytes(data: list[bytes]) -> bytes:
    for item in data:
        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
            return item[1]
        if isinstance(item, bytes) and b"\r\n" in item:
            return item
    raise NaverSyncError("IMAP FETCH response did not include message bytes.")


def _address_header(value: object) -> str:
    if isinstance(value, Address):
        return value.addr_spec
    addresses = getattr(value, "addresses", None)
    if addresses:
        return ", ".join(str(getattr(address, "addr_spec", address)) for address in addresses)
    return str(value or "").strip()


def _date_header(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return parsedate_to_datetime(raw).isoformat()
    except (TypeError, ValueError, IndexError, AttributeError):
        return raw


def _attachment_count(message: EmailMessage) -> int:
    count = 0
    for part in message.walk():
        if part.is_multipart():
            continue
        filename = part.get_filename()
        disposition = str(part.get_content_disposition() or "").casefold()
        if filename or disposition == "attachment":
            count += 1
    return count


def _walk_message_parts(message: EmailMessage, *, provider_uid: str) -> tuple[str, str, list[GmailAttachmentDraft]]:
    text_parts: list[str] = []
    html_parts: list[str] = []
    attachment_candidates: list[dict[str, Any]] = []
    for index, part in enumerate(message.walk()):
        if part.is_multipart():
            continue
        content_type = part.get_content_type() or "application/octet-stream"
        filename = _decode_header_value(part.get_filename() or "")
        disposition = str(part.get_content_disposition() or "").casefold()
        content_id = str(part.get("Content-ID", "") or "").strip().strip("<>")
        payload = part.get_payload(decode=True) or b""
        if filename or disposition == "attachment":
            attachment_candidates.append(
                {
                    "provider_attachment_id": f"{provider_uid}:{index}",
                    "filename": filename or "attachment",
                    "content_type": content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream",
                    "file_size": len(payload) if payload else None,
                    "content_id": content_id,
                    "content_disposition": disposition,
                    "content_bytes": payload,
                }
            )
            continue
        if content_type == "text/plain":
            text_parts.append(_part_text(part, payload))
        elif content_type == "text/html":
            html_parts.append(_part_text(part, payload))
    text = "\n\n".join(part.strip() for part in text_parts if part.strip())
    html = "\n\n".join(part.strip() for part in html_parts if part.strip())
    attachments = [
        GmailAttachmentDraft(
            provider_attachment_id=str(candidate["provider_attachment_id"]),
            filename=str(candidate["filename"]),
            content_type=str(candidate["content_type"]),
            file_size=candidate["file_size"] if isinstance(candidate["file_size"], int) else None,
            is_inline=is_inline_image_part(
                str(candidate["content_type"]),
                str(candidate["content_disposition"]),
                str(candidate["content_id"]),
                body_html=html,
            ),
            content_id=str(candidate["content_id"]),
            content_disposition=str(candidate["content_disposition"]),
            content_bytes=candidate["content_bytes"] if isinstance(candidate["content_bytes"], bytes) else b"",
        )
        for candidate in attachment_candidates
    ]
    return text, html, attachments


def _part_text(part: EmailMessage, payload: bytes) -> str:
    try:
        content = part.get_content()
    except Exception:
        content = ""
    if isinstance(content, str) and content:
        return content
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def _parse_addresses(value: str) -> list[GmailAddress]:
    return [
        GmailAddress(name=_clean_text(_decode_header_value(name)), address=_clean_text(address))
        for name, address in getaddresses([value])
        if address
    ]


def _decode_header_value(value: str) -> str:
    fragments: list[str] = []
    for fragment, encoding in decode_header(value or ""):
        if isinstance(fragment, bytes):
            fragments.append(fragment.decode(encoding or "utf-8", errors="replace"))
        else:
            fragments.append(fragment)
    return "".join(fragments).strip()


def _strip_html(value: str) -> str:
    return " ".join(value.replace("<", " <").replace(">", "> ").split())


def _clean_text(value: str) -> str:
    return value.replace("\x00", "")


def _expect_ok(label: str, response: tuple[str, list[bytes]]) -> None:
    status = str(response[0] or "").upper()
    if status != "OK":
        raise NaverSyncError(f"{label} failed with status {status or 'UNKNOWN'}.")


def _int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)).strip())
    except ValueError:
        value = default
    return min(max(value, minimum), maximum)


def _max_results_env(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw or raw.casefold() in {"all", "none", "unlimited", "0"}:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return max(1, value)

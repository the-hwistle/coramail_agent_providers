from __future__ import annotations

import mimetypes
import os
import poplib
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


class HiworksSyncError(RuntimeError):
    """Raised when Hiworks POP3 feasibility checks cannot complete."""


@dataclass(frozen=True, slots=True)
class HiworksPop3Config:
    email_address: str
    app_password: str
    pop3_username: str = ""
    pop3_host: str = "pop3s.hiworks.com"
    pop3_port: int = 995
    smtp_host: str = "smtps.hiworks.com"
    smtp_port: int = 465
    max_results: int | None = None

    @classmethod
    def from_env(cls) -> "HiworksPop3Config":
        return cls(
            email_address=os.getenv("CORAMAIL_HIWORKS_MAIL_ADDRESS", "").strip(),
            app_password=os.getenv("CORAMAIL_HIWORKS_APP_PASSWORD", "").strip(),
            pop3_username=os.getenv("CORAMAIL_HIWORKS_POP3_USERNAME", "").strip(),
            pop3_host=os.getenv("CORAMAIL_HIWORKS_POP3_HOST", "pop3s.hiworks.com").strip() or "pop3s.hiworks.com",
            pop3_port=_int_env("CORAMAIL_HIWORKS_POP3_PORT", 995, minimum=1, maximum=65535),
            smtp_host=os.getenv("CORAMAIL_HIWORKS_SMTP_HOST", "smtps.hiworks.com").strip() or "smtps.hiworks.com",
            smtp_port=_int_env("CORAMAIL_HIWORKS_SMTP_PORT", 465, minimum=1, maximum=65535),
            max_results=_max_results_env("CORAMAIL_HIWORKS_MAX_RESULTS"),
        )

    @property
    def login_username(self) -> str:
        if self.pop3_username:
            return self.pop3_username
        return self.email_address

    def validate(self) -> None:
        if not self.email_address:
            raise HiworksSyncError("CORAMAIL_HIWORKS_MAIL_ADDRESS is required.")
        if not self.app_password:
            raise HiworksSyncError("CORAMAIL_HIWORKS_APP_PASSWORD is required.")


@dataclass(frozen=True, slots=True)
class HiworksMessagePreview:
    provider_uid: str
    message_id: str
    subject: str
    sender: str
    sent_at: str
    attachment_count: int


class Pop3Client(Protocol):
    def user(self, user: str) -> bytes: ...

    def pass_(self, password: str) -> bytes: ...

    def list(self, which: int | None = None) -> tuple[bytes, list[bytes], int]: ...

    def uidl(self, which: int | None = None) -> tuple[bytes, list[bytes], int]: ...

    def retr(self, which: int) -> tuple[bytes, list[bytes], int]: ...

    def quit(self) -> bytes: ...


def probe_inbox(config: HiworksPop3Config, *, client: Pop3Client | None = None) -> dict[str, Any]:
    config.validate()
    try:
        pop3 = client or poplib.POP3_SSL(config.pop3_host, config.pop3_port)
    except (OSError, socket.gaierror) as exc:
        raise HiworksSyncError(f"POP3 connection failed: {exc}") from exc
    try:
        _login(pop3, config)
        message_numbers = _list_message_numbers(pop3)
        uid_map = _message_uid_map(pop3, message_numbers)
        selected_numbers = _select_latest_message_numbers(message_numbers, config.max_results)
        previews = [_fetch_preview(pop3, number, uid_map.get(number, str(number))) for number in selected_numbers]
        return {
            "status": "ok",
            "account": config.email_address,
            "pop3_host": config.pop3_host,
            "pop3_port": config.pop3_port,
            "matched_message_count": len(message_numbers),
            "preview_count": len(previews),
            "previews": previews,
        }
    except (poplib.error_proto, OSError) as exc:
        raise HiworksSyncError(f"POP3 authentication or command failed: {exc}") from exc
    finally:
        try:
            pop3.quit()
        except Exception:
            pass


def fetch_inbox_message_drafts(config: HiworksPop3Config, *, client: Pop3Client | None = None) -> dict[str, Any]:
    config.validate()
    try:
        pop3 = client or poplib.POP3_SSL(config.pop3_host, config.pop3_port)
    except (OSError, socket.gaierror) as exc:
        raise HiworksSyncError(f"POP3 connection failed: {exc}") from exc
    try:
        _login(pop3, config)
        message_numbers = _list_message_numbers(pop3)
        uid_map = _message_uid_map(pop3, message_numbers)
        selected_numbers = _select_latest_message_numbers(message_numbers, config.max_results)
        messages = [_fetch_message_draft(pop3, number, uid_map.get(number, str(number))) for number in selected_numbers]
        return {
            "status": "ok",
            "account": config.email_address,
            "pop3_host": config.pop3_host,
            "pop3_port": config.pop3_port,
            "matched_message_count": len(message_numbers),
            "message_count": len(messages),
            "messages": messages,
        }
    except (poplib.error_proto, OSError) as exc:
        raise HiworksSyncError(f"POP3 authentication or command failed: {exc}") from exc
    finally:
        try:
            pop3.quit()
        except Exception:
            pass


def _login(pop3: Pop3Client, config: HiworksPop3Config) -> None:
    _expect_pop_ok("USER", pop3.user(config.login_username))
    _expect_pop_ok("PASS", pop3.pass_(config.app_password))


def _list_message_numbers(pop3: Pop3Client) -> list[int]:
    response, lines, _ = pop3.list()
    _expect_pop_ok("LIST", response)
    numbers: list[int] = []
    for line in lines:
        parts = line.decode("ascii", errors="ignore").split()
        if parts:
            try:
                numbers.append(int(parts[0]))
            except ValueError:
                continue
    return numbers


def _message_uid_map(pop3: Pop3Client, message_numbers: list[int]) -> dict[int, str]:
    try:
        response, lines, _ = pop3.uidl()
        _expect_pop_ok("UIDL", response)
    except Exception:
        return {number: str(number) for number in message_numbers}
    uid_map: dict[int, str] = {}
    for line in lines:
        parts = line.decode("utf-8", errors="replace").split(maxsplit=1)
        if len(parts) != 2:
            continue
        try:
            uid_map[int(parts[0])] = _clean_text(parts[1])
        except ValueError:
            continue
    return uid_map


def _select_latest_message_numbers(numbers: list[int], max_results: int | None) -> list[int]:
    if max_results is None:
        return list(numbers)
    return numbers[-max_results:]


def _fetch_preview(pop3: Pop3Client, number: int, provider_uid: str) -> HiworksMessagePreview:
    message = _fetch_message(pop3, number)
    return parse_message_preview(provider_uid, message)


def _fetch_message_draft(pop3: Pop3Client, number: int, provider_uid: str) -> GmailMessageDraft:
    message = _fetch_message(pop3, number)
    return parse_message_draft(provider_uid, message)


def _fetch_message(pop3: Pop3Client, number: int) -> EmailMessage:
    response, lines, _ = pop3.retr(number)
    _expect_pop_ok(f"RETR {number}", response)
    return BytesParser(policy=policy.default).parsebytes(b"\r\n".join(lines))


def parse_message_preview(provider_uid: str, message: EmailMessage) -> HiworksMessagePreview:
    return HiworksMessagePreview(
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
    provider_message_id = f"hiworks:{provider_uid}"
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


def _expect_pop_ok(label: str, response: bytes) -> None:
    if not response.upper().startswith(b"+OK"):
        status = response.decode("utf-8", errors="replace") or "UNKNOWN"
        raise HiworksSyncError(f"{label} failed with status {status}.")


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

from __future__ import annotations

import base64
import json
import mimetypes
import os
from dataclasses import dataclass, field
from email import message_from_bytes
from email.header import decode_header
from email.message import Message
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Any

from app.integrations.gmail.attachment_utils import is_inline_image_part


GMAIL_READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_MODIFY_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_FULL_ACCESS_SCOPE = "https://mail.google.com/"
GMAIL_PRIMARY_SCOPES = [GMAIL_FULL_ACCESS_SCOPE]
GMAIL_READ_SCOPES = [GMAIL_READ_SCOPE]
GOOGLE_CREDENTIALS_ENV = "GOOGLE_CREDENTIALS_JSON"
GOOGLE_TOKEN_ENV = "GOOGLE_TOKEN_JSON"
DEFAULT_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"


@dataclass(frozen=True)
class GmailSyncConfig:
    credentials_path: Path | None = None
    token_path: Path | None = None
    credentials_json_env: str = GOOGLE_CREDENTIALS_ENV
    token_json_env: str = GOOGLE_TOKEN_ENV
    env_path: Path | None = None
    scopes: list[str] = field(default_factory=lambda: list(GMAIL_PRIMARY_SCOPES))
    max_body_length: int = 3000


@dataclass(frozen=True)
class GmailAddress:
    name: str
    address: str


@dataclass(frozen=True)
class GmailAttachmentDraft:
    provider_attachment_id: str
    filename: str
    content_type: str
    file_size: int | None
    is_inline: bool
    content_id: str = ""
    content_disposition: str = ""
    content_bytes: bytes = b""


@dataclass(frozen=True)
class GmailMessageDraft:
    provider_message_id: str
    provider_thread_id: str
    rfc_message_id: str
    sender_name: str
    sender_address: str
    recipients_to: list[GmailAddress]
    recipients_cc: list[GmailAddress]
    subject: str
    body_text: str
    body_html: str
    snippet: str
    sent_at: str
    received_at: str
    attachments: list[GmailAttachmentDraft]


@dataclass(frozen=True)
class GmailOutboundActivity:
    provider_message_id: str
    provider_thread_id: str
    rfc_message_id: str
    sender_address: str
    recipients_to: list[GmailAddress]
    recipients_cc: list[GmailAddress]
    subject: str
    sent_at: str


class GmailSyncUnavailable(RuntimeError):
    pass


def build_gmail_service(config: GmailSyncConfig, *, allow_interactive_auth: bool = True) -> Any:
    """Build a Gmail API service.

    This is an isolated porting boundary from `coramail_ai`. It intentionally imports
    Google libraries lazily so fixture demo mode does not need Gmail dependencies.
    """

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise GmailSyncUnavailable("Install the `gmail` optional dependencies to use Gmail sync.") from exc

    credentials = _load_credentials(config, Credentials)
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        _persist_token(config, credentials.to_json())
    if not credentials or not credentials.valid:
        if not allow_interactive_auth:
            raise GmailSyncUnavailable("Gmail token is unavailable or invalid.")
        credentials_info = _load_client_config(config)
        if credentials_info:
            flow = InstalledAppFlow.from_client_config(credentials_info, config.scopes)
        elif config.credentials_path is not None:
            flow = InstalledAppFlow.from_client_secrets_file(str(config.credentials_path), config.scopes)
        else:
            raise GmailSyncUnavailable(
                "Gmail OAuth client JSON is required for interactive OAuth. "
                f"Set {config.credentials_json_env} or CORAMAIL_GMAIL_CREDENTIALS_PATH."
            )
        credentials = flow.run_local_server(port=0)
        _persist_token(config, credentials.to_json())
    return build("gmail", "v1", credentials=credentials)


def gmail_profile_email(service: Any) -> str:
    profile = service.users().getProfile(userId="me").execute()
    return str(profile.get("emailAddress") or "").strip()


def fetch_inbox_messages(
    service: Any,
    *,
    max_results: int | None = None,
    query: str = "",
    max_body_length: int = 3000,
) -> list[GmailMessageDraft]:
    messages: list[GmailMessageDraft] = []
    page_token = ""
    query = query.strip()
    while True:
        remaining = None if max_results is None else max_results - len(messages)
        if remaining is not None and remaining <= 0:
            break
        list_request: dict[str, Any] = {
            "userId": "me",
            "labelIds": ["INBOX"],
            "maxResults": min(500, remaining) if remaining is not None else 500,
        }
        if page_token:
            list_request["pageToken"] = page_token
        if query:
            list_request["q"] = query
        listing = service.users().messages().list(**list_request).execute()
        refs = listing.get("messages", []) if isinstance(listing.get("messages"), list) else []
        for ref in refs:
            remaining = None if max_results is None else max_results - len(messages)
            if remaining is not None and remaining <= 0:
                break
            message_id = str(ref.get("id") or "") if isinstance(ref, dict) else ""
            if not message_id:
                continue
            raw_message = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
            messages.append(parse_gmail_message(raw_message, max_body_length=max_body_length))
        page_token = str(listing.get("nextPageToken") or "") if isinstance(listing, dict) else ""
        if not page_token:
            break
    return messages


def fetch_sent_messages(
    service: Any,
    *,
    max_results: int | None = None,
    query: str = "",
    max_body_length: int = 500,
) -> list[GmailOutboundActivity]:
    messages: list[GmailOutboundActivity] = []
    page_token = ""
    query = query.strip()
    while True:
        remaining = None if max_results is None else max_results - len(messages)
        if remaining is not None and remaining <= 0:
            break
        list_request: dict[str, Any] = {
            "userId": "me",
            "labelIds": ["SENT"],
            "maxResults": min(500, remaining) if remaining is not None else 500,
        }
        if page_token:
            list_request["pageToken"] = page_token
        if query:
            list_request["q"] = query
        listing = service.users().messages().list(**list_request).execute()
        refs = listing.get("messages", []) if isinstance(listing.get("messages"), list) else []
        for ref in refs:
            remaining = None if max_results is None else max_results - len(messages)
            if remaining is not None and remaining <= 0:
                break
            message_id = str(ref.get("id") or "") if isinstance(ref, dict) else ""
            if not message_id:
                continue
            raw_message = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="metadata", metadataHeaders=["Date", "From", "To", "Cc", "Subject", "Message-Id"])
                .execute()
            )
            messages.append(parse_gmail_outbound_activity(raw_message, max_body_length=max_body_length))
        page_token = str(listing.get("nextPageToken") or "") if isinstance(listing, dict) else ""
        if not page_token:
            break
    return messages


def fetch_attachment_bytes(service: Any, message_id: str, attachment: GmailAttachmentDraft) -> bytes:
    if attachment.content_bytes:
        return attachment.content_bytes
    if not attachment.provider_attachment_id:
        raise GmailSyncUnavailable(f"Gmail attachment id is missing for {attachment.filename}")
    payload = (
        service.users()
        .messages()
        .attachments()
        .get(
            userId="me",
            messageId=message_id,
            id=attachment.provider_attachment_id,
        )
        .execute()
    )
    data = str(payload.get("data") or "") if isinstance(payload, dict) else ""
    if not data:
        raise GmailSyncUnavailable(f"Gmail attachment payload is empty for {attachment.filename}")
    return _decode_base64url_bytes(data)


def send_gmail_message(
    service: Any,
    to_email: str,
    subject: str,
    body: str,
    *,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    message = MIMEMultipart()
    message["to"] = to_email
    message["subject"] = subject
    message.attach(MIMEText(body, "plain", "utf-8"))

    for attachment in attachments or []:
        path = Path(str(attachment.get("path") or ""))
        if not path.exists() or not path.is_file():
            continue
        filename = str(attachment.get("filename") or path.name)
        content_type = str(attachment.get("content_type") or "") or mimetypes.guess_type(filename)[0]
        maintype, subtype = (content_type or "application/octet-stream").split("/", 1)
        if maintype != "application":
            subtype = "octet-stream"
        part = MIMEApplication(path.read_bytes(), _subtype=subtype)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        message.attach(part)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    return service.users().messages().send(userId="me", body={"raw": raw}).execute()


def parse_gmail_message(raw_message: dict[str, Any], *, max_body_length: int = 3000) -> GmailMessageDraft:
    provider_message_id = str(raw_message.get("id") or "")
    provider_thread_id = str(raw_message.get("threadId") or "")
    payload = raw_message.get("payload") if isinstance(raw_message.get("payload"), dict) else {}
    headers = {
        str(item.get("name") or "").casefold(): str(item.get("value") or "")
        for item in payload.get("headers", [])
        if isinstance(item, dict)
    }
    sender_name, sender_address = parseaddr(headers.get("from", ""))
    sent_at = _header_datetime(headers.get("date", ""))
    body_text, body_html, attachments = _walk_payload(payload, max_body_length=max_body_length)
    return GmailMessageDraft(
        provider_message_id=provider_message_id,
        provider_thread_id=provider_thread_id,
        rfc_message_id=headers.get("message-id", ""),
        sender_name=sender_name,
        sender_address=sender_address,
        recipients_to=_parse_addresses(headers.get("to", "")),
        recipients_cc=_parse_addresses(headers.get("cc", "")),
        subject=_decode_header_value(headers.get("subject", "")),
        body_text=body_text,
        body_html=body_html,
        snippet=str(raw_message.get("snippet") or "")[:300],
        sent_at=sent_at,
        received_at=sent_at,
        attachments=attachments,
    )


def parse_gmail_outbound_activity(raw_message: dict[str, Any], *, max_body_length: int = 500) -> GmailOutboundActivity:
    draft = parse_gmail_message(raw_message, max_body_length=max_body_length)
    return GmailOutboundActivity(
        provider_message_id=draft.provider_message_id,
        provider_thread_id=draft.provider_thread_id,
        rfc_message_id=draft.rfc_message_id,
        sender_address=draft.sender_address,
        recipients_to=draft.recipients_to,
        recipients_cc=draft.recipients_cc,
        subject=draft.subject,
        sent_at=draft.sent_at,
    )


def _load_credentials(config: GmailSyncConfig, credentials_cls: Any) -> Any | None:
    token_json = _read_json_env_value(config.token_json_env, config.env_path).strip()
    if token_json:
        return credentials_cls.from_authorized_user_info(json.loads(token_json), config.scopes)
    if config.token_path and config.token_path.exists():
        return credentials_cls.from_authorized_user_file(str(config.token_path), config.scopes)
    return None


def _load_client_config(config: GmailSyncConfig) -> dict[str, Any]:
    raw_value = _read_json_env_value(config.credentials_json_env, config.env_path).strip()
    if not raw_value:
        return {}
    parsed = json.loads(raw_value)
    if not isinstance(parsed, dict):
        raise GmailSyncUnavailable(f"{config.credentials_json_env} must contain a JSON object.")
    return parsed


def _persist_token(config: GmailSyncConfig, token_json: str) -> None:
    _persist_json_env(config.token_json_env, token_json, config.env_path)
    if config.token_path:
        config.token_path.parent.mkdir(parents=True, exist_ok=True)
        config.token_path.write_text(token_json, encoding="utf-8")


def _active_env_path(configured_path: Path | None = None) -> Path:
    if configured_path is not None:
        return configured_path.expanduser().resolve()
    path = Path(os.getenv("CORAMAIL_ENV_FILE", str(DEFAULT_ENV_PATH))).expanduser()
    return path.resolve()


def _strip_env_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _read_dotenv_value(name: str, env_path: Path) -> str:
    if not env_path.exists():
        return ""
    prefix = f"{name}="
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or not stripped.startswith(prefix):
            continue
        return _strip_env_quotes(stripped.split("=", 1)[1].strip())
    return ""


def _read_json_env_value(name: str, configured_path: Path | None = None) -> str:
    env_path = _active_env_path(configured_path)
    file_value = _read_dotenv_value(name, env_path)
    if file_value:
        os.environ[name] = file_value
        return file_value
    return os.getenv(name, "")


def _persist_json_env(name: str, raw_json: str, configured_path: Path | None = None) -> None:
    if not raw_json.strip():
        return
    env_path = _active_env_path(configured_path)
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError:
        return
    compact_json = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    os.environ[name] = compact_json
    if not env_path.exists():
        return

    next_line = f"{name}='{compact_json}'"
    existing_lines = env_path.read_text(encoding="utf-8").splitlines()
    replaced = False
    updated_lines: list[str] = []
    for existing_line in existing_lines:
        if existing_line.strip().startswith(f"{name}="):
            updated_lines.append(next_line)
            replaced = True
        else:
            updated_lines.append(existing_line)
    if not replaced:
        if updated_lines and updated_lines[-1].strip():
            updated_lines.append("")
        updated_lines.append(next_line)
    env_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")


def _parse_addresses(value: str) -> list[GmailAddress]:
    return [GmailAddress(name=name, address=address) for name, address in getaddresses([value]) if address]


def _header_datetime(value: str) -> str:
    try:
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError, IndexError):
        return ""


def _decode_header_value(value: str) -> str:
    fragments: list[str] = []
    for fragment, encoding in decode_header(value or ""):
        if isinstance(fragment, bytes):
            fragments.append(fragment.decode(encoding or "utf-8", errors="replace"))
        else:
            fragments.append(fragment)
    return "".join(fragments).strip()


def _walk_payload(payload: dict[str, Any], *, max_body_length: int) -> tuple[str, str, list[GmailAttachmentDraft]]:
    text_parts: list[str] = []
    html_parts: list[str] = []
    attachment_candidates: list[dict[str, Any]] = []

    def visit(part: dict[str, Any]) -> None:
        mime_type = str(part.get("mimeType") or "")
        filename = _decode_header_value(str(part.get("filename") or ""))
        body = part.get("body") if isinstance(part.get("body"), dict) else {}
        attachment_id = str(body.get("attachmentId") or "")
        headers = {
            str(item.get("name") or "").casefold(): str(item.get("value") or "")
            for item in part.get("headers", [])
            if isinstance(item, dict)
        }
        if filename or attachment_id:
            disposition = headers.get("content-disposition", "").split(";", 1)[0].strip().casefold()
            content_id = str(headers.get("content-id") or "").strip().strip("<>")
            content_bytes = _decode_base64url_bytes(str(body.get("data") or "")) if body.get("data") else b""
            attachment_candidates.append(
                {
                    "provider_attachment_id": attachment_id,
                    "filename": filename or "attachment",
                    "content_type": mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream",
                    "file_size": body.get("size") if isinstance(body.get("size"), int) else None,
                    "content_id": content_id,
                    "content_disposition": disposition,
                    "content_bytes": content_bytes,
                }
            )
            return

        data = str(body.get("data") or "")
        if data:
            decoded = _decode_base64url(data)
            if mime_type == "text/plain":
                text_parts.append(decoded)
            elif mime_type == "text/html":
                html_parts.append(decoded)

        for child in part.get("parts", []) or []:
            if isinstance(child, dict):
                visit(child)

    visit(payload)
    text = "\n\n".join(part.strip() for part in text_parts if part.strip())[:max_body_length]
    html = "\n\n".join(part.strip() for part in html_parts if part.strip())
    attachments = [
        GmailAttachmentDraft(
            provider_attachment_id=str(candidate["provider_attachment_id"]),
            filename=str(candidate["filename"]),
            content_type=str(candidate["content_type"]),
            file_size=candidate["file_size"] if isinstance(candidate["file_size"], int) else None,
            is_inline=is_inline_image_part(
                candidate["content_type"],
                candidate["content_disposition"],
                candidate["content_id"],
                body_html=html,
            ),
            content_id=str(candidate["content_id"]),
            content_disposition=str(candidate["content_disposition"]),
            content_bytes=candidate["content_bytes"] if isinstance(candidate["content_bytes"], bytes) else b"",
        )
        for candidate in attachment_candidates
    ]
    return text, html, attachments


def _decode_base64url(value: str) -> str:
    return _decode_base64url_bytes(value).decode("utf-8", errors="replace")


def _decode_base64url_bytes(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def parse_raw_email_bytes(raw_bytes: bytes) -> Message:
    """Helper retained from the old fetcher for future MIME test fixtures."""

    return message_from_bytes(raw_bytes)

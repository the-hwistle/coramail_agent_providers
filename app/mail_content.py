from __future__ import annotations

import html
import re
from typing import Any


QUOTE_MARKERS = (
    "\n----- Original Message -----",
    "\n-----Original Message-----",
    "\nFrom:",
    "\n보낸 사람:",
    "\n발신자:",
    "\nOn ",
)

NON_CUSTOMER_SUBJECT_LABELS = {
    "re",
    "fw",
    "fwd",
    "견적서",
    "견적서 송부",
    "견적의뢰서",
    "견적 요청",
    "견적요청",
    "견적 문의",
    "견적문의",
    "납기 확인",
    "납기확인",
    "납품 일정 문의",
    "발주서 접수",
    "발주 접수",
    "발주서 요청",
    "발주 요청",
    "사양 확인",
    "사양확인",
    "사양확인 요청건",
    "기술 문의",
    "기술문의",
    "서비스 요청",
    "수리 요청",
    "클레임",
    "입금 확인",
    "결제 문의",
    "발주서",
    "인보이스",
    "세금계산서",
    "quotation",
    "quote",
    "rfq",
    "request for quotation",
    "purchase order",
    "invoice",
}


def current_message_body(mail: dict[str, Any], *, limit: int = 5000) -> str:
    """Keep the sender's newest request and exclude quoted thread history."""
    body = str(mail.get("body_text") or mail.get("snippet") or "")
    cut = len(body)
    for marker in QUOTE_MARKERS:
        position = body.find(marker)
        if position >= 0:
            cut = min(cut, position)
    return body[:cut].strip()[:limit]


def subject_business_refs(subject: str) -> list[str]:
    patterns = (
        r"\b(?:RFQ|PO|QTN|REF|FM|FB|KOPA|SALES)[-_ ]?\d[\w-]*\b",
        r"\b[A-Z]{2,}\d{5,}\b",
    )
    refs: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, subject, flags=re.IGNORECASE):
            value = str(match).strip()
            if value and value not in refs:
                refs.append(value)
    return refs[:8]


def bracketed_customer(subject: str) -> str | None:
    for value in re.findall(r"\[([^\]]+)\]", subject):
        candidate = re.sub(r"^(?:RE|FW|FWD)\s*", "", value, flags=re.IGNORECASE).strip()
        if re.match(r"^(?:PRJ|RFQ|PO|QTN|REF|FM|FB|SALES)[-_ ]?\d", candidate, flags=re.IGNORECASE):
            continue
        if candidate and candidate.casefold() not in NON_CUSTOMER_SUBJECT_LABELS:
            return candidate
    return None


def rewrite_email_body_cid_images(body_html: str, attachments: list[dict[str, Any]]) -> str:
    html_body = str(body_html or "")
    if not html_body:
        return ""

    for attachment in attachments or []:
        if not isinstance(attachment, dict):
            continue
        content_id = str(
            attachment.get("content_id")
            or (attachment.get("parse_metadata") or {}).get("content_id")
            or ""
        ).strip().strip("<>")
        view_url = str(attachment.get("view_url") or "").strip()
        if not content_id or not view_url:
            continue

        escaped_cid = re.escape(content_id)
        html_body = re.sub(
            rf'(["\'])cid:{escaped_cid}\1',
            rf"\1{view_url}\1",
            html_body,
            flags=re.IGNORECASE,
        )
        html_body = re.sub(
            rf"url\((['\"]?)cid:{escaped_cid}\1\)",
            f'url("{view_url}")',
            html_body,
            flags=re.IGNORECASE,
        )
    return html_body


def email_body_srcdoc(body_html: str, attachments: list[dict[str, Any]]) -> str:
    body = rewrite_email_body_cid_images(body_html, attachments)
    if not body:
        return ""
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <base target="_blank">
  <style>
    *,
    *::before,
    *::after {{
      box-sizing: border-box;
      max-width: 100% !important;
      min-width: 0 !important;
    }}

    html, body {{
      margin: 0;
      padding: 0;
      width: 100%;
      max-width: 100%;
      overflow-x: hidden;
      background: #ffffff;
      color: #111827;
    }}

    body {{
      padding: 20px;
      overflow-wrap: anywhere;
      word-break: break-word;
      white-space: normal;
    }}

    img {{
      max-width: 100%;
      height: auto;
    }}

    table {{
      width: auto !important;
      max-width: 100% !important;
      table-layout: auto;
    }}

    th,
    td,
    p,
    div,
    span,
    a {{
      overflow-wrap: anywhere;
      word-break: break-word;
      white-space: normal !important;
    }}

    pre {{
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
  </style>
</head>
<body>
{body}
</body>
</html>"""


def plain_email_body_srcdoc(body_text: str) -> str:
    text = str(body_text or "")
    if not text:
        return ""
    return email_body_srcdoc(f"<pre>{html.escape(text)}</pre>", [])

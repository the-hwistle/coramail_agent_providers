from __future__ import annotations

import re
from typing import Any


def normalize_attachment_disposition(value: Any) -> str:
    return str(value or "").strip().casefold()


def normalized_content_id(value: Any) -> str:
    return str(value or "").strip().strip("<>")


def html_references_content_id(body_html: Any, content_id: Any) -> bool:
    html = str(body_html or "")
    cid = normalized_content_id(content_id)
    if not html or not cid:
        return False
    escaped_cid = re.escape(cid)
    return bool(
        re.search(rf'["\']cid:{escaped_cid}["\']', html, flags=re.IGNORECASE)
        or re.search(rf"url\((['\"]?)cid:{escaped_cid}\1\)", html, flags=re.IGNORECASE)
    )


def is_inline_image_part(content_type: Any, disposition: Any, content_id: Any, *, body_html: Any = "") -> bool:
    media_type = str(content_type or "").strip().casefold()
    normalized_disposition = normalize_attachment_disposition(disposition)
    if normalized_disposition == "inline":
        return True
    if not media_type.startswith("image/"):
        return False
    if not normalized_content_id(content_id):
        return False
    return html_references_content_id(body_html, content_id)


def is_visible_attachment(attachment: Any) -> bool:
    return bool(attachment) and not bool(getattr(attachment, "is_inline", False))

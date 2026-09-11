from __future__ import annotations

import base64
import hashlib
import hmac
import time


def encode_auth_cookie(
    username: str,
    *,
    secret: str,
    session_seconds: int,
    now: float | None = None,
) -> str:
    expires_at = int((now or time.time()) + session_seconds)
    payload = f"{username}:{expires_at}"
    signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{signature}".encode("utf-8")).decode("ascii")


def decode_auth_cookie(
    cookie_value: str | None,
    *,
    secret: str,
    now: float | None = None,
) -> str | None:
    if not cookie_value:
        return None
    try:
        decoded = base64.urlsafe_b64decode(cookie_value.encode("ascii")).decode("utf-8")
        username, expires_at_text, signature = decoded.rsplit(":", 2)
        payload = f"{username}:{expires_at_text}"
        expected = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        if int(expires_at_text) < int(now or time.time()):
            return None
    except (UnicodeDecodeError, ValueError, TypeError):
        return None
    return username

from __future__ import annotations

import base64

from app.web.auth_session import decode_auth_cookie, encode_auth_cookie


def test_auth_cookie_round_trip() -> None:
    cookie = encode_auth_cookie("m.kim@example.com", secret="test-secret", session_seconds=3600, now=1000)

    assert decode_auth_cookie(cookie, secret="test-secret", now=1200) == "m.kim@example.com"


def test_auth_cookie_rejects_expired_value() -> None:
    cookie = encode_auth_cookie("m.kim@example.com", secret="test-secret", session_seconds=60, now=1000)

    assert decode_auth_cookie(cookie, secret="test-secret", now=1061) is None


def test_auth_cookie_rejects_tampered_signature() -> None:
    cookie = encode_auth_cookie("m.kim@example.com", secret="test-secret", session_seconds=3600, now=1000)
    decoded = base64.urlsafe_b64decode(cookie.encode("ascii")).decode("utf-8")
    username, expires_at, _ = decoded.rsplit(":", 2)
    tampered = base64.urlsafe_b64encode(f"{username}:{expires_at}:invalid".encode("utf-8")).decode("ascii")

    assert decode_auth_cookie(tampered, secret="test-secret", now=1200) is None


def test_auth_cookie_rejects_malformed_value() -> None:
    assert decode_auth_cookie("not-base64!", secret="test-secret", now=1200) is None

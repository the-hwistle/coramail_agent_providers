from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from app.web.security import add_security_headers, request_origin_allowed


def _request(method: str, *, headers: dict[str, str] | None = None) -> Request:
    encoded_headers = [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]
    return Request(
        {
            "type": "http",
            "method": method,
            "scheme": "https",
            "path": "/ui/settings",
            "raw_path": b"/ui/settings",
            "query_string": b"",
            "headers": encoded_headers,
            "server": ("internal", 8000),
            "client": ("127.0.0.1", 1234),
        }
    )


def test_request_origin_allows_same_public_origin_behind_proxy() -> None:
    request = _request(
        "POST",
        headers={
            "host": "web:8000",
            "origin": "https://mail.example.com",
            "x-forwarded-host": "mail.example.com",
            "x-forwarded-proto": "https",
            "sec-fetch-site": "same-origin",
        },
    )

    assert request_origin_allowed(request) is True


def test_request_origin_rejects_cross_origin_mutation() -> None:
    request = _request(
        "POST",
        headers={
            "host": "mail.example.com",
            "origin": "https://attacker.example.net",
            "sec-fetch-site": "cross-site",
        },
    )

    assert request_origin_allowed(request) is False


def test_request_origin_allows_non_browser_client_without_origin() -> None:
    assert request_origin_allowed(_request("POST", headers={"host": "mail.example.com"})) is True


def test_request_origin_rejects_cross_site_fetch_without_origin() -> None:
    request = _request("POST", headers={"host": "mail.example.com", "sec-fetch-site": "cross-site"})

    assert request_origin_allowed(request) is False


def test_security_headers_are_added_without_overwriting_edge_policy() -> None:
    response = Response(headers={"X-Frame-Options": "DENY"})

    add_security_headers(response)

    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"

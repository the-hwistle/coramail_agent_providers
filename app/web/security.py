from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import Request, Response


MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def request_origin_allowed(request: Request) -> bool:
    if request.method.upper() not in MUTATING_METHODS:
        return True

    origin = request.headers.get("origin", "").strip()
    fetch_site = request.headers.get("sec-fetch-site", "").strip().casefold()
    if not origin:
        return fetch_site not in {"cross-site"}
    if origin.casefold() == "null":
        return False

    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False

    forwarded_host = request.headers.get("x-forwarded-host", "").split(",", 1)[0].strip()
    expected_host = forwarded_host or request.headers.get("host", "").strip()
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
    expected_scheme = forwarded_proto or request.url.scheme
    return parsed.scheme.casefold() == expected_scheme.casefold() and parsed.netloc.casefold() == expected_host.casefold()


def add_security_headers(response: Response) -> Response:
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response

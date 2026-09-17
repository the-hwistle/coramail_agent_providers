from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.attachments import build_attachment_response, build_attachment_router


def test_attachment_router_registers_expected_path() -> None:
    router = build_attachment_router(resolve_attachment=lambda *_, **__: None)
    paths = {(route.path, method) for route in router.routes for method in route.methods}
    assert ("/api/emails/{email_ref}/attachments/{attachment_index}", "GET") in paths


def test_attachment_response_preserves_inline_and_cache_headers(tmp_path: Path) -> None:
    path = tmp_path / "quote.pdf"
    path.write_bytes(b"pdf")
    response = build_attachment_response(
        "mail-1",
        0,
        download=False,
        inline=True,
        resolve_attachment=lambda email_ref, index, **kwargs: (
            path,
            "quote.pdf",
            "application/pdf",
        ),
    )
    assert response.media_type == "application/pdf"
    assert response.headers["cache-control"] == "private, max-age=3600"
    assert response.headers["content-disposition"].startswith("inline;")


def test_attachment_download_response_keeps_no_store_cache_header(tmp_path: Path) -> None:
    path = tmp_path / "quote.pdf"
    path.write_bytes(b"pdf")
    response = build_attachment_response(
        "mail-1",
        0,
        download=True,
        inline=True,
        resolve_attachment=lambda email_ref, index, **kwargs: (
            path,
            "quote.pdf",
            "application/pdf",
        ),
    )
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-disposition"].startswith("attachment;")


def test_attachment_response_maps_missing_resolution_to_not_found() -> None:
    with pytest.raises(HTTPException) as exc_info:
        build_attachment_response(
            "mail-1",
            0,
            download=False,
            inline=False,
            resolve_attachment=lambda *_, **__: None,
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "첨부파일을 찾을 수 없습니다."


def test_attachment_response_maps_missing_file_to_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "missing.pdf"
    with pytest.raises(HTTPException) as exc_info:
        build_attachment_response(
            "mail-1",
            0,
            download=True,
            inline=False,
            resolve_attachment=lambda *_, **__: (missing, "missing.pdf", "application/pdf"),
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "첨부파일 원본이 존재하지 않습니다."

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse


AttachmentResolver = Callable[..., tuple[Path, str, str] | None]


def build_attachment_response(
    email_ref: str,
    attachment_index: int,
    *,
    download: bool,
    inline: bool,
    resolve_attachment: AttachmentResolver,
) -> FileResponse:
    resolved = resolve_attachment(email_ref, attachment_index, include_inline=inline)
    if resolved is None:
        raise HTTPException(status_code=404, detail="첨부파일을 찾을 수 없습니다.")
    path, filename, media_type = resolved
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="첨부파일 원본이 존재하지 않습니다.")
    cache_control = "private, max-age=3600" if inline and not download else "no-store"
    return FileResponse(
        path=path,
        media_type=media_type,
        filename=filename,
        content_disposition_type="attachment" if download else "inline",
        headers={"Cache-Control": cache_control},
    )


def build_attachment_router(*, resolve_attachment: AttachmentResolver) -> APIRouter:
    router = APIRouter()

    @router.get("/api/emails/{email_ref}/attachments/{attachment_index}")
    def attachment(
        email_ref: str,
        attachment_index: int,
        download: bool = False,
        inline: bool = False,
    ) -> FileResponse:
        return build_attachment_response(
            email_ref,
            attachment_index,
            download=download,
            inline=inline,
            resolve_attachment=resolve_attachment,
        )

    return router

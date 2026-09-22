from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse


AttachmentResolver = Callable[..., tuple[Path, str, str] | None]

HIGH_RISK_ATTACHMENT_EXTENSIONS = {
    ".bat",
    ".cmd",
    ".com",
    ".exe",
    ".hta",
    ".jar",
    ".js",
    ".msi",
    ".ps1",
    ".scr",
    ".vbs",
}
MEDIUM_RISK_ATTACHMENT_EXTENSIONS = {
    ".docm",
    ".pptm",
    ".xlsm",
}
HIGH_RISK_MEDIA_TYPES = {
    "application/java-archive",
    "application/x-msdownload",
    "application/x-msdos-program",
}


def attachment_risk_level(filename: str, media_type: str = "") -> str:
    suffix = Path(filename).suffix.casefold()
    normalized_media_type = media_type.partition(";")[0].strip().casefold()
    if suffix in HIGH_RISK_ATTACHMENT_EXTENSIONS or normalized_media_type in HIGH_RISK_MEDIA_TYPES:
        return "high"
    if suffix in MEDIUM_RISK_ATTACHMENT_EXTENSIONS:
        return "medium"
    return "low"


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

    risk_level = attachment_risk_level(filename, media_type)
    force_download = download or risk_level == "high"
    cache_control = "private, max-age=3600" if inline and not force_download else "no-store"
    return FileResponse(
        path=path,
        media_type=media_type,
        filename=filename,
        content_disposition_type="attachment" if force_download else "inline",
        headers={
            "Cache-Control": cache_control,
            "X-Content-Type-Options": "nosniff",
            "X-CoRAMail-Attachment-Risk": risk_level,
        },
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

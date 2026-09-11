from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse


DocumentTypesContext = Callable[..., dict[str, object]]
RenderView = Callable[..., HTMLResponse]


def render_documents(
    request: Request,
    *,
    q: str = "",
    document_types_context: DocumentTypesContext,
    render_view: RenderView,
) -> HTMLResponse:
    return render_view(
        request,
        "views/document_types.html",
        {**document_types_context(q=q), "request": request},
        active_view="documents",
    )


def build_documents_ui_router(
    *,
    document_types_context: DocumentTypesContext,
    render_view: RenderView,
    templates: Any,
) -> APIRouter:
    router = APIRouter()

    @router.post("/ui/documents", response_class=HTMLResponse)
    @router.get("/ui/documents", response_class=HTMLResponse)
    def documents(request: Request, q: str = "") -> HTMLResponse:
        return render_documents(
            request,
            q=q,
            document_types_context=document_types_context,
            render_view=render_view,
        )

    @router.get("/ui/document-types", response_class=HTMLResponse)
    def document_types_legacy(request: Request, q: str = "") -> HTMLResponse:
        return render_documents(
            request,
            q=q,
            document_types_context=document_types_context,
            render_view=render_view,
        )

    @router.get("/ui/document-type-sections", response_class=HTMLResponse)
    def document_type_sections(request: Request, q: str = "") -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "partials/document_type_sections.html",
            {**document_types_context(q=q), "request": request},
        )

    return router

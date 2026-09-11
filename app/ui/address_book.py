from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse


AddressBookContext = Callable[..., dict[str, object]]
RenderView = Callable[..., HTMLResponse]


def render_address_book(
    request: Request,
    *,
    q: str = "",
    organization: str = "",
    address_book_context: AddressBookContext,
    render_view: RenderView,
) -> HTMLResponse:
    return render_view(
        request,
        "views/address_book.html",
        {**address_book_context(q=q, organization=organization), "request": request},
        active_view="address-book",
    )


def build_address_book_ui_router(
    *,
    address_book_context: AddressBookContext,
    render_view: RenderView,
    templates: Any,
) -> APIRouter:
    router = APIRouter()

    @router.post("/ui/address-book", response_class=HTMLResponse)
    @router.get("/ui/address-book", response_class=HTMLResponse)
    def address_book(request: Request, q: str = "", organization: str = "") -> HTMLResponse:
        return render_address_book(
            request,
            q=q,
            organization=organization,
            address_book_context=address_book_context,
            render_view=render_view,
        )

    @router.get("/ui/address-book-list", response_class=HTMLResponse)
    def address_book_list(request: Request, q: str = "", organization: str = "") -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "partials/address_book_list.html",
            {**address_book_context(q=q, organization=organization), "request": request},
        )

    return router

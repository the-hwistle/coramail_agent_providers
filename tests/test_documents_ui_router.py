from __future__ import annotations

from types import SimpleNamespace

from starlette.requests import Request

from app.ui.documents import build_documents_ui_router, render_documents


class TemplatesStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def TemplateResponse(self, request: Request, template_name: str, context: dict[str, object]):  # noqa: N802
        self.calls.append((template_name, context))
        return SimpleNamespace(template_name=template_name, context=context)


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


def test_documents_router_registers_expected_paths() -> None:
    router = build_documents_ui_router(
        document_types_context=lambda **_kwargs: {},
        render_view=lambda *_args, **_kwargs: SimpleNamespace(),
        templates=TemplatesStub(),
    )
    paths = {(route.path, method) for route in router.routes for method in route.methods}
    assert ("/ui/documents", "GET") in paths
    assert ("/ui/documents", "POST") in paths
    assert ("/ui/document-types", "GET") in paths
    assert ("/ui/document-type-sections", "GET") in paths


def test_render_documents_preserves_template_and_active_view() -> None:
    captured: dict[str, object] = {}

    def render_view(request, template_name, context, *, active_view):
        captured.update(template_name=template_name, context=context, active_view=active_view)
        return SimpleNamespace()

    render_documents(
        _request(),
        q="quote",
        document_types_context=lambda **kwargs: {"query": kwargs["q"]},
        render_view=render_view,
    )
    assert captured["template_name"] == "views/document_types.html"
    assert captured["active_view"] == "documents"
    assert captured["context"]["query"] == "quote"


def test_document_type_sections_preserves_partial_template() -> None:
    templates = TemplatesStub()
    router = build_documents_ui_router(
        document_types_context=lambda **kwargs: {"query": kwargs["q"]},
        render_view=lambda *_args, **_kwargs: SimpleNamespace(),
        templates=templates,
    )
    endpoint = next(route.endpoint for route in router.routes if route.path == "/ui/document-type-sections")
    endpoint(_request(), "quote")
    template_name, context = templates.calls[-1]
    assert template_name == "partials/document_type_sections.html"
    assert context["query"] == "quote"

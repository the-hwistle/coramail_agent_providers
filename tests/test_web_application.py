from fastapi import APIRouter
from jinja2 import ChainableUndefined

from app.web.application import build_web_application


def test_build_web_application_registers_static_templates_and_router(tmp_path):
    static_dir = tmp_path / "static"
    templates_dir = tmp_path / "templates"
    static_dir.mkdir()
    templates_dir.mkdir()

    router = APIRouter()

    @router.get("/probe")
    def probe():
        return {"ok": True}

    app, templates = build_web_application(
        static_dir=static_dir,
        templates_dir=templates_dir,
        routers=[router],
    )
    route_paths = {path for route in app.routes if (path := getattr(route, "path", None)) is not None}

    assert "/probe" in app.openapi()["paths"]
    assert "/static" in route_paths
    assert templates.env.undefined is ChainableUndefined
    assert app.title == "CoRA Mail Agent"

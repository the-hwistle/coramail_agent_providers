from fastapi import FastAPI

from app.api.system import build_system_router


def test_system_router_registers_expected_public_paths() -> None:
    router = build_system_router(
        asset_version=lambda: "v1",
        ui_state=lambda **_: {"versions": {}},
        health=lambda: {"status": "ok"},
    )
    app = FastAPI()
    app.include_router(router)

    paths = set(app.openapi()["paths"])
    assert paths == {
        "/api/client-version",
        "/api/release",
        "/api/ui-state",
        "/api/health",
        "/api/health/details",
    }


def test_release_endpoint_exposes_only_version_and_status() -> None:
    router = build_system_router(
        asset_version=lambda: "beta-20260922",
        ui_state=lambda **_: {"versions": {}},
        health=lambda: {
            "status": "ok",
            "gmail": {"account": "private@example.com"},
            "local_ai": {"qdrant": {"url": "http://qdrant.internal:6333"}},
        },
    )
    endpoints = {route.path: route.endpoint for route in router.routes if hasattr(route, "endpoint")}

    assert endpoints["/api/release"]() == {
        "version": "beta-20260922",
        "status": "ok",
    }


def test_public_health_redacts_operating_details() -> None:
    router = build_system_router(
        asset_version=lambda: "v1",
        ui_state=lambda **_: {"versions": {}},
        health=lambda: {
            "status": "ok",
            "gmail": {"account": "private@example.com"},
            "local_ai": {"qdrant": {"url": "http://qdrant.internal:6333"}},
        },
    )
    endpoints = {route.path: route.endpoint for route in router.routes if hasattr(route, "endpoint")}

    assert endpoints["/api/health"]() == {"status": "ok"}
    assert endpoints["/api/health/details"]()["gmail"]["account"] == "private@example.com"


def test_system_router_does_not_import_server_module() -> None:
    import ast
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "app" / "api" / "system.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert "app.server" not in imports

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
    assert paths == {"/api/client-version", "/api/ui-state", "/api/health"}


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

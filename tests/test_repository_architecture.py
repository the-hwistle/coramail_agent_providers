from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "app"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_routing_policy_does_not_import_http_or_provider_layers() -> None:
    imports = _imports(APP_ROOT / "routing" / "policy.py")
    forbidden_prefixes = (
        "fastapi",
        "app.server",
        "app.integrations",
        "app.repositories",
    )
    assert not any(module.startswith(forbidden_prefixes) for module in imports)


def test_mail_decision_orchestrator_does_not_import_http_layer() -> None:
    imports = _imports(APP_ROOT / "workflows" / "mail_decision" / "orchestrator.py")
    assert not any(module.startswith(("fastapi", "app.server")) for module in imports)


def test_agents_do_not_import_fastapi_or_server() -> None:
    violations: dict[str, list[str]] = {}
    for path in sorted((APP_ROOT / "agents").glob("*.py")):
        imports = _imports(path)
        forbidden = sorted(module for module in imports if module.startswith(("fastapi", "app.server")))
        if forbidden:
            violations[str(path.relative_to(PROJECT_ROOT))] = forbidden
    assert violations == {}

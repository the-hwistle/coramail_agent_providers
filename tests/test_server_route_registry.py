from __future__ import annotations

import ast
from pathlib import Path

import app.server as server


def test_server_has_no_direct_app_route_decorators():
    source = Path("app/server.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    direct_routes = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            owner = decorator.func.value
            if isinstance(owner, ast.Name) and owner.id == "app" and decorator.func.attr in {
                "get",
                "post",
                "put",
                "patch",
                "delete",
            }:
                direct_routes.append((node.name, decorator.func.attr))
    assert direct_routes == []


def test_server_route_registry_preserves_public_paths():
    assert str(server.app.url_path_for("login_form")) == "/login"
    assert str(server.app.url_path_for("react_shell")) == "/"
    assert str(server.app.url_path_for("ui_root")) == "/legacy"
    assert (
        str(server.app.url_path_for("ui_my_work_email_drawer", email_ref="mail-1"))
        == "/ui/my-work/emails/mail-1"
    )
    assert str(server.app.url_path_for("ui_search")) == "/ui/search"
    assert (
        str(server.app.url_path_for("ui_chat_email_drawer", email_ref="mail-1"))
        == "/ui/chats/emails/mail-1"
    )
    assert str(server.app.url_path_for("ui_settings")) == "/ui/settings"
    assert (
        str(server.app.url_path_for("ui_email_classification_regenerate", email_ref="mail-1"))
        == "/ui/emails/mail-1/classification/regenerate"
    )
    assert (
        str(server.app.url_path_for("ui_settings_update_assignee", assignee_id="00000000-0000-0000-0000-000000000001"))
        == "/ui/settings/routing-table/00000000-0000-0000-0000-000000000001"
    )
    assert (
        str(server.app.url_path_for("demo_email_attachment", email_index=0, attachment_index=1))
        == "/api/demo/emails/0/attachments/1"
    )

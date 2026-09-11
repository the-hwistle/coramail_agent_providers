# ruff: noqa: F401
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from uuid import UUID

from starlette.requests import Request

import app.server as server
from app.api.search import SearchRequest, execute_search
from app.ui.monitoring import render_monitoring_email_inspector
from app.ui.mail_display import render_email_detail, render_mail_rows
from app.mail_content import email_body_srcdoc, rewrite_email_body_cid_images
from app.repositories.postgres_assignee_admin_repository import PostgresAssigneeAdminRepository
from app.repositories.postgres_routing_policy_settings_repository import RoutingPolicySettings
from app.schemas.attachment_analysis import AttachmentAnalysisResult, AttachmentAnalysisStatus
from app.services.mail_chat_service import MailChatService, MailChatSessionStore, MailChatTurn
from app.services.mail_decision_runtime_client import MailDecisionRuntimeConnectionError, MailDecisionRuntimeTimeoutError
from app.services.postgres_mail_service import PostgresMailboxService


RUN_PAYLOAD = {
    "run_id": "5df8b829-b235-4ecd-a0b7-66dfd90c30de",
    "email_message_id": "e9105ba1-da36-5ef8-9471-7bcee37b48e4",
    "workflow_version": "mail-decision-decision-agent-v1",
    "status": "review_required",
    "context": {"review_reason": "retrieval_context_insufficient"},
    "started_at": "2026-07-30T01:00:00+00:00",
    "completed_at": "",
}

STEPS = [
    {"node_name": "load_mail_context", "status": "completed", "started_at": "s1", "completed_at": "c1"},
    {"node_name": "analyze_attachments", "status": "completed", "started_at": "s2", "completed_at": "c2"},
    {"node_name": "extract_facts", "status": "completed", "started_at": "s3", "completed_at": "c3"},
    {"node_name": "plan_retrieval", "status": "completed", "started_at": "s4", "completed_at": "c4"},
    {"node_name": "retrieve_context", "status": "completed", "started_at": "s5", "completed_at": "c5"},
    {"node_name": "evaluate_context", "status": "completed", "started_at": "s6", "completed_at": "c6"},
]


class _PanelNestingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._div_stack: list[set[str]] = []
        self.mail_decision_inside_overview = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "div":
            return
        attr_map = dict(attrs)
        classes = set((attr_map.get("class") or "").split())
        if "mail-decision-inspector" in classes:
            self.mail_decision_inside_overview = any("mail-overview-panel" in item for item in self._div_stack)
        self._div_stack.append(classes)

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self._div_stack:
            self._div_stack.pop()


def _app_css_source() -> str:
    return "".join(
        (server.STATIC_DIR / name).read_text(encoding="utf-8")
        for name in ("app.css", "app-02.css", "app-03.css", "app-04.css")
    )


def request(method: str = "GET") -> Request:
    return Request({"type": "http", "method": method, "path": "/", "headers": [], "app": server.app})


def request_with_body(method: str, path: str, body: bytes = b"", headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": headers or [],
            "app": server.app,
            "scheme": "http",
            "server": ("testserver", 80),
            "query_string": b"",
        },
        receive,
    )













































































































































































































































































































































































































__all__ = [name for name in globals() if not name.startswith("__")]

from __future__ import annotations

from pathlib import Path

from starlette.requests import Request

import app.server as server
from app.presentation.attachment_analysis import canonical_document_type
from app.services.postgres_mail_service import PostgresMailboxService


def request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [], "app": server.app})


def _message(message_id: str, subject: str) -> dict[str, object]:
    return {
        "id": message_id,
        "sender_name": "Buyer",
        "sender_address": "buyer@example.com",
        "subject": subject,
        "body_text": "Please review attached documents.",
        "snippet": "Please review attached documents.",
        "sent_at": "2026-08-11T01:00:00+00:00",
        "received_at": "2026-08-11T01:01:00+00:00",
        "has_attachment": True,
        "attachment_count": 2,
        "mail_category": "문의",
    }


class Repository:
    def __init__(self, attachment_path: Path):
        self.attachment_path_value = attachment_path

    def list_messages(self, *, q: str = "", category: str = "", limit: int | None = None):
        rows = [_message("mail-1", "RFQ and PO"), _message("mail-2", "Quote")]
        if q:
            rows = [row for row in rows if q.casefold() in str(row["subject"]).casefold()]
        return rows

    def attachments_for_message(self, email_message_id: str, *, include_inline: bool = False):
        if email_message_id == "mail-1":
            return [
                {
                    "id": "att-rfq",
                    "filename": "request.pdf",
                    "storage_uri": str(self.attachment_path_value),
                    "content_type": "application/pdf",
                    "file_size": 128,
                    "is_inline": False,
                    "analysis_status": "completed",
                    "analysis_result_json": {"document_type": "rfq"},
                },
                {
                    "id": "att-po",
                    "filename": "po.pdf",
                    "storage_uri": str(self.attachment_path_value),
                    "content_type": "application/pdf",
                    "file_size": 128,
                    "is_inline": False,
                    "analysis_status": "completed",
                    "analysis_result_json": {"document_type": "발주서"},
                },
            ]
        return [
            {
                "id": "att-quote-1",
                "filename": "quote-a.pdf",
                "storage_uri": str(self.attachment_path_value),
                "content_type": "application/pdf",
                "file_size": 128,
                "is_inline": False,
                "analysis_status": "completed",
                "analysis_result_json": {"document_type": "quote"},
            },
            {
                "id": "att-quote-2",
                "filename": "quote-b.pdf",
                "storage_uri": str(self.attachment_path_value),
                "content_type": "application/pdf",
                "file_size": 128,
                "is_inline": False,
                "analysis_status": "completed",
                "analysis_result_json": {"document_type": "quotation"},
            },
        ]

    def attachment_path(self, attachment):
        return self.attachment_path_value


def test_document_type_sections_group_emails_by_attachment_type(tmp_path):
    path = tmp_path / "attachment.pdf"
    path.write_bytes(b"pdf")
    service = PostgresMailboxService("", tmp_path)
    service.repository = Repository(path)

    sections = service.document_type_sections()
    by_type = {section["document_type"]: section for section in sections}

    assert canonical_document_type("발주서") == "purchase_order"
    assert [section["document_type"] for section in sections[:3]] == ["rfq", "quote", "purchase_order"]
    assert by_type["rfq"]["email_count"] == 1
    assert by_type["purchase_order"]["emails"][0]["email_uid"] == "mail-1"
    assert by_type["quote"]["email_count"] == 1
    assert by_type["quote"]["attachment_count"] == 2
    assert [item["filename"] for item in by_type["quote"]["emails"][0]["document_attachments"]] == [
        "quote-a.pdf",
        "quote-b.pdf",
    ]


def test_document_type_view_renders_sectioned_mail_rows():
    html = server.templates.get_template("views/document_types.html").render(
        **server.ui_globals(),
        request=request(),
        query="",
        document_type_sections=[
            {
                "document_type": "purchase_order",
                "label": "발주서",
                "email_count": 1,
                "attachment_count": 1,
                "emails": [
                    {
                        "email_uid": "mail-1",
                        "subject": "PO attached",
                        "sender_name": "Buyer",
                        "sender_address": "buyer@example.com",
                        "date": "2026-08-11T01:00:00+00:00",
                        "mail_category": "발주",
                        "work_status": "review_required",
                        "work_status_label": "검토 필요",
                        "routing_display": "미할당",
                        "classification": {"mail_category": "발주"},
                        "document_attachments": [
                            {"filename": "po.pdf", "parse_status": "completed"},
                        ],
                    }
                ],
            }
        ],
        document_type_section_count=1,
        document_type_email_count=1,
        document_type_attachment_count=1,
    )

    assert 'data-view="documents"' in html
    assert "document-type-card-grid" in html
    assert "document-type-card" in html
    assert "document-type-chip" not in html
    assert "data-document-type-icon" in html
    assert html.count("document-type-icon-option material-symbols-outlined") == 10
    assert "documentTypeSearch" not in html
    assert "document-types-summary" not in html
    assert "1 emails · 1 attachments" not in html
    assert "발주서" in html
    assert "PO attached" in html
    assert "po.pdf" in html
    assert 'hx-post="/ui/inbox?email_uid=mail-1"' in html


def test_shell_has_document_type_navigation():
    context = {**server.ui_globals(), "demo_mode": False}
    html = server.templates.get_template("shell.html").render(
        **context,
        request=request(),
        active_view="documents",
        initial_view_template="views/document_types.html",
        query="",
        document_type_sections=[],
        document_type_section_count=0,
        document_type_email_count=0,
        document_type_attachment_count=0,
    )

    assert "Documents 탭 열기" in html
    assert 'hx-post="/ui/documents"' in html
    assert "documents: \"Documents\"" in html
    assert "function installMainNavigation()" in html
    assert 'view === "dashboard" || view === "inbox" || view === "monitoring" || view === "documents"' in html
    assert "documentsStateUrl()" in html
    assert "initDocumentTypeIconPickers" in html
    assert "coramail.documentTypeIcon." in html
    assert 'url.searchParams.set("view", "documents")' in html
    assert "documentTypeSearch" not in html


def test_shell_hides_document_type_navigation_in_demo_mode():
    context = {**server.ui_globals(), "demo_mode": True}
    html = server.templates.get_template("shell.html").render(
        **context,
        request=request(),
        active_view="dashboard",
        initial_view_template="views/dashboard.html",
    )

    assert "Documents 탭 열기" not in html
    assert 'hx-post="/ui/documents"' not in html
    assert "documents: \"Documents\"" in html
    assert 'url.searchParams.set("view", "documents")' in html


def test_documents_routes_are_registered():
    assert str(server.app.url_path_for("documents")) == "/ui/documents"
    assert str(server.app.url_path_for("document_types_legacy")) == "/ui/document-types"
    assert str(server.app.url_path_for("document_type_sections")) == "/ui/document-type-sections"


def test_documents_ui_state_includes_document_sections(monkeypatch):
    monkeypatch.setattr(
        server,
        "mail_rows",
        lambda q="", category="", limit=None: [{"email_uid": "mail-1"}],
    )

    class Service:
        def document_type_sections(self, *, q=""):
            return [{"email_count": 2, "attachment_count": 3}]

    monkeypatch.setattr(server, "mail_service", lambda: Service())

    state = server.ui_state(view="documents", q="po")

    assert "document_sections" in state["versions"]
    assert state["versions"]["document_sections"].endswith(":documents:1:2:3")

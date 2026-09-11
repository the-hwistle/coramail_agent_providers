from __future__ import annotations

import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from app.presentation.attachment_analysis import (
    DOCUMENT_TYPE_SECTION_ORDER,
    canonical_document_type,
    document_type_label,
)
from app.repositories.demo_mail_repository import DemoMailRepository
from app.schemas.demo_mail import DemoAttachment, DemoMessage


CATEGORY_LABELS = {
    "certificate_request": "인증서 요청",
    "claim": "클레임",
    "compatibility_check": "호환성 확인",
    "delivery_confirmation": "납기 확인",
    "drawing_review": "도면 검토",
    "payment_inquiry": "결제 문의",
    "purchase_order": "발주",
    "purchase_delivery_followup": "발주",
    "quotation_request": "견적 요청",
    "quotation_received": "문의",
    "service_request": "서비스 요청",
    "specification_check": "기술",
    "specification_recheck": "기술",
    "technical_inquiry": "기술 문의",
    "unclassified": "미분류",
    "urgent_failure": "긴급 장애",
}

PRIORITY_LABELS = {
    "high": "높음",
    "normal": "보통",
    "low": "낮음",
}

ATTENTION_LABELS = {
    "urgent_important": "긴급·중요",
    "urgent": "긴급",
    "important": "중요",
    "normal": "일반",
}

ASSIGNEE_AREA_LABELS = {
    "admin": "관리",
    "logistics": "물류",
    "service": "서비스",
    "sales": "영업",
    "technical": "기술",
    "technical_sales": "기술영업",
    "urgent_service": "긴급 서비스",
}

DEMO_MAIL_DECISION_NAMESPACE = UUID("22222222-3333-4444-5555-666666666666")

DEMO_MAIL_DECISION_TYPE_ALIASES = {
    "purchase_delivery_followup": "delivery_confirmation",
    "quotation_received": "quotation_request",
    "specification_check": "specification_review",
    "specification_recheck": "specification_review",
}

DOCUMENT_CATEGORY_LABELS = {
    "delivery_followup": "납기 확인",
    "quotation": "견적서",
    "technical_drawing": "기술 도면",
    "technical_specification": "기술 사양서",
}


class DemoMailService:
    def __init__(self, repository: DemoMailRepository):
        self.repository = repository

    def list_emails(self, *, q: str = "", category: str = "", limit: int | None = None) -> list[dict[str, Any]]:
        rows = [self._message_row(message, index) for index, message in enumerate(self.repository.messages())]
        query = " ".join(q.split()).casefold()
        if query:
            rows = [
                row
                for row in rows
                if query in " ".join(
                    [
                        row.get("sender_name", ""),
                        row.get("sender_address", ""),
                        row.get("subject", ""),
                        row.get("body_preview", ""),
                        row.get("mail_category", ""),
                        " ".join(map(str, row.get("business_refs") or [])),
                        " ".join(map(str, row.get("vessel_names") or [])),
                        " ".join(map(str, row.get("equipment") or [])),
                        self._key_spec_search_text(row.get("key_spec_fields") or {}),
                    ]
                ).casefold()
            ]
        if category:
            rows = [row for row in rows if row.get("mail_category") == category]
        return rows[:limit] if limit else rows

    def category_order(self) -> list[str]:
        labels = {self._category_label(message) for message in self.repository.messages()}
        preferred = ["발주", "문의", "서비스", "기술", "기타", "미분류"]
        return [label for label in preferred if label in labels] + sorted(labels.difference(preferred))

    def search_documents(self) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        for index, message in enumerate(self.repository.messages()):
            row = self._message_row(message, index)
            classification = self._classification_payload(message)
            common = {
                "email_uid": message.id,
                "title": message.subject,
                "category": row["mail_category"],
                "sender": f"{message.sender_name} {message.sender_address}",
                "business_refs": classification.get("business_refs", []),
                "vessel_names": classification.get("vessel_names", []),
                "received_at": message.received_at,
                "detail_url": f"/?view=inbox&email_uid={message.id}",
            }
            documents.append(
                {
                    **common,
                    "source_type": "mail",
                    "source": message.subject or "(제목 없음)",
                    "document_category": "",
                    "preview": self._mail_search_preview(message, classification),
                }
            )
            for attachment in message.attachments:
                documents.append(
                    {
                        **common,
                        "source_type": "attachment",
                        "source": attachment.filename,
                        "document_category": classification.get("document_category_label", ""),
                        "preview": self._attachment_search_preview(attachment, message, classification),
                    }
                )
        return documents

    def document_type_sections(self, *, q: str = "", limit_per_section: int = 8) -> list[dict[str, Any]]:
        rows = self.list_emails(q=q)
        messages_by_id = {message.id: message for message in self.repository.messages()}
        sections: dict[str, dict[str, Any]] = {}
        for row in rows:
            message = messages_by_id.get(str(row.get("email_uid") or ""))
            if message is None:
                continue
            document_type = canonical_document_type(message.expected_demo_labels.document_category or "")
            if not document_type:
                document_type = "unknown" if message.attachments else "no_attachment"
            attachments = [
                {
                    **self._attachment_payload(attachment, message.id, attachment_index),
                    "document_type": document_type,
                    "document_category": document_type,
                    "document_category_label": _document_type_section_label(document_type),
                }
                for attachment_index, attachment in enumerate(message.attachments)
            ]
            if not attachments:
                continue
            section = sections.setdefault(
                document_type,
                {
                    "document_type": document_type,
                    "label": _document_type_section_label(document_type),
                    "email_count": 0,
                    "attachment_count": 0,
                    "emails": [],
                },
            )
            section["email_count"] += 1
            section["attachment_count"] += len(attachments)
            if len(section["emails"]) < limit_per_section:
                section["emails"].append({**row, "document_attachments": attachments})
        return _ordered_document_type_sections(sections)

    def email_detail(self, index: int) -> dict[str, Any] | None:
        message = self.repository.message_by_index(index)
        if message is None:
            return None
        return self._email_detail_payload(message, index)

    def email_detail_by_uid(self, email_uid: str) -> dict[str, Any] | None:
        resolved = self.repository.message_by_uid(email_uid)
        if resolved is None:
            return None
        index, message = resolved
        return self._email_detail_payload(message, index)

    def mail_decision_run_by_uid(self, email_uid: str) -> dict[str, Any] | None:
        resolved = self.repository.message_by_uid(email_uid)
        if resolved is None:
            return None
        _, message = resolved
        return self._mail_decision_run_payload(message)

    def _email_detail_payload(self, message: DemoMessage, index: int) -> dict[str, Any]:
        row = self._message_row(message, index)
        row.update(
            {
                "body": message.body_text,
                "attachments": [
                    self._attachment_payload(attachment, message.id, attachment_index)
                    for attachment_index, attachment in enumerate(message.attachments)
                ],
                "classification": self._classification_payload(message),
                "executive_summary_sections": self._summary_sections(message),
            }
        )
        return row

    def attachment_path(self, email_index: int, attachment_index: int) -> tuple[Path, str, str] | None:
        message = self.repository.message_by_index(email_index)
        return self._attachment_path(message, attachment_index)

    def attachment_path_by_uid(self, email_uid: str, attachment_index: int) -> tuple[Path, str, str] | None:
        resolved = self.repository.message_by_uid(email_uid)
        message = resolved[1] if resolved is not None else None
        return self._attachment_path(message, attachment_index)

    def _attachment_path(self, message: DemoMessage | None, attachment_index: int) -> tuple[Path, str, str] | None:
        if message is None or attachment_index < 0 or attachment_index >= len(message.attachments):
            return None
        attachment = message.attachments[attachment_index]
        path = self.repository.attachment_path(attachment)
        media_type = attachment.content_type or mimetypes.guess_type(attachment.filename)[0] or "application/octet-stream"
        return path, attachment.filename, media_type

    def _message_row(self, message: DemoMessage, index: int) -> dict[str, Any]:
        labels = message.expected_demo_labels
        urgency = _demo_level(labels.urgency)
        importance = _demo_level(labels.importance)
        attention_quadrant = _demo_attention(labels.attention_quadrant, urgency, importance)
        return {
            "index": index,
            "email_uid": message.id,
            "provider_thread_id": message.provider_thread_id,
            "sender_name": message.sender_name,
            "sender_address": message.sender_address,
            "subject": message.subject,
            "subject_normalized": message.subject.casefold(),
            "body_preview": message.snippet or message.body_text[:180],
            "date": message.sent_at,
            "received_at": message.received_at,
            "cc": ", ".join(rec.address for rec in message.recipients if rec.recipient_type == "cc"),
            "has_attachment": message.has_attachment,
            "attachment_count": message.attachment_count,
            "work_status": "forwarded",
            "work_status_label": "전달 완료",
            "classification_state": "completed",
            "classification_state_label": "Demo",
            "summary_state": "completed",
            "summary_state_label": "Demo",
            "mail_decision_status": "auto_assigned",
            "mail_decision_started_at": message.received_at,
            "mail_decision_completed_at": message.received_at,
            "mail_decision_duration_label": "0.00초",
            "mail_category": self._category_label(message),
            "business_label": self._category_label(message),
            "routing_display": ASSIGNEE_AREA_LABELS.get(labels.assignee_area, labels.assignee_area or "미할당"),
            "routing_target_label": ASSIGNEE_AREA_LABELS.get(labels.assignee_area, labels.assignee_area or "미할당"),
            "routing_status": "forwarded",
            "routing_assigned_at": message.received_at,
            "routing_forwarded_at": message.received_at,
            "manual_route_status": "sent",
            "manual_route_status_label": "전달 완료",
            "manual_route_button_label": "전달 완료",
            "manual_route_button_variant": "sent",
            "manual_route_button_title": "전달이 완료되었습니다.",
            "manual_route_sent_at": message.received_at,
            "urgency": urgency,
            "urgency_label": PRIORITY_LABELS.get(urgency, urgency),
            "importance": importance,
            "importance_label": PRIORITY_LABELS.get(importance, importance),
            "attention_quadrant": attention_quadrant,
            "attention_label": ATTENTION_LABELS.get(attention_quadrant, attention_quadrant),
            "priority_label": ATTENTION_LABELS.get(attention_quadrant, attention_quadrant),
            "priority": attention_quadrant,
            "classification": self._classification_payload(message),
            "mail_facts": {"customer_name": labels.counterparty, "customer_candidates": [labels.counterparty] if labels.counterparty else []},
            "customer_name": labels.counterparty,
            "business_refs": labels.business_refs,
            "vessel_names": labels.vessel_names,
            "equipment": labels.equipment,
            "key_spec_fields": labels.key_spec_fields,
        }

    def _mail_decision_run_payload(self, message: DemoMessage) -> dict[str, Any]:
        labels = message.expected_demo_labels
        primary_type = DEMO_MAIL_DECISION_TYPE_ALIASES.get(labels.mail_category, labels.mail_category)
        assignee_user_id = _demo_assignee_area_user_id(labels.assignee_area)
        assignee_label = ASSIGNEE_AREA_LABELS.get(labels.assignee_area, labels.assignee_area or "")
        summary_text = self._summary_text(message)
        return {
            "run_id": str(uuid5(DEMO_MAIL_DECISION_NAMESPACE, f"run:{message.id}")),
            "email_message_id": message.id,
            "workflow_version": "demo-fixture-mail-decision:v1",
            "status": "auto_assigned",
            "current_node": "",
            "retrieval_cycle": 0,
            "attempt_count": 1,
            "started_at": message.received_at,
            "completed_at": message.received_at,
            "context": {
                "decision_output": {
                    "summary": {
                        "one_line_summary": summary_text,
                        "requested_actions": [labels.key_spec_fields.get("requested_action") or message.snippet],
                        "business_refs": labels.business_refs,
                        "key_facts": [
                            value
                            for value in [
                                labels.counterparty,
                                ", ".join(labels.vessel_names),
                                ", ".join(labels.equipment),
                            ]
                            if value
                        ],
                    },
                    "classification": {
                        "primary_type": primary_type,
                        "confidence": 1.0,
                        "review_required": False,
                    },
                    "requested_actions": [labels.key_spec_fields.get("requested_action") or message.snippet],
                },
                "routing_decision": {
                    "decision": "auto_assign",
                    "selected_user_id": assignee_user_id,
                    "confidence": 1.0,
                    "candidates": [
                        {
                            "user_id": assignee_user_id,
                            "total_score": 1.0,
                            "rank": 1,
                            "reasons": ["demo_fixture_expected_labels"],
                        }
                    ]
                    if assignee_user_id
                    else [],
                },
                "routing_users": {
                    assignee_user_id: {
                        "name": assignee_label,
                        "email": "",
                        "department": "데모 담당 영역",
                        "position": "",
                        "areas": [assignee_label] if assignee_label else [],
                    }
                }
                if assignee_user_id
                else {},
                "assigned_user_id": assignee_user_id,
                "demo_source": "data/demo/*.fixture.json expected_demo_labels",
            },
            "facts": {
                "customer_name": labels.counterparty,
                "business_refs": labels.business_refs,
                "vessel_names": labels.vessel_names,
                "product_names": labels.equipment,
            },
        }

    def _classification_payload(self, message: DemoMessage) -> dict[str, Any]:
        labels = message.expected_demo_labels
        urgency = _demo_level(labels.urgency)
        importance = _demo_level(labels.importance)
        attention_quadrant = _demo_attention(labels.attention_quadrant, urgency, importance)
        return {
            "business_label": self._category_label(message),
            "mail_category": self._category_label(message),
            "demo_mail_subtype": labels.mail_category,
            "document_category": labels.document_category,
            "document_category_label": DOCUMENT_CATEGORY_LABELS.get(labels.document_category, labels.document_category),
            "urgency": urgency,
            "urgency_label": PRIORITY_LABELS.get(urgency, urgency),
            "importance": importance,
            "importance_label": PRIORITY_LABELS.get(importance, importance),
            "attention_quadrant": attention_quadrant,
            "attention_label": ATTENTION_LABELS.get(attention_quadrant, attention_quadrant),
            "routing_display": ASSIGNEE_AREA_LABELS.get(labels.assignee_area, labels.assignee_area),
            "business_refs": labels.business_refs,
            "vessel_names": labels.vessel_names,
            "equipment": labels.equipment,
            "key_spec_fields": labels.key_spec_fields,
            "counterparty": labels.counterparty,
            "follow_up_of": labels.follow_up_of,
            "summary": self._summary_text(message),
            "confidence": 1.0,
        }

    def _mail_search_preview(self, message: DemoMessage, classification: dict[str, Any]) -> str:
        labels = message.expected_demo_labels
        return " ".join(
            str(value)
            for value in (
                message.body_text,
                message.snippet,
                classification.get("summary"),
                labels.counterparty,
                ASSIGNEE_AREA_LABELS.get(labels.assignee_area, labels.assignee_area or ""),
                " ".join(labels.business_refs),
                " ".join(labels.vessel_names),
                " ".join(labels.equipment),
                self._key_spec_search_text(labels.key_spec_fields),
            )
            if value
        )

    def _attachment_search_preview(
        self,
        attachment: DemoAttachment,
        message: DemoMessage,
        classification: dict[str, Any],
    ) -> str:
        labels = message.expected_demo_labels
        return " ".join(
            str(value)
            for value in (
                attachment.filename,
                attachment.mapping_basis,
                DOCUMENT_CATEGORY_LABELS.get(labels.document_category, labels.document_category),
                classification.get("summary"),
                labels.counterparty,
                ASSIGNEE_AREA_LABELS.get(labels.assignee_area, labels.assignee_area or ""),
                " ".join(labels.business_refs),
                " ".join(labels.vessel_names),
                " ".join(labels.equipment),
                self._key_spec_search_text(labels.key_spec_fields),
            )
            if value
        )

    @staticmethod
    def _key_spec_search_text(fields: dict[str, str]) -> str:
        return " ".join(f"{key}: {value}" for key, value in fields.items() if value)

    def _attachment_payload(self, attachment: DemoAttachment, email_uid: str, attachment_index: int) -> dict[str, Any]:
        path = self.repository.attachment_path(attachment)
        return {
            "attachment_uid": attachment.id,
            "index": attachment_index,
            "filename": attachment.filename,
            "content_type": attachment.content_type,
            "file_group": attachment.file_group,
            "size_label": self._size_label(attachment.file_size),
            "exists": path.exists(),
            "view_url": f"/api/emails/{email_uid}/attachments/{attachment_index}",
            "download_url": f"/api/emails/{email_uid}/attachments/{attachment_index}?download=true",
            "preview_kind": "pdf" if attachment.content_type == "application/pdf" else "file",
            "parse_status": attachment.processing_status,
            "analysis_rows": [],
        }

    def _summary_sections(self, message: DemoMessage) -> list[dict[str, str]]:
        labels = message.expected_demo_labels
        sections = [
            {"title": "요청", "body": self._summary_text(message)},
            {"title": "업무번호", "body": ", ".join(labels.business_refs) or "-"},
            {"title": "선박", "body": ", ".join(labels.vessel_names) or "-"},
            {"title": "담당 영역", "body": ASSIGNEE_AREA_LABELS.get(labels.assignee_area, labels.assignee_area or "-")},
        ]
        if labels.key_spec_fields:
            sections.append(
                {
                    "title": "주요 사양",
                    "body": ", ".join(f"{key}: {value}" for key, value in labels.key_spec_fields.items()),
                }
            )
        return sections

    def _summary_text(self, message: DemoMessage) -> str:
        label = self._category_label(message)
        refs = ", ".join(message.expected_demo_labels.business_refs)
        vessels = ", ".join(message.expected_demo_labels.vessel_names)
        base = message.snippet or message.body_text.splitlines()[0]
        context = " / ".join(item for item in [vessels, refs] if item)
        return f"{label}: {context} - {base}" if context else f"{label}: {base}"

    def _category_label(self, message: DemoMessage) -> str:
        return CATEGORY_LABELS.get(message.expected_demo_labels.mail_category, message.expected_demo_labels.mail_category)

    @staticmethod
    def _size_label(size: int | None) -> str:
        if size is None:
            return ""
        if size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        if size >= 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size} B"


def parse_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _document_type_section_label(document_type: str) -> str:
    if document_type == "no_attachment":
        return "첨부 없음"
    if document_type == "unknown":
        return "알 수 없음"
    return document_type_label(document_type, document_type)


def _demo_level(value: str) -> str:
    return value if value in {"high", "normal"} else "normal"


def _demo_attention(value: str, urgency: str, importance: str) -> str:
    if value in ATTENTION_LABELS:
        return value
    if urgency == "high" and importance == "high":
        return "urgent_important"
    if urgency == "high":
        return "urgent"
    if importance == "high":
        return "important"
    return "normal"


def _demo_assignee_area_user_id(assignee_area: str) -> str:
    return {
        "sales": "10000000-0000-0000-0000-000000000001",
        "overseas_sales": "10000000-0000-0000-0000-000000000002",
        "technical": "10000000-0000-0000-0000-000000000003",
        "technical_sales": "10000000-0000-0000-0000-000000000004",
        "service": "10000000-0000-0000-0000-000000000005",
        "urgent_service": "10000000-0000-0000-0000-000000000006",
        "logistics": "10000000-0000-0000-0000-000000000007",
        "admin": "10000000-0000-0000-0000-000000000008",
    }.get(assignee_area, "")


def _ordered_document_type_sections(sections: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    order = {document_type: index for index, document_type in enumerate(DOCUMENT_TYPE_SECTION_ORDER)}
    return sorted(
        sections.values(),
        key=lambda section: (
            order.get(str(section.get("document_type") or ""), len(order)),
            str(section.get("label") or ""),
        ),
    )

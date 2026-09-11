from __future__ import annotations

import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any

from app.presentation.attachment_analysis import (
    DOCUMENT_TYPE_SECTION_ORDER,
    business_analysis_rows,
    canonical_document_type,
    document_type_label,
)
from app.mail_content import email_body_srcdoc, plain_email_body_srcdoc
from app.presentation.summary_text import polish_korean_summary_text
from app.repositories.postgres_mail_repository import PostgresMailRepository
from app.repositories.postgres_routing_repository import PostgresRoutingRepository
from app.services.demo_mail_service import DemoMailService


LEVEL_LABELS = {"high": "높음", "normal": "보통"}
ATTENTION_LABELS = {
    "urgent_important": "긴급·중요",
    "urgent": "긴급",
    "important": "중요",
    "normal": "일반",
}


class PostgresMailboxService:
    """PostgreSQL-backed mailbox adapter that preserves the current UI contract."""

    def __init__(self, database_url: str, project_dir: Path, *, provider: str = ""):
        self.repository = PostgresMailRepository(database_url, project_dir, provider=provider)
        self.routing_repository = PostgresRoutingRepository(database_url)

    def list_emails(self, *, q: str = "", category: str = "", limit: int | None = None) -> list[dict[str, Any]]:
        self.routing_repository.forward_auto_assigned_without_notification()
        return [
            self._message_row(message, index)
            for index, message in enumerate(self.repository.list_messages(q=q, category=category, limit=limit))
        ]

    def category_order(self) -> list[str]:
        return ["발주", "문의", "서비스", "기술", "기타", "미분류"]

    def search_documents(self) -> list[dict[str, Any]]:
        return self.repository.search_documents()

    def attachments_for_messages_payload(self, email_uids: list[str]) -> dict[str, list[dict[str, Any]]]:
        attachments_by_message: dict[str, list[dict[str, Any]]] = {email_uid: [] for email_uid in email_uids}
        for attachment in self.repository.attachments_for_messages(email_uids):
            email_uid = str(attachment.get("email_message_id") or "")
            if email_uid not in attachments_by_message:
                continue
            attachment_index = len(attachments_by_message[email_uid])
            attachments_by_message[email_uid].append(
                self._attachment_payload(attachment, email_uid, attachment_index)
            )
        return attachments_by_message

    def document_type_sections(self, *, q: str = "", limit_per_section: int = 8) -> list[dict[str, Any]]:
        rows = self.repository.list_messages(q=q)
        sections: dict[str, dict[str, Any]] = {}
        for index, message in enumerate(rows):
            email_row = self._message_row(message, index)
            attachments = [
                self._attachment_payload(attachment, str(message["id"]), attachment_index)
                for attachment_index, attachment in enumerate(
                    self.repository.attachments_for_message(str(message["id"]))
                )
            ]
            by_type: dict[str, list[dict[str, Any]]] = {}
            for attachment in attachments:
                document_type = canonical_document_type(
                    str(attachment.get("document_type") or attachment.get("document_category") or "")
                )
                if not document_type:
                    status = str(attachment.get("parse_status") or "")
                    document_type = "unknown" if status in {"completed", "partial_success"} else "unanalyzed"
                by_type.setdefault(document_type, []).append(attachment)

            for document_type, matching_attachments in by_type.items():
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
                section["attachment_count"] += len(matching_attachments)
                if len(section["emails"]) < limit_per_section:
                    section["emails"].append({**email_row, "document_attachments": matching_attachments})
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

    def _email_detail_payload(self, message: dict[str, Any], index: int) -> dict[str, Any]:
        row = self._message_row(message, index)
        all_attachments = self.repository.attachments_for_message(str(message["id"]), include_inline=True)
        attachments = self.repository.attachments_for_message(str(message["id"]))
        recipients = self.repository.recipients_for_message(str(message["id"]))
        row.update(
            {
                "body": message.get("body_text") or "",
                "body_html": message.get("body_html") or "",
                "body_html_srcdoc": self._body_html_srcdoc(message, all_attachments),
                "attachments": [
                    self._attachment_payload(attachment, str(message["id"]), attachment_index)
                    for attachment_index, attachment in enumerate(attachments)
                ],
                "to": ", ".join(
                    str(recipient["address"])
                    for recipient in recipients
                    if str(recipient.get("recipient_type") or "") == "to"
                ),
                "cc": ", ".join(
                    str(recipient["address"])
                    for recipient in recipients
                    if str(recipient.get("recipient_type") or "") == "cc"
                ),
                "classification": self._classification_payload(message),
                "summary": polish_korean_summary_text(str(message.get("summary_result_text") or "")),
                "executive_summary_sections": self._summary_sections(message),
            }
        )
        return row

    def _body_html_srcdoc(self, message: dict[str, Any], attachments: list[dict[str, Any]]) -> str:
        body_html = str(message.get("body_html") or "")
        if body_html:
            return email_body_srcdoc(
                body_html,
                [
                    self._attachment_payload(
                        attachment,
                        str(message["id"]),
                        attachment_index,
                        inline_lookup=True,
                    )
                    for attachment_index, attachment in enumerate(attachments)
                ],
            )
        return plain_email_body_srcdoc(str(message.get("body_text") or ""))

    def attachment_path(self, email_index: int, attachment_index: int) -> tuple[Path, str, str] | None:
        message = self.repository.message_by_index(email_index)
        return self._attachment_path(message, attachment_index)

    def attachment_path_by_uid(
        self,
        email_uid: str,
        attachment_index: int,
        *,
        include_inline: bool = False,
    ) -> tuple[Path, str, str] | None:
        resolved = self.repository.message_by_uid(email_uid)
        message = resolved[1] if resolved is not None else None
        return self._attachment_path(message, attachment_index, include_inline=include_inline)

    def _attachment_path(
        self,
        message: dict[str, Any] | None,
        attachment_index: int,
        *,
        include_inline: bool = False,
    ) -> tuple[Path, str, str] | None:
        if message is None:
            return None
        attachments = self.repository.attachments_for_message(str(message["id"]), include_inline=include_inline)
        if attachment_index < 0 or attachment_index >= len(attachments):
            return None
        attachment = attachments[attachment_index]
        path = self.repository.attachment_path(attachment)
        media_type = str(attachment.get("content_type") or "") or mimetypes.guess_type(str(path))[0]
        return path, str(attachment.get("filename") or path.name), media_type or "application/octet-stream"

    def _message_row(self, message: dict[str, Any], index: int) -> dict[str, Any]:
        classification = self._classification_payload(message)
        classification_state = self._classification_state(message)
        work_status = self._work_status(message, classification_state=classification_state)
        execution_status = str(message.get("work_item_status") or "")
        if execution_status:
            work_status = execution_status
        routing_status = str(message.get("routing_status") or "")
        has_confirmed_assignee = self._has_confirmed_assignee(message)
        routing_display = str(message.get("assignee_name") or "") if has_confirmed_assignee else ""
        routing_display = routing_display or "미할당"
        manual_route = self._manual_route_state(message, has_confirmed_assignee=has_confirmed_assignee)
        return {
            "index": index,
            "email_uid": str(message["id"]),
            "provider_message_id": str(message.get("provider_message_id") or ""),
            "provider_thread_id": str(message.get("provider_thread_id") or ""),
            "sender_name": message.get("sender_name") or message.get("sender_address") or "",
            "sender_address": message.get("sender_address") or "",
            "subject": message.get("subject") or "",
            "subject_normalized": message.get("subject_normalized") or "",
            "body_preview": message.get("snippet") or str(message.get("body_text") or "")[:180],
            "date": self._datetime_text(message.get("sent_at")),
            "received_at": self._datetime_text(message.get("received_at") or message.get("sent_at")),
            "cc": "",
            "has_attachment": bool(message.get("has_attachment")),
            "attachment_count": int(message.get("attachment_count") or 0),
            "work_status": work_status,
            "work_status_label": self._work_status_label(work_status, execution=bool(execution_status)),
            "work_item_id": str(message.get("work_item_id") or ""),
            "work_item_status": execution_status,
            "work_item_status_label": self._work_status_label(execution_status, execution=True) if execution_status else "",
            "work_item_assigned_at": self._datetime_text(message.get("work_item_assigned_at")),
            "work_item_acknowledged_at": self._datetime_text(message.get("work_item_acknowledged_at")),
            "work_item_reply_initiated_at": self._datetime_text(message.get("work_item_reply_initiated_at")),
            "work_item_first_responded_at": self._datetime_text(message.get("work_item_first_responded_at")),
            "work_item_responded_at": self._datetime_text(message.get("work_item_responded_at")),
            "work_item_completed_at": self._datetime_text(message.get("work_item_completed_at")),
            "work_item_due_at": self._datetime_text(message.get("work_item_due_at")),
            "work_item_last_activity_at": self._datetime_text(message.get("work_item_last_activity_at")),
            "classification_state": classification_state,
            "classification_state_label": self._classification_state_label(message),
            "classification_result_status": str(message.get("classification_result_status") or ""),
            "classification_result_created_at": self._datetime_text(message.get("classification_result_created_at")),
            "classification_result_updated_at": self._datetime_text(message.get("classification_result_updated_at")),
            "classification_duration_label": self._duration_label(
                message.get("classification_result_created_at"),
                message.get("classification_result_updated_at"),
            ),
            "summary_result_status": str(message.get("summary_result_status") or ""),
            "summary_result_created_at": self._datetime_text(message.get("summary_result_created_at")),
            "summary_result_updated_at": self._datetime_text(message.get("summary_result_updated_at")),
            "summary_duration_label": self._duration_label(
                message.get("summary_result_created_at"),
                message.get("summary_result_updated_at"),
            ),
            "summary_state": self._summary_state(message),
            "summary_state_label": self._summary_state_label(message),
            "mail_decision_status": str(message.get("mail_decision_status") or ""),
            "mail_decision_started_at": self._datetime_text(message.get("mail_decision_started_at")),
            "mail_decision_completed_at": self._datetime_text(message.get("mail_decision_completed_at")),
            "mail_decision_duration_label": self._duration_label(
                message.get("mail_decision_started_at"),
                message.get("mail_decision_completed_at"),
            ),
            "analysis_job_status": str(message.get("analysis_job_status") or ""),
            "mail_category": classification["mail_category"],
            "business_label": classification["business_label"],
            "urgency": classification["urgency"],
            "urgency_label": classification["urgency_label"],
            "importance": classification["importance"],
            "importance_label": classification["importance_label"],
            "attention_quadrant": classification["attention_quadrant"],
            "attention_label": classification["attention_label"],
            "priority": classification["attention_quadrant"],
            "priority_label": classification["attention_label"],
            "business_refs": classification["business_refs"],
            "routing_display": routing_display,
            "routing_target_label": routing_display,
            "assignee_name": (message.get("assignee_name") or "") if has_confirmed_assignee else "",
            "assignee_email": (message.get("assignee_email") or "") if has_confirmed_assignee else "",
            "assignee_department": self._assignee_preference(message, "department") if has_confirmed_assignee else "",
            "assignee_position": self._assignee_preference(message, "position") if has_confirmed_assignee else "",
            "assignee_user_id": str(message.get("assignee_user_id") or "") if has_confirmed_assignee else "",
            "routing_status": routing_status,
            "routing_assigned_at": self._datetime_text(message.get("routing_assigned_at")),
            "routing_fixed_at": self._datetime_text(message.get("routing_fixed_at")),
            "routing_forwarded_at": self._datetime_text(message.get("routing_forwarded_at")),
            "routing_completed_at": self._datetime_text(message.get("routing_completed_at")),
            **manual_route,
            "classification": classification,
            "mail_facts": message.get("mail_facts_json") if isinstance(message.get("mail_facts_json"), dict) else {},
            "customer_name": str(
                (message.get("mail_facts_json") if isinstance(message.get("mail_facts_json"), dict) else {}).get(
                    "customer_name"
                )
                or ""
            ),
        }

    def _classification_payload(self, message: dict[str, Any]) -> dict[str, Any]:
        mail_category = str(message.get("mail_category") or "미분류")
        confidence = message.get("category_confidence")
        summary_text = polish_korean_summary_text(str(message.get("summary_result_text") or ""))
        result_json = message.get("classification_result_json") if isinstance(message.get("classification_result_json"), dict) else {}
        urgency = _level_from_payload(result_json.get("urgency"), result_json.get("urgency_level"))
        importance = _level_from_payload(result_json.get("importance"), result_json.get("importance_level"))
        attention_quadrant = str(result_json.get("attention_quadrant") or "").strip()
        if attention_quadrant not in ATTENTION_LABELS:
            attention_quadrant = _attention_quadrant(urgency, importance)
        return {
            "business_label": mail_category,
            "mail_category": mail_category,
            "urgency": urgency,
            "urgency_label": LEVEL_LABELS.get(urgency, urgency),
            "importance": importance,
            "importance_label": LEVEL_LABELS.get(importance, importance),
            "attention_quadrant": attention_quadrant,
            "attention_label": str(result_json.get("attention_label") or ATTENTION_LABELS[attention_quadrant]),
            "routing_display": self._routing_display(message),
            "business_refs": result_json.get("business_refs", []),
            "vessel_names": result_json.get("vessel_names", []),
            "summary": summary_text,
            "executive_summary": summary_text,
            "confidence": float(confidence) if confidence is not None else 0,
            "label_scores": result_json.get("label_scores", {}),
            "reasoning_summary": result_json.get("reason", ""),
        }

    @staticmethod
    def _summary_sections(message: dict[str, Any]) -> list[dict[str, str]]:
        result_json = message.get("summary_result_json")
        if not isinstance(result_json, dict):
            return []
        sections = result_json.get("sections")
        if not isinstance(sections, list):
            return []
        payload: list[dict[str, str]] = []
        for section in sections:
            if not isinstance(section, dict):
                continue
            body = polish_korean_summary_text(str(section.get("body") or ""))
            if not body:
                continue
            payload.append({"title": str(section.get("title") or ""), "body": body})
        return payload

    def _attachment_payload(
        self,
        attachment: dict[str, Any],
        email_uid: str,
        attachment_index: int,
        *,
        inline_lookup: bool = False,
    ) -> dict[str, Any]:
        path = self.repository.attachment_path(attachment)
        analysis_json = attachment.get("analysis_result_json") if isinstance(attachment.get("analysis_result_json"), dict) else {}
        extracted_text = str(attachment.get("analysis_result_text") or analysis_json.get("extracted_text") or "")
        raw_analysis_status = str(attachment.get("analysis_status") or "").strip()
        storage_status = str(attachment.get("processing_status") or "").strip()
        if raw_analysis_status:
            analysis_status = raw_analysis_status
        elif storage_status in {"failed", "error", "pending", "queued", "running", "processing"}:
            analysis_status = storage_status
        else:
            analysis_status = "unknown"
        raw_fields = analysis_json.get("fields")
        if not isinstance(raw_fields, dict) or not raw_fields:
            raw_fields = analysis_json.get("extracted_fields")
        fields = raw_fields if isinstance(raw_fields, dict) else {}
        document_type = str(
            analysis_json.get("document_type")
            or analysis_json.get("document_category")
            or ""
        )
        document_type = canonical_document_type(document_type)
        document_label = document_type_label(
            document_type,
            str(analysis_json.get("document_category_label") or ""),
        )
        analysis_rows = business_analysis_rows(
            document_type=document_type,
            fields=fields,
            extracted_text=extracted_text,
            analysis_summary=str(analysis_json.get("analysis_summary") or ""),
            status=analysis_status,
            error_message=str(attachment.get("analysis_error_message") or attachment.get("parse_error") or ""),
        )
        return {
            "attachment_uid": str(attachment["id"]),
            "index": attachment_index,
            "filename": attachment.get("filename") or "attachment",
            "path": str(path),
            "content_type": attachment.get("content_type") or "",
            "content_id": attachment.get("content_id") or "",
            "content_disposition": attachment.get("content_disposition") or "",
            "is_inline": bool(attachment.get("is_inline")),
            "file_group": attachment.get("file_group") or "",
            "document_type": document_type,
            "document_category": document_type,
            "document_category_label": document_label,
            "size_label": DemoMailService._size_label(attachment.get("file_size")),
            "exists": path.exists(),
            "view_url": f"/api/emails/{email_uid}/attachments/{attachment_index}{'?inline=true' if inline_lookup else ''}",
            "download_url": f"/api/emails/{email_uid}/attachments/{attachment_index}?download=true",
            "preview_kind": "pdf" if attachment.get("content_type") == "application/pdf" else "file",
            "parse_status": analysis_status,
            "analysis_rows": analysis_rows,
        }

    @staticmethod
    def _classification_state(message: dict[str, Any]) -> str:
        if message.get("category_source"):
            return "completed"
        result_status = str(message.get("classification_result_status") or "")
        if result_status == "pending":
            return "queued"
        if result_status == "processing":
            return "running"
        if result_status == "failed":
            return "failed"
        job_status = str(message.get("analysis_job_status") or "")
        if job_status == "pending":
            return "queued"
        if job_status == "running":
            return "running"
        if job_status == "failed":
            return "failed"
        return "unclassified"

    @staticmethod
    def _work_status(message: dict[str, Any], *, classification_state: str) -> str:
        mail_decision_status = str(message.get("mail_decision_status") or "")
        job_status = str(message.get("analysis_job_status") or "")
        result_statuses = {
            str(message.get("classification_result_status") or ""),
            str(message.get("summary_result_status") or ""),
        }
        routing_status = str(message.get("routing_status") or "")
        has_confirmed_assignee = PostgresMailboxService._has_confirmed_assignee(message)

        if "failed" in {mail_decision_status, job_status, classification_state, *result_statuses}:
            return "failed"
        if "running" in {mail_decision_status, job_status, classification_state} or "processing" in result_statuses:
            return "running"
        if (
            routing_status == "forwarded"
            or str(message.get("manual_route_status") or "").strip() == "sent"
            or message.get("manual_route_sent_at")
        ):
            return "forwarded"
        if mail_decision_status == "auto_assigned":
            return "auto_assigned"
        if has_confirmed_assignee:
            return "assigned"
        if mail_decision_status == "review_required" or routing_status == "review_required":
            return "review_required"
        if "queued" in {mail_decision_status, classification_state} or "pending" in {job_status, *result_statuses}:
            return "queued"
        if classification_state in {"completed", "success"}:
            return "completed"
        return "unclassified"

    @staticmethod
    def _has_confirmed_assignee(message: dict[str, Any]) -> bool:
        routing_status = str(message.get("routing_status") or "")
        has_assignee = bool(message.get("assignee_name") or message.get("assignee_email") or message.get("assignee_user_id"))
        return has_assignee and routing_status in {"assigned", "forwarded", "completed"}

    @staticmethod
    def _manual_route_state(message: dict[str, Any], *, has_confirmed_assignee: bool) -> dict[str, str]:
        status = str(message.get("manual_route_status") or "").strip()
        if status == "pending":
            label = "전달 중"
            return {
                "manual_route_status": status,
                "manual_route_sent_at": "",
                "manual_route_error": "",
                "manual_route_label": label,
                "manual_route_status_label": label,
                "manual_route_button_label": label,
                "manual_route_button_variant": "pending",
                "manual_route_button_title": "이미 전달 작업이 진행 중입니다.",
            }
        if status == "sent" or str(message.get("routing_status") or "") == "forwarded":
            label = "전달 완료"
            return {
                "manual_route_status": "sent",
                "manual_route_sent_at": PostgresMailboxService._datetime_text(message.get("manual_route_sent_at")),
                "manual_route_error": "",
                "manual_route_label": label,
                "manual_route_status_label": label,
                "manual_route_button_label": label,
                "manual_route_button_variant": "sent",
                "manual_route_button_title": "전달이 완료되었습니다.",
            }
        if status == "failed":
            error = str(message.get("manual_route_error") or "전달 실패")
            return {
                "manual_route_status": status,
                "manual_route_sent_at": "",
                "manual_route_error": error,
                "manual_route_label": "재전달",
                "manual_route_status_label": "전달 실패",
                "manual_route_button_label": "재전달",
                "manual_route_button_variant": "failed",
                "manual_route_button_title": error,
            }
        if has_confirmed_assignee:
            assignee_email = str(message.get("assignee_email") or "")
            return {
                "manual_route_status": "",
                "manual_route_sent_at": "",
                "manual_route_error": "",
                "manual_route_label": "전달",
                "manual_route_status_label": "미전달",
                "manual_route_button_label": "전달",
                "manual_route_button_variant": "ready",
                "manual_route_button_title": assignee_email or "담당자에게 전달합니다.",
            }
        return {
            "manual_route_status": "",
            "manual_route_sent_at": "",
            "manual_route_error": "",
            "manual_route_label": "전달",
            "manual_route_status_label": "미할당",
            "manual_route_button_label": "전달",
            "manual_route_button_variant": "unassigned",
            "manual_route_button_title": "담당자 이메일이 아직 없습니다.",
        }

    @staticmethod
    def _assignee_preference(message: dict[str, Any], key: str) -> str:
        preferences = message.get("assignee_notification_preferences")
        if not isinstance(preferences, dict):
            return ""
        return str(preferences.get(key) or "")

    @staticmethod
    def _duration_label(start: object, end: object) -> str:
        if not isinstance(start, datetime) or not isinstance(end, datetime):
            return ""
        seconds = max(0.0, (end - start).total_seconds())
        if seconds < 60:
            return f"{seconds:.2f}초"
        minutes, remaining_seconds = divmod(seconds, 60.0)
        minutes = int(minutes)
        if minutes < 60:
            return f"{minutes}분 {remaining_seconds:.2f}초"
        hours, remaining_minutes = divmod(minutes, 60)
        return f"{hours}시간 {remaining_minutes}분 {remaining_seconds:.2f}초"

    @staticmethod
    def _routing_display(message: dict[str, Any]) -> str:
        if PostgresMailboxService._has_confirmed_assignee(message):
            return str(message.get("assignee_name") or "")
        return "미할당"

    @staticmethod
    def _work_status_label(status: str, *, execution: bool = False) -> str:
        labels = {
            "unclassified": "미분류",
            "queued": "대기",
            "running": "분석중",
            "completed": "분석 완료",
            "review_required": "검토 필요",
            "auto_assigned": "자동 배정",
            "assigned": "배정 완료",
            "acknowledged": "확인함",
            "in_progress": "진행중",
            "responded": "회신함",
            "forwarded": "전달 완료",
            "failed": "실패",
            "cancelled": "취소",
        }
        if execution and status == "completed":
            return "완료"
        if execution and status == "assigned":
            return "미확인"
        return labels.get(status, status or "미분류")

    @staticmethod
    def _classification_state_label(message: dict[str, Any]) -> str:
        if message.get("category_source"):
            return "DB"
        result_status = str(message.get("classification_result_status") or "")
        if result_status:
            return {
                "pending": "대기",
                "processing": "분석중",
                "success": "완료",
                "failed": "실패",
            }.get(result_status, result_status)
        job_status = str(message.get("analysis_job_status") or "")
        return {
            "pending": "대기",
            "running": "분석중",
            "failed": "실패",
            "success": "완료",
            "cancelled": "취소",
        }.get(job_status, "미분류")

    @staticmethod
    def _summary_state(message: dict[str, Any]) -> str:
        if message.get("summary_result_text") or message.get("summary_result_json"):
            return "completed"
        result_status = str(message.get("summary_result_status") or "")
        if result_status == "pending":
            return "queued"
        if result_status == "processing":
            return "running"
        if result_status == "failed":
            return "failed"
        job_status = str(message.get("analysis_job_status") or "")
        if job_status == "pending":
            return "queued"
        if job_status == "running":
            return "running"
        if job_status == "failed":
            return "failed"
        return "not_started"

    @staticmethod
    def _summary_state_label(message: dict[str, Any]) -> str:
        state = PostgresMailboxService._summary_state(message)
        return {
            "completed": "완료",
            "queued": "대기",
            "running": "생성중",
            "failed": "실패",
            "not_started": "미생성",
        }.get(state, state)

    @staticmethod
    def _datetime_text(value: object) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value or "")


def _document_type_section_label(document_type: str) -> str:
    if document_type == "unanalyzed":
        return "미분석"
    if document_type == "unknown":
        return "알 수 없음"
    return document_type_label(document_type, document_type)


def _level_from_payload(payload: object, legacy_value: object = None) -> str:
    if isinstance(payload, dict):
        value = str(payload.get("level") or "").strip()
    else:
        value = str(payload or legacy_value or "").strip()
    return value if value in LEVEL_LABELS else "normal"


def _attention_quadrant(urgency: str, importance: str) -> str:
    urgent = urgency == "high"
    important = importance == "high"
    if urgent and important:
        return "urgent_important"
    if urgent:
        return "urgent"
    if important:
        return "important"
    return "normal"


def _ordered_document_type_sections(sections: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    order = {document_type: index for index, document_type in enumerate(DOCUMENT_TYPE_SECTION_ORDER)}
    return sorted(
        sections.values(),
        key=lambda section: (
            order.get(str(section.get("document_type") or ""), len(order)),
            str(section.get("label") or ""),
        ),
    )

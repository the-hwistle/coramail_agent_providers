from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.document_processing.parsers import filter_predefined_document_fields
from app.schemas.attachment_analysis import AttachmentAnalysisResult


class PostgresAttachmentAnalysisRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url.strip()

    def save(self, result: AttachmentAnalysisResult, *, model_name: str = "local-parser-v1") -> None:
        import psycopg
        from psycopg.types.json import Jsonb

        now = datetime.now(timezone.utc)
        payload = result.model_dump(mode="json")
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT result_json
                        FROM attachment_analysis_results
                        WHERE attachment_id = %(attachment_id)s
                          AND analysis_type = 'document_understanding'
                          AND is_current IS TRUE
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        {"attachment_id": str(result.attachment_id)},
                    )
                    payload = preserve_current_business_fields(
                        payload,
                        _result_json_from_row(cursor.fetchone()),
                    )
                    cursor.execute(
                        """
                        UPDATE attachment_analysis_results
                        SET is_current = FALSE, updated_at = %(updated_at)s
                        WHERE attachment_id = %(attachment_id)s
                          AND analysis_type = 'document_understanding'
                          AND is_current IS TRUE
                        """,
                        {"attachment_id": str(result.attachment_id), "updated_at": now},
                    )
                    cursor.execute(
                        """
                        INSERT INTO attachment_analysis_results (
                            id, attachment_id, analysis_type, result_text, result_json,
                            model_name, model_version, status, error_message,
                            is_current, created_at, updated_at
                        ) VALUES (
                            %(id)s, %(attachment_id)s, 'document_understanding', %(result_text)s,
                            %(result_json)s, %(model_name)s, 'v1', %(status)s, %(error_message)s,
                            TRUE, %(created_at)s, %(updated_at)s
                        )
                        """,
                        {
                            "id": str(uuid4()),
                            "attachment_id": str(result.attachment_id),
                            "result_text": result.extracted_text or None,
                            "result_json": Jsonb(payload),
                            "model_name": model_name,
                            "status": result.status.value,
                            "error_message": result.error_message,
                            "created_at": now,
                            "updated_at": now,
                        },
                    )
                    cursor.execute(
                        """
                        UPDATE email_attachments
                        SET processing_status = %(status)s,
                            parse_error = %(parse_error)s,
                            updated_at = %(updated_at)s
                        WHERE id = %(attachment_id)s
                        """,
                        {
                            "attachment_id": str(result.attachment_id),
                            "status": result.status.value,
                            "parse_error": result.error_message,
                            "updated_at": now,
                        },
                    )

    def save_evidence(self, run_id: UUID, result: AttachmentAnalysisResult) -> None:
        import hashlib
        import psycopg
        from psycopg.types.json import Jsonb

        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    for evidence in result.evidence:
                        cursor.execute(
                            """
                            INSERT INTO evidence_items (
                                id, mail_decision_run_id, source_type, source_id, attachment_id,
                                page_number, bbox, evidence_text, content_hash, created_at
                            ) VALUES (
                                %(id)s, %(run_id)s, 'attachment', %(source_id)s, %(attachment_id)s,
                                %(page_number)s, %(bbox)s, %(evidence_text)s, %(content_hash)s, %(created_at)s
                            )
                            """,
                            {
                                "id": str(uuid4()),
                                "run_id": str(run_id),
                                "source_id": str(result.attachment_id),
                                "attachment_id": str(result.attachment_id),
                                "page_number": evidence.page_number,
                                "bbox": Jsonb(evidence.bbox) if evidence.bbox is not None else None,
                                "evidence_text": evidence.text,
                                "content_hash": hashlib.sha256(evidence.text.encode("utf-8")).hexdigest(),
                                "created_at": now,
                            },
                        )


def preserve_current_business_fields(
    new_payload: dict[str, Any],
    current_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Prevent reanalysis from replacing useful extracted fields with type-only output."""
    if not isinstance(current_payload, dict):
        return new_payload
    if has_business_fields(new_payload):
        return new_payload
    current_fields = _business_fields(current_payload)
    if not current_fields:
        return new_payload
    if _canonical_document_type(new_payload) != _canonical_document_type(current_payload):
        return new_payload
    preserved = dict(new_payload)
    preserved["fields"] = current_fields
    warnings = list(preserved.get("warnings") or [])
    if "preserved_previous_business_fields" not in warnings:
        warnings.append("preserved_previous_business_fields")
    preserved["warnings"] = warnings
    if not str(preserved.get("analysis_summary") or "").strip():
        preserved["analysis_summary"] = current_payload.get("analysis_summary") or ""
    return preserved


def has_business_fields(payload: dict[str, Any]) -> bool:
    return bool(_business_fields(payload))


def _business_fields(payload: dict[str, Any]) -> dict[str, Any]:
    document_type = _canonical_document_type(payload)
    fields = payload.get("fields")
    if isinstance(fields, dict) and any(value not in (None, "", [], {}) for value in fields.values()):
        return filter_predefined_document_fields(document_type, fields)
    extracted_fields = payload.get("extracted_fields")
    if isinstance(extracted_fields, dict) and any(
        value not in (None, "", [], {}) for value in extracted_fields.values()
    ):
        return filter_predefined_document_fields(document_type, extracted_fields)
    return {}


def _canonical_document_type(payload: dict[str, Any]) -> str:
    value = str(payload.get("document_type") or payload.get("document_category") or "").strip().casefold()
    aliases = {
        "quotation": "quote",
        "estimate": "quote",
        "견적서": "quote",
        "quote_request": "rfq",
        "request_for_quote": "rfq",
        "quotation_request": "rfq",
        "견적의뢰서": "rfq",
    }
    return aliases.get(value, value)


def _result_json_from_row(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    value = row.get("result_json") if isinstance(row, dict) else row[0]
    return value if isinstance(value, dict) else None

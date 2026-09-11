from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.llm.gateway import LocalLLMGateway
from app.document_processing.attachment_classifier import canonical_document_category, document_category_label
from app.document_processing.parsers import (
    PREDEFINED_DOCUMENT_FIELD_ORDER,
    PredefinedDocumentFieldName,
    validated_predefined_document_fields,
)
from app.schemas.attachment_analysis import AttachmentAnalysisResult


class BusinessDocumentUnderstanding(BaseModel):
    document_type: Literal[
        "quote",
        "rfq",
        "purchase_order",
        "payment_request",
        "transaction_statement",
        "invoice",
        "technical_document",
        "certificate",
        "general_document",
        "drawing_scan",
        "manual_scan",
        "field_photo",
        "part_photo",
        "document_scan",
        "unknown",
    ]
    confidence: float = Field(ge=0, le=1)
    summary: str
    fields: dict[PredefinedDocumentFieldName, Any] = Field(default_factory=dict)


class TextAttachmentAnalyzer:
    """Extracts user-facing business facts from already parsed document text."""

    def __init__(self, gateway: LocalLLMGateway):
        self.gateway = gateway

    def enrich(self, parsed: AttachmentAnalysisResult) -> AttachmentAnalysisResult:
        if not parsed.extracted_text.strip():
            return parsed
        document_input = parsed.document_html.strip() or parsed.extracted_text
        document_input_format = "HTML" if parsed.document_html.strip() else "plain text"
        output = self.gateway.generate_structured(
            system_prompt=(
                "You analyze business documents attached to email. Use only the parsed document text. "
                "When the input is HTML, preserve table row boundaries and read header-cell relationships from the markup. "
                "Choose the document type. Extract fields only when the field name is exactly one of the "
                "fixed field names in the JSON schema. "
                "Do not return parser metadata, checksums, page counts, dimensions, model names, or invented values. "
                "Do not create, translate, rename, or normalize field names."
            ),
            user_prompt=(
                f"Filename: {parsed.filename}\n"
                f"Input format: {document_input_format}\n"
                "Return a short Korean business summary and fixed-schema structured facts from this document. "
                "For quote/rfq documents only, include line_items for every table row. "
                "For quotes, use the largest No column value as the expected line item count, "
                "but do not output No as a field. For quote line_items, do not add the Korean "
                "currency unit 원 to Amount values. For rfq line_items, keep No and Code when visible "
                "and use the largest No value as the expected line item count. Do not invent U/Price or Amount. "
                f"Fixed fields by document type: {PREDEFINED_DOCUMENT_FIELD_ORDER}\n\n"
                f"{document_input[:16000]}"
            ),
            output_schema=BusinessDocumentUnderstanding,
            temperature=0.0,
        )
        output_type = canonical_document_category(output.document_type)
        if output_type == "unknown" and output.document_type not in {"unknown", None}:
            output_type = output.document_type
        parser_type = canonical_document_category(parsed.document_type)
        document_type = parser_type if parser_type != "unknown" and output_type in {"unknown", "general_document"} else output_type
        warnings = list(parsed.warnings)
        if (
            parser_type in {"quote", "rfq"}
            and output_type in {"quote", "rfq"}
            and parser_type != output_type
            and parsed.document_type_confidence >= 0.9
            and "attachment_text_rule" in warnings
        ):
            document_type = parser_type
            warnings.append(f"document_type_conflict:parser={parser_type},llm={output_type}")
        confidence = max(parsed.document_type_confidence, output.confidence) if document_type == parser_type else output.confidence
        fields, validation_warnings = validated_predefined_document_fields(
            document_type,
            parsed.extracted_text,
            {**parsed.fields, **output.fields},
        )
        for warning in validation_warnings:
            if warning not in warnings:
                warnings.append(warning)
        analysis_summary = (
            f"{document_category_label(document_type)} 유형으로 추정됩니다."
            if any(warning.startswith("document_type_conflict:") for warning in warnings)
            else output.summary
        )
        return parsed.model_copy(
            update={
                "document_type": document_type,
                "document_type_confidence": confidence,
                "analysis_summary": analysis_summary,
                "fields": fields,
                "warnings": warnings,
            }
        )

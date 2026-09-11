from __future__ import annotations

import base64
import io
import mimetypes
from pathlib import Path
from typing import Any, get_args
from uuid import UUID

from PIL import Image
from pydantic import BaseModel, Field, model_validator

from app.document_processing.attachment_classifier import (
    canonical_document_category,
    infer_attachment_document_category,
)
from app.document_processing.parsers import (
    PREDEFINED_DOCUMENT_FIELD_ORDER,
    PredefinedDocumentFieldName,
    filter_predefined_document_fields,
    validated_predefined_document_fields,
)
from app.llm.gateway import LocalLLMGateway
from app.schemas.attachment_analysis import (
    AttachmentAnalysisResult,
    AttachmentAnalysisStatus,
    AttachmentEvidence,
    AttachmentPage,
)


class VisionDocumentResult(BaseModel):
    document_type: str | None = None
    document_type_confidence: float = Field(default=0.0, ge=0, le=1)
    extracted_text: str = ""
    fields: dict[PredefinedDocumentFieldName, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_fixed_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        raw_fields = value.get("fields")
        if not isinstance(raw_fields, dict):
            return value

        document_type = canonical_document_category(value.get("document_type"))
        if document_type in PREDEFINED_DOCUMENT_FIELD_ORDER:
            filtered = filter_predefined_document_fields(document_type, raw_fields)
        else:
            allowed = set(get_args(PredefinedDocumentFieldName))
            filtered = {
                str(key).strip(): field_value
                for key, field_value in raw_fields.items()
                if str(key).strip() in allowed and field_value not in (None, "", [], {})
            }
        dropped = sorted({str(key).strip() for key in raw_fields if str(key).strip() not in filtered})
        if dropped:
            warnings = list(value.get("warnings") or [])
            warnings.extend(f"vision_unknown_field:{key}" for key in dropped if key)
            value = dict(value)
            value["warnings"] = warnings
        value["fields"] = filtered
        return value


class VisionAttachmentAnalyzer:
    def __init__(self, gateway: LocalLLMGateway):
        self.gateway = gateway

    def analyze_image(
        self,
        *,
        attachment_id: UUID,
        filename: str,
        content_type: str,
        path: Path,
    ) -> AttachmentAnalysisResult:
        encoded, mime_type = self._encode_image(path)
        result = self.gateway.generate_structured_vision(
            system_prompt=(
                "You analyze business email attachments. Extract only visible facts. "
                "Use only exact fixed field names from the JSON schema. "
                "Do not create, translate, rename, or normalize field names. "
                "Do not infer missing identifiers, dates, quantities, customers, products, or actions."
            ),
            user_prompt=(
                "Analyze this attachment. Return its document type, all readable text, and structured fields. "
                "For quote/rfq documents only, include line_items for every table row. "
                "For quotes, use the largest No column value as the expected line item count, "
                "but do not output No as a field. For quote line_items, do not add the Korean "
                "currency unit 원 to Amount values. For rfq line_items, keep No and Code when visible "
                "and use the largest No value as the expected line item count. Do not invent U/Price or Amount. "
                f"Fixed fields by document type: {PREDEFINED_DOCUMENT_FIELD_ORDER}. "
                "Use warnings for unreadable or ambiguous regions."
            ),
            image_base64=encoded,
            image_mime_type=mime_type,
            output_schema=VisionDocumentResult,
        )
        text = result.extracted_text.strip()
        evidence = [AttachmentEvidence(attachment_id=attachment_id, text=text[:4000])] if text else []
        status = AttachmentAnalysisStatus.COMPLETED if text else AttachmentAnalysisStatus.PARTIAL_SUCCESS
        warnings = list(result.warnings)
        if not text:
            warnings.append("vision_no_text_extracted")
        document_type = canonical_document_category(result.document_type)
        confidence = result.document_type_confidence
        inferred_type, inferred_confidence, inferred_reason = infer_attachment_document_category(
            filename=filename,
            content_type=content_type,
            extracted_text=text,
        )
        if (
            inferred_type in {"quote", "rfq"}
            and inferred_confidence >= 0.9
            and document_type in {"quote", "rfq"}
            and document_type != inferred_type
        ):
            warnings.append(f"document_type_conflict:vision={document_type},text={inferred_type}")
            document_type = inferred_type
            confidence = inferred_confidence
        elif document_type == "unknown":
            document_type = inferred_type
            confidence = inferred_confidence
            warnings.append(inferred_reason)
        fields, validation_warnings = validated_predefined_document_fields(document_type, text, result.fields)
        warnings.extend(warning for warning in validation_warnings if warning not in warnings)
        return AttachmentAnalysisResult(
            attachment_id=attachment_id,
            filename=filename,
            content_type=content_type,
            status=status,
            document_type=document_type,
            document_type_confidence=confidence,
            extracted_text=text,
            fields=fields,
            evidence=evidence,
            warnings=warnings,
        )

    def analyze_pdf_pages(
        self,
        *,
        attachment_id: UUID,
        filename: str,
        content_type: str,
        path: Path,
        existing_pages: list[AttachmentPage],
    ) -> AttachmentAnalysisResult:
        import fitz

        document = fitz.open(path)
        merged_pages: list[AttachmentPage] = []
        warnings: list[str] = []
        document_types: list[str] = []
        fields: dict[str, Any] = {}

        for page_index, existing in enumerate(existing_pages):
            if existing.text.strip():
                merged_pages.append(existing)
                continue
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = Image.open(io.BytesIO(pixmap.tobytes("png")))
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            result = self.gateway.generate_structured_vision(
                system_prompt=(
                    "Extract only facts visibly present on this scanned business document page. "
                    "Use only exact fixed field names from the JSON schema. "
                    "Do not create, translate, rename, or normalize field names."
                ),
                user_prompt=(
                    f"Analyze page {page_index + 1} of {filename}. "
                    "Return readable text and fixed-schema structured fields. "
                    "For quote/rfq documents only, include line_items for every table row. "
                    "For quotes, use the largest No column value as the expected line item count, "
                    "but do not output No as a field. For quote line_items, do not add the Korean "
                    "currency unit 원 to Amount values. For rfq line_items, keep No and Code when visible "
                    "and use the largest No value as the expected line item count. Do not invent U/Price or Amount. "
                    f"Fixed fields by document type: {PREDEFINED_DOCUMENT_FIELD_ORDER}."
                ),
                image_base64=base64.b64encode(buffer.getvalue()).decode("ascii"),
                image_mime_type="image/png",
                output_schema=VisionDocumentResult,
            )
            merged_pages.append(AttachmentPage(page_number=page_index + 1, text=result.extracted_text.strip()))
            document_type = canonical_document_category(result.document_type)
            if document_type != "unknown":
                document_types.append(document_type)
            fields.update(filter_predefined_document_fields(document_type, result.fields))
            warnings.extend(result.warnings)
            if not result.extracted_text.strip():
                warnings.append(f"page_{page_index + 1}_vision_no_text")

        text = "\n\n".join(page.text for page in merged_pages if page.text.strip())
        inferred_type, inferred_confidence, inferred_reason = infer_attachment_document_category(
            filename=filename,
            content_type=content_type,
            extracted_text=text,
        )
        if not document_types and inferred_reason != "no_rule_match":
            warnings.append(inferred_reason)
        evidence = [AttachmentEvidence(attachment_id=attachment_id, text=text[:4000])] if text else []
        unresolved = any(not page.text.strip() for page in merged_pages)
        final_document_type = document_types[0] if document_types else inferred_type
        if (
            inferred_type in {"quote", "rfq"}
            and inferred_confidence >= 0.9
            and final_document_type in {"quote", "rfq"}
            and final_document_type != inferred_type
        ):
            warnings.append(f"document_type_conflict:vision={final_document_type},text={inferred_type}")
            final_document_type = inferred_type
            document_types = []
        fields, validation_warnings = validated_predefined_document_fields(final_document_type, text, fields)
        warnings.extend(warning for warning in validation_warnings if warning not in warnings)
        return AttachmentAnalysisResult(
            attachment_id=attachment_id,
            filename=filename,
            content_type=content_type,
            status=AttachmentAnalysisStatus.PARTIAL_SUCCESS if unresolved else AttachmentAnalysisStatus.COMPLETED,
            document_type=final_document_type,
            document_type_confidence=0.7 if document_types else inferred_confidence,
            extracted_text=text,
            pages=merged_pages,
            fields=fields,
            evidence=evidence,
            warnings=warnings,
        )

    @staticmethod
    def _encode_image(path: Path) -> tuple[str, str]:
        mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
        return base64.b64encode(path.read_bytes()).decode("ascii"), mime_type

from __future__ import annotations

import re
from typing import Any

from app.document_processing.parsers import (
    PREDEFINED_DOCUMENT_FIELD_ORDER,
    RFQ_LINE_ITEM_FIELDS,
    QUOTE_LINE_ITEM_FIELDS,
    filter_predefined_document_fields,
    validated_predefined_document_fields,
)


FIELD_DISPLAY_ORDER = PREDEFINED_DOCUMENT_FIELD_ORDER

DOCUMENT_TYPE_ALIASES = {
    "quotation": "quote",
    "estimate": "quote",
    "견적서": "quote",
    "quote_request": "rfq",
    "request_for_quote": "rfq",
    "quotation_request": "rfq",
    "견적의뢰서": "rfq",
    "po": "purchase_order",
    "purchase order": "purchase_order",
    "purchase_order": "purchase_order",
    "발주서": "purchase_order",
    "입금요청서": "payment_request",
    "거래명세서": "transaction_statement",
    "technical_drawing": "drawing_scan",
    "delivery_followup": "delivery_confirmation",
}

FIELD_LABEL_ALIASES = {
    "customer": "To",
    "delivery_time": "Terms & Conditions - Delivery time",
    "packing": "Packing",
    "payment_method": "Payment Method",
    "payment_percentage": "Payment Percentage",
    "quantity": "Qty",
    "supplier": "Supplier",
    "total_price": "Total Price",
    "unit_price": "U/Price",
    "vessel/project": "Vessel",
    "total price": "Total Price",
    "delivery time": "Terms & Conditions - Delivery time",
    "Vessel Name": "Vessel",
}

QUOTE_FIELD_DISPLAY_LABELS = {
    "To": "거래처",
    "Date": "날짜",
    "Our Ref No": "거래처측 업무번호",
    "Total Price": "총액",
    "Your Ref No": "업무번호",
    "In Charge": "담당자명",
    "Tel": "연락처",
    "Vessel": "선박 (IMO 번호)",
}

LINE_ITEM_LABEL_ALIASES = {
    "amount": "Amount",
    "code": "Code",
    "description": "Description",
    "qty": "Qty",
    "quantity": "Qty",
    "unit": "Unit",
    "unit_price": "U/Price",
    "u/price": "U/Price",
}

TECHNICAL_FIELDS = {
    "attachment_id", "checksum", "content_type", "filename", "model_name", "pages",
    "parse_status", "status", "tables", "warnings", "width", "height", "mode", "format",
}

DOCUMENT_TYPE_LABELS = {
    "quote": "견적서",
    "rfq": "견적의뢰서",
    "purchase_order": "발주서",
    "payment_request": "입금요청서",
    "transaction_statement": "거래명세서",
    "invoice": "송장",
    "technical_document": "기술문서",
    "certificate": "인증서",
    "drawing_scan": "도면 스캔본",
    "manual_scan": "매뉴얼 스캔본",
    "field_photo": "현장 사진",
    "part_photo": "부품 사진",
    "document_scan": "JPG 스캔본",
    "general_document": "일반 문서",
    "delivery_confirmation": "납기 확인",
}

DOCUMENT_TYPE_SECTION_ORDER = [
    "rfq",
    "quote",
    "purchase_order",
    "delivery_confirmation",
    "payment_request",
    "transaction_statement",
    "invoice",
    "drawing_scan",
    "manual_scan",
    "field_photo",
    "part_photo",
    "document_scan",
    "unknown",
]


def normalize_business_fields(value: Any) -> dict[str, Any]:
    """Accept both coramail_ai and Mail Decision attachment field contracts."""
    if not isinstance(value, dict):
        return {}

    normalized: dict[str, Any] = {}
    field_list = value.get("field_name_from_schema")
    if isinstance(field_list, list):
        for item in field_list:
            _append_business_field(normalized, item, fallback_label="")

    for key, item in value.items():
        if key == "field_name_from_schema":
            continue
        _append_business_field(normalized, item, fallback_label=str(key))
    return normalized


def _append_business_field(normalized: dict[str, Any], item: Any, *, fallback_label: str) -> None:
    if item in (None, "", [], {}):
        return
    if fallback_label in TECHNICAL_FIELDS:
        return
    if isinstance(item, list):
        if fallback_label == "line_items":
            normalized[fallback_label] = [_normalize_line_item(child) for child in item]
            return
        if fallback_label == "dates":
            scalar_values = [
                _value_text(child) for child in item
                if not isinstance(child, (dict, list)) and _value_text(child)
            ]
            if scalar_values:
                normalized["Date"] = scalar_values[0]
                return
        if fallback_label == "reference_numbers":
            scalar_values = [
                _value_text(child) for child in item
                if not isinstance(child, (dict, list)) and _value_text(child)
            ]
            if scalar_values:
                normalized["Our Ref No"] = scalar_values[0]
            if len(scalar_values) > 1:
                normalized["Your Ref No"] = scalar_values[1]
            if scalar_values:
                return
        for child in item:
            _append_business_field(normalized, child, fallback_label="")
        return
    if isinstance(item, dict):
        label = _field_label(item.get("field_name") or item.get("name") or "")
        field_value = item.get("value")
        if label and field_value not in (None, "", [], {}):
            normalized[label] = field_value
            return
        flattened = False
        for child_key, child_value in item.items():
            if child_key in {"field_name", "name", "value"}:
                continue
            before_count = len(normalized)
            _append_business_field(normalized, child_value, fallback_label=str(child_key))
            flattened = flattened or len(normalized) != before_count
        if flattened:
            return
    if fallback_label:
        normalized[_field_label(fallback_label)] = item


def _normalize_line_item(item: Any) -> Any:
    if not isinstance(item, dict):
        return item
    normalized: dict[str, Any] = {}
    for key, value in item.items():
        label = LINE_ITEM_LABEL_ALIASES.get(str(key).strip().casefold(), str(key).strip())
        normalized[label] = value
    return normalized


def _field_label(value: Any) -> str:
    label = str(value or "").strip()
    return FIELD_LABEL_ALIASES.get(label, FIELD_LABEL_ALIASES.get(label.casefold(), label))


def field_display_label(label: Any, document_type: str = "") -> str:
    text = str(label or "").strip()
    if canonical_document_type(document_type) == "quote":
        return QUOTE_FIELD_DISPLAY_LABELS.get(text, text)
    return text


def document_type_label(document_type: str, fallback: str = "") -> str:
    canonical_type = canonical_document_type(document_type)
    return DOCUMENT_TYPE_LABELS.get(canonical_type, fallback.strip() or document_type.strip())


def canonical_document_type(document_type: str) -> str:
    normalized = document_type.strip()
    return DOCUMENT_TYPE_ALIASES.get(normalized, DOCUMENT_TYPE_ALIASES.get(normalized.casefold(), normalized))


def business_analysis_rows(
    *,
    document_type: str,
    fields: dict[str, Any],
    extracted_text: str,
    analysis_summary: str = "",
    status: str,
    error_message: str = "",
) -> list[dict[str, Any]]:
    """Return only information that helps a mail user act on the document."""
    document_type = canonical_document_type(document_type)
    if document_type in FIELD_DISPLAY_ORDER:
        fields = filter_predefined_document_fields(document_type, fields)
    else:
        fields = normalize_business_fields(fields)
    if extracted_text.strip() and document_type in FIELD_DISPLAY_ORDER:
        validated_fields, _warnings = validated_predefined_document_fields(document_type, extracted_text, fields)
        if validated_fields:
            fields = validated_fields
    rows: list[dict[str, Any]] = []
    ordered = FIELD_DISPLAY_ORDER.get(document_type, [])
    keys = ordered or [key for key in fields if key not in TECHNICAL_FIELDS and key != "line_items"]
    seen_keys: set[str] = set()
    for key in keys:
        if key == "line_items":
            continue
        seen_keys.add(key)
        value = _display_value(key, fields.get(key))
        if value:
            rows.append({"label": key, "value": value})
    line_items = fields.get("line_items")
    if isinstance(line_items, list):
        line_item_fields = _line_item_fields_for_display(document_type)
        for index, item in enumerate(line_items, start=1):
            if not isinstance(item, dict):
                continue
            columns = [
                {"label": key, "value": _display_line_item_value(key, item.get(key))}
                for key in line_item_fields
            ]
            if any(column["value"] for column in columns):
                rows.append(
                    {
                        "label": f"품목 {index}",
                        "value": " ".join(column["value"] for column in columns if column["value"]),
                        "kind": "line_item",
                        "columns": columns,
                    }
                )

    if rows:
        return rows
    if document_type in FIELD_DISPLAY_ORDER:
        return []
    summary = " ".join(analysis_summary.split())
    if summary and not _is_type_guess_summary(summary):
        return [{"label": "내용", "value": summary[:500]}]
    if extracted_text.strip():
        preview = " ".join(extracted_text.split())
        return [{"label": "내용", "value": preview[:500]}]
    return []


def _line_item_fields_for_display(document_type: str) -> tuple[str, ...]:
    if document_type == "rfq":
        return RFQ_LINE_ITEM_FIELDS
    return QUOTE_LINE_ITEM_FIELDS


def _is_type_guess_summary(value: str) -> bool:
    summary = " ".join(value.split()).strip()
    return summary.endswith("유형으로 추정됩니다.") or summary.endswith("유형으로 추정됩니다")


def _value_text(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, dict):
        return " / ".join(
            f"{key} {_value_text(item)}" for key, item in value.items() if _value_text(item)
        )
    if isinstance(value, list):
        return ", ".join(_value_text(item) for item in value if _value_text(item))
    return str(value).strip()


def _display_value(label: str, value: Any) -> str:
    text = _value_text(value)
    if not text:
        return ""
    if label in {"Total Price", "U/Price", "Amount"}:
        return _format_krw_as_won(text)
    return text


def _display_line_item_value(label: str, value: Any) -> str:
    text = _value_text(value)
    if not text:
        return ""
    if label == "U/Price":
        return _format_krw_as_won(text)
    return text


def _format_krw_as_won(value: str) -> str:
    text = re.sub(
        r"\b([0-9][0-9,]*(?:\.\d+)?)\s*KRW\b",
        lambda match: f"{match.group(1)}원",
        value,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bKRW\s*([0-9][0-9,]*(?:\.\d+)?)\b",
        lambda match: f"{match.group(1)}원",
        text,
        flags=re.IGNORECASE,
    )
    if re.search(r"\b(?:USD|EUR|JPY)\b", text, flags=re.IGNORECASE):
        return text
    return re.sub(
        r"\b([0-9][0-9,]*(?:\.\d+)?)(?![,\d])\b(?!\s*원)",
        lambda match: f"{match.group(1)}원",
        text,
    )

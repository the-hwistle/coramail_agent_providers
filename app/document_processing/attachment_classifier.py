from __future__ import annotations

from pathlib import Path
import re


DOCUMENT_CATEGORIES = {
    "quote",
    "rfq",
    "purchase_order",
    "payment_request",
    "transaction_statement",
    "drawing_scan",
    "manual_scan",
    "field_photo",
    "part_photo",
    "document_scan",
    "unknown",
}

DOCUMENT_CATEGORY_LABELS = {
    "quote": "견적서",
    "rfq": "견적의뢰서",
    "purchase_order": "발주서",
    "payment_request": "입금요청서",
    "transaction_statement": "거래명세서",
    "drawing_scan": "도면 스캔본",
    "manual_scan": "매뉴얼 스캔본",
    "field_photo": "현장 사진",
    "part_photo": "부품 사진",
    "document_scan": "JPG 스캔본",
    "unknown": "미분류",
}

DOCUMENT_CATEGORY_ALIASES = {
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
    "jpg_scan": "document_scan",
    "image_scan": "document_scan",
}

STRUCTURED_DOCUMENT_TYPES = {"quote", "rfq", "purchase_order", "payment_request", "transaction_statement"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp", ".gif"}


def document_category_label(category: str) -> str:
    return DOCUMENT_CATEGORY_LABELS.get(canonical_document_category(category), DOCUMENT_CATEGORY_LABELS["unknown"])


def canonical_document_category(category: str | None) -> str:
    normalized = str(category or "").strip()
    if not normalized:
        return "unknown"
    canonical = DOCUMENT_CATEGORY_ALIASES.get(normalized, DOCUMENT_CATEGORY_ALIASES.get(normalized.casefold(), normalized))
    return canonical if canonical in DOCUMENT_CATEGORIES else "unknown"


def infer_document_category_from_text(text: str) -> str:
    normalized = str(text or "")
    upper = normalized.upper()
    compact = " ".join(normalized.split())
    if _contains_rfq_marker(normalized, upper, compact):
        return "rfq"
    if "QUOTATION" in upper or "견적서" in normalized:
        return "quote"
    if "PURCHASE ORDER" in upper or "P/O" in upper or "발주서" in normalized:
        return "purchase_order"
    if "입 금 요 청 서" in normalized or "입금요청서" in normalized:
        return "payment_request"
    if "거래명세서" in normalized or "거래 명세서" in compact:
        return "transaction_statement"
    return "unknown"


def infer_attachment_document_category(
    *,
    filename: str,
    content_type: str,
    extracted_text: str = "",
) -> tuple[str, float, str]:
    text_category = infer_document_category_from_text(extracted_text)
    if text_category != "unknown":
        return text_category, 0.94, "attachment_text_rule"

    name = Path(filename or "").name.casefold()
    content_type = content_type.casefold()
    suffix = Path(filename or "").suffix.casefold()
    if content_type.startswith("image/") or suffix in IMAGE_EXTENSIONS:
        return _image_category_from_name(name), 0.55, "image_filename_rule"

    if content_type == "application/pdf" or suffix == ".pdf":
        category = _pdf_category_from_name(name)
        if category != "unknown":
            return category, 0.62, "pdf_filename_rule"

    return "unknown", 0.0, "no_rule_match"


def _pdf_category_from_name(name: str) -> str:
    if any(
        token in name
        for token in (
            "inquiry",
            "rfq",
            "quote_request",
            "quotation_request",
            "request_for_quote",
            "request_for_quotation",
            "견적의뢰",
            "견적요청",
            "견적_요청",
            "견적 요청",
        )
    ):
        return "rfq"
    if any(token in name for token in ("quotation", "quote", "견적서")):
        return "quote"
    if any(token in name for token in ("purchase_order", "purchase order", "po_", "p_o", "발주서")):
        return "purchase_order"
    if any(token in name for token in ("payment", "입금요청")):
        return "payment_request"
    if any(token in name for token in ("transaction", "statement", "거래명세")):
        return "transaction_statement"
    return "unknown"


def _contains_rfq_marker(normalized: str, upper: str, compact: str) -> bool:
    if any(token in upper for token in ("INQUIRY", "RFQ")):
        return True
    if re.search(r"\bREQUEST\s+FOR\s+(?:A\s+)?QUOT(?:ATION|E)\b", upper):
        return True
    if re.search(r"\bQUOT(?:ATION|E)\s+REQUEST\b", upper):
        return True
    if any(
        token in normalized
        for token in (
            "견적의뢰서",
            "견적 의뢰서",
            "견적의뢰",
            "견적 의뢰",
            "견적요청서",
            "견적 요청서",
            "견적요청",
            "견적 요청",
        )
    ):
        return True
    return "견적 의뢰" in compact or "견적 요청" in compact


def _image_category_from_name(name: str) -> str:
    if any(token in name for token in ("drawing", "dwg", "도면")):
        return "drawing_scan"
    if any(token in name for token in ("manual", "매뉴얼", "메뉴얼")):
        return "manual_scan"
    if any(token in name for token in ("field", "site", "onsite", "현장")):
        return "field_photo"
    if any(token in name for token in ("part", "component", "품목", "부품")):
        return "part_photo"
    return "document_scan"

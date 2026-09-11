from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.document_processing.attachment_classifier import (
    infer_attachment_document_category,
    infer_document_category_from_text,
)
from app.document_processing.paddleocr_adapter import PaddleOCRParsedDocument
from app.document_processing.text_analyzer import BusinessDocumentUnderstanding, TextAttachmentAnalyzer
from app.document_processing.parsers import AttachmentParserDispatcher
from app.document_processing.parsers import filter_predefined_document_fields
from app.document_processing.parsers import validated_predefined_document_fields
from app.evaluation.fixtures import SyntheticFixtureGenerator
from app.schemas.attachment_analysis import AttachmentAnalysisResult, AttachmentAnalysisStatus


def attachment(path: Path, content_type: str) -> dict[str, object]:
    return {
        "id": str(uuid4()),
        "filename": path.name,
        "storage_uri": str(path),
        "content_type": content_type,
    }


class QuoteBiasedGateway:
    def generate_structured(self, **_kwargs) -> BusinessDocumentUnderstanding:
        return BusinessDocumentUnderstanding(
            document_type="quote",
            confidence=0.88,
            summary="견적서 유형으로 추정됩니다.",
            fields={},
        )


class CapturingDocumentGateway:
    def __init__(self):
        self.calls: list[dict[str, object]] = []

    def generate_structured(self, **kwargs) -> BusinessDocumentUnderstanding:
        self.calls.append(kwargs)
        return BusinessDocumentUnderstanding(
            document_type="rfq",
            confidence=0.91,
            summary="견적의뢰서 표를 확인했습니다.",
            fields={
                "Our Ref No": "RFQ-2026-0902-01",
                "line_items": [
                    {"No": "1", "Description": "FILTER ELEMENT", "Code": "FE-100", "Qty": "20", "Unit": "EA"}
                ],
            },
        )


def test_text_attachment_is_completed(tmp_path: Path) -> None:
    path = tmp_path / "request.txt"
    path.write_text("PO-2026-001 delivery request", encoding="utf-8")
    result = AttachmentParserDispatcher(tmp_path).analyze(attachment(path, "text/plain"))
    assert result.status == AttachmentAnalysisStatus.COMPLETED
    assert "PO-2026-001" in result.extracted_text
    assert result.evidence


def test_missing_attachment_is_failed(tmp_path: Path) -> None:
    path = tmp_path / "missing.pdf"
    result = AttachmentParserDispatcher(tmp_path).analyze(attachment(path, "application/pdf"))
    assert result.status == AttachmentAnalysisStatus.FAILED
    assert "attachment_source_missing" in result.warnings


def test_image_requires_vision(tmp_path: Path) -> None:
    from PIL import Image

    path = tmp_path / "field-site-photo.png"
    Image.new("RGB", (10, 20)).save(path)
    result = AttachmentParserDispatcher(tmp_path).analyze(attachment(path, "image/png"))
    assert result.status == AttachmentAnalysisStatus.PARTIAL_SUCCESS
    assert result.document_type == "field_photo"
    assert result.analysis_summary == "현장 사진 유형으로 추정됩니다."
    assert result.fields["width"] == 10
    assert "vision_analysis_required" in result.warnings


def test_rfq_text_markers_take_precedence_over_generic_quotation() -> None:
    assert infer_document_category_from_text("REQUEST FOR QUOTATION\nNo | Description | Code | Qty | Unit") == "rfq"
    assert infer_document_category_from_text("QUOTATION REQUEST\nNo | Description | Code | Qty | Unit") == "rfq"
    assert infer_document_category_from_text("견적 요청서\nNo | Description | Code | Qty | Unit") == "rfq"
    assert infer_document_category_from_text("QUOTATION / 견적서\nTotal Price KRW 10,000") == "quote"


def test_rfq_filename_markers_take_precedence_over_generic_quotation() -> None:
    assert (
        infer_attachment_document_category(
            filename="FM260000777_quotation_request.pdf",
            content_type="application/pdf",
            extracted_text="",
        )[0]
        == "rfq"
    )
    assert (
        infer_attachment_document_category(
            filename="request_for_quotation.pdf",
            content_type="application/pdf",
            extracted_text="",
        )[0]
        == "rfq"
    )
    assert (
        infer_attachment_document_category(
            filename="FM250016329_quotation.pdf",
            content_type="application/pdf",
            extracted_text="",
        )[0]
        == "quote"
    )


def test_image_filename_rules_assign_business_image_labels(tmp_path: Path) -> None:
    from PIL import Image

    expected = {
        "pump-drawing.png": "drawing_scan",
        "part-seal.jpg": "part_photo",
        "scanned-page.png": "document_scan",
    }
    for filename, document_type in expected.items():
        path = tmp_path / filename
        Image.new("RGB", (10, 20)).save(path)
        result = AttachmentParserDispatcher(tmp_path).analyze(attachment(path, "image/png"))
        assert result.document_type == document_type
        assert result.document_type_confidence == 0.55


def test_pdf_text_rules_assign_structured_form_labels(tmp_path: Path) -> None:
    path = tmp_path / "FM250016329.pdf"
    SyntheticFixtureGenerator._pdf(
        path,
        (
            "QUOTATION\n"
            "To FLUMAX Co., Ltd.\n"
            "Vessel GH MADISON\n"
            "Our Ref No FM250016329\n"
            "Total Price KRW 518,000\n"
            "Description | Code | Qty | Unit | U/Price | Amount\n"
            "Pump Seal | PS-10 | 2 | EA | KRW 100,000 | KRW 200,000"
        ),
    )

    result = AttachmentParserDispatcher(tmp_path).analyze(attachment(path, "application/pdf"))

    assert result.status == AttachmentAnalysisStatus.COMPLETED
    assert result.document_type == "quote"
    assert result.document_type_confidence == 0.94
    assert result.analysis_summary == "견적서 유형으로 추정됩니다."
    assert result.fields["To"] == "FLUMAX Co., Ltd."
    assert result.fields["Vessel"] == "GH MADISON"
    assert result.fields["Our Ref No"] == "FM250016329"
    assert result.fields["Total Price"] == "KRW 518,000"
    assert result.fields["line_items"] == [
        {
            "Description": "Pump Seal",
            "Qty": "2",
            "Unit": "EA",
            "U/Price": "KRW 100,000",
            "Amount": "KRW 200,000",
        }
    ]
    assert "attachment_text_rule" in result.warnings


def test_pdf_parser_preserves_paddleocr_html_for_document_understanding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "FM260000777_INQUIRY.pdf"
    SyntheticFixtureGenerator._pdf(path, "INQUIRY\nNo | Description | Code | Qty | Unit\n")
    document_html = (
        '<section data-page="1"><table><tr><th>No</th><th>Description</th><th>Code</th><th>Qty</th><th>Unit</th></tr>'
        "<tr><td>1</td><td>FILTER ELEMENT</td><td>FE-100</td><td>20</td><td>EA</td></tr></table></section>"
    )

    monkeypatch.setenv("CORAMAIL_PADDLEOCR_MODE", "always")
    monkeypatch.setenv("CORAMAIL_PADDLEOCR_ENABLED", "true")
    monkeypatch.setattr(
        "app.document_processing.parsers.parse_with_paddleocr",
        lambda _path: PaddleOCRParsedDocument(
            text="INQUIRY\nNo | Description | Code | Qty | Unit\n1 | FILTER ELEMENT | FE-100 | 20 | EA",
            html=document_html,
            page_texts=["INQUIRY\nNo | Description | Code | Qty | Unit\n1 | FILTER ELEMENT | FE-100 | 20 | EA"],
            warnings=["paddleocr_structurev3"],
        ),
    )

    parsed = AttachmentParserDispatcher(tmp_path).analyze(attachment(path, "application/pdf"))
    gateway = CapturingDocumentGateway()
    enriched = TextAttachmentAnalyzer(gateway).enrich(parsed)  # type: ignore[arg-type]

    assert parsed.status == AttachmentAnalysisStatus.COMPLETED
    assert parsed.document_html == document_html
    assert "paddleocr_structurev3" in parsed.warnings
    assert "Input format: HTML" in str(gateway.calls[0]["user_prompt"])
    assert document_html in str(gateway.calls[0]["user_prompt"])
    assert enriched.fields["line_items"] == [
        {"No": "1", "Description": "FILTER ELEMENT", "Code": "FE-100", "Qty": "20", "Unit": "EA"}
    ]


def test_pdf_text_rules_extract_rfq_fields_and_line_items(tmp_path: Path) -> None:
    path = tmp_path / "FM260000777_INQUIRY.pdf"
    SyntheticFixtureGenerator._pdf(
        path,
        (
            "INQUIRY / 견적의뢰서\n"
            "To FLUMAX Co., Ltd.\n"
            "Attn Ryan Kim\n"
            "Email sales@flumax.example\n"
            "Tel 051-000-0000\n"
            "Fax 051-000-0001\n"
            "Vessel GH MADISON\n"
            "Date 2026-08-31\n"
            "Our Ref No RFQ-2026-0831-01\n"
            "In Charge Alex Lee\n"
            "No | Description | Code | Qty | Unit\n"
            "1 | FILTER ELEMENT | FE-100 | 20 | EA\n"
            "2 | O-RING KIT | ORK-77 | 3 | SET\n"
        ),
    )

    result = AttachmentParserDispatcher(tmp_path).analyze(attachment(path, "application/pdf"))

    assert result.status == AttachmentAnalysisStatus.COMPLETED
    assert result.document_type == "rfq"
    assert result.document_type_confidence == 0.94
    assert result.analysis_summary == "견적의뢰서 유형으로 추정됩니다."
    assert result.fields == {
        "To": "FLUMAX Co., Ltd.",
        "Attn": "Ryan Kim",
        "Email": "sales@flumax.example",
        "Fax": "051-000-0001",
        "Vessel": "GH MADISON",
        "Date": "2026-08-31",
        "Our Ref No": "RFQ-2026-0831-01",
        "In Charge": "Alex Lee",
        "Tel": "051-000-0000",
        "line_items": [
            {"No": "1", "Description": "FILTER ELEMENT", "Code": "FE-100", "Qty": "20", "Unit": "EA"},
            {"No": "2", "Description": "O-RING KIT", "Code": "ORK-77", "Qty": "3", "Unit": "SET"},
        ],
    }
    assert "attachment_text_rule" in result.warnings


def test_text_enrichment_keeps_high_confidence_rfq_when_llm_returns_quote() -> None:
    attachment_id = uuid4()
    parsed = AttachmentAnalysisResult(
        attachment_id=attachment_id,
        filename="FM260000777_quotation_request.pdf",
        content_type="application/pdf",
        status=AttachmentAnalysisStatus.COMPLETED,
        document_type="rfq",
        document_type_confidence=0.94,
        analysis_summary="견적의뢰서 유형으로 추정됩니다.",
        extracted_text=(
            "REQUEST FOR QUOTATION\n"
            "To FLUMAX Co., Ltd.\n"
            "Our Ref No RFQ-2026-0831-01\n"
            "No | Description | Code | Qty | Unit\n"
            "1 | FILTER ELEMENT | FE-100 | 20 | EA\n"
        ),
        fields={"Our Ref No": "RFQ-2026-0831-01"},
        warnings=["attachment_text_rule"],
    )

    result = TextAttachmentAnalyzer(QuoteBiasedGateway()).enrich(parsed)  # type: ignore[arg-type]

    assert result.document_type == "rfq"
    assert result.analysis_summary == "견적의뢰서 유형으로 추정됩니다."
    assert "document_type_conflict:parser=rfq,llm=quote" in result.warnings
    assert result.fields["line_items"] == [
        {"No": "1", "Description": "FILTER ELEMENT", "Code": "FE-100", "Qty": "20", "Unit": "EA"}
    ]


def test_rfq_validation_recovers_compact_line_items_with_code() -> None:
    fields, warnings = validated_predefined_document_fields(
        "rfq",
        (
            "INQUIRY\n"
            "To FLUMAX Co., Ltd.\n"
            "Our Ref No RFQ-2026-0831-02\n"
            "No  Description                         Code     Qty Unit\n"
            "1   FILTER ELEMENT                      FE-100   20  EA\n"
            "2   O-RING KIT                          ORK-77   3   SET\n"
        ),
        {},
    )

    assert fields["line_items"] == [
        {"No": "1", "Description": "FILTER ELEMENT", "Code": "FE-100", "Qty": "20", "Unit": "EA"},
        {"No": "2", "Description": "O-RING KIT", "Code": "ORK-77", "Qty": "3", "Unit": "SET"},
    ]
    assert warnings == []


def test_rfq_validation_recovers_vertical_pdf_line_item_tokens() -> None:
    fields, warnings = validated_predefined_document_fields(
        "rfq",
        (
            "INQUIRY / 견적의뢰서\n"
            "Our Ref No\n:\nFM250015721\n"
            "No\nNo\nDescription\nDescription\nCode\nCode\nQty\nQty\nUnit\nUnit\n"
            "SOLENOID VALVE\nSOLENOID VALVE\n"
            "1\nWDEFA04-AB3-1/x-G24-VD\n3\nEA\n"
            "PAGE 1 /\n1\n"
        ),
        {},
    )

    assert fields["line_items"] == [
        {
            "No": "1",
            "Description": "SOLENOID VALVE",
            "Code": "WDEFA04-AB3-1/x-G24-VD",
            "Qty": "3",
            "Unit": "EA",
        }
    ]
    assert warnings == []


def test_rfq_validation_recovers_wrapped_vertical_pdf_line_item_tokens() -> None:
    fields, warnings = validated_predefined_document_fields(
        "rfq",
        (
            "INQUIRY / 견적의뢰서\n"
            "No\nNo\nDescription\nDescription\nCode\nCode\nQty\nQty\nUnit\nUnit\n"
            "1\nITEM 1\nCODE-1\n1\nEA\n"
            "2\nITEM 2\nCODE-2\n1\nEA\n"
            "3\nITEM 3\nCODE-3\n1\nEA\n"
            "4\nITEM 4\nCODE-4\n1\nEA\n"
            "5\nITEM 5\nCODE-5\n1\nEA\n"
            "6\nITEM 6\nCODE-6\n1\nEA\n"
            "7\nITEM 7\nCODE-7\n1\nEA\n"
            "8\nITEM 8\nCODE-8\n1\nEA\n"
            "9\nITEM 9\nCODE-9\n1\nEA\n"
            "10\nITEM 10\nCODE-10\n1\nEA\n"
            "11\n"
            "FLOWMETER INCL. REG. VALVE TILSLUTNING 1/8 NPT\n"
            "98500037-66\n"
            "2\n"
            "EA\n"
            "ELECTRICAL MOTOR (985 16704-80B-2)\n"
            "ELECTRICAL MOTOR (985 16704-80B-2)\n"
            "12\n"
            "MOTOR FOR FRESH WATER PUMP ELECTRIC MOTOR (C1 FLANGED)\n"
            "98516704-80B-\n"
            "2\n"
            "1\n"
            "EA\n"
            "FRESH WATER GENERATOR ALFA LAVAL VSP-36-125 CC/SWC (SA)\n"
            "FRESH WATER GENERATOR ALFA LAVAL VSP-36-125 CC/SWC (SA)\n"
            "13\n"
            "SOLENOID VALVE (NORMALLY OPEN) ITEM NO:VA-FR-05 ITEM NAME: SOLENOID\n"
            "VALVE (NORMALLY OPEN) PART NO:VA-FR-05 DWG NO:SHI-H1536/3/A-1 DESC:\n"
            "SOLENOID VALVE (N.O.) FRESH WATER PUMP OUTLET TO BRINE LINE. Information\n"
            "from : MM-31\n"
            "VA-FR-05\n"
            "3\n"
            "EA\n"
            "PAGE 1 /\n1\n"
        ),
        {},
    )

    assert [item["No"] for item in fields["line_items"]] == [str(number) for number in range(1, 14)]
    assert fields["line_items"][11] == {
        "No": "12",
        "Description": "MOTOR FOR FRESH WATER PUMP ELECTRIC MOTOR (C1 FLANGED)",
        "Code": "98516704-80B-2",
        "Qty": "1",
        "Unit": "EA",
    }
    assert fields["line_items"][12] == {
        "No": "13",
        "Description": (
            "SOLENOID VALVE (NORMALLY OPEN) ITEM NO:VA-FR-05 ITEM NAME: SOLENOID "
            "VALVE (NORMALLY OPEN) PART NO:VA-FR-05 DWG NO:SHI-H1536/3/A-1 DESC: "
            "SOLENOID VALVE (N.O.) FRESH WATER PUMP OUTLET TO BRINE LINE. Information from : MM-31"
        ),
        "Code": "VA-FR-05",
        "Qty": "3",
        "Unit": "EA",
    }
    assert warnings == []


def test_rfq_validation_reextracts_line_items_when_no_column_count_is_larger() -> None:
    fields, warnings = validated_predefined_document_fields(
        "rfq",
        (
            "INQUIRY / 견적의뢰서\n"
            "No | Description | Code | Qty | Unit\n"
            "1 | FILTER ELEMENT | FE-100 | 20 | EA\n"
            "2 | O-RING KIT | ORK-77 | 3 | SET\n"
            "3 | SOLENOID VALVE | SV-9 | 1 | EA\n"
        ),
        {
            "line_items": [
                {"No": "1", "Description": "FILTER ELEMENT", "Code": "FE-100", "Qty": "20", "Unit": "EA"}
            ]
        },
    )

    assert fields["line_items"] == [
        {"No": "1", "Description": "FILTER ELEMENT", "Code": "FE-100", "Qty": "20", "Unit": "EA"},
        {"No": "2", "Description": "O-RING KIT", "Code": "ORK-77", "Qty": "3", "Unit": "SET"},
        {"No": "3", "Description": "SOLENOID VALVE", "Code": "SV-9", "Qty": "1", "Unit": "EA"},
    ]
    assert "fixed_rfq_line_items_missing:expected=3,actual=1" not in warnings


def test_rfq_validation_warns_when_no_column_count_still_exceeds_extracted_items() -> None:
    fields, warnings = validated_predefined_document_fields(
        "rfq",
        (
            "INQUIRY / 견적의뢰서\n"
            "No | Description | Code | Qty | Unit\n"
            "1 | FILTER ELEMENT | FE-100 | 20 | EA\n"
            "3 | SOLENOID VALVE | SV-9 | 1 | EA\n"
        ),
        {},
    )

    assert len(fields["line_items"]) == 2
    assert "fixed_rfq_line_items_missing:expected=3,actual=2" in warnings


def test_quote_validation_recovers_total_price_and_multiple_line_items_from_fixed_pool() -> None:
    fields, warnings = validated_predefined_document_fields(
        "quote",
        (
            "QUOTATION\n"
            "To 주식회사 두베코\n"
            "Attn 이병수\n"
            "Your Ref No A-25021919\n"
            "Date 2025-02-21\n"
            "Our Ref No FM250016389\n"
            "In Charge Ryan Kim\n"
            "Tel 051-000-0000\n"
            "Vessel FRONT OTRA / Hyundai Samho Heavy Industries S777 (IMO : 9732541)\n"
            "No  Description                         Qty Unit U/Price     Amount\n"
            "1   FRONT OTRA CONTROL VALVE SEAT       2   EA   KRW 65,000  KRW 130,000\n"
            "2   FRONT OTRA O-RING KIT               1   SET  KRW 25,000  KRW 25,000\n"
            "Total Price KRW 155,000 (Vat Excluded)\n"
            "Terms & Conditions - Delivery time 7 Days\n"
        ),
        {},
    )

    assert fields == {
        "To": "주식회사 두베코",
        "Attn": "이병수",
        "Your Ref No": "A-25021919",
        "Date": "2025-02-21",
        "Our Ref No": "FM250016389",
        "In Charge": "Ryan Kim",
        "Tel": "051-000-0000",
        "Vessel": "FRONT OTRA / Hyundai Samho Heavy Industries S777 (IMO : 9732541)",
        "Total Price": "KRW 155,000 (Vat Excluded)",
        "line_items": [
            {
                "Description": "FRONT OTRA CONTROL VALVE SEAT",
                "Qty": "2",
                "Unit": "EA",
                "U/Price": "KRW 65,000",
                "Amount": "KRW 130,000",
            },
            {
                "Description": "FRONT OTRA O-RING KIT",
                "Qty": "1",
                "Unit": "SET",
                "U/Price": "KRW 25,000",
                "Amount": "KRW 25,000",
            },
        ],
    }
    assert warnings == []


def test_quote_validation_recovers_vertical_pdf_price_and_line_item_tokens() -> None:
    fields, warnings = validated_predefined_document_fields(
        "quote",
        (
            "QUOTATION / 견적서\n"
            "To\n:\n주식회사 두베코\n"
            "Date\n:\n2025-02-21\n"
            "Attn\n:\n이병수 사원님\n"
            "Our Ref No\n:\nFM250016389\n"
            "Your Ref No\n:\nA-25021919\n"
            "In Charge\n:\n정영빈 사원\n"
            "Tel\n:\n070-4107-8527\n"
            "Vessel\n:\nFRONT OTRA / Hyundai Samho Heavy Industries S777 ( IMO : 9732541 )\n"
            "The total price for the proposal is\n"
            "KRW\n"
            "KRW\n"
            "130,000\n"
            "130,000\n"
            "(Vat Excluded)\n"
            "No\n"
            "No\n"
            "Description\n"
            "Description\n"
            "Code\n"
            "Code\n"
            "Qty\n"
            "Qty\n"
            "Unit\n"
            "Unit\n"
            "U/Price\n"
            "U/Price\n"
            "Amount\n"
            "Amount\n"
            "FOR IGS:OXUS\n"
            "FOR IGS:OXUS\n"
            "1\n"
            "FILTER ELEMENT\n"
            "20\n"
            "EA\n"
            "6,500\n"
            "130,000\n"
            "KRW\n"
            "KRW\n"
            "130,000\n"
            "130,000\n"
            "* Terms & Conditions\n"
        ),
        {},
    )

    assert fields["Total Price"] == "KRW 130,000 (Vat Excluded)"
    assert fields["line_items"] == [
        {
            "Description": "FILTER ELEMENT",
            "Qty": "20",
            "Unit": "EA",
            "U/Price": "KRW 6,500",
            "Amount": "KRW 130,000",
        }
    ]
    assert warnings == []


def test_quote_validation_reextracts_line_items_when_no_column_count_is_larger() -> None:
    fields, warnings = validated_predefined_document_fields(
        "quote",
        (
            "QUOTATION\n"
            "To FLUMAX Co., Ltd.\n"
            "Our Ref No FM260000010\n"
            "Total Price KRW 45,000\n"
            "No  Description                         Qty Unit U/Price     Amount\n"
            "1   O-RING                              5   EA   1,000       5,000\n"
            "2   X-RING                              5   EA   3,000       15,000\n"
            "3   FILTER                              5   EA   5,000       25,000\n"
        ),
        {
            "line_items": [
                {
                    "Description": "O-RING",
                    "Qty": "5",
                    "Unit": "EA",
                    "U/Price": "1,000",
                    "Amount": "5,000",
                }
            ]
        },
    )

    assert fields["line_items"] == [
        {
            "Description": "O-RING",
            "Qty": "5",
            "Unit": "EA",
            "U/Price": "1,000",
            "Amount": "5,000",
        },
        {
            "Description": "X-RING",
            "Qty": "5",
            "Unit": "EA",
            "U/Price": "3,000",
            "Amount": "15,000",
        },
        {
            "Description": "FILTER",
            "Qty": "5",
            "Unit": "EA",
            "U/Price": "5,000",
            "Amount": "25,000",
        },
    ]
    assert "fixed_quote_line_items_missing:expected=3,actual=1" not in warnings


def test_quote_validation_strips_korean_won_unit_from_line_item_amounts() -> None:
    fields, warnings = validated_predefined_document_fields(
        "quote",
        (
            "견적서\n"
            "견적번호: QT-2026-0812-03\n"
            "합계금액 5,346,000원\n"
            "품목명 규격 수량 단가 금액\n"
            "Industrial Ethernet Switch 8 Port / DIN Rail 5 EA 420,000원 2,100,000원\n"
        ),
        {
            "line_items": [
                {
                    "Description": "Industrial Ethernet Switch 8 Port / DIN Rail",
                    "Qty": "5",
                    "Unit": "EA",
                    "U/Price": "420,000원",
                    "Amount": "2,100,000원",
                }
            ]
        },
    )

    assert fields["line_items"] == [
        {
            "Description": "Industrial Ethernet Switch 8 Port / DIN Rail",
            "Qty": "5",
            "Unit": "EA",
            "U/Price": "420,000",
            "Amount": "2,100,000",
        }
    ]
    assert "원" not in fields["line_items"][0]["Amount"]
    assert not any(warning.startswith("fixed_quote_line_items_missing") for warning in warnings)


def test_quote_validation_warns_when_no_column_count_still_exceeds_extracted_items() -> None:
    fields, warnings = validated_predefined_document_fields(
        "quote",
        (
            "QUOTATION\n"
            "To FLUMAX Co., Ltd.\n"
            "Our Ref No FM260000011\n"
            "Total Price KRW 30,000\n"
            "No  Description                         Qty Unit U/Price     Amount\n"
            "1   O-RING                              5   EA   1,000       5,000\n"
            "3   FILTER                              5   EA   5,000       25,000\n"
        ),
        {},
    )

    assert len(fields["line_items"]) == 2
    assert "fixed_quote_line_items_missing:expected=3,actual=2" in warnings


def test_quote_validation_recovers_vertical_items_when_equal_price_amount_was_deduped() -> None:
    fields, warnings = validated_predefined_document_fields(
        "quote",
        (
            "QUOTATION / 견적서\n"
            "To\n:\n주식회사 두베코\n"
            "Attn\n:\n최승해 주임님\n"
            "Your Ref No\n:\nA-25021680\n"
            "Date\n:\n2025-02-21\n"
            "Our Ref No\n:\nFM250016062\n"
            "In Charge\n:\n임승락 팀장\n"
            "Tel\n:\n070-4205-7535\n"
            "Vessel\n:\nPHOENIX D / Hyundai Heavy Inds - Ulsan 1032 ( IMO : 9149823 )\n"
            "Total Price\nKRW\n448,000\n(Vat Excluded)\n"
            "No\nNo\nDescription\nDescription\nCode\nCode\nQty\nQty\nUnit\nUnit\nU/Price\nU/Price\nAmount\nAmount\n"
            "FOR INCINERATOR: KANGRIM\nFOR INCINERATOR: KANGRIM\n"
            "1\nTIMER\n3\nEA\n18,000\n54,000\n"
            "2\nAUX. BLOCK\n3\nEA\n8,000\n24,000\n"
            "3\nAUX. RELAY\n2\nEA\n20,000\n40,000\n"
            "4\nTEMPERATE\n1\nEA\n130,000\n"
            "5\nALARM CONTROL RELAY\n1\nEA\n200,000\n"
            "6\nTEMPERATE LIMITER\n1\nEA\n0\n"
            "*REMARK\n#6. 모델명 재확인 바랍니다.\n"
        ),
        {},
    )

    assert fields["line_items"] == [
        {"Description": "TIMER", "Qty": "3", "Unit": "EA", "U/Price": "18,000", "Amount": "54,000"},
        {"Description": "AUX. BLOCK", "Qty": "3", "Unit": "EA", "U/Price": "8,000", "Amount": "24,000"},
        {"Description": "AUX. RELAY", "Qty": "2", "Unit": "EA", "U/Price": "20,000", "Amount": "40,000"},
        {"Description": "TEMPERATE", "Qty": "1", "Unit": "EA", "U/Price": "130,000", "Amount": "130,000"},
        {
            "Description": "ALARM CONTROL RELAY",
            "Qty": "1",
            "Unit": "EA",
            "U/Price": "200,000",
            "Amount": "200,000",
        },
        {"Description": "TEMPERATE LIMITER", "Qty": "1", "Unit": "EA", "U/Price": "0", "Amount": "0"},
    ]
    assert warnings == []


def test_xlsx_text_rules_assign_structured_form_fields(tmp_path: Path) -> None:
    path = tmp_path / "quotation.xlsx"
    SyntheticFixtureGenerator._xlsx(
        path,
        "QUOTATION\nTo: FLUMAX Co., Ltd.\nVessel: MV EXCEL\nOur Ref No: FM260000001",
    )

    result = AttachmentParserDispatcher(tmp_path).analyze(
        attachment(path, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    )

    assert result.status == AttachmentAnalysisStatus.COMPLETED
    assert result.document_type == "quote"
    assert result.fields["To"] == "FLUMAX Co., Ltd."
    assert result.fields["Vessel"] == "MV EXCEL"
    assert result.fields["Our Ref No"] == "FM260000001"


def test_predefined_form_filter_keeps_only_exact_fixed_fields_and_quote_tables() -> None:
    fields = filter_predefined_document_fields(
        "quote",
        {
            "Contact Person": "이병수 사원님",
            "Fluemax Ref No": "FM250016389",
            "Jinhan Line Ref No": "A-25021919",
            "Packing": "Unpacking",
            "Freeform LLM Field": "must not survive",
            "Attn": "정확한 필드명",
            "Our Ref No": "FM250016390",
            "line_items": [
                {
                    "Description": "Pump Seal",
                    "Qty": "2",
                    "Unit": "EA",
                    "quantity": "not fixed",
                    "confidence": 0.91,
                }
            ],
        },
    )

    assert fields == {
        "Attn": "정확한 필드명",
        "Our Ref No": "FM250016390",
        "line_items": [{"Description": "Pump Seal", "Qty": "2", "Unit": "EA"}],
    }


def test_predefined_form_filter_drops_non_quote_tables() -> None:
    fields = filter_predefined_document_fields(
        "payment_request",
        {
            "공급자 - 상호": "플루맥스",
            "line_items": [{"Description": "Seal", "Qty": "3"}],
        },
    )

    assert fields == {"공급자 - 상호": "플루맥스"}


def test_document_understanding_schema_rejects_non_fixed_field_names() -> None:
    with pytest.raises(ValidationError):
        BusinessDocumentUnderstanding.model_validate(
            {
                "document_type": "quote",
                "confidence": 0.9,
                "summary": "견적서",
                "fields": {
                    "Contact Person": "이병수 사원님",
                    "Fluemax Ref No": "FM250016389",
                    "Jinhan Line Ref No": "A-25021919",
                },
            }
        )


def test_unsupported_attachment_is_explicit(tmp_path: Path) -> None:
    path = tmp_path / "archive.bin"
    path.write_bytes(b"binary")
    result = AttachmentParserDispatcher(tmp_path).analyze(attachment(path, "application/octet-stream"))
    assert result.status == AttachmentAnalysisStatus.UNSUPPORTED

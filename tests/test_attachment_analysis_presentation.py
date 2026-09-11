from app.presentation.attachment_analysis import (
    business_analysis_rows,
    canonical_document_type,
    document_type_label,
    normalize_business_fields,
)
from app.services.postgres_mail_service import PostgresMailboxService


def test_attachment_rows_show_business_fields_not_runtime_metadata():
    rows = business_analysis_rows(
        document_type="quote",
        fields={
            "Vessel": "MV TEST",
            "Our Ref No": "Q-100",
            "checksum": "secret-runtime-detail",
            "pages": 4,
            "line_items": [{"Description": "Pump", "Qty": 2, "U/Price": "50", "Amount": "100"}],
        },
        extracted_text="",
        status="completed",
    )

    assert rows == [
        {"label": "Our Ref No", "value": "Q-100"},
        {"label": "Vessel", "value": "MV TEST"},
        {
            "label": "품목 1",
            "value": "Pump 2 50원 100",
            "kind": "line_item",
            "columns": [
                {"label": "Description", "value": "Pump"},
                {"label": "Qty", "value": "2"},
                {"label": "Unit", "value": ""},
                {"label": "U/Price", "value": "50원"},
                {"label": "Amount", "value": "100"},
            ],
        },
    ]


def test_attachment_rows_use_content_preview_only_when_business_fields_are_absent():
    rows = business_analysis_rows(
        document_type="",
        fields={"checksum": "hidden", "pages": 1},
        extracted_text="  Delivery   requested\nfor PO-1 ",
        status="completed",
    )

    assert rows == [{"label": "내용", "value": "Delivery requested for PO-1"}]


def test_attachment_rows_accept_coramail_ai_field_list_contract():
    rows = business_analysis_rows(
        document_type="payment_request",
        fields={
            "field_name_from_schema": [
                {"field_name": "공급자 - 상호", "value": "플루맥스"},
                {"field_name": "공급자 - 계좌번호", "value": "000-000"},
            ],
            "line_items": [{"Description": "Seal", "Qty": "3", "Unit": "EA"}],
        },
        extracted_text="",
        status="completed",
    )

    assert rows == [
        {"label": "공급자 - 상호", "value": "플루맥스"},
        {"label": "공급자 - 계좌번호", "value": "000-000"},
    ]


def test_attachment_rows_keep_only_exact_fixed_fields_from_grouped_name_value_fields():
    rows = business_analysis_rows(
        document_type="quote",
        fields={
            "dates": {"name": "Date", "value": "2025-02-21"},
            "totals": [{"name": "Total Price", "value": "KRW 130,000 (Vat Excluded)"}],
            "customer": [
                {"name": "Company Name", "value": "주식회사 두베코"},
                {"name": "Contact Person", "value": "이병수 사원님"},
            ],
            "delivery_terms": [
                {"name": "Delivery Time", "value": "5 Days"},
                {"name": "Packing", "value": "Unpacking"},
            ],
            "vessel/project": [
                {
                    "name": "Vessel Name",
                    "value": "FRONT OTRA / Hyundai Samho Heavy Industries S777 (IMO : 9732541)",
                },
                {"name": "Project/Order Number", "value": ""},
            ],
            "reference_numbers": [
                {"name": "Our Ref No", "value": "FM250016389"},
                {"name": "Your Ref No", "value": "A-25021919"},
            ],
        },
        extracted_text="",
        status="completed",
    )

    assert rows == [
        {"label": "Your Ref No", "value": "A-25021919"},
        {"label": "Date", "value": "2025-02-21"},
        {"label": "Our Ref No", "value": "FM250016389"},
        {"label": "Total Price", "value": "130,000원 (Vat Excluded)"},
    ]


def test_attachment_rows_recover_fixed_columns_from_text_without_model_key_mapping():
    rows = business_analysis_rows(
        document_type="quote",
        fields={
            "dates": ["2025-02-21"],
            "totals": {"total_price": 1359000},
            "customer": "Alphamarine",
            "supplier": "FLUemax",
            "line_items": [
                {
                    "code": "WIPER CONTROL",
                    "amount": 540000,
                    "quantity": 1,
                    "unit_price": 540000,
                    "description": "FOR WINDOW WIPER:JUNG-A",
                }
            ],
            "delivery_terms": {
                "packing": "Unpacking",
                "delivery_time": "7 Days",
            },
            "vessel/project": "SEAWAYS TRITON / Shanghai Waigaoqiao Shipbuilding Co Ltd, H1385",
            "reference_numbers": ["FM250016318", "AP250220022"],
            "payment_details": {
                "payment_method": "Cash",
                "payment_percentage": 100,
            },
        },
        extracted_text=(
            "QUOTATION / 견적서\n"
            "To\n:\n알파마린\n"
            "Date\n:\n2025-02-21\n"
            "Our Ref No\n:\nFM250016318\n"
            "Your Ref No\n:\nAP250220022\n"
            "Vessel\n:\nSEAWAYS TRITON / Shanghai Waigaoqiao Shipbuilding Co Ltd H1385\n"
            "The total price for the proposal is KRW 1,359,000\n"
        ),
        status="completed",
    )

    assert rows == [
        {"label": "To", "value": "알파마린"},
        {"label": "Your Ref No", "value": "AP250220022"},
        {"label": "Date", "value": "2025-02-21"},
        {"label": "Our Ref No", "value": "FM250016318"},
        {"label": "Vessel", "value": "SEAWAYS TRITON / Shanghai Waigaoqiao Shipbuilding Co Ltd H1385"},
        {"label": "Total Price", "value": "1,359,000원"},
    ]
    assert all(row["label"] != "품목 1" for row in rows)


def test_attachment_rows_show_all_quote_line_items_without_five_item_limit():
    rows = business_analysis_rows(
        document_type="quote",
        fields={
            "line_items": [
                {"Description": f"Part {index}", "Qty": "1", "Unit": "EA", "U/Price": "1,000", "Amount": "1,000"}
                for index in range(1, 7)
            ],
        },
        extracted_text="",
        status="completed",
    )

    item_rows = [row for row in rows if row["label"].startswith("품목 ")]
    assert [row["label"] for row in item_rows] == ["품목 1", "품목 2", "품목 3", "품목 4", "품목 5", "품목 6"]
    assert item_rows[-1]["columns"] == [
        {"label": "Description", "value": "Part 6"},
        {"label": "Qty", "value": "1"},
        {"label": "Unit", "value": "EA"},
        {"label": "U/Price", "value": "1,000원"},
        {"label": "Amount", "value": "1,000"},
    ]


def test_attachment_rows_show_rfq_line_items_with_no_and_code():
    rows = business_analysis_rows(
        document_type="rfq",
        fields={
            "To": "FLUMAX Co., Ltd.",
            "Our Ref No": "RFQ-2026-0831-01",
            "line_items": [
                {"No": "1", "Description": "FILTER ELEMENT", "Code": "FE-100", "Qty": "20", "Unit": "EA"}
            ],
        },
        extracted_text="",
        status="completed",
    )

    assert rows == [
        {"label": "To", "value": "FLUMAX Co., Ltd."},
        {"label": "Our Ref No", "value": "RFQ-2026-0831-01"},
        {
            "label": "품목 1",
            "value": "1 FILTER ELEMENT FE-100 20 EA",
            "kind": "line_item",
            "columns": [
                {"label": "No", "value": "1"},
                {"label": "Description", "value": "FILTER ELEMENT"},
                {"label": "Code", "value": "FE-100"},
                {"label": "Qty", "value": "20"},
                {"label": "Unit", "value": "EA"},
            ],
        },
    ]


def test_attachment_rows_replace_incomplete_stored_line_items_from_no_count_validation():
    rows = business_analysis_rows(
        document_type="quote",
        fields={
            "line_items": [
                {"Description": "TIMER", "Qty": "3", "Unit": "EA", "U/Price": "18,000", "Amount": "54,000"}
            ]
        },
        extracted_text=(
            "QUOTATION\n"
            "No\nNo\nDescription\nDescription\nCode\nCode\nQty\nQty\nUnit\nUnit\nU/Price\nU/Price\nAmount\nAmount\n"
            "1\nTIMER\n3\nEA\n18,000\n54,000\n"
            "2\nAUX. BLOCK\n3\nEA\n8,000\n24,000\n"
            "3\nTEMPERATE\n1\nEA\n130,000\n"
            "*REMARK\n"
        ),
        status="completed",
    )

    item_rows = [row for row in rows if row["label"].startswith("품목 ")]
    assert [row["label"] for row in item_rows] == ["품목 1", "품목 2", "품목 3"]
    assert item_rows[-1]["columns"] == [
        {"label": "Description", "value": "TEMPERATE"},
        {"label": "Qty", "value": "1"},
        {"label": "Unit", "value": "EA"},
        {"label": "U/Price", "value": "130,000원"},
        {"label": "Amount", "value": "130,000"},
    ]


def test_attachment_rows_extract_synthetic_korean_quote_fields_and_items():
    rows = business_analysis_rows(
        document_type="quote",
        fields={},
        extracted_text=(
            "견적서\n"
            "견적번호: QT-2026-0812-03\n"
            "견적일자: 2026-08-12\n"
            "공급사: 미래산업기술\n"
            "수신 회사: 다원\n"
            "견적 유효기간: 2026-08-26\n"
            "예상 납기: 발주 후 14일 이내\n"
            "품목명 규격 수량 단가 금액\n"
            "Industrial Ethernet Switch 8 Port / DIN Rail 5 EA 420,000원 2,100,000원\n"
            "DC Power Supply Module 24V / 10A 8 EA 270,000원 2,160,000원\n"
            "Terminal Block 2.5㎟ / Feed-through 50 EA 12,000원 600,000원\n"
            "공급가액 4,860,000원\n"
            "부가세 486,000원\n"
            "합계금액 5,346,000원\n"
        ),
        status="partial_success",
    )

    assert {"label": "To", "value": "다원"} in rows
    assert {"label": "Date", "value": "2026-08-12"} in rows
    assert {"label": "Our Ref No", "value": "QT-2026-0812-03"} in rows
    assert {"label": "Total Price", "value": "5,346,000원"} in rows
    item_rows = [row for row in rows if row["label"].startswith("품목 ")]
    assert [row["label"] for row in item_rows] == ["품목 1", "품목 2", "품목 3"]
    assert item_rows[0]["columns"] == [
        {"label": "Description", "value": "Industrial Ethernet Switch 8 Port / DIN Rail"},
        {"label": "Qty", "value": "5"},
        {"label": "Unit", "value": "EA"},
        {"label": "U/Price", "value": "420,000원"},
        {"label": "Amount", "value": "2,100,000"},
    ]


def test_attachment_failure_does_not_replace_extraction_table_with_status():
    rows = business_analysis_rows(
        document_type="quote",
        fields={},
        extracted_text="",
        status="partial_success",
        error_message="gateway unavailable",
    )

    assert rows == []


def test_attachment_document_labels_cover_mail_decision_types():
    assert document_type_label("purchase_order") == "발주서"
    assert document_type_label("quotation") == "견적서"
    assert document_type_label("견적의뢰서") == "견적의뢰서"
    assert document_type_label("unknown", "기존 라벨") == "기존 라벨"


def test_attachment_rows_drop_non_schema_form_document_aliases():
    assert canonical_document_type("quotation") == "quote"
    rows = business_analysis_rows(
        document_type="견적서",
        fields={
            "To": "FLUMAX Co., Ltd.",
            "Reference No.": "FM250016329",
            "Vessel": "GH MADISON",
            "checksum": "hidden",
        },
        extracted_text="",
        status="completed",
    )

    assert rows == [
        {"label": "To", "value": "FLUMAX Co., Ltd."},
        {"label": "Vessel", "value": "GH MADISON"},
    ]


def test_attachment_rows_drop_non_schema_quote_fields_instead_of_mapping_them():
    rows = business_analysis_rows(
        document_type="quote",
        fields={
            "Contact Person": "이병수 사원님",
            "Fluemax Ref No": "FM250016389",
            "Jinhan Line Ref No": "A-25021919",
            "Packing": "Unpacking",
            "Freeform LLM Field": "must not display",
        },
        extracted_text="",
        status="completed",
    )

    assert rows == []


def test_attachment_rows_recover_predefined_fields_from_stored_text_when_fields_are_empty():
    rows = business_analysis_rows(
        document_type="quote",
        fields={},
        extracted_text=(
            "QUOTATION\n"
            "To FLUMAX Co., Ltd.\n"
            "Vessel GH MADISON\n"
            "Our Ref No FM250016329\n"
            "Total Price KRW 518,000"
        ),
        analysis_summary="견적서 유형으로 추정됩니다.",
        status="partial_success",
    )

    assert rows == [
        {"label": "To", "value": "FLUMAX Co., Ltd."},
        {"label": "Our Ref No", "value": "FM250016329"},
        {"label": "Vessel", "value": "GH MADISON"},
        {"label": "Total Price", "value": "518,000원"},
    ]


def test_attachment_rows_do_not_show_type_guess_as_structured_details():
    rows = business_analysis_rows(
        document_type="quote",
        fields={},
        extracted_text="",
        analysis_summary="견적서 유형으로 추정됩니다.",
        status="partial_success",
    )

    assert rows == []


def test_attachment_rows_do_not_show_non_predefined_type_guess_as_details():
    rows = business_analysis_rows(
        document_type="field_photo",
        fields={},
        extracted_text="",
        analysis_summary="현장 사진 유형으로 추정됩니다.",
        status="partial_success",
    )

    assert rows == []


def test_attachment_rows_do_not_use_content_fallback_for_predefined_document_types():
    rows = business_analysis_rows(
        document_type="quote",
        fields={},
        extracted_text="QUOTATION free text without recoverable business labels",
        analysis_summary="",
        status="partial_success",
    )

    assert rows == []


def test_attachment_field_normalization_keeps_direct_values():
    assert normalize_business_fields(
        {
            "field_name_from_schema": [{"field_name": "Vessel", "value": "MV TEST"}],
            "Our Ref No": "Q-10",
        }
    ) == {"Vessel": "MV TEST", "Our Ref No": "Q-10"}


def test_postgres_attachment_payload_maps_legacy_analysis_to_details(tmp_path):
    attachment_path = tmp_path / "request.pdf"
    attachment_path.write_bytes(b"fixture")

    class Repository:
        @staticmethod
        def attachment_path(_attachment):
            return attachment_path

    service = object.__new__(PostgresMailboxService)
    service.repository = Repository()
    payload = service._attachment_payload(
        {
            "id": "attachment-1",
            "filename": "request.pdf",
            "content_type": "application/pdf",
            "file_size": 7,
            "processing_status": "completed",
            "analysis_result_json": {
                "document_category": "rfq",
                "document_category_label": "견적의뢰서",
                "fields": {},
                "extracted_fields": {
                    "Vessel": "MV LEGACY",
                    "Our Ref No": "RFQ-1",
                },
            },
        },
        "email-1",
        0,
    )

    assert payload["document_category_label"] == "견적의뢰서"
    assert payload["analysis_rows"] == [
        {"label": "Vessel", "value": "MV LEGACY"},
        {"label": "Our Ref No", "value": "RFQ-1"},
    ]


def test_postgres_attachment_payload_does_not_treat_download_as_analysis(tmp_path):
    attachment_path = tmp_path / "unknown.pdf"
    attachment_path.write_bytes(b"fixture")

    class Repository:
        @staticmethod
        def attachment_path(_attachment):
            return attachment_path

    service = object.__new__(PostgresMailboxService)
    service.repository = Repository()
    payload = service._attachment_payload(
        {
            "id": "attachment-1",
            "filename": "unknown.pdf",
            "content_type": "application/pdf",
            "file_size": 7,
            "processing_status": "downloaded",
            "analysis_result_json": {},
        },
        "email-1",
        0,
    )

    assert payload["parse_status"] == "unknown"
    assert payload["document_category_label"] == ""
    assert payload["analysis_rows"] == []

from app.presentation.attachment_analysis import field_display_label


def test_quote_attachment_field_labels_use_requested_korean_copy():
    assert field_display_label("To", "quote") == "거래처"
    assert field_display_label("Date", "quote") == "날짜"
    assert field_display_label("Our Ref No", "quote") == "거래처측 업무번호"
    assert field_display_label("Total Price", "quote") == "총액"
    assert field_display_label("Your Ref No", "quote") == "업무번호"
    assert field_display_label("In Charge", "quote") == "담당자명"
    assert field_display_label("Tel", "quote") == "연락처"
    assert field_display_label("Vessel", "quote") == "선박 (IMO 번호)"


def test_quote_attachment_field_labels_do_not_apply_to_other_document_types():
    assert field_display_label("To", "payment_request") == "To"
    assert field_display_label("Date", "transaction_statement") == "Date"
    assert field_display_label("Vessel", "rfq") == "Vessel"

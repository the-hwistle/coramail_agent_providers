from app.repositories.postgres_attachment_analysis_repository import (
    has_business_fields,
    preserve_current_business_fields,
)


def test_preserve_current_business_fields_prevents_summary_only_reanalysis_downgrade():
    current = {
        "document_type": "quote",
        "analysis_summary": "견적서 필드 추출 완료",
        "fields": {
            "To": "FLUMAX Co., Ltd.",
            "Vessel": "GH MADISON",
            "Our Ref No": "FM250016329",
        },
    }
    new = {
        "document_type": "quote",
        "analysis_summary": "견적서 유형으로 추정됩니다.",
        "fields": {},
        "warnings": ["document_understanding_gateway_failed"],
    }

    preserved = preserve_current_business_fields(new, current)

    assert preserved["fields"] == current["fields"]
    assert "preserved_previous_business_fields" in preserved["warnings"]
    assert has_business_fields(preserved)


def test_preserve_current_business_fields_does_not_mix_different_document_types():
    current = {
        "document_type": "rfq",
        "fields": {"Vessel": "MV RFQ"},
    }
    new = {
        "document_type": "quote",
        "fields": {},
        "analysis_summary": "견적서 유형으로 추정됩니다.",
    }

    assert preserve_current_business_fields(new, current) == new


def test_preserve_current_business_fields_keeps_new_business_fields_when_present():
    current = {
        "document_type": "quote",
        "fields": {"Our Ref No": "OLD"},
    }
    new = {
        "document_type": "quote",
        "fields": {"Our Ref No": "NEW"},
    }

    assert preserve_current_business_fields(new, current) == new


def test_preserve_current_business_fields_drops_legacy_non_schema_fields():
    current = {
        "document_type": "quote",
        "fields": {
            "Contact Person": "이병수 사원님",
            "Fluemax Ref No": "FM250016389",
            "Jinhan Line Ref No": "A-25021919",
            "Packing": "Unpacking",
            "Attn": "정확한 필드명",
            "Our Ref No": "FM250016390",
        },
    }
    new = {
        "document_type": "quote",
        "fields": {},
        "warnings": [],
    }

    preserved = preserve_current_business_fields(new, current)

    assert preserved["fields"] == {
        "Attn": "정확한 필드명",
        "Our Ref No": "FM250016390",
    }

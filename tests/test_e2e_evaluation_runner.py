from __future__ import annotations

from pathlib import Path
from uuid import UUID

from app.evaluation.fixtures import SyntheticFixtureGenerator
from app.evaluation.runner import EndToEndEvaluationRunner
from app.evaluation.synthetic_dataset import SyntheticDatasetConfig, SyntheticEvaluationDatasetGenerator


def test_fixture_generator_materializes_all_supported_formats(tmp_path: Path) -> None:
    dataset = SyntheticEvaluationDatasetGenerator(
        SyntheticDatasetConfig(email_count=10, attachment_count=5, ground_truth_count=5)
    ).generate()

    result = SyntheticFixtureGenerator(tmp_path).generate(dataset)

    assert result["fixtures"] == 5
    assert {Path(row["storage_uri"]).suffix for row in dataset["attachments"]} == {
        ".pdf", ".xlsx", ".docx", ".png", ".txt"
    }
    assert all(Path(row["storage_uri"]).is_file() for row in dataset["attachments"])
    assert all(row["file_size"] > 0 for row in dataset["attachments"])


def test_runner_prediction_uses_metric_contract() -> None:
    email_id = UUID("11111111-1111-1111-1111-111111111111")
    state = {
        "run_id": "22222222-2222-2222-2222-222222222222",
        "status": "auto_assigned",
        "context": {
            "decision_output": {
                "classification": {
                    "business_area": "order",
                    "primary_type": "purchase_order",
                    "confidence": 0.97,
                },
                "unsupported_claims": [],
            },
            "routing_decision": {
                "decision": "auto_assign",
                "selected_user_id": "33333333-3333-3333-3333-333333333333",
                "candidates": [
                    {"user_id": "33333333-3333-3333-3333-333333333333"},
                    {"user_id": "44444444-4444-4444-4444-444444444444"},
                ],
            },
        },
    }

    prediction = EndToEndEvaluationRunner._prediction(email_id, state)

    assert prediction["business_type"] == "purchase_order"
    assert prediction["selected_user_id"] == "33333333-3333-3333-3333-333333333333"
    assert prediction["candidate_user_ids"][:2] == [
        "33333333-3333-3333-3333-333333333333",
        "44444444-4444-4444-4444-444444444444",
    ]
    assert prediction["auto_assigned"] is True
    assert prediction["unsupported_claim_count"] == 0


def test_runner_does_not_read_removed_flat_business_type_field() -> None:
    email_id = UUID("11111111-1111-1111-1111-111111111111")
    state = {
        "status": "review_required",
        "context": {
            "decision_output": {
                "primary_type": "claim",
                "classification": {
                    "business_area": "service",
                    "primary_type": "repair_request",
                    "confidence": 0.91,
                },
            },
            "routing_decision": {"candidates": []},
        },
    }

    prediction = EndToEndEvaluationRunner._prediction(email_id, state)

    assert prediction["business_type"] == "repair_request"

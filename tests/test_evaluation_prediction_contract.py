from __future__ import annotations

from uuid import UUID

from app.evaluation.metrics import evaluate_predictions
from app.evaluation.runner import EndToEndEvaluationRunner


EMAIL_ID = UUID("00000000-0000-0000-0000-000000000001")
ASSIGNEE_ID = "00000000-0000-0000-0000-000000000002"


def _completed_state() -> dict:
    return {
        "run_id": "run-1",
        "status": "completed",
        "workflow_version": "test-v1",
        "facts": {"customer": "synthetic"},
        "context": {
            "mail": {"subject": "Synthetic PO", "body_text": "Please process this purchase order."},
            "decision_output": {
                "classification": {"primary_type": "purchase_order"},
                "urgency": {"level": "normal"},
                "unsupported_claims": [],
            },
            "routing_decision": {
                "decision": "auto_assign",
                "selected_user_id": ASSIGNEE_ID,
                "candidates": [{"user_id": ASSIGNEE_ID, "score": 0.95}],
            },
            "retrieval_context": {"sufficient": True},
            "review_reason": None,
        },
    }


def test_runner_prediction_contains_fields_consumed_by_metrics() -> None:
    prediction = EndToEndEvaluationRunner._prediction(EMAIL_ID, _completed_state())

    required_fields = {
        "email_message_id",
        "status",
        "business_type",
        "candidate_user_ids",
        "selected_user_id",
        "auto_assigned",
        "unsupported_claim_count",
        "review_reason",
    }
    assert required_fields <= prediction.keys()
    assert prediction["candidate_user_ids"] == [ASSIGNEE_ID]
    assert prediction["selected_user_id"] == ASSIGNEE_ID
    assert prediction["auto_assigned"] is True


def test_runner_prediction_is_accepted_by_primary_metrics_contract() -> None:
    prediction = EndToEndEvaluationRunner._prediction(EMAIL_ID, _completed_state())
    ground_truth = [
        {
            "email_message_id": str(EMAIL_ID),
            "business_type": "purchase_order",
            "expected_assignee_user_id": ASSIGNEE_ID,
            "urgent": False,
        }
    ]

    result = evaluate_predictions(ground_truth, [prediction])

    assert result["metrics"]["coverage"] == 1.0
    assert result["metrics"]["classification_macro_f1"] == 1.0
    assert result["metrics"]["routing_top1_accuracy"] == 1.0
    assert result["metrics"]["routing_top3_recall"] == 1.0
    assert result["metrics"]["auto_assignment_precision"] == 1.0

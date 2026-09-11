import csv
import json

from app.evaluation.leakage import validate_dataset_leakage
from app.evaluation.metrics import evaluate_predictions, macro_f1, score_predictions, write_evaluation_outputs
from app.evaluation.synthetic_dataset import SyntheticDatasetConfig, SyntheticEvaluationDatasetGenerator
from app.routing.policy import RoutingPolicy
from app.schemas.mail_decision import MailClassification, MailFacts
from app.schemas.retrieval import RetrievalContext


def test_dataset_is_reproducible_and_has_required_counts():
    first = SyntheticEvaluationDatasetGenerator().generate()
    second = SyntheticEvaluationDatasetGenerator().generate()
    assert first == second
    assert len(first["assignees"]) == 8
    assert len(first["customers"]) == 12
    assert len(first["product_groups"]) == 6
    assert len(first["projects"]) == 15
    assert len(first["emails"]) == 200
    assert len(first["attachments"]) == 120
    assert len(first["ground_truth"]) == 100
    assert len(first["qdrant_cases"]) == 100
    assert first["metadata"]["synthetic"] is True


def test_perfect_predictions_pass_all_thresholds():
    dataset = SyntheticEvaluationDatasetGenerator().generate()
    predictions = []
    for truth in dataset["ground_truth"]:
        predictions.append(
            {
                "email_message_id": truth["email_message_id"],
                "business_type": truth["business_type"],
                "selected_user_id": truth["expected_assignee_user_id"],
                "candidate_user_ids": [truth["expected_assignee_user_id"]],
                "auto_assigned": True,
                "unsupported_claim_count": 0,
            }
        )
    report = evaluate_predictions(dataset["ground_truth"], predictions)
    assert report["passed"] is True
    assert report["metrics"]["classification_macro_f1"] == 1.0
    assert report["metrics"]["routing_top1_accuracy"] == 1.0
    assert report["metrics"]["auto_assignment_precision"] == 1.0


def test_attention_axis_metrics_are_reported_when_ground_truth_exists():
    ground_truth = [
        {
            "email_message_id": "email-1",
            "business_type": "urgent_failure",
            "expected_assignee_user_id": "user-1",
            "expected_urgency": "high",
            "expected_importance": "high",
            "expected_attention_quadrant": "urgent_important",
        },
        {
            "email_message_id": "email-2",
            "business_type": "quotation_request",
            "expected_assignee_user_id": "user-2",
            "expected_urgency": "high",
            "expected_importance": "normal",
            "expected_attention_quadrant": "urgent",
        },
    ]
    dataset = {
        "emails": [{"id": "email-1", "subject": "a", "body_text": "a"}, {"id": "email-2", "subject": "b", "body_text": "b"}],
        "attachments": [],
        "ground_truth": ground_truth,
        "qdrant_cases": [],
    }
    predictions = [
        {
            "email_message_id": "email-1",
            "status": "auto_assigned",
            "business_type": "urgent_failure",
            "urgency": "high",
            "importance": "high",
            "attention_quadrant": "urgent_important",
            "selected_user_id": "user-1",
            "candidate_user_ids": ["user-1"],
            "auto_assigned": True,
        },
        {
            "email_message_id": "email-2",
            "status": "auto_assigned",
            "business_type": "quotation_request",
            "decision_output": {
                "urgency": {"level": "high"},
                "importance": {"level": "normal"},
                "attention_quadrant": "urgent",
            },
            "selected_user_id": "user-2",
            "candidate_user_ids": ["user-2"],
            "auto_assigned": True,
        },
    ]

    report, traces = score_predictions(dataset, predictions, strict=True)
    values = report.metrics.values

    assert values["urgency_accuracy"].value == 1.0
    assert values["importance_accuracy"].value == 1.0
    assert values["attention_quadrant_accuracy"].value == 1.0
    assert traces[0].ground_truth["expected_attention_quadrant"] == "urgent_important"
    assert traces[1].evaluation["attention_quadrant_correct"] is True


def test_bad_predictions_fail_and_report_missing_ids():
    dataset = SyntheticEvaluationDatasetGenerator().generate()
    truth = dataset["ground_truth"]
    predictions = [
        {
            "email_message_id": truth[0]["email_message_id"],
            "business_type": "general_inquiry",
            "selected_user_id": "00000000-0000-0000-0000-000000000000",
            "candidate_user_ids": [],
            "auto_assigned": True,
            "unsupported_claim_count": 2,
        }
    ]
    report = evaluate_predictions(truth, predictions)
    assert report["passed"] is False
    assert len(report["missing_prediction_ids"]) == 99
    assert report["metrics"]["coverage"] == 0.01


def test_macro_f1_handles_multiple_labels():
    assert macro_f1(["a", "a", "b", "b"], ["a", "b", "b", "b"]) < 1.0


def test_detailed_metric_fixture_counts_denominators_and_failures(tmp_path):
    truth = [
        {"email_message_id": f"email-{index}", "business_type": "type_a" if index < 4 else "type_b", "expected_assignee_user_id": f"user-{index}", "customer_name": "Customer", "product_group": "pump", "project_code": "PRJ", "urgent": False}
        for index in range(1, 8)
    ]
    dataset = {
        "emails": [{"id": row["email_message_id"], "subject": f"Subject {index}", "body_text": "body"} for index, row in enumerate(truth, start=1)],
        "attachments": [],
        "ground_truth": truth,
        "qdrant_cases": [],
    }
    predictions = [
        {"email_message_id": "email-1", "status": "auto_assigned", "business_type": "type_a", "selected_user_id": "user-1", "candidate_user_ids": ["user-1"], "auto_assigned": True},
        {"email_message_id": "email-2", "status": "completed", "business_type": "type_a", "selected_user_id": "other", "candidate_user_ids": ["other"], "auto_assigned": False},
        {"email_message_id": "email-3", "status": "review_required", "business_type": "type_a", "selected_user_id": None, "candidate_user_ids": ["other", "user-3"], "auto_assigned": False, "review_reason": "routing_policy_review_required"},
        {"email_message_id": "email-4", "status": "review_required", "business_type": None, "selected_user_id": None, "candidate_user_ids": [], "auto_assigned": False, "review_reason": "retrieval_context_insufficient"},
        {"email_message_id": "email-5", "status": "failed", "business_type": None, "selected_user_id": None, "candidate_user_ids": [], "auto_assigned": False, "error": "RuntimeError: boom"},
        {"email_message_id": "email-6", "status": "auto_assigned", "business_type": "type_b", "selected_user_id": "wrong", "candidate_user_ids": ["wrong", "user-6"], "auto_assigned": True},
        {"email_message_id": "email-6", "status": "auto_assigned", "business_type": "type_b", "selected_user_id": "wrong", "candidate_user_ids": ["wrong", "user-6"], "auto_assigned": True},
        {"email_message_id": "email-unknown", "status": "completed", "business_type": "type_b", "selected_user_id": "user-x", "candidate_user_ids": ["user-x"], "auto_assigned": False},
    ]

    report, traces = score_predictions(dataset, predictions, strict=True)
    values = report.metrics.values

    assert values["business_type_accuracy_overall"].denominator == 7
    assert values["business_type_accuracy_overall"].numerator == 4
    assert values["top1_assignee_accuracy_overall"].denominator == 7
    assert values["candidate_mrr"].numerator == 2.0
    assert values["candidate_mrr"].denominator == 7
    assert values["auto_assignment_rate"].numerator == 2
    assert values["auto_assignment_accuracy"].numerator == 1
    assert report.metrics.review_reason_counts["retrieval_context_insufficient"] == 1
    assert report.metrics.primary_failure_stage_counts["runtime_failed"] == 2
    assert report.failure_summary.missing_prediction_ids == ["email-7"]
    assert report.failure_summary.duplicate_prediction_ids == ["email-6"]
    assert report.failure_summary.unexpected_prediction_ids == ["email-unknown"]
    assert traces[3].sufficiency["unresolved_context"]

    report_json = tmp_path / "evaluation_report.json"
    cases_csv = tmp_path / "evaluation_cases.csv"
    trace_jsonl = tmp_path / "evaluation_trace.jsonl"
    write_evaluation_outputs(report, traces, report_json=report_json, cases_csv=cases_csv, trace_jsonl=trace_jsonl)

    assert json.loads(report_json.read_text(encoding="utf-8"))["metrics"]["values"]["failed_count"]["denominator"] == 7
    rows = list(csv.DictReader(cases_csv.open(encoding="utf-8")))
    assert rows[0]["email_message_id"] == "email-1"
    assert len(trace_jsonl.read_text(encoding="utf-8").splitlines()) == 7


def test_trace_integrity_fills_retrieval_excluded_reason_and_review_unresolved_context():
    truth = {
        "email_message_id": "email-1",
        "business_type": "repair_request",
        "expected_assignee_user_id": "user-1",
        "customer_name": "Customer",
        "product_group": "pump",
        "project_code": "PRJ",
    }
    dataset = {"emails": [{"id": "email-1", "subject": "<b>x</b>", "body_text": "body"}], "attachments": [], "ground_truth": [truth], "qdrant_cases": []}
    predictions = [
        {
            "email_message_id": "email-1",
            "status": "review_required",
            "business_type": None,
            "candidate_user_ids": [],
            "selected_user_id": None,
            "review_reason": "retrieval_context_insufficient",
            "retrieval_context": {
                "cycles": [
                    {
                        "cycle_number": 1,
                        "plan": {"queries": [{"retriever_type": "similar_case", "query_text": "q", "filters": {}, "limit": 5}]},
                        "hits": [{"retriever_type": "similar_case", "source_type": "qdrant", "source_id": "case-1", "retrieval_score": 0.2, "included_in_prompt": False}],
                        "sufficient": False,
                    }
                ],
                "sufficient": False,
            },
        }
    ]

    report, traces = score_predictions(dataset, predictions, strict=True)

    hit = traces[0].retrieval["cycles"][0]["hits"][0]
    assert hit["excluded_reason"] == "unknown"
    assert traces[0].sufficiency["unresolved_context"]
    assert report.failure_summary.trace_integrity_errors == []


def test_leakage_validator_detects_id_body_near_duplicate_answer_and_duplicates():
    dataset = {
        "metadata": {"dataset_version": "test"},
        "emails": [
            {"id": "target-1", "subject": "Repair request", "body_text": "Customer: A\nProject: P\nProduct group: pump"},
            {"id": "target-1", "subject": "Repair request", "body_text": "Customer: A\nProject: P\nProduct group: pump"},
        ],
        "ground_truth": [
            {"email_message_id": "target-1", "business_type": "repair_request", "expected_assignee_user_id": "user-1"},
            {"email_message_id": "target-1", "business_type": "repair_request", "expected_assignee_user_id": "user-1"},
        ],
        "qdrant_cases": [
            {
                "id": "case-1",
                "text": "Repair request\r\n Customer: A   Project: P Product group: pump",
                "payload": {"email_message_id": "target-1", "business_type": "repair_request", "assignee_user_id": "user-1"},
            },
            {
                "id": "case-1",
                "source_email_message_id": "source-2",
                "text": "Repair request Customer: A Project: P Product group: pump",
                "payload": {"source_email_message_id": "source-2"},
            },
        ],
    }

    report = validate_dataset_leakage(dataset)

    finding_types = {finding.finding_type for finding in report.findings}
    assert report.passed is False
    assert "target_source_id_overlap" in finding_types
    assert "qdrant_payload_target_id_exposure" in finding_types
    assert "expected_assignee_direct_exposure" in finding_types
    assert "target_business_type_direct_exposure" in finding_types
    assert "duplicate_target" in finding_types
    assert "duplicate_retrieval_case" in finding_types
    assert report.near_duplicate_count >= 1


def test_clean_generator_is_deterministic_and_passes_leakage_validation():
    config = SyntheticDatasetConfig(
        dataset_version="synthetic-mail-decision-v2-clean",
        id_prefix="clean-v2-",
        clean_retrieval_cases=True,
    )
    first = SyntheticEvaluationDatasetGenerator(config).generate()
    second = SyntheticEvaluationDatasetGenerator(config).generate()

    assert first == second
    assert len(first["ground_truth"]) == 100
    assert len(first["qdrant_cases"]) == 100
    assert {row["email_message_id"] for row in first["ground_truth"]}.isdisjoint(
        {row["payload"]["source_email_message_id"] for row in first["qdrant_cases"]}
    )
    assert all("assignee_user_id" not in row["payload"] for row in first["qdrant_cases"])
    assert all("business_type" not in row["payload"] for row in first["qdrant_cases"])
    assert all("historical_assignee_user_id" in row["payload"] for row in first["qdrant_cases"])
    assert validate_dataset_leakage(first).passed is True


def test_synthetic_assignee_ownership_routes_ground_truth_without_review() -> None:
    dataset = SyntheticEvaluationDatasetGenerator(
        SyntheticDatasetConfig(
            dataset_version="synthetic-mail-decision-v2-clean",
            id_prefix="clean-v2-",
            clean_retrieval_cases=True,
        )
    ).generate()
    capabilities_by_user: dict[str, list[dict]] = {}
    for capability in dataset["assignee_capabilities"]:
        capabilities_by_user.setdefault(capability["user_id"], []).append(capability)
    users = [
        {
            **assignee,
            "capabilities": capabilities_by_user.get(assignee["id"], []),
        }
        for assignee in dataset["assignees"]
    ]
    emails_by_id = {email["id"]: email for email in dataset["emails"]}

    assert all(
        capability["capability_type"] in {"customer", "product", "business_type", "project"}
        for capability in dataset["assignee_capabilities"]
    )
    for truth in dataset["ground_truth"]:
        email = emails_by_id[truth["email_message_id"]]
        decision = RoutingPolicy().score(
            users=users,
            facts=MailFacts(
                customer_name=email["customer_name"],
                product_groups=[email["product_group"]],
                project_numbers=[email["project_code"]],
            ),
            classification=MailClassification(
                business_area="service",
                primary_type=email["business_type"],
                confidence=0.95,
            ),
            retrieval=RetrievalContext(sufficient=True),
        )

        assert decision.decision == "auto_assign"
        assert str(decision.selected_user_id) == truth["expected_assignee_user_id"]
        assert decision.candidates[0].total_score >= 0.82

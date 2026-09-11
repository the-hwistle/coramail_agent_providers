from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class EvaluationThresholds:
    classification_macro_f1: float = 0.85
    routing_top1_accuracy: float = 0.85
    routing_top3_recall: float = 0.95
    auto_assignment_precision: float = 0.95
    urgent_misroute_rate: float = 0.02
    unsupported_claim_rate: float = 0.01


def _safe_div(numerator: float, denominator: float) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def macro_f1(expected: list[str], predicted: list[str]) -> float:
    labels = sorted(set(expected) | set(predicted))
    scores = []
    for label in labels:
        tp = sum(e == label and p == label for e, p in zip(expected, predicted, strict=True))
        fp = sum(e != label and p == label for e, p in zip(expected, predicted, strict=True))
        fn = sum(e == label and p != label for e, p in zip(expected, predicted, strict=True))
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        scores.append(_safe_div(2 * precision * recall, precision + recall))
    return _safe_div(sum(scores), len(scores))


def evaluate_predictions(
    ground_truth: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    thresholds: EvaluationThresholds | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or EvaluationThresholds()
    truth_by_id = {str(row["email_message_id"]): row for row in ground_truth}
    prediction_by_id = {str(row["email_message_id"]): row for row in predictions}
    matched_ids = sorted(set(truth_by_id) & set(prediction_by_id))

    expected_labels = [str(truth_by_id[item]["business_type"]) for item in matched_ids]
    predicted_labels = [str(prediction_by_id[item].get("business_type") or "") for item in matched_ids]
    classification_score = macro_f1(expected_labels, predicted_labels) if matched_ids else 0.0

    top1_correct = 0
    top3_correct = 0
    auto_assigned = 0
    auto_correct = 0
    urgent_total = 0
    urgent_misroutes = 0
    unsupported_claims = 0
    for item in matched_ids:
        truth = truth_by_id[item]
        prediction = prediction_by_id[item]
        expected_assignee = str(truth["expected_assignee_user_id"])
        candidates = [str(value) for value in prediction.get("candidate_user_ids") or []]
        selected = str(prediction.get("selected_user_id") or "")
        if selected == expected_assignee:
            top1_correct += 1
        if expected_assignee in candidates[:3]:
            top3_correct += 1
        if prediction.get("auto_assigned") is True:
            auto_assigned += 1
            if selected == expected_assignee:
                auto_correct += 1
        if truth.get("urgent") is True:
            urgent_total += 1
            if selected and selected != expected_assignee:
                urgent_misroutes += 1
        unsupported_claims += int(prediction.get("unsupported_claim_count") or 0)

    count = len(matched_ids)
    metrics = {
        "evaluated_cases": count,
        "coverage": _safe_div(count, len(ground_truth)),
        "classification_macro_f1": classification_score,
        "routing_top1_accuracy": _safe_div(top1_correct, count),
        "routing_top3_recall": _safe_div(top3_correct, count),
        "auto_assignment_precision": _safe_div(auto_correct, auto_assigned),
        "urgent_misroute_rate": _safe_div(urgent_misroutes, urgent_total),
        "unsupported_claim_rate": _safe_div(unsupported_claims, count),
    }
    checks = {
        "classification_macro_f1": metrics["classification_macro_f1"] >= thresholds.classification_macro_f1,
        "routing_top1_accuracy": metrics["routing_top1_accuracy"] >= thresholds.routing_top1_accuracy,
        "routing_top3_recall": metrics["routing_top3_recall"] >= thresholds.routing_top3_recall,
        "auto_assignment_precision": metrics["auto_assignment_precision"] >= thresholds.auto_assignment_precision,
        "urgent_misroute_rate": metrics["urgent_misroute_rate"] <= thresholds.urgent_misroute_rate,
        "unsupported_claim_rate": metrics["unsupported_claim_rate"] <= thresholds.unsupported_claim_rate,
    }
    return {
        "metrics": metrics,
        "thresholds": thresholds.__dict__,
        "checks": checks,
        "passed": bool(count) and all(checks.values()),
        "missing_prediction_ids": sorted(set(truth_by_id) - set(prediction_by_id)),
        "unexpected_prediction_ids": sorted(set(prediction_by_id) - set(truth_by_id)),
        "expected_label_distribution": dict(Counter(expected_labels)),
        "predicted_label_distribution": dict(Counter(predicted_labels)),
    }


class EvaluationMetricValue(BaseModel):
    numerator: float
    denominator: float
    value: float


class EvaluationCaseResult(BaseModel):
    email_message_id: str
    run_id: str | None = None
    status: str
    expected_business_type: str
    predicted_business_type: str | None = None
    business_type_correct: bool = False
    expected_urgency: str | None = None
    predicted_urgency: str | None = None
    urgency_correct: bool | None = None
    expected_importance: str | None = None
    predicted_importance: str | None = None
    importance_correct: bool | None = None
    expected_attention_quadrant: str | None = None
    predicted_attention_quadrant: str | None = None
    attention_quadrant_correct: bool | None = None
    expected_assignee_user_id: str
    candidate_user_ids: list[str] = Field(default_factory=list)
    expected_assignee_rank: int | None = None
    candidate_contains_expected: bool = False
    selected_user_id: str | None = None
    selected_assignee_correct: bool = False
    auto_assigned: bool = False
    review_reason: str | None = None
    primary_failure_stage: str
    primary_failure_reason: str
    error: str | None = None


class EvaluationMetrics(BaseModel):
    values: dict[str, EvaluationMetricValue]
    confusion_matrix: dict[str, dict[str, int]]
    per_type_precision: dict[str, EvaluationMetricValue]
    per_type_recall: dict[str, EvaluationMetricValue]
    per_type_f1: dict[str, EvaluationMetricValue]
    review_reason_counts: dict[str, int]
    primary_failure_stage_counts: dict[str, int]
    error_type_counts: dict[str, int]


class EvaluationFailureSummary(BaseModel):
    missing_prediction_ids: list[str] = Field(default_factory=list)
    duplicate_prediction_ids: list[str] = Field(default_factory=list)
    unexpected_prediction_ids: list[str] = Field(default_factory=list)
    trace_integrity_errors: list[str] = Field(default_factory=list)
    leakage: dict[str, Any] = Field(default_factory=dict)


class DeveloperEvaluationTrace(BaseModel):
    email_message_id: str
    run_id: str | None = None
    dataset_version: str | None = None
    qdrant_collection: str | None = None
    input: dict[str, Any]
    ground_truth: dict[str, Any]
    facts: dict[str, Any]
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    retrieval: dict[str, Any]
    sufficiency: dict[str, Any]
    decision: dict[str, Any] = Field(default_factory=dict)
    routing: dict[str, Any]
    evaluation: dict[str, Any]


class EvaluationReport(BaseModel):
    generated_at: str
    dataset_path: str | None = None
    predictions_path: str | None = None
    model_context: dict[str, str] = Field(default_factory=dict)
    metrics: EvaluationMetrics
    cases: list[EvaluationCaseResult]
    failure_summary: EvaluationFailureSummary
    passed: bool


FAILURE_STAGE_ORDER = (
    "runtime_failed",
    "attachment_analysis_failed",
    "fact_extraction_empty",
    "fact_extraction_incorrect",
    "retrieval_no_hits",
    "retrieval_context_insufficient",
    "business_type_missing",
    "business_type_incorrect",
    "candidate_generation_empty",
    "expected_assignee_not_in_candidates",
    "selected_assignee_missing",
    "selected_assignee_incorrect",
    "unsafe_auto_assignment",
    "success",
    "unknown",
)


def score_predictions(
    dataset: dict[str, Any],
    predictions: list[dict[str, Any]],
    *,
    dataset_path: Path | None = None,
    predictions_path: Path | None = None,
    strict: bool = False,
    prediction_scope: bool = False,
) -> tuple[EvaluationReport, list[DeveloperEvaluationTrace]]:
    truth_rows = list(dataset.get("ground_truth") or [])
    scoped_prediction_ids = {str(row.get("email_message_id") or "") for row in predictions if row.get("email_message_id")}
    if prediction_scope and scoped_prediction_ids:
        truth_rows = [row for row in truth_rows if str(row.get("email_message_id")) in scoped_prediction_ids]
    emails_by_id = {str(row.get("id")): row for row in dataset.get("emails") or []}
    attachments_by_email: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for attachment in dataset.get("attachments") or []:
        attachments_by_email[str(attachment.get("email_message_id"))].append(attachment)

    truth_by_id = {str(row["email_message_id"]): row for row in truth_rows}
    prediction_counts = Counter(str(row.get("email_message_id") or "") for row in predictions)
    duplicate_ids = sorted(item for item, count in prediction_counts.items() if item and count > 1)
    prediction_by_id: dict[str, dict[str, Any]] = {}
    for prediction in predictions:
        email_id = str(prediction.get("email_message_id") or "")
        if email_id and email_id not in prediction_by_id:
            prediction_by_id[email_id] = prediction

    leakage = _detect_leakage(dataset)
    cases: list[EvaluationCaseResult] = []
    traces: list[DeveloperEvaluationTrace] = []
    integrity_errors: list[str] = []
    for truth in truth_rows:
        email_id = str(truth["email_message_id"])
        prediction = prediction_by_id.get(email_id)
        email = emails_by_id.get(email_id, {})
        case = _case_result(truth, prediction)
        trace = _developer_trace(
            truth=truth,
            prediction=prediction,
            email=email,
            attachments=attachments_by_email.get(email_id, []),
            case=case,
        )
        integrity_errors.extend(_trace_integrity_errors(trace))
        cases.append(case)
        traces.append(trace)

    metrics = _detailed_metrics(cases, len(predictions))
    failure_summary = EvaluationFailureSummary(
        missing_prediction_ids=sorted(set(truth_by_id) - set(prediction_by_id)),
        duplicate_prediction_ids=duplicate_ids,
        unexpected_prediction_ids=sorted(set(prediction_by_id) - set(truth_by_id)),
        trace_integrity_errors=integrity_errors,
        leakage=leakage,
    )
    passed = not failure_summary.missing_prediction_ids and not failure_summary.duplicate_prediction_ids
    passed = passed and not failure_summary.unexpected_prediction_ids
    passed = passed and (not strict or not failure_summary.trace_integrity_errors)
    report = EvaluationReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        dataset_path=str(dataset_path) if dataset_path else None,
        predictions_path=str(predictions_path) if predictions_path else None,
        model_context=_model_context(predictions),
        metrics=metrics,
        cases=cases,
        failure_summary=failure_summary,
        passed=passed,
    )
    return report, traces


def write_evaluation_outputs(
    report: EvaluationReport,
    traces: list[DeveloperEvaluationTrace],
    *,
    report_json: Path,
    cases_csv: Path,
    trace_jsonl: Path,
) -> None:
    report_json.parent.mkdir(parents=True, exist_ok=True)
    cases_csv.parent.mkdir(parents=True, exist_ok=True)
    trace_jsonl.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    fieldnames = list(EvaluationCaseResult.model_fields)
    with cases_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for case in report.cases:
            row = case.model_dump(mode="json")
            row["candidate_user_ids"] = json.dumps(row["candidate_user_ids"], ensure_ascii=False)
            writer.writerow(row)
    with trace_jsonl.open("w", encoding="utf-8") as handle:
        for trace in traces:
            handle.write(json.dumps(trace.model_dump(mode="json"), ensure_ascii=False) + "\n")


def _metric(numerator: float, denominator: float) -> EvaluationMetricValue:
    return EvaluationMetricValue(numerator=numerator, denominator=denominator, value=_safe_div(numerator, denominator))


def _case_result(truth: dict[str, Any], prediction: dict[str, Any] | None) -> EvaluationCaseResult:
    expected_type = str(truth.get("business_type") or "")
    expected_assignee = str(truth.get("expected_assignee_user_id") or "")
    expected_urgency = _expected_urgency(truth)
    expected_importance = str(truth.get("expected_importance") or "").strip() or None
    expected_attention = str(truth.get("expected_attention_quadrant") or "").strip() or None
    if prediction is None:
        return EvaluationCaseResult(
            email_message_id=str(truth["email_message_id"]),
            status="missing_prediction",
            expected_business_type=expected_type,
            expected_urgency=expected_urgency,
            expected_importance=expected_importance,
            expected_attention_quadrant=expected_attention,
            expected_assignee_user_id=expected_assignee,
            primary_failure_stage="runtime_failed",
            primary_failure_reason="prediction_missing",
        )
    candidates = [str(value) for value in prediction.get("candidate_user_ids") or [] if str(value)]
    selected = str(prediction.get("selected_user_id") or "") or None
    business_type = str(prediction.get("business_type") or "") or None
    predicted_urgency = _prediction_urgency(prediction)
    predicted_importance = _prediction_importance(prediction)
    predicted_attention = _prediction_attention_quadrant(prediction)
    expected_rank = candidates.index(expected_assignee) + 1 if expected_assignee in candidates else None
    case = EvaluationCaseResult(
        email_message_id=str(truth["email_message_id"]),
        run_id=str(prediction.get("run_id") or "") or None,
        status=str(prediction.get("status") or "unknown"),
        expected_business_type=expected_type,
        predicted_business_type=business_type,
        business_type_correct=business_type == expected_type,
        expected_urgency=expected_urgency,
        predicted_urgency=predicted_urgency,
        urgency_correct=predicted_urgency == expected_urgency if expected_urgency else None,
        expected_importance=expected_importance,
        predicted_importance=predicted_importance,
        importance_correct=predicted_importance == expected_importance if expected_importance else None,
        expected_attention_quadrant=expected_attention,
        predicted_attention_quadrant=predicted_attention,
        attention_quadrant_correct=predicted_attention == expected_attention if expected_attention else None,
        expected_assignee_user_id=expected_assignee,
        candidate_user_ids=candidates,
        expected_assignee_rank=expected_rank,
        candidate_contains_expected=expected_rank is not None,
        selected_user_id=selected,
        selected_assignee_correct=selected == expected_assignee,
        auto_assigned=prediction.get("auto_assigned") is True,
        review_reason=str(prediction.get("review_reason") or "") or None,
        primary_failure_stage="unknown",
        primary_failure_reason="unknown",
        error=str(prediction.get("error") or "") or None,
    )
    stage, reason = _classify_failure(case, truth, prediction)
    case.primary_failure_stage = stage
    case.primary_failure_reason = reason
    return case


def _classify_failure(
    case: EvaluationCaseResult,
    truth: dict[str, Any],
    prediction: dict[str, Any],
) -> tuple[str, str]:
    if case.status == "failed" or case.error:
        return "runtime_failed", case.error or "prediction_status_failed"
    if _attachment_failed(prediction):
        return "attachment_analysis_failed", "attachment analysis status is failed or unsupported"
    facts = _facts_values(prediction)
    if facts is not None and _facts_empty(facts):
        return "fact_extraction_empty", "core fact fields are empty"
    if facts is not None:
        mismatch = _fact_mismatch_reason(truth, facts)
        if mismatch:
            return "fact_extraction_incorrect", mismatch
    retrieval = _retrieval_cycles(prediction)
    if retrieval and not any(cycle.get("hits") for cycle in retrieval):
        return "retrieval_no_hits", "retrieval cycles contain no hits"
    if case.review_reason == "retrieval_context_insufficient" or not _sufficiency(prediction).get("sufficient", False):
        return "retrieval_context_insufficient", case.review_reason or "sufficiency_false"
    if not case.predicted_business_type:
        return "business_type_missing", "business_type is null"
    if not case.business_type_correct:
        return "business_type_incorrect", "predicted business_type differs from ground truth"
    if not case.candidate_user_ids:
        return "candidate_generation_empty", "candidate_user_ids is empty"
    if not case.candidate_contains_expected:
        return "expected_assignee_not_in_candidates", "expected assignee is not in candidate_user_ids"
    if not case.selected_user_id:
        return "selected_assignee_missing", "selected_user_id is null"
    if not case.selected_assignee_correct:
        return "unsafe_auto_assignment" if case.auto_assigned else "selected_assignee_incorrect", "selected user differs from ground truth"
    return "success", "prediction matches ground truth"


def _detailed_metrics(cases: list[EvaluationCaseResult], raw_prediction_count: int) -> EvaluationMetrics:
    total = len(cases)
    prediction_count = sum(case.status != "missing_prediction" for case in cases)
    failed_count = sum(case.status == "failed" for case in cases)
    review_count = sum(case.status == "review_required" for case in cases)
    execution_success = prediction_count - failed_count
    business_pred_count = sum(bool(case.predicted_business_type) for case in cases)
    business_correct = sum(case.business_type_correct for case in cases)
    urgency_cases = [case for case in cases if case.expected_urgency]
    urgency_correct = sum(case.urgency_correct is True for case in urgency_cases)
    importance_cases = [case for case in cases if case.expected_importance]
    importance_correct = sum(case.importance_correct is True for case in importance_cases)
    attention_cases = [case for case in cases if case.expected_attention_quadrant]
    attention_correct = sum(case.attention_quadrant_correct is True for case in attention_cases)
    selected_count = sum(bool(case.selected_user_id) for case in cases)
    selected_correct = sum(case.selected_assignee_correct for case in cases)
    candidate_contains = sum(case.candidate_contains_expected for case in cases)
    auto_count = sum(case.auto_assigned for case in cases)
    auto_correct = sum(case.auto_assigned and case.selected_assignee_correct for case in cases)
    mrr_sum = sum((1.0 / case.expected_assignee_rank) for case in cases if case.expected_assignee_rank)
    values = {
        "total_cases": _metric(total, total),
        "prediction_count": _metric(prediction_count, total),
        "missing_prediction_count": _metric(total - prediction_count, total),
        "execution_success_count": _metric(execution_success, total),
        "failed_count": _metric(failed_count, total),
        "failure_rate": _metric(failed_count, total),
        "review_required_count": _metric(review_count, total),
        "review_required_rate": _metric(review_count, total),
        "business_type_prediction_count": _metric(business_pred_count, total),
        "business_type_prediction_coverage": _metric(business_pred_count, total),
        "business_type_correct_count": _metric(business_correct, total),
        "business_type_accuracy_overall": _metric(business_correct, total),
        "business_type_accuracy_when_predicted": _metric(business_correct, business_pred_count),
        "urgency_accuracy": _metric(urgency_correct, len(urgency_cases)),
        "importance_accuracy": _metric(importance_correct, len(importance_cases)),
        "attention_quadrant_accuracy": _metric(attention_correct, len(attention_cases)),
        "selected_assignee_count": _metric(selected_count, total),
        "selected_assignee_coverage": _metric(selected_count, total),
        "selected_assignee_correct_count": _metric(selected_correct, total),
        "top1_assignee_accuracy_overall": _metric(selected_correct, total),
        "top1_assignee_accuracy_when_selected": _metric(selected_correct, selected_count),
        "candidate_contains_expected_count": _metric(candidate_contains, total),
        "candidate_recall_at_k": _metric(candidate_contains, total),
        "candidate_mrr": _metric(mrr_sum, total),
        "auto_assigned_count": _metric(auto_count, total),
        "auto_assignment_rate": _metric(auto_count, total),
        "auto_assignment_correct_count": _metric(auto_correct, auto_count),
        "auto_assignment_accuracy": _metric(auto_correct, auto_count),
        "raw_prediction_count": _metric(raw_prediction_count, total),
    }
    labels = sorted({case.expected_business_type for case in cases} | {case.predicted_business_type or "" for case in cases})
    confusion: dict[str, dict[str, int]] = {label: {inner: 0 for inner in labels} for label in labels}
    for case in cases:
        confusion[case.expected_business_type][case.predicted_business_type or ""] += 1
    precision = {}
    recall = {}
    f1 = {}
    for label in labels:
        tp = confusion.get(label, {}).get(label, 0)
        fp = sum(confusion.get(other, {}).get(label, 0) for other in labels if other != label)
        fn = sum(count for pred, count in confusion.get(label, {}).items() if pred != label)
        precision[label] = _metric(tp, tp + fp)
        recall[label] = _metric(tp, tp + fn)
        p_value = precision[label].value
        r_value = recall[label].value
        f1[label] = EvaluationMetricValue(
            numerator=2 * p_value * r_value,
            denominator=p_value + r_value,
            value=_safe_div(2 * p_value * r_value, p_value + r_value),
        )
    return EvaluationMetrics(
        values=values,
        confusion_matrix=confusion,
        per_type_precision=precision,
        per_type_recall=recall,
        per_type_f1=f1,
        review_reason_counts=dict(Counter(case.review_reason or "none" for case in cases)),
        primary_failure_stage_counts=dict(Counter(case.primary_failure_stage for case in cases)),
        error_type_counts=dict(Counter((case.error or "").split(":", 1)[0] for case in cases if case.error)),
    )


def _developer_trace(
    *,
    truth: dict[str, Any],
    prediction: dict[str, Any] | None,
    email: dict[str, Any],
    attachments: list[dict[str, Any]],
    case: EvaluationCaseResult,
) -> DeveloperEvaluationTrace:
    facts = _facts_values(prediction or {}) or {}
    retrieval_cycles = _normalized_retrieval_cycles(prediction or {})
    sufficiency = _normalized_sufficiency(prediction or {}, case)
    routing_candidates = _normalized_routing_candidates(prediction or {}, case)
    body = str(email.get("body_text") or "")
    return DeveloperEvaluationTrace(
        email_message_id=case.email_message_id,
        run_id=case.run_id,
        dataset_version=str((prediction or {}).get("dataset_version") or ""),
        qdrant_collection=str((prediction or {}).get("qdrant_collection") or ""),
        input={
            "subject": str(email.get("subject") or ""),
            "body_preview": body[:240],
            "body_length": len(body),
            "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest() if body else "",
            "attachment_filenames": [str(item.get("filename") or "") for item in attachments],
        },
        ground_truth={
            "business_type": truth.get("business_type"),
            "assignee_user_id": truth.get("expected_assignee_user_id"),
            "customer": truth.get("customer_name"),
            "product_group": truth.get("product_group"),
            "project": truth.get("project_code"),
            "urgent": truth.get("urgent"),
            "expected_urgency": truth.get("expected_urgency"),
            "expected_importance": truth.get("expected_importance"),
            "expected_attention_quadrant": truth.get("expected_attention_quadrant"),
        },
        facts={"values": facts, "field_comparison": _field_comparison(truth, facts)},
        attachments=_normalized_attachments(prediction or {}, attachments),
        retrieval={"cycles": retrieval_cycles},
        sufficiency=sufficiency,
        decision=_decision_output(prediction or {}),
        routing={
            "candidates": routing_candidates,
            "selected_user_id": case.selected_user_id,
            "expected_assignee_rank": case.expected_assignee_rank,
            "score_observability": _routing_score_observability(routing_candidates),
        },
        evaluation={
            "business_type_correct": case.business_type_correct,
            "urgency_correct": case.urgency_correct,
            "importance_correct": case.importance_correct,
            "attention_quadrant_correct": case.attention_quadrant_correct,
            "candidate_contains_expected": case.candidate_contains_expected,
            "selected_assignee_correct": case.selected_assignee_correct,
            "primary_failure_stage": case.primary_failure_stage,
            "primary_failure_reason": case.primary_failure_reason,
        },
    )


def _facts_values(prediction: dict[str, Any]) -> dict[str, Any] | None:
    facts = prediction.get("facts")
    if isinstance(facts, dict):
        return facts.get("values") if isinstance(facts.get("values"), dict) else facts
    return None


def _expected_urgency(truth: dict[str, Any]) -> str | None:
    explicit = str(truth.get("expected_urgency") or "").strip()
    if explicit:
        return explicit
    if truth.get("urgent") is True:
        return "high"
    if truth.get("urgent") is False:
        return "normal"
    return None


def _prediction_urgency(prediction: dict[str, Any]) -> str | None:
    decision = prediction.get("decision_output") if isinstance(prediction.get("decision_output"), dict) else {}
    urgency = decision.get("urgency")
    if isinstance(urgency, dict):
        value = str(urgency.get("level") or "").strip()
        return value or None
    return str(prediction.get("urgency") or "").strip() or None


def _prediction_importance(prediction: dict[str, Any]) -> str | None:
    decision = prediction.get("decision_output") if isinstance(prediction.get("decision_output"), dict) else {}
    importance = decision.get("importance")
    if isinstance(importance, dict):
        value = str(importance.get("level") or "").strip()
        return value or None
    return str(prediction.get("importance") or "").strip() or None


def _prediction_attention_quadrant(prediction: dict[str, Any]) -> str | None:
    decision = prediction.get("decision_output") if isinstance(prediction.get("decision_output"), dict) else {}
    return str(decision.get("attention_quadrant") or prediction.get("attention_quadrant") or "").strip() or None


def _facts_empty(facts: dict[str, Any]) -> bool:
    keys = ("customer_name", "request_types", "requested_actions", "product_groups", "project_numbers", "vessel_names")
    return not any(facts.get(key) for key in keys)


def _fact_mismatch_reason(truth: dict[str, Any], facts: dict[str, Any]) -> str:
    comparisons = _field_comparison(truth, facts)
    for field, row in comparisons.items():
        if row["present"] and not row["match"]:
            return f"{field} extracted value differs from ground truth"
    return ""


def _field_comparison(truth: dict[str, Any], facts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapping = {
        "customer": ("customer_name", "customer_name"),
        "product_group": ("product_group", "product_groups"),
        "project": ("project_code", "project_numbers"),
        "request_type": ("business_type", "request_types"),
    }
    result: dict[str, dict[str, Any]] = {}
    for field, (truth_key, fact_key) in mapping.items():
        expected = truth.get(truth_key)
        actual = facts.get(fact_key)
        values = actual if isinstance(actual, list) else ([actual] if actual else [])
        normalized_expected = str(expected or "").strip().casefold()
        normalized_values = {str(value).strip().casefold() for value in values if str(value).strip()}
        result[field] = {
            "expected": expected,
            "actual": actual,
            "present": bool(normalized_values),
            "match": bool(normalized_expected and normalized_expected in normalized_values),
        }
    return result


def _attachment_failed(prediction: dict[str, Any]) -> bool:
    for item in prediction.get("attachment_analysis") or prediction.get("attachments") or []:
        if isinstance(item, dict) and str(item.get("status") or "") in {"failed", "unsupported"}:
            return True
    return False


def _normalized_attachments(prediction: dict[str, Any], dataset_attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    recorded = prediction.get("attachment_analysis") or prediction.get("attachments")
    if isinstance(recorded, list) and recorded:
        return [item for item in recorded if isinstance(item, dict)]
    return [
        {
            "attachment_id": item.get("id"),
            "filename": item.get("filename"),
            "content_type": item.get("content_type"),
            "status": "not_recorded",
        }
        for item in dataset_attachments
    ]


def _retrieval_cycles(prediction: dict[str, Any]) -> list[dict[str, Any]]:
    retrieval = prediction.get("retrieval") or prediction.get("retrieval_context") or {}
    if isinstance(retrieval, dict):
        cycles = retrieval.get("cycles")
        return cycles if isinstance(cycles, list) else []
    cycles = prediction.get("retrieval_cycles")
    return cycles if isinstance(cycles, list) else []


def _normalized_retrieval_cycles(prediction: dict[str, Any]) -> list[dict[str, Any]]:
    cycles = []
    for cycle in _retrieval_cycles(prediction):
        if not isinstance(cycle, dict):
            continue
        plan = cycle.get("plan") if isinstance(cycle.get("plan"), dict) else {}
        queries = plan.get("queries") if isinstance(plan.get("queries"), list) else []
        hits = []
        for hit in cycle.get("hits") or []:
            if not isinstance(hit, dict):
                continue
            included = hit.get("included_in_prompt") is True
            metadata = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
            hits.append(
                {
                    "cycle": cycle.get("cycle_number") or cycle.get("cycle") or 1,
                    "strategy": hit.get("retriever_type") or hit.get("strategy") or "unknown",
                    "query_text": _query_text_for_hit(queries, hit),
                    "filter": _query_filter_for_hit(queries, hit),
                    "top_k": _query_limit_for_hit(queries, hit),
                    "source_type": hit.get("source_type") or "unknown",
                    "candidate_id": str(hit.get("source_id") or hit.get("candidate_id") or ""),
                    "score": hit.get("rerank_score") if hit.get("rerank_score") is not None else hit.get("retrieval_score"),
                    "threshold": hit.get("threshold") if hit.get("threshold") is not None else "not_recorded",
                    "included_in_prompt": included,
                    "excluded_reason": "" if included else str(hit.get("excluded_reason") or "unknown"),
                    "payload_summary": _payload_summary(hit, metadata),
                }
            )
        cycles.append(
            {
                "cycle": cycle.get("cycle_number") or cycle.get("cycle") or 1,
                "strategy": ", ".join(str(q.get("retriever_type") or "") for q in queries if isinstance(q, dict)) or "unknown",
                "queries": queries,
                "hits": hits,
                "sufficient": cycle.get("sufficient") is True,
                "missing_context": cycle.get("missing_context") or [],
                "reasons": cycle.get("reasons") or [],
            }
        )
    return cycles


def _query_text_for_hit(queries: list[Any], hit: dict[str, Any]) -> str:
    retriever = str(hit.get("retriever_type") or "")
    for query in queries:
        if isinstance(query, dict) and str(query.get("retriever_type") or "") == retriever:
            return str(query.get("query_text") or "")
    return str(hit.get("query_text") or "")


def _query_filter_for_hit(queries: list[Any], hit: dict[str, Any]) -> dict[str, Any]:
    retriever = str(hit.get("retriever_type") or "")
    for query in queries:
        if isinstance(query, dict) and str(query.get("retriever_type") or "") == retriever:
            filters = query.get("filters")
            return filters if isinstance(filters, dict) else {}
    filters = hit.get("filter") or hit.get("filters")
    return filters if isinstance(filters, dict) else {}


def _query_limit_for_hit(queries: list[Any], hit: dict[str, Any]) -> int | str:
    retriever = str(hit.get("retriever_type") or "")
    for query in queries:
        if isinstance(query, dict) and str(query.get("retriever_type") or "") == retriever:
            return query.get("limit") or "not_recorded"
    return hit.get("top_k") or "not_recorded"


def _payload_summary(hit: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": hit.get("title") or "",
        "metadata_keys": sorted(metadata),
        "assignee_user_id": metadata.get("assignee_user_id"),
        "business_type": metadata.get("business_type"),
    }


def _sufficiency(prediction: dict[str, Any]) -> dict[str, Any]:
    value = prediction.get("sufficiency")
    if isinstance(value, dict):
        return value
    retrieval = prediction.get("retrieval_context")
    if isinstance(retrieval, dict):
        return {
            "required_context": [],
            "resolved_context": [],
            "unresolved_context": retrieval.get("missing_context") or [],
            "business_type_context_resolved": not retrieval.get("missing_context"),
            "sufficient": retrieval.get("sufficient") is True,
            "review_reason": prediction.get("review_reason"),
        }
    return {}


def _normalized_sufficiency(prediction: dict[str, Any], case: EvaluationCaseResult) -> dict[str, Any]:
    sufficiency = _sufficiency(prediction)
    unresolved = list(sufficiency.get("unresolved_context") or sufficiency.get("missing_context") or [])
    if case.status == "review_required" and not unresolved:
        unresolved = _unresolved_from_review_reason(case.review_reason)
    resolved = list(sufficiency.get("resolved_context") or [])
    required = list(sufficiency.get("required_context") or sorted(set(resolved + unresolved)))
    return {
        "required_context": required,
        "resolved_context": resolved,
        "unresolved_context": unresolved,
        "business_type_context_resolved": bool(sufficiency.get("business_type_context_resolved") or "business_type_context" not in unresolved),
        "sufficient": sufficiency.get("sufficient") is True,
        "review_reason": case.review_reason,
        "reason": sufficiency.get("reason") or case.review_reason,
    }


def _unresolved_from_review_reason(reason: str | None) -> list[str]:
    if reason == "retrieval_context_insufficient":
        return ["business_type_context", "routing_context"]
    if reason:
        return [reason]
    return []


def _decision_output(prediction: dict[str, Any]) -> dict[str, Any]:
    decision = prediction.get("decision_output") or prediction.get("decision")
    return decision if isinstance(decision, dict) else {}


def _normalized_routing_candidates(prediction: dict[str, Any], case: EvaluationCaseResult) -> list[dict[str, Any]]:
    routing = prediction.get("routing_decision") or prediction.get("routing") or {}
    raw_candidates = routing.get("candidates") if isinstance(routing, dict) else None
    candidates = raw_candidates if isinstance(raw_candidates, list) else []
    if not candidates:
        candidates = [{"user_id": user_id, "rank": index} for index, user_id in enumerate(case.candidate_user_ids, start=1)]
    normalized = []
    for index, candidate in enumerate(candidates, start=1):
        if not isinstance(candidate, dict):
            continue
        components = candidate.get("component_scores") if isinstance(candidate.get("component_scores"), dict) else {}
        user_id = str(candidate.get("user_id") or candidate.get("candidate_user_id") or "")
        normalized.append(
            {
                "candidate_user_id": user_id,
                "candidate_rank": candidate.get("rank") or index,
                "capability_score": "not_recorded",
                "retrieval_score": components.get("history") or components.get("similarity") or "not_recorded",
                "rule_score": "not_recorded",
                "final_score": candidate.get("total_score") if candidate.get("total_score") is not None else "not_recorded",
                "component_scores": components,
                "eligible": candidate.get("eligible") if candidate.get("eligible") is not None else "not_recorded",
                "excluded_reason": str(candidate.get("excluded_reason") or ""),
                "selected": user_id == (case.selected_user_id or ""),
                "expected_assignee": user_id == case.expected_assignee_user_id,
            }
        )
    return normalized


def _routing_score_observability(candidates: list[dict[str, Any]]) -> dict[str, list[str]]:
    provided = set()
    missing = set()
    for field in ("capability_score", "retrieval_score", "rule_score", "final_score"):
        if any(candidate.get(field) != "not_recorded" for candidate in candidates):
            provided.add(field)
        else:
            missing.add(field)
    return {
        "provided_scores": sorted(provided),
        "missing_scores": sorted(missing),
        "observability_needed_at": ["app.routing.policy.RoutingPolicy.score", "app.services.mail_decision_routing_service"],
    }


def _trace_integrity_errors(trace: DeveloperEvaluationTrace) -> list[str]:
    errors = []
    for cycle in trace.retrieval.get("cycles", []):
        for hit in cycle.get("hits", []):
            if hit.get("included_in_prompt") is False and not hit.get("excluded_reason"):
                errors.append(f"{trace.email_message_id}: retrieval hit missing excluded_reason")
    if trace.sufficiency.get("review_reason") and not trace.sufficiency.get("unresolved_context"):
        errors.append(f"{trace.email_message_id}: review_required trace missing unresolved_context")
    return errors


def _detect_leakage(dataset: dict[str, Any]) -> dict[str, Any]:
    emails = {str(item.get("id")): item for item in dataset.get("emails") or []}
    truth = {str(item.get("email_message_id")): item for item in dataset.get("ground_truth") or []}
    cases = dataset.get("qdrant_cases") or []
    case_email_ids = {
        str(item.get("email_message_id") or item.get("source_email_message_id") or item.get("payload", {}).get("email_message_id") or "")
        for item in cases
    }
    overlap = sorted(set(truth) & case_email_ids)
    content_overlap = 0
    direct_label_exposure = 0
    for case in cases:
        payload = case.get("payload") if isinstance(case.get("payload"), dict) else {}
        email_id = str(payload.get("email_message_id") or case.get("email_message_id") or "")
        email = emails.get(email_id)
        if email and str(email.get("body_text") or "") and str(email.get("body_text")) in str(case.get("text") or ""):
            content_overlap += 1
        if payload.get("business_type") or payload.get("assignee_user_id"):
            direct_label_exposure += 1
    return {
        "ground_truth_and_qdrant_id_overlap": len(overlap),
        "qdrant_cases_with_target_body_text": content_overlap,
        "qdrant_cases_with_direct_labels": direct_label_exposure,
        "leakage_detected": bool(overlap or content_overlap or direct_label_exposure),
    }


def _model_context(predictions: list[dict[str, Any]]) -> dict[str, str]:
    keys = ("model_name", "text_model", "vision_model", "embedding_model", "workflow_version")
    result = {}
    for key in keys:
        values = sorted({str(prediction.get(key) or "") for prediction in predictions if prediction.get(key)})
        if values:
            result[key] = ", ".join(values)
    return result

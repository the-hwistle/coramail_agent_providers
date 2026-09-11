from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

SEQUENCE_NEAR_DUPLICATE_THRESHOLD = 0.95
TOKEN_JACCARD_NEAR_DUPLICATE_THRESHOLD = 0.90


class LeakageFinding(BaseModel):
    finding_type: str
    severity: str = "error"
    target_id: str | None = None
    retrieval_case_id: str | None = None
    source_id: str | None = None
    detail: str
    score: float | None = None


class LeakageValidationReport(BaseModel):
    dataset_version: str
    target_count: int
    retrieval_case_count: int
    id_overlap_count: int
    exact_content_overlap_count: int
    near_duplicate_count: int
    answer_exposure_count: int
    duplicate_target_count: int
    duplicate_retrieval_case_count: int
    passed: bool
    findings: list[LeakageFinding] = Field(default_factory=list)
    thresholds: dict[str, float] = Field(
        default_factory=lambda: {
            "sequence_ratio": SEQUENCE_NEAR_DUPLICATE_THRESHOLD,
            "token_jaccard": TOKEN_JACCARD_NEAR_DUPLICATE_THRESHOLD,
        }
    )


@dataclass(frozen=True)
class TextFingerprint:
    raw_id: str
    normalized_text: str
    sha256: str
    tokens: set[str]


def validate_dataset_leakage(dataset: dict[str, Any]) -> LeakageValidationReport:
    metadata = dataset.get("metadata") if isinstance(dataset.get("metadata"), dict) else {}
    target_ids = [str(item.get("email_message_id") or "") for item in dataset.get("ground_truth") or []]
    emails_by_id = {str(item.get("id") or ""): item for item in dataset.get("emails") or []}
    cases = [item for item in dataset.get("qdrant_cases") or [] if isinstance(item, dict)]
    findings: list[LeakageFinding] = []

    findings.extend(_duplicate_findings("duplicate_target", target_ids))
    case_ids = [str(item.get("id") or "") for item in cases]
    findings.extend(_duplicate_findings("duplicate_retrieval_case", case_ids))

    source_ids = [_case_source_id(item) for item in cases]
    target_id_set = {item for item in target_ids if item}
    for case, source_id in zip(cases, source_ids, strict=True):
        if source_id in target_id_set:
            findings.append(
                LeakageFinding(
                    finding_type="target_source_id_overlap",
                    target_id=source_id,
                    retrieval_case_id=str(case.get("id") or ""),
                    source_id=source_id,
                    detail="retrieval case source id overlaps evaluation target id",
                )
            )

    target_fingerprints = [
        _target_fingerprint(target_id, emails_by_id[target_id])
        for target_id in target_ids
        if target_id in emails_by_id
    ]
    case_fingerprints = [_case_fingerprint(case) for case in cases]
    target_hashes = {fingerprint.sha256: fingerprint for fingerprint in target_fingerprints}
    for case_fp in case_fingerprints:
        target_fp = target_hashes.get(case_fp.sha256)
        if target_fp is not None:
            findings.append(
                LeakageFinding(
                    finding_type="exact_content_overlap",
                    target_id=target_fp.raw_id,
                    retrieval_case_id=case_fp.raw_id,
                    detail="normalized target subject/body equals retrieval case text",
                )
            )

    for target_fp in target_fingerprints:
        for case_fp in case_fingerprints:
            sequence_ratio = SequenceMatcher(None, target_fp.normalized_text, case_fp.normalized_text).ratio()
            token_jaccard = _token_jaccard(target_fp.tokens, case_fp.tokens)
            if (
                sequence_ratio >= SEQUENCE_NEAR_DUPLICATE_THRESHOLD
                or token_jaccard >= TOKEN_JACCARD_NEAR_DUPLICATE_THRESHOLD
            ):
                findings.append(
                    LeakageFinding(
                        finding_type="near_duplicate_content",
                        target_id=target_fp.raw_id,
                        retrieval_case_id=case_fp.raw_id,
                        detail="target and retrieval text exceed near-duplicate threshold",
                        score=max(sequence_ratio, token_jaccard),
                    )
                )

    truth_by_id = {str(item.get("email_message_id") or ""): item for item in dataset.get("ground_truth") or []}
    for case in cases:
        payload = case.get("payload") if isinstance(case.get("payload"), dict) else {}
        source_id = _case_source_id(case)
        missing_provenance = [
            key
            for key in ("provider", "dataset_type", "synthetic", "evaluation", "assignment_confirmed")
            if key not in payload
        ]
        if missing_provenance:
            findings.append(
                LeakageFinding(
                    finding_type="qdrant_payload_missing_retrieval_provenance",
                    retrieval_case_id=str(case.get("id") or ""),
                    source_id=source_id,
                    detail=f"qdrant payload is missing retrieval provenance fields: {', '.join(missing_provenance)}",
                )
            )
        if payload.get("email_message_id") in target_id_set or payload.get("source_email_message_id") in target_id_set:
            findings.append(
                LeakageFinding(
                    finding_type="qdrant_payload_target_id_exposure",
                    target_id=str(payload.get("email_message_id") or payload.get("source_email_message_id") or ""),
                    retrieval_case_id=str(case.get("id") or ""),
                    source_id=source_id,
                    detail="qdrant payload exposes evaluation target id",
                )
            )
        if "assignee_user_id" in payload:
            findings.append(
                LeakageFinding(
                    finding_type="expected_assignee_direct_exposure",
                    target_id=source_id if source_id in truth_by_id else None,
                    retrieval_case_id=str(case.get("id") or ""),
                    source_id=source_id,
                    detail="qdrant payload uses answer-like assignee_user_id field",
                )
            )
        if "business_type" in payload:
            findings.append(
                LeakageFinding(
                    finding_type="target_business_type_direct_exposure",
                    target_id=source_id if source_id in truth_by_id else None,
                    retrieval_case_id=str(case.get("id") or ""),
                    source_id=source_id,
                    detail="qdrant payload uses answer-like business_type field",
                )
            )
        if source_id in truth_by_id and payload.get("historical_assignee_user_id") == truth_by_id[source_id].get("expected_assignee_user_id"):
            findings.append(
                LeakageFinding(
                    finding_type="ground_truth_object_direct_copy",
                    target_id=source_id,
                    retrieval_case_id=str(case.get("id") or ""),
                    source_id=source_id,
                    detail="retrieval payload historical assignee copies target ground truth for the same source id",
                )
            )

    id_overlap = sum(1 for finding in findings if finding.finding_type in {"target_source_id_overlap", "qdrant_payload_target_id_exposure"})
    exact_overlap = sum(1 for finding in findings if finding.finding_type == "exact_content_overlap")
    near_duplicates = sum(1 for finding in findings if finding.finding_type == "near_duplicate_content")
    answer_exposure = sum(
        1
        for finding in findings
        if finding.finding_type
        in {
            "expected_assignee_direct_exposure",
            "target_business_type_direct_exposure",
            "ground_truth_object_direct_copy",
        }
    )
    duplicate_targets = sum(1 for finding in findings if finding.finding_type == "duplicate_target")
    duplicate_cases = sum(1 for finding in findings if finding.finding_type == "duplicate_retrieval_case")
    return LeakageValidationReport(
        dataset_version=str(metadata.get("dataset_version") or "unknown"),
        target_count=len(target_ids),
        retrieval_case_count=len(cases),
        id_overlap_count=id_overlap,
        exact_content_overlap_count=exact_overlap,
        near_duplicate_count=near_duplicates,
        answer_exposure_count=answer_exposure,
        duplicate_target_count=duplicate_targets,
        duplicate_retrieval_case_count=duplicate_cases,
        passed=not findings,
        findings=findings,
    )


def write_leakage_report(report: LeakageValidationReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFC", value)
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return re.sub(r"\s+", " ", text)


def _duplicate_findings(finding_type: str, values: list[str]) -> list[LeakageFinding]:
    result = []
    for value, count in Counter(item for item in values if item).items():
        if count > 1:
            result.append(LeakageFinding(finding_type=finding_type, target_id=value, detail=f"{value} appears {count} times"))
    return result


def _target_fingerprint(target_id: str, email: dict[str, Any]) -> TextFingerprint:
    text = normalize_text(f"{email.get('subject') or ''}\n{email.get('body_text') or ''}")
    return _fingerprint(target_id, text)


def _case_fingerprint(case: dict[str, Any]) -> TextFingerprint:
    text = normalize_text(str(case.get("text") or ""))
    return _fingerprint(str(case.get("id") or ""), text)


def _fingerprint(raw_id: str, text: str) -> TextFingerprint:
    return TextFingerprint(
        raw_id=raw_id,
        normalized_text=text,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        tokens=set(re.findall(r"[\w.-]+", text)),
    )


def _case_source_id(case: dict[str, Any]) -> str:
    payload = case.get("payload") if isinstance(case.get("payload"), dict) else {}
    return str(
        case.get("email_message_id")
        or case.get("source_email_message_id")
        or payload.get("email_message_id")
        or payload.get("source_email_message_id")
        or ""
    )


def _token_jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)

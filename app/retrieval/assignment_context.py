from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from app.schemas.retrieval import (
    AssignmentCandidateContext,
    AssignmentContext,
    AssignmentEvidence,
    AssignmentEvidenceType,
    RetrievalContext,
    RetrievalHit,
    RetrieverType,
)


class AssignmentContextBuilder:
    """Normalizes retrieval hits into assignment evidence without scoring candidates."""

    _EVIDENCE_TYPE_BY_RETRIEVER = {
        RetrieverType.EXACT: AssignmentEvidenceType.EXACT_HISTORY,
        RetrieverType.ROUTING_RULE: AssignmentEvidenceType.ROUTING_RULE,
        RetrieverType.ASSIGNEE_CAPABILITY: AssignmentEvidenceType.ASSIGNEE_CAPABILITY,
        RetrieverType.SIMILAR_CASE: AssignmentEvidenceType.SIMILAR_CASE,
    }

    def build(self, retrieval: RetrievalContext) -> AssignmentContext:
        warnings: list[str] = []
        evidence: list[AssignmentEvidence] = []
        seen_evidence: set[tuple[str, str, str, str, str]] = set()

        for hit in retrieval.selected_hits:
            normalized = self._evidence_from_hit(hit, warnings)
            if normalized is None:
                continue
            key = self._evidence_key(normalized)
            if key in seen_evidence:
                continue
            seen_evidence.add(key)
            evidence.append(normalized)

        candidate_contexts = self._candidate_contexts(evidence)
        missing_context = list(retrieval.missing_context)
        if not retrieval.selected_hits:
            missing_context.append("selected_hits_empty")
        if evidence and not candidate_contexts:
            missing_context.append("assignee_linked_evidence_missing")
        if not evidence and retrieval.selected_hits:
            missing_context.append("assignment_evidence_missing")

        return AssignmentContext(
            selected_hits=[hit.model_copy(deep=True) for hit in retrieval.selected_hits],
            evidence=evidence,
            candidate_contexts=candidate_contexts,
            missing_context=list(dict.fromkeys(missing_context)),
            conflicts=[],
            warnings=list(dict.fromkeys(warnings)),
        )

    def _evidence_from_hit(self, hit: RetrievalHit, warnings: list[str]) -> AssignmentEvidence | None:
        evidence_type = self._EVIDENCE_TYPE_BY_RETRIEVER.get(hit.retriever_type)
        if evidence_type is None:
            warnings.append(f"unknown_retriever_type:{hit.retriever_type}")
            return None

        metadata = dict(hit.metadata)
        assignee_user_id = self._uuid_or_none(metadata.get("assignee_user_id"))
        if metadata.get("assignee_user_id") and assignee_user_id is None:
            warnings.append("malformed_assignee_user_id")
        if assignee_user_id is None:
            warnings.append(f"assignee_user_id_missing:{hit.retriever_type.value}")
        if hit.source_id is None:
            warnings.append(f"source_id_missing:{hit.retriever_type.value}")

        score = hit.rerank_score if hit.rerank_score is not None else hit.retrieval_score
        return AssignmentEvidence(
            evidence_type=evidence_type,
            assignee_user_id=assignee_user_id,
            retriever_type=hit.retriever_type,
            source_type=hit.source_type,
            source_id=hit.source_id,
            title=hit.title,
            content=hit.content,
            score=score,
            confidence=self._optional_float(metadata.get("confidence")),
            confirmed=self._confirmed(hit),
            observed_at=self._datetime_or_none(metadata.get("observed_at")),
            valid_from=self._datetime_or_none(metadata.get("valid_from")),
            valid_to=self._datetime_or_none(metadata.get("valid_to")),
            metadata=metadata,
        )

    @staticmethod
    def _candidate_contexts(evidence: list[AssignmentEvidence]) -> list[AssignmentCandidateContext]:
        by_user: dict[UUID, list[AssignmentEvidence]] = {}
        for item in evidence:
            if item.assignee_user_id is None:
                continue
            by_user.setdefault(item.assignee_user_id, []).append(item)

        contexts: list[AssignmentCandidateContext] = []
        for assignee_user_id, rows in by_user.items():
            strongest = max(rows, key=lambda item: item.score)
            contexts.append(
                AssignmentCandidateContext(
                    assignee_user_id=assignee_user_id,
                    evidence=rows,
                    reasons=[
                        f"{item.evidence_type.value}:{item.score:.2f}"
                        for item in rows
                    ],
                    strongest_score=strongest.score,
                    strongest_evidence_type=strongest.evidence_type,
                    has_confirmed_evidence=any(item.confirmed is True for item in rows),
                    observed_at=AssignmentContextBuilder._latest_datetime(
                        item.observed_at for item in rows
                    ),
                    valid_from=AssignmentContextBuilder._earliest_datetime(
                        item.valid_from for item in rows
                    ),
                    valid_to=AssignmentContextBuilder._latest_datetime(
                        item.valid_to for item in rows
                    ),
                )
            )
        contexts.sort(key=lambda item: (item.strongest_score, str(item.assignee_user_id)), reverse=True)
        return contexts

    @staticmethod
    def _confirmed(hit: RetrievalHit) -> bool | None:
        if hit.retriever_type == RetrieverType.SIMILAR_CASE:
            value = hit.metadata.get("assignment_confirmed")
            return value if isinstance(value, bool) else None
        if hit.retriever_type in {
            RetrieverType.ROUTING_RULE,
            RetrieverType.ASSIGNEE_CAPABILITY,
        }:
            return True
        if hit.retriever_type == RetrieverType.EXACT:
            return bool(hit.metadata.get("assignee_user_id"))
        return None

    @staticmethod
    def _evidence_key(evidence: AssignmentEvidence) -> tuple[str, str, str, str, str]:
        return (
            evidence.evidence_type.value,
            str(evidence.assignee_user_id or ""),
            evidence.source_type,
            str(evidence.source_id or ""),
            evidence.title,
        )

    @staticmethod
    def _uuid_or_none(value: Any) -> UUID | None:
        if value in (None, ""):
            return None
        try:
            return UUID(str(value))
        except (TypeError, ValueError, AttributeError):
            return None

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return max(0.0, min(1.0, number))

    @staticmethod
    def _datetime_or_none(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _latest_datetime(values: Any) -> datetime | None:
        rows = [value for value in values if value is not None]
        return max(rows) if rows else None

    @staticmethod
    def _earliest_datetime(values: Any) -> datetime | None:
        rows = [value for value in values if value is not None]
        return min(rows) if rows else None

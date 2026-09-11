from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.schemas.mail_decision import MailClassification, MailFacts, RoutingCandidate, RoutingDecision
from app.schemas.retrieval import RetrievalContext


@dataclass(frozen=True)
class RoutingPolicyConfig:
    auto_assign_threshold: float = 0.82
    minimum_margin: float = 0.15
    minimum_classification_confidence: float = 0.78


WEIGHTS = {
    "customer": 0.30,
    "product": 0.20,
    "business_type": 0.20,
    "project": 0.10,
    "history": 0.10,
    "similarity": 0.05,
    "availability": 0.05,
}


class RoutingPolicy:
    def __init__(self, config: RoutingPolicyConfig | None = None):
        self.config = config or RoutingPolicyConfig()

    def score(
        self,
        *,
        users: list[dict],
        facts: MailFacts,
        classification: MailClassification,
        retrieval: RetrievalContext,
    ) -> RoutingDecision:
        evidence_by_user = self._retrieval_evidence(retrieval)
        candidates: list[RoutingCandidate] = []
        for user in users:
            user_id = UUID(str(user["id"]))
            capabilities = list(user.get("capabilities") or [])
            components = {
                "customer": self._match(capabilities, "customer", [facts.customer_name, *facts.customer_candidates]),
                "product": self._match(capabilities, "product", [*facts.product_names, *facts.product_groups, *facts.part_numbers]),
                "business_type": self._match(capabilities, "business_type", [classification.primary_type, *classification.secondary_types]),
                "project": self._match(capabilities, "project", [*facts.project_numbers, *facts.vessel_names]),
                "history": evidence_by_user.get(str(user_id), {}).get("history", 0.0),
                "similarity": evidence_by_user.get(str(user_id), {}).get("similarity", 0.0),
                "availability": 1.0 if user.get("status") == "active" else 0.0,
            }
            total = round(sum(components[name] * weight for name, weight in WEIGHTS.items()), 4)
            reasons = [f"{name}={value:.2f}" for name, value in components.items() if value > 0]
            candidates.append(RoutingCandidate(user_id=user_id, total_score=total, rank=1, reasons=reasons, component_scores=components))

        candidates.sort(key=lambda item: item.total_score, reverse=True)
        candidates = [item.model_copy(update={"rank": index}) for index, item in enumerate(candidates, start=1)]
        review_reasons: list[str] = []
        if not candidates:
            review_reasons.append("no_active_candidates")
        elif candidates[0].total_score < self.config.auto_assign_threshold:
            review_reasons.append("top_score_below_threshold")
        if len(candidates) > 1 and candidates[0].total_score - candidates[1].total_score < self.config.minimum_margin:
            review_reasons.append("candidate_margin_too_small")
        if classification.confidence < self.config.minimum_classification_confidence:
            review_reasons.append("classification_confidence_too_low")
        if classification.review_required:
            review_reasons.append("classification_review_required")
        if facts.contradictions:
            review_reasons.append("fact_contradictions_present")
        if not (facts.customer_name or facts.customer_candidates or facts.product_names or facts.product_groups or facts.project_numbers):
            review_reasons.append("required_routing_evidence_missing")

        decision = "review_required" if review_reasons else "auto_assign"
        selected = candidates[0].user_id if candidates and decision == "auto_assign" else None
        confidence = candidates[0].total_score if candidates else 0.0
        return RoutingDecision(candidates=candidates[:5], selected_user_id=selected, decision=decision, confidence=confidence, review_reasons=review_reasons)

    @staticmethod
    def _match(capabilities: list[dict], capability_type: str, values: list[str | None]) -> float:
        normalized = {str(value).strip().casefold() for value in values if value and str(value).strip()}
        if not normalized:
            return 0.0
        matches = [cap for cap in capabilities if cap.get("capability_type") == capability_type and str(cap.get("capability_value") or "").strip().casefold() in normalized]
        return 1.0 if matches else 0.0

    @staticmethod
    def _retrieval_evidence(retrieval: RetrievalContext) -> dict[str, dict[str, float]]:
        result: dict[str, dict[str, float]] = {}
        for hit in retrieval.selected_hits:
            user_id = hit.metadata.get("assignee_user_id")
            if not user_id:
                continue
            bucket = result.setdefault(str(user_id), {"history": 0.0, "similarity": 0.0})
            if hit.retriever_type.value == "similar_case":
                bucket["similarity"] = max(bucket["similarity"], hit.retrieval_score)
            else:
                bucket["history"] = max(bucket["history"], hit.retrieval_score)
        return result

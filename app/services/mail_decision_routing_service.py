from __future__ import annotations

import os

from app.agents.decision_agent import DecisionAgentOutput
from app.repositories.postgres_assignee_admin_repository import CATEGORY_BUSINESS_TYPES
from app.repositories.postgres_routing_policy_settings_repository import PostgresRoutingPolicySettingsRepository
from app.repositories.postgres_routing_repository import PostgresRoutingRepository
from app.routing.policy import RoutingPolicy, RoutingPolicyConfig
from app.schemas.mail_decision import MailDecisionNode, MailDecisionRunState, MailDecisionStatus, MailClassification
from app.schemas.retrieval import RetrievalContext
from app.services.mail_decision_runtime_service import MailDecisionRuntimeService
from app.workflows.mail_decision.orchestrator import MailDecisionOrchestrator, NodeHandler


class MailDecisionRoutingService(MailDecisionRuntimeService):
    """Extends the analysis runtime with deterministic candidate scoring and assignment."""

    def __init__(self, repository):
        super().__init__(repository)
        self.routing_repository = PostgresRoutingRepository(
            getattr(repository, "database_url", ""),
            assignment_indexer=getattr(self, "production_case_indexer", None),
        )
        self.routing_policy_settings_repository = PostgresRoutingPolicySettingsRepository(
            getattr(repository, "database_url", "")
        )
        self.routing_policy = RoutingPolicy(
            RoutingPolicyConfig(
                auto_assign_threshold=float(os.getenv("CORAMAIL_AUTO_ASSIGN_THRESHOLD", "0.82")),
                minimum_margin=float(os.getenv("CORAMAIL_ROUTING_MIN_MARGIN", "0.15")),
                minimum_classification_confidence=float(os.getenv("CORAMAIL_CLASSIFICATION_MIN_CONFIDENCE", "0.78")),
            )
        )

    def _orchestrator(self) -> MailDecisionOrchestrator:
        handlers: dict[MailDecisionNode, NodeHandler] = {
            MailDecisionNode.LOAD_MAIL_CONTEXT: self._load_mail_context,
            MailDecisionNode.ANALYZE_ATTACHMENTS: self._analyze_attachments,
            MailDecisionNode.EXTRACT_FACTS: self._extract_facts,
            MailDecisionNode.PLAN_RETRIEVAL: self._plan_retrieval,
            MailDecisionNode.RETRIEVE_CONTEXT: self._retrieve_context,
            MailDecisionNode.EVALUATE_CONTEXT: self._evaluate_context,
            MailDecisionNode.GENERATE_DECISION: self._generate_decision,
            MailDecisionNode.GENERATE_ROUTING_CANDIDATES: self._generate_routing_candidates,
            MailDecisionNode.VALIDATE_DECISION: self._validate_routing_decision,
            MailDecisionNode.PERSIST_RESULT: self._persist_routing_result,
        }
        return MailDecisionOrchestrator(store=self.repository, handlers=handlers)

    def _generate_routing_candidates(self, state: MailDecisionRunState) -> MailDecisionRunState:
        if state.facts is None:
            return self._review(state, "facts_missing_before_routing")
        decision_payload = state.context.get("decision_output")
        retrieval_payload = state.context.get("retrieval_context")
        if not decision_payload or not retrieval_payload:
            return self._review(state, "decision_or_retrieval_missing_before_routing")

        output = DecisionAgentOutput.model_validate(decision_payload)
        classification = MailClassification(
            business_area=output.classification.business_area,
            primary_type=output.classification.primary_type,
            secondary_types=output.classification.secondary_types,
            candidate_scores=output.classification.candidate_scores,
            confidence=output.classification.confidence,
            review_required=output.review_required,
        )
        provider = str((state.context.get("mail") or {}).get("account_provider") or "")
        users = self.routing_repository.load_active_users_with_capabilities(
            include_synthetic=provider == "synthetic"
        )
        state.context["routing_users"] = {
            str(user["id"]): {
                "name": str(user.get("name") or ""),
                "email": str(user.get("email") or ""),
                "department": str((user.get("notification_preferences") or {}).get("department") or ""),
                "position": str((user.get("notification_preferences") or {}).get("position") or ""),
                "areas": _capability_areas(user.get("capabilities") if isinstance(user.get("capabilities"), list) else []),
            }
            for user in users
        }
        routing_policy = RoutingPolicy(self.routing_policy_settings_repository.get().as_config())
        decision = routing_policy.score(
            users=users,
            facts=state.facts,
            classification=classification,
            retrieval=RetrievalContext.model_validate(retrieval_payload),
        )
        self.routing_repository.save_candidates(
            run_id=state.run_id,
            email_message_id=state.email_message_id,
            decision=decision,
        )
        state.context["routing_decision"] = decision.model_dump(mode="json")
        if decision.decision == "review_required":
            self.routing_repository.apply_decision(
                email_message_id=state.email_message_id,
                decision=decision,
            )
            state.context["routing_review_reasons"] = decision.review_reasons
            return self._review(state, "routing_policy_review_required")
        if state.context.get("review_reason") == "attachment_analysis_incomplete":
            warnings = list(state.context.get("non_blocking_warnings") or [])
            warnings.append("attachment_analysis_incomplete")
            state.context["non_blocking_warnings"] = list(dict.fromkeys(warnings))
            state.context.pop("review_reason", None)
        state.status = MailDecisionStatus.AUTO_ASSIGNED
        return state

    def _validate_routing_decision(self, state: MailDecisionRunState) -> MailDecisionRunState:
        payload = state.context.get("routing_decision")
        if not payload:
            return self._review(state, "routing_decision_missing")
        from app.schemas.mail_decision import RoutingDecision

        decision = RoutingDecision.model_validate(payload)
        if decision.decision != "auto_assign" or decision.selected_user_id is None:
            return self._review(state, "routing_decision_not_auto_assignable")
        return state

    def _persist_routing_result(self, state: MailDecisionRunState) -> MailDecisionRunState:
        from app.schemas.mail_decision import RoutingDecision

        decision = RoutingDecision.model_validate(state.context["routing_decision"])
        self.routing_repository.apply_decision(email_message_id=state.email_message_id, decision=decision)
        if decision.decision == "auto_assign" and decision.selected_user_id is not None:
            mail = state.context.get("mail") if isinstance(state.context.get("mail"), dict) else {}
            self.routing_repository.mark_auto_forwarded(
                email_message_id=state.email_message_id,
                assignee_user_id=decision.selected_user_id,
                title=str(mail.get("subject") or "자동 라우팅"),
                body=str(mail.get("body_text") or mail.get("snippet") or ""),
                reason="Demo Mail Decision auto routing forwarded after processing completed.",
            )
        state.context["assigned_user_id"] = str(decision.selected_user_id)
        return state


def _capability_areas(capabilities: list[dict[str, object]]) -> list[str]:
    business_types = {
        str(capability.get("capability_value") or "")
        for capability in capabilities
        if capability.get("capability_type") == "business_type"
    }
    return [
        category
        for category, values in CATEGORY_BUSINESS_TYPES.items()
        if business_types.intersection(values)
    ]

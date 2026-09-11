from __future__ import annotations

from uuid import uuid4

from app.agents.decision_agent import DecisionAgentOutput
from app.repositories.postgres_routing_policy_settings_repository import RoutingPolicySettings
from app.schemas.mail_decision import (
    MailClassification,
    MailDecisionRunState,
    MailDecisionStatus,
    MailFacts,
    MailImportance,
    MailSummary,
    MailUrgency,
)
from app.schemas.retrieval import RetrievalContext
from app.services.mail_decision_routing_service import MailDecisionRoutingService


class FakeRepository:
    database_url = ""


class FakeRoutingRepository:
    def __init__(self):
        self.saved = None

    def load_active_users_with_capabilities(self, *, include_synthetic=True):
        self.include_synthetic = include_synthetic
        user_id = uuid4()
        self.user_id = user_id
        return [
            {
                "id": user_id,
                "status": "active",
                "capabilities": [
                    {"capability_type": "customer", "capability_value": "Acme"},
                    {"capability_type": "product", "capability_value": "Pump"},
                    {"capability_type": "business_type", "capability_value": "repair_request"},
                    {"capability_type": "project", "capability_value": "P-100"},
                ],
            }
        ]

    def save_candidates(self, *, run_id, email_message_id, decision):
        self.saved = decision

    def apply_decision(self, *, email_message_id, decision):
        self.applied = decision

    def mark_auto_forwarded(self, **kwargs):
        self.auto_forwarded = kwargs


class FakeRoutingPolicySettingsRepository:
    def __init__(self, settings):
        self.settings = settings

    def get(self):
        return self.settings


def test_routing_service_uses_nested_decision_classification_fields():
    service = MailDecisionRoutingService(FakeRepository())
    routing_repository = FakeRoutingRepository()
    service.routing_repository = routing_repository
    state = MailDecisionRunState(
        run_id=uuid4(),
        email_message_id=uuid4(),
        workflow_version="test",
        status=MailDecisionStatus.RUNNING,
        facts=MailFacts(
            customer_name="Acme",
            product_groups=["Pump"],
            project_numbers=["P-100"],
            request_types=["repair_request"],
        ),
        context={
            "mail": {"account_provider": "gmail"},
            "decision_output": DecisionAgentOutput(
                summary=MailSummary(one_line_summary="Repair request", confidence=0.84),
                classification=MailClassification(
                    business_area="service",
                    primary_type="repair_request",
                    candidate_scores={"repair_request": 0.84},
                    confidence=0.84,
                ),
                urgency=MailUrgency(level="normal", confidence=0.8),
                importance=MailImportance(level="normal", confidence=0.8),
            ).model_dump(mode="json"),
            "retrieval_context": RetrievalContext(sufficient=True).model_dump(mode="json"),
        },
    )

    result = service._generate_routing_candidates(state)

    assert result.context["routing_decision"]["candidates"]
    assert routing_repository.saved is not None
    assert routing_repository.include_synthetic is False


def test_routing_service_uses_saved_auto_assignment_threshold():
    service = MailDecisionRoutingService(FakeRepository())
    routing_repository = FakeRoutingRepository()
    service.routing_repository = routing_repository
    service.routing_policy_settings_repository = FakeRoutingPolicySettingsRepository(
        RoutingPolicySettings(
            auto_assign_threshold=0.99,
            minimum_margin=0.15,
            minimum_classification_confidence=0.78,
        )
    )
    state = MailDecisionRunState(
        run_id=uuid4(),
        email_message_id=uuid4(),
        workflow_version="test",
        status=MailDecisionStatus.RUNNING,
        facts=MailFacts(
            customer_name="Acme",
            product_groups=["Pump"],
            project_numbers=["P-100"],
            request_types=["repair_request"],
        ),
        context={
            "mail": {"account_provider": "gmail"},
            "decision_output": DecisionAgentOutput(
                summary=MailSummary(one_line_summary="Repair request", confidence=0.95),
                classification=MailClassification(
                    business_area="service",
                    primary_type="repair_request",
                    candidate_scores={"repair_request": 0.95},
                    confidence=0.95,
                ),
                urgency=MailUrgency(level="normal", confidence=0.8),
                importance=MailImportance(level="normal", confidence=0.8),
            ).model_dump(mode="json"),
            "retrieval_context": RetrievalContext(sufficient=True).model_dump(mode="json"),
        },
    )

    result = service._generate_routing_candidates(state)

    assert result.status == MailDecisionStatus.REVIEW_REQUIRED
    assert routing_repository.saved is not None
    assert routing_repository.saved.confidence < 0.99
    assert "top_score_below_threshold" in result.context["routing_review_reasons"]


def test_routing_service_archives_non_blocking_attachment_warning_after_auto_assignment():
    service = MailDecisionRoutingService(FakeRepository())
    routing_repository = FakeRoutingRepository()
    service.routing_repository = routing_repository
    state = MailDecisionRunState(
        run_id=uuid4(),
        email_message_id=uuid4(),
        workflow_version="test",
        status=MailDecisionStatus.RUNNING,
        facts=MailFacts(
            customer_name="Acme",
            product_groups=["Pump"],
            project_numbers=["P-100"],
            request_types=["repair_request"],
        ),
        context={
            "mail": {"account_provider": "synthetic"},
            "review_reason": "attachment_analysis_incomplete",
            "decision_output": DecisionAgentOutput(
                summary=MailSummary(one_line_summary="Repair request", confidence=0.95),
                classification=MailClassification(
                    business_area="service",
                    primary_type="repair_request",
                    candidate_scores={"repair_request": 0.95},
                    confidence=0.95,
                ),
                urgency=MailUrgency(level="normal", confidence=0.8),
                importance=MailImportance(level="normal", confidence=0.8),
            ).model_dump(mode="json"),
            "retrieval_context": RetrievalContext(sufficient=True).model_dump(mode="json"),
        },
    )

    result = service._generate_routing_candidates(state)

    assert result.status == MailDecisionStatus.AUTO_ASSIGNED
    assert "review_reason" not in result.context
    assert result.context["non_blocking_warnings"] == ["attachment_analysis_incomplete"]
    assert routing_repository.include_synthetic is True


def test_routing_service_auto_forwards_auto_assignment():
    service = MailDecisionRoutingService(FakeRepository())
    routing_repository = FakeRoutingRepository()
    service.routing_repository = routing_repository
    state = MailDecisionRunState(
        run_id=uuid4(),
        email_message_id=uuid4(),
        workflow_version="test",
        status=MailDecisionStatus.AUTO_ASSIGNED,
        context={
            "mail": {
                "account_provider": "gmail",
                "subject": "RFQ auto route",
                "body_text": "Please review the attached quotation request.",
            },
            "routing_decision": {
                "decision": "auto_assign",
                "selected_user_id": str(uuid4()),
                "confidence": 1.0,
                "candidates": [],
                "review_reasons": [],
            },
        },
    )

    service._persist_routing_result(state)

    assert routing_repository.applied is not None
    assert routing_repository.auto_forwarded["email_message_id"] == state.email_message_id
    assert routing_repository.auto_forwarded["title"] == "RFQ auto route"
    assert routing_repository.auto_forwarded["body"] == "Please review the attached quotation request."


def test_runtime_retrieval_scope_for_gmail_is_production():
    service = MailDecisionRoutingService(FakeRepository())
    account_id = uuid4()
    state = MailDecisionRunState(
        run_id=uuid4(),
        email_message_id=uuid4(),
        workflow_version="test",
        status=MailDecisionStatus.RUNNING,
        context={"mail": {"account_provider": "gmail", "email_account_id": account_id}},
    )

    scope = service._routing_retrieval_scope(state)

    assert scope.provider == "gmail"
    assert scope.dataset_type == "production"
    assert scope.email_account_id == account_id
    assert scope.allow_synthetic is False
    assert scope.allow_evaluation is False


def test_runtime_retrieval_scope_for_synthetic_defaults_to_demo():
    service = MailDecisionRoutingService(FakeRepository())
    state = MailDecisionRunState(
        run_id=uuid4(),
        email_message_id=uuid4(),
        workflow_version="test",
        status=MailDecisionStatus.RUNNING,
        context={"mail": {"account_provider": "synthetic", "email_account_id": uuid4()}},
    )

    scope = service._routing_retrieval_scope(state)

    assert scope.provider == "synthetic"
    assert scope.dataset_type == "demo"
    assert scope.email_account_id is None
    assert scope.allow_synthetic is True
    assert scope.allow_evaluation is False


def test_runtime_retrieval_scope_can_be_explicit_evaluation(monkeypatch):
    monkeypatch.setenv("CORAMAIL_RETRIEVAL_DATASET_TYPE", "evaluation")
    monkeypatch.setenv("CORAMAIL_RETRIEVAL_DATASET_VERSION", "synthetic-mail-decision-v2-clean")
    service = MailDecisionRoutingService(FakeRepository())
    state = MailDecisionRunState(
        run_id=uuid4(),
        email_message_id=uuid4(),
        workflow_version="test",
        status=MailDecisionStatus.RUNNING,
        context={"mail": {"account_provider": "synthetic"}},
    )

    scope = service._routing_retrieval_scope(state)

    assert scope.purpose == "evaluation"
    assert scope.provider == "synthetic"
    assert scope.dataset_type == "evaluation"
    assert scope.dataset_version == "synthetic-mail-decision-v2-clean"
    assert scope.allow_synthetic is True
    assert scope.allow_evaluation is True

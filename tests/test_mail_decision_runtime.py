from __future__ import annotations

from uuid import uuid4

from app.llm.gateway import LLMGatewayError
from app.schemas.attachment_analysis import AttachmentAnalysisResult, AttachmentAnalysisStatus
from app.schemas.retrieval import RetrievalContext
from app.schemas.mail_decision import MailDecisionRunState, MailDecisionStatus, MailFacts
from app.services.mail_decision_runtime_service import MailDecisionRuntimeService, WORKFLOW_VERSION


class NoopAttachmentAnalysisRepository:
    def save(self, result):
        return None

    def save_evidence(self, run_id, result):
        return None


class NoopFactsRepository:
    def save(self, *, email_message_id, run_id, facts, confidence=None):
        return None


class EmptyRetrievalPlan:
    def model_dump(self, mode="json"):
        return {"queries": []}


class InsufficientRetrievalService:
    def __init__(self):
        self.planner = self

    def plan(self, facts, *, cycle_number):
        return EmptyRetrievalPlan()

    def execute(self, *, run_id, facts, retrieval_scope=None):
        return RetrievalContext(sufficient=False, missing_context=["routing_context"])


class SufficientRetrievalService:
    def __init__(self):
        self.planner = self

    def plan(self, facts, *, cycle_number):
        return EmptyRetrievalPlan()

    def execute(self, *, run_id, facts, retrieval_scope=None):
        return RetrievalContext(sufficient=True, missing_context=[])


class FixedFactAgent:
    def extract(self, *, mail, attachment_results):
        return MailFacts(
            sender_person=mail.get("sender_name"),
            sender_domain="example.invalid",
            missing_information=["llm_fact_extraction", "attachment_source_missing"],
        )


class FakeRepository:
    database_url = ""

    def __init__(self, *, has_attachments: bool):
        self.has_attachments = has_attachments
        self.saved = []
        self.steps = []
        self.state = None

    def create_or_get_active_run(self, *, email_message_id, workflow_version):
        assert workflow_version == WORKFLOW_VERSION
        self.state = MailDecisionRunState(
            run_id=uuid4(),
            email_message_id=email_message_id,
            workflow_version=workflow_version,
            status=MailDecisionStatus.QUEUED,
        )
        return self.state

    def get_run(self, run_id):
        if self.state and self.state.run_id == run_id:
            return self.state
        return None

    def load_email_context(self, email_message_id):
        attachments = []
        if self.has_attachments:
            attachments = [
                {
                    "id": uuid4(),
                    "filename": "purchase-order.pdf",
                    "processing_status": "pending",
                }
            ]
        return {
            "email": {
                "id": email_message_id,
                "sender_name": "Test Buyer",
                "sender_address": "buyer@example.invalid",
                "subject": "Attached purchase order",
                "body_text": "Please review the attached document.",
            },
            "attachments": attachments,
        }

    def save_run(self, state):
        self.state = state
        self.saved.append(state.model_copy(deep=True))

    def start_step(self, state, node):
        self.steps.append((node.value, "running"))

    def complete_step(self, state, node):
        self.steps.append((node.value, "completed"))

    def fail_step(self, state, node, error):
        self.steps.append((node.value, "failed"))


class FailingFactAgent:
    def extract(self, *, mail, attachment_results):
        raise LLMGatewayError("not configured")

    def extract_grounded(self, *, mail, attachment_results, reason):
        return MailFacts(
            sender_person=mail.get("sender_name"),
            sender_domain="example.invalid",
            request_types=["general_inquiry"],
            requested_actions=["메일 내용 확인 후 담당자 검토"],
            missing_information=["llm_fact_extraction_unavailable", reason],
        )


class NoopDecisionRepository:
    def __init__(self):
        self.saved = []

    def save(self, *, email_message_id, output, model_name):
        self.saved.append(output)


class FailingDecisionAgent:
    def decide(self, *, mail, facts, retrieval):
        raise LLMGatewayError("not configured")

    def fallback_decision(self, *, mail, facts, reason):
        from app.agents.decision_agent import DecisionAgent

        return DecisionAgent.fallback_decision(mail=mail, facts=facts, reason=reason)


def test_runtime_skips_document_understanding_when_parser_recovers_fields():
    service = MailDecisionRuntimeService(FakeRepository(has_attachments=False))
    attachment_id = uuid4()

    class Parser:
        def analyze(self, attachment):
            return AttachmentAnalysisResult(
                attachment_id=attachment_id,
                filename="Quotation_QT-2026-0812-03.pdf",
                content_type="application/pdf",
                status=AttachmentAnalysisStatus.COMPLETED,
                document_type="quote",
                extracted_text="QUOTATION\nOur Ref No QT-2026-0812-03",
                fields={"Our Ref No": "QT-2026-0812-03"},
            )

    class Analyzer:
        def enrich(self, result):
            raise AssertionError("parser-recovered fields should not require LLM enrichment")

    saved = []
    service.attachment_dispatcher = Parser()
    service.text_attachment_analyzer = Analyzer()
    service.attachment_repository = type(
        "Repository",
        (),
        {
            "save": lambda _self, result: saved.append(result),
            "save_evidence": lambda _self, _run_id, _result: None,
        },
    )()
    state = MailDecisionRunState(
        run_id=uuid4(),
        email_message_id=uuid4(),
        workflow_version=WORKFLOW_VERSION,
        status=MailDecisionStatus.RUNNING,
        context={"attachments": [{"id": attachment_id, "filename": "Quotation_QT-2026-0812-03.pdf"}]},
    )

    result = service._analyze_attachments(state)

    assert saved[0].fields == {"Our Ref No": "QT-2026-0812-03"}
    assert result.context["attachment_analysis_results"][0]["fields"] == {"Our Ref No": "QT-2026-0812-03"}
    assert result.context.get("attachment_review_reasons", []) == []


def test_runtime_records_attachment_review_and_continues_to_fact_extraction():
    repository = FakeRepository(has_attachments=True)
    service = MailDecisionRuntimeService(repository)
    service.attachment_repository = NoopAttachmentAnalysisRepository()
    service.facts_repository = NoopFactsRepository()
    service.retrieval_service = InsufficientRetrievalService()
    service.fact_agent = FixedFactAgent()
    service.decision_repository = NoopDecisionRepository()
    service.decision_agent = FailingDecisionAgent()

    state = service.create_and_run(uuid4())

    assert state.status == MailDecisionStatus.REVIEW_REQUIRED
    assert state.context["review_reason"] == "decision_review_required"
    assert "retrieval_context_insufficient" in state.context["decision_output"]["review_reasons"]
    assert state.context["attachment_review_reasons"] == ["purchase-order.pdf:failed"]
    assert state.facts is not None
    assert state.facts.sender_domain == "example.invalid"
    assert [node for node, status in repository.steps if status == "running"] == [
        "load_mail_context",
        "analyze_attachments",
        "extract_facts",
        "plan_retrieval",
        "retrieve_context",
        "evaluate_context",
        "generate_decision",
    ]


def test_runtime_persists_review_decision_when_retrieval_is_insufficient():
    repository = FakeRepository(has_attachments=False)
    service = MailDecisionRuntimeService(repository)
    service.fact_agent = FailingFactAgent()
    service.facts_repository = NoopFactsRepository()
    service.retrieval_service = InsufficientRetrievalService()
    service.decision_repository = NoopDecisionRepository()
    service.decision_agent = FailingDecisionAgent()

    state = service.create_and_run(uuid4())

    assert state.status == MailDecisionStatus.REVIEW_REQUIRED
    assert state.context["review_reason"] == "decision_review_required"
    assert state.context["non_blocking_warnings"] == [
        "fact_extraction_gateway_failed",
        "retrieval_context_insufficient",
        "decision_agent_gateway_failed",
    ]
    assert state.context["routing_blockers"] == ["retrieval_context_insufficient"]
    assert state.facts is not None
    assert "llm_fact_extraction_unavailable" in state.facts.missing_information
    assert state.context["decision_output"]["generation_mode"] == "fallback_llm_unavailable"
    assert state.context["decision_output"]["review_required"] is True
    assert "retrieval_context_insufficient" in state.context["decision_output"]["review_reasons"]
    assert service.decision_repository.saved[0].review_required is True


def test_runtime_persists_review_decision_when_decision_llm_is_unavailable():
    repository = FakeRepository(has_attachments=False)
    service = MailDecisionRuntimeService(repository)
    service.fact_agent = FixedFactAgent()
    service.facts_repository = NoopFactsRepository()
    service.retrieval_service = SufficientRetrievalService()
    service.decision_repository = NoopDecisionRepository()
    service.decision_agent = FailingDecisionAgent()

    state = service.create_and_run(uuid4())

    assert state.status == MailDecisionStatus.REVIEW_REQUIRED
    assert state.context["review_reason"] == "decision_review_required"
    assert state.context["non_blocking_warnings"] == ["decision_agent_gateway_failed"]
    assert state.context["decision_output"]["generation_mode"] == "fallback_llm_unavailable"
    assert state.context["decision_output"]["review_required"] is True
    assert service.decision_repository.saved[0].generation_mode == "fallback_llm_unavailable"

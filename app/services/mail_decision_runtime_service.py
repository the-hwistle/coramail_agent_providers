from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

from app.config import (
    database_url,
    embedding_model,
    embedding_base_url,
    embedding_provider,
    llm_base_url,
    llm_max_concurrency,
    llm_max_output_tokens,
    llm_provider,
    qdrant_case_collection,
    qdrant_url,
    text_llm_base_url,
    text_llm_provider,
    text_model,
    vision_llm_base_url,
    vision_llm_provider,
    vision_model,
)
from app.agents.decision_agent import DecisionAgent
from app.agents.fact_extraction_agent import FactExtractionAgent
from app.document_processing.parsers import AttachmentParserDispatcher, resolve_storage_path
from app.document_processing.text_analyzer import TextAttachmentAnalyzer
from app.document_processing.vision_analyzer import VisionAttachmentAnalyzer
from app.llm.gateway import LLMGatewayError, LocalLLMConfig, LocalLLMGateway
from app.repositories.postgres_attachment_analysis_repository import PostgresAttachmentAnalysisRepository
from app.repositories.postgres_decision_result_repository import PostgresDecisionResultRepository
from app.repositories.postgres_mail_decision_repository import PostgresMailDecisionRepository
from app.repositories.postgres_mail_facts_repository import PostgresMailFactsRepository
from app.repositories.postgres_retrieval_repository import PostgresRetrievalRepository
from app.retrieval.qdrant_indexing import ProductionSimilarCaseIndexer, QdrantCaseIndexClient
from app.retrieval.planner import RetrievalPlanner
from app.retrieval.qdrant_client import QdrantConfig, QdrantSimilarCaseRetriever
from app.retrieval.service import AgenticRetrievalService
from app.schemas.attachment_analysis import AttachmentAnalysisResult, AttachmentAnalysisStatus
from app.schemas.mail_decision import MailDecisionNode, MailDecisionRunState, MailDecisionStatus, MailFacts
from app.schemas.retrieval import RetrievalContext, RetrievalScope
from app.workflows.mail_decision.orchestrator import MailDecisionOrchestrator, NodeHandler


WORKFLOW_VERSION = "mail-decision-decision-agent-v1"
PROJECT_DIR = Path(__file__).resolve().parents[2]


class MailDecisionRuntimeService:
    """Runs evidence-grounded analysis through structured decision generation."""

    def __init__(self, repository: PostgresMailDecisionRepository):
        config = LocalLLMConfig(
            base_url=llm_base_url(),
            text_base_url=text_llm_base_url(),
            vision_base_url=vision_llm_base_url(),
            embedding_base_url=embedding_base_url(),
            text_model=text_model(),
            vision_model=vision_model(),
            embedding_model=embedding_model(),
            provider=llm_provider(),
            text_provider=text_llm_provider(),
            vision_provider=vision_llm_provider(),
            embedding_provider=embedding_provider(),
            text_max_concurrency=llm_max_concurrency("text"),
            vision_max_concurrency=llm_max_concurrency("vision"),
            embedding_max_concurrency=llm_max_concurrency("embedding"),
            max_output_tokens=llm_max_output_tokens(),
        )
        db_url = getattr(repository, "database_url", database_url())
        self.repository = repository
        self.attachment_dispatcher = AttachmentParserDispatcher(PROJECT_DIR)
        self.attachment_repository = PostgresAttachmentAnalysisRepository(db_url)
        self.facts_repository = PostgresMailFactsRepository(db_url)
        self.decision_repository = PostgresDecisionResultRepository(db_url)
        self.llm_gateway = LocalLLMGateway(config)
        self.vision_analyzer = VisionAttachmentAnalyzer(self.llm_gateway)
        self.text_attachment_analyzer = TextAttachmentAnalyzer(self.llm_gateway)
        self.fact_agent = FactExtractionAgent(self.llm_gateway)
        self.decision_agent = DecisionAgent(self.llm_gateway)
        self.production_case_indexer = ProductionSimilarCaseIndexer(
            database_url=db_url,
            qdrant_client=QdrantCaseIndexClient(base_url=qdrant_url(), collection=qdrant_case_collection()),
            embedder=self.llm_gateway.embed,
            embedding_model=embedding_model(),
        )
        self.retrieval_service = AgenticRetrievalService(
            planner=RetrievalPlanner(),
            postgres=PostgresRetrievalRepository(db_url),
            qdrant=QdrantSimilarCaseRetriever(
                self.llm_gateway,
                QdrantConfig(
                    base_url=qdrant_url(),
                    collection=qdrant_case_collection(),
                ),
            ),
            max_cycles=int(os.getenv("CORAMAIL_RETRIEVAL_MAX_CYCLES", "3")),
            prompt_hit_limit=int(os.getenv("CORAMAIL_RETRIEVAL_PROMPT_LIMIT", "6")),
        )

    def create_and_run(self, email_message_id: UUID) -> MailDecisionRunState:
        state = self.repository.create_or_get_active_run(
            email_message_id=email_message_id,
            workflow_version=WORKFLOW_VERSION,
        )
        if state.status == MailDecisionStatus.REVIEW_REQUIRED:
            state.status = MailDecisionStatus.QUEUED
            state.current_node = None
            state.context = {}
            state.facts = None
            state.result = None
            state.completed_at = None
            self.repository.save_run(state)
        return self._orchestrator().run(state)

    def resume(self, run_id: UUID) -> MailDecisionRunState:
        state = self.repository.get_run(run_id)
        if state is None:
            raise LookupError(f"mail decision run not found: {run_id}")
        if state.status == MailDecisionStatus.COMPLETED:
            return state
        if state.status in {MailDecisionStatus.FAILED, MailDecisionStatus.REVIEW_REQUIRED}:
            state.status = MailDecisionStatus.QUEUED
        return self._orchestrator().run(state)

    def _orchestrator(self) -> MailDecisionOrchestrator:
        handlers: dict[MailDecisionNode, NodeHandler] = {
            MailDecisionNode.LOAD_MAIL_CONTEXT: self._load_mail_context,
            MailDecisionNode.ANALYZE_ATTACHMENTS: self._analyze_attachments,
            MailDecisionNode.EXTRACT_FACTS: self._extract_facts,
            MailDecisionNode.PLAN_RETRIEVAL: self._plan_retrieval,
            MailDecisionNode.RETRIEVE_CONTEXT: self._retrieve_context,
            MailDecisionNode.EVALUATE_CONTEXT: self._evaluate_context,
            MailDecisionNode.GENERATE_DECISION: self._generate_decision,
            MailDecisionNode.GENERATE_ROUTING_CANDIDATES: self._not_available("routing_not_connected"),
            MailDecisionNode.VALIDATE_DECISION: self._not_available("validation_not_connected"),
            MailDecisionNode.PERSIST_RESULT: self._not_available("result_persistence_not_connected"),
        }
        return MailDecisionOrchestrator(store=self.repository, handlers=handlers)

    def _load_mail_context(self, state: MailDecisionRunState) -> MailDecisionRunState:
        context = self.repository.load_email_context(state.email_message_id)
        state.context["mail"] = context["email"]
        state.context["attachments"] = context["attachments"]
        sender_address = str(context["email"].get("sender_address") or "")
        state.facts = MailFacts(
            sender_person=context["email"].get("sender_name"),
            sender_domain=sender_address.rsplit("@", 1)[-1].lower() if "@" in sender_address else None,
            missing_information=["llm_fact_extraction", "routing_context"],
        )
        return state

    def _analyze_attachments(self, state: MailDecisionRunState) -> MailDecisionRunState:
        results: list[AttachmentAnalysisResult] = []
        blocking: list[str] = []
        for attachment in list(state.context.get("attachments") or []):
            result = self.attachment_dispatcher.analyze(attachment)
            needs_vision = "vision_analysis_required" in result.warnings or any(
                warning.endswith("requires_vision_or_ocr") for warning in result.warnings
            )
            if needs_vision:
                try:
                    result = self._run_vision(attachment, result)
                except LLMGatewayError as exc:
                    result.warnings.append("vision_gateway_failed")
                    result.error_message = str(exc)
                    result.status = AttachmentAnalysisStatus.PARTIAL_SUCCESS
            if result.extracted_text.strip() and (result.document_html.strip() or not result.fields):
                try:
                    result = self.text_attachment_analyzer.enrich(result)
                except LLMGatewayError as exc:
                    result.warnings.append("document_understanding_gateway_failed")
                    result.error_message = str(exc)
                    result.status = AttachmentAnalysisStatus.PARTIAL_SUCCESS
            self.attachment_repository.save(result)
            self.attachment_repository.save_evidence(state.run_id, result)
            results.append(result)
            if result.status in {AttachmentAnalysisStatus.FAILED, AttachmentAnalysisStatus.UNSUPPORTED}:
                blocking.append(f"{result.filename}:{result.status.value}")
            if result.status == AttachmentAnalysisStatus.PARTIAL_SUCCESS and not result.extracted_text.strip():
                blocking.append(f"{result.filename}:content_unavailable")
        state.context["attachment_analysis_results"] = [result.model_dump(mode="json") for result in results]
        if blocking:
            state.context["review_reason"] = "attachment_analysis_incomplete"
            state.context["attachment_review_reasons"] = blocking
        return state

    def _run_vision(self, attachment: dict, parsed: AttachmentAnalysisResult) -> AttachmentAnalysisResult:
        path = resolve_storage_path(str(attachment.get("storage_uri") or ""), PROJECT_DIR)
        content_type = str(attachment.get("content_type") or parsed.content_type)
        if content_type.startswith("image/"):
            return self.vision_analyzer.analyze_image(
                attachment_id=parsed.attachment_id, filename=parsed.filename, content_type=content_type, path=path
            )
        if content_type == "application/pdf" or path.suffix.lower() == ".pdf":
            return self.vision_analyzer.analyze_pdf_pages(
                attachment_id=parsed.attachment_id,
                filename=parsed.filename,
                content_type=content_type,
                path=path,
                existing_pages=parsed.pages,
            )
        return parsed

    def _extract_facts(self, state: MailDecisionRunState) -> MailDecisionRunState:
        try:
            facts = self.fact_agent.extract(
                mail=dict(state.context.get("mail") or {}),
                attachment_results=list(state.context.get("attachment_analysis_results") or []),
            )
        except LLMGatewayError as exc:
            state.context.setdefault("non_blocking_warnings", []).append("fact_extraction_gateway_failed")
            state.context["fact_extraction_error"] = str(exc)
            facts = self.fact_agent.extract_grounded(
                mail=dict(state.context.get("mail") or {}),
                attachment_results=list(state.context.get("attachment_analysis_results") or []),
                reason="fact_extraction_gateway_failed",
            )
        facts.missing_information = [item for item in facts.missing_information if item != "llm_fact_extraction"]
        state.facts = facts
        self.facts_repository.save(
            email_message_id=state.email_message_id,
            run_id=state.run_id,
            facts=facts,
            confidence=self._fact_confidence(facts),
        )
        return state

    def _plan_retrieval(self, state: MailDecisionRunState) -> MailDecisionRunState:
        if state.facts is None:
            return self._review(state, "facts_missing_before_retrieval")
        state.context["retrieval_plan"] = self.retrieval_service.planner.plan(
            state.facts, cycle_number=1
        ).model_dump(mode="json")
        return state

    def _retrieve_context(self, state: MailDecisionRunState) -> MailDecisionRunState:
        if state.facts is None:
            return self._review(state, "facts_missing_before_retrieval")
        retrieval_scope = self._routing_retrieval_scope(state)
        state.context["retrieval_scope"] = retrieval_scope.model_dump(mode="json")
        context = self.retrieval_service.execute(
            run_id=state.run_id,
            facts=state.facts,
            retrieval_scope=retrieval_scope,
        )
        state.retrieval_cycle = len(context.cycles)
        state.context["retrieval_context"] = context.model_dump(mode="json")
        return state

    def _routing_retrieval_scope(self, state: MailDecisionRunState) -> RetrievalScope:
        mail = dict(state.context.get("mail") or {})
        provider = str(mail.get("account_provider") or "").strip().casefold()
        configured_dataset_type = os.getenv("CORAMAIL_RETRIEVAL_DATASET_TYPE", "").strip().casefold()
        dataset_version = os.getenv("CORAMAIL_RETRIEVAL_DATASET_VERSION", "").strip() or None
        if configured_dataset_type in {"production", "demo", "evaluation", "development"}:
            dataset_type = configured_dataset_type
        elif provider == "synthetic":
            dataset_type = "demo"
        else:
            dataset_type = "production"
        allow_evaluation = dataset_type == "evaluation"
        allow_synthetic = provider == "synthetic" or dataset_type in {"demo", "evaluation", "development"}
        account_id = mail.get("email_account_id") if dataset_type == "production" else None
        return RetrievalScope(
            purpose="assignment_routing" if dataset_type != "evaluation" else "evaluation",
            provider=provider or "unknown",
            dataset_type=dataset_type,  # type: ignore[arg-type]
            email_account_id=account_id,
            dataset_version=dataset_version,
            allow_synthetic=allow_synthetic,
            allow_evaluation=allow_evaluation,
        )

    def _evaluate_context(self, state: MailDecisionRunState) -> MailDecisionRunState:
        payload = state.context.get("retrieval_context")
        if not payload:
            return self._review(state, "retrieval_context_missing")
        context = RetrievalContext.model_validate(payload)
        if not context.sufficient:
            state.context["retrieval_missing_context"] = context.missing_context
            warnings = list(state.context.get("non_blocking_warnings") or [])
            warnings.append("retrieval_context_insufficient")
            state.context["non_blocking_warnings"] = list(dict.fromkeys(warnings))
            state.context["routing_blockers"] = list(
                dict.fromkeys([*(state.context.get("routing_blockers") or []), "retrieval_context_insufficient"])
            )
            return state
        if state.facts is not None:
            state.facts.missing_information = [item for item in state.facts.missing_information if item != "routing_context"]
        return state

    def _generate_decision(self, state: MailDecisionRunState) -> MailDecisionRunState:
        if state.facts is None:
            return self._review(state, "facts_missing_before_decision")
        retrieval_payload = state.context.get("retrieval_context")
        if not retrieval_payload:
            return self._review(state, "retrieval_context_missing_before_decision")
        try:
            output = self.decision_agent.decide(
                mail=dict(state.context.get("mail") or {}),
                facts=state.facts,
                retrieval=RetrievalContext.model_validate(retrieval_payload),
            )
        except LLMGatewayError as exc:
            state.context.setdefault("non_blocking_warnings", []).append("decision_agent_gateway_failed")
            state.context["decision_error"] = str(exc)
            output = self.decision_agent.fallback_decision(
                mail=dict(state.context.get("mail") or {}),
                facts=state.facts,
                reason="decision_agent_gateway_failed",
            )
        if "retrieval_context_insufficient" in (state.context.get("routing_blockers") or []):
            output.review_required = True
            output.review_reasons = list(
                dict.fromkeys([*output.review_reasons, "retrieval_context_insufficient"])
            )
            output.classification.review_required = True
        self.decision_repository.save(
            email_message_id=state.email_message_id,
            output=output,
            model_name=self.llm_gateway.config.text_model,
        )
        state.context["decision_output"] = output.model_dump(mode="json")
        if output.review_required:
            state.context["decision_review_reasons"] = output.review_reasons
            state.context["review_reason"] = "decision_review_required"
            state.status = MailDecisionStatus.REVIEW_REQUIRED
        return state

    @staticmethod
    def _fact_confidence(facts: MailFacts) -> float:
        penalty = min(0.6, 0.08 * len(facts.missing_information) + 0.12 * len(facts.contradictions))
        return round(max(0.0, 0.9 - penalty), 4)

    @staticmethod
    def _review(state: MailDecisionRunState, reason: str) -> MailDecisionRunState:
        state.context["review_reason"] = reason
        state.status = MailDecisionStatus.REVIEW_REQUIRED
        return state

    @staticmethod
    def _not_available(reason: str) -> Callable[[MailDecisionRunState], MailDecisionRunState]:
        def handler(state: MailDecisionRunState) -> MailDecisionRunState:
            return MailDecisionRuntimeService._review(state, reason)

        return handler

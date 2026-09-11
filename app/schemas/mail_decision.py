from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

PrimaryMailType = Literal[
    "quotation_request",
    "quotation_followup",
    "purchase_order",
    "order_change",
    "order_cancellation",
    "delivery_confirmation",
    "delivery_delay",
    "technical_inquiry",
    "drawing_review",
    "specification_review",
    "compatibility_check",
    "service_request",
    "repair_request",
    "claim",
    "urgent_failure",
    "invoice",
    "payment_inquiry",
    "certificate_request",
    "general_inquiry",
    "spam",
]

AttentionQuadrant = Literal["urgent_important", "urgent", "important", "normal"]


class MailDecisionStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    REVIEW_REQUIRED = "review_required"
    AUTO_ASSIGNED = "auto_assigned"
    COMPLETED = "completed"
    FAILED = "failed"


class MailDecisionNode(str, Enum):
    LOAD_MAIL_CONTEXT = "load_mail_context"
    ANALYZE_ATTACHMENTS = "analyze_attachments"
    EXTRACT_FACTS = "extract_facts"
    PLAN_RETRIEVAL = "plan_retrieval"
    RETRIEVE_CONTEXT = "retrieve_context"
    EVALUATE_CONTEXT = "evaluate_context"
    GENERATE_DECISION = "generate_decision"
    GENERATE_ROUTING_CANDIDATES = "generate_routing_candidates"
    VALIDATE_DECISION = "validate_decision"
    PERSIST_RESULT = "persist_result"


class EvidenceRef(BaseModel):
    evidence_id: UUID | None = None
    source_type: Literal["email_body", "attachment", "retrieval"]
    source_id: UUID | None = None
    attachment_id: UUID | None = None
    page_number: int | None = Field(default=None, ge=1)
    text: str = Field(min_length=1)
    bbox: list[float] | None = None


class MailFacts(BaseModel):
    sender_company: str | None = None
    sender_person: str | None = None
    sender_domain: str | None = None
    customer_name: str | None = None
    customer_candidates: list[str] = Field(default_factory=list)
    request_types: list[str] = Field(default_factory=list)
    requested_actions: list[str] = Field(default_factory=list)
    product_names: list[str] = Field(default_factory=list)
    product_groups: list[str] = Field(default_factory=list)
    part_numbers: list[str] = Field(default_factory=list)
    po_numbers: list[str] = Field(default_factory=list)
    quotation_numbers: list[str] = Field(default_factory=list)
    project_numbers: list[str] = Field(default_factory=list)
    vessel_names: list[str] = Field(default_factory=list)
    requested_dates: list[str] = Field(default_factory=list)
    urgency_signals: list[str] = Field(default_factory=list)
    importance_signals: list[str] = Field(default_factory=list)
    claim_signals: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)


class MailSummary(BaseModel):
    one_line_summary: str = Field(min_length=1)
    requester: str | None = None
    requested_actions: list[str] = Field(default_factory=list)
    key_facts: list[str] = Field(default_factory=list)
    deadlines: list[str] = Field(default_factory=list)
    business_refs: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class MailClassification(BaseModel):
    business_area: Literal["sales", "order", "technical", "service", "finance", "general"]
    primary_type: PrimaryMailType
    secondary_types: list[str] = Field(default_factory=list)
    candidate_scores: dict[str, float] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[UUID] = Field(default_factory=list)
    review_required: bool = False

    @model_validator(mode="after")
    def validate_scores(self) -> MailClassification:
        invalid = [name for name, score in self.candidate_scores.items() if not 0 <= score <= 1]
        if invalid:
            raise ValueError(f"candidate scores must be between 0 and 1: {invalid}")
        return self


class MailUrgency(BaseModel):
    level: Literal["high", "normal"]
    confidence: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)


class MailImportance(BaseModel):
    level: Literal["high", "normal"]
    confidence: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)


def attention_quadrant_for(urgency: MailUrgency, importance: MailImportance) -> AttentionQuadrant:
    urgent = urgency.level == "high"
    important = importance.level == "high"
    if urgent and important:
        return "urgent_important"
    if urgent:
        return "urgent"
    if important:
        return "important"
    return "normal"


class RoutingCandidate(BaseModel):
    user_id: UUID
    total_score: float = Field(ge=0, le=1)
    rank: int = Field(ge=1)
    reasons: list[str] = Field(default_factory=list)
    component_scores: dict[str, float] = Field(default_factory=dict)


class RoutingDecision(BaseModel):
    candidates: list[RoutingCandidate] = Field(default_factory=list)
    selected_user_id: UUID | None = None
    decision: Literal["auto_assign", "review_required"]
    confidence: float = Field(ge=0, le=1)
    review_reasons: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    valid: bool
    contradictions: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    missing_required_evidence: list[str] = Field(default_factory=list)
    routing_conflict: bool = False
    recommendation: Literal["auto_assign", "review_required"]


class MailDecisionResult(BaseModel):
    summary: MailSummary
    classification: MailClassification
    urgency: MailUrgency
    importance: MailImportance
    attention_quadrant: AttentionQuadrant
    facts: MailFacts
    routing: RoutingDecision
    validation: ValidationResult


class MailDecisionRunState(BaseModel):
    run_id: UUID
    email_message_id: UUID
    workflow_version: str
    status: MailDecisionStatus
    current_node: MailDecisionNode | None = None
    retrieval_cycle: int = Field(default=0, ge=0, le=3)
    context: dict[str, Any] = Field(default_factory=dict)
    facts: MailFacts | None = None
    result: MailDecisionResult | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

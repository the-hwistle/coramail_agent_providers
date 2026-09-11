from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class RetrieverType(str, Enum):
    EXACT = "exact"
    ROUTING_RULE = "routing_rule"
    SIMILAR_CASE = "similar_case"
    ASSIGNEE_CAPABILITY = "assignee_capability"


class AssignmentEvidenceType(str, Enum):
    EXACT_HISTORY = "exact_history"
    ROUTING_RULE = "routing_rule"
    ASSIGNEE_CAPABILITY = "assignee_capability"
    SIMILAR_CASE = "similar_case"


class RetrievalQuery(BaseModel):
    purpose: str = Field(min_length=1)
    retriever_type: RetrieverType
    query_text: str = Field(min_length=1)
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=5, ge=1, le=20)


class RetrievalScope(BaseModel):
    """Mandatory source boundary for Qdrant-backed retrieval."""

    purpose: Literal["assignment_routing", "demo_search", "evaluation"] = "assignment_routing"
    provider: str = Field(min_length=1)
    dataset_type: Literal["production", "demo", "evaluation", "development"]
    email_account_id: UUID | None = None
    dataset_version: str | None = None
    allow_synthetic: bool = False
    allow_evaluation: bool = False


class RetrievalPlan(BaseModel):
    cycle_number: int = Field(ge=1, le=3)
    queries: list[RetrievalQuery] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)


class RetrievalHit(BaseModel):
    retriever_type: RetrieverType
    source_type: str
    source_id: UUID | None = None
    title: str = ""
    content: str = ""
    retrieval_score: float = Field(default=0.0, ge=0, le=1)
    rerank_score: float | None = Field(default=None, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    included_in_prompt: bool = False


class RetrievalCycleResult(BaseModel):
    cycle_number: int = Field(ge=1, le=3)
    plan: RetrievalPlan
    hits: list[RetrievalHit] = Field(default_factory=list)
    sufficient: bool = False
    missing_context: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class RetrievalContext(BaseModel):
    cycles: list[RetrievalCycleResult] = Field(default_factory=list)
    selected_hits: list[RetrievalHit] = Field(default_factory=list)
    sufficient: bool = False
    missing_context: list[str] = Field(default_factory=list)


class AssignmentEvidence(BaseModel):
    evidence_type: AssignmentEvidenceType
    assignee_user_id: UUID | None = None
    retriever_type: RetrieverType
    source_type: str
    source_id: UUID | None = None
    title: str = ""
    content: str = ""
    score: float = Field(default=0.0, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    confirmed: bool | None = None
    observed_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssignmentCandidateContext(BaseModel):
    assignee_user_id: UUID
    evidence: list[AssignmentEvidence] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    strongest_score: float = Field(default=0.0, ge=0, le=1)
    strongest_evidence_type: AssignmentEvidenceType | None = None
    has_confirmed_evidence: bool = False
    observed_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class AssignmentContext(BaseModel):
    selected_hits: list[RetrievalHit] = Field(default_factory=list)
    evidence: list[AssignmentEvidence] = Field(default_factory=list)
    candidate_contexts: list[AssignmentCandidateContext] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    context_version: str = "assignment-context-v1"

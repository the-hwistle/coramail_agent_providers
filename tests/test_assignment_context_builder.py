from __future__ import annotations

from uuid import uuid4

from app.retrieval.assignment_context import AssignmentContextBuilder
from app.schemas.retrieval import (
    AssignmentEvidenceType,
    RetrievalContext,
    RetrievalHit,
    RetrieverType,
)


def _hit(
    retriever_type: RetrieverType,
    *,
    assignee_user_id: str | None = None,
    source_id=None,
    score: float = 0.8,
    metadata: dict | None = None,
) -> RetrievalHit:
    payload = dict(metadata or {})
    if assignee_user_id is not None:
        payload["assignee_user_id"] = assignee_user_id
    return RetrievalHit(
        retriever_type=retriever_type,
        source_type={
            RetrieverType.EXACT: "email_message",
            RetrieverType.ROUTING_RULE: "routing_rule",
            RetrieverType.ASSIGNEE_CAPABILITY: "assignee_capability",
            RetrieverType.SIMILAR_CASE: "similar_email_case",
        }[retriever_type],
        source_id=source_id or uuid4(),
        title=f"{retriever_type.value} title",
        content=f"{retriever_type.value} content",
        retrieval_score=score,
        metadata=payload,
    )


def _build(*hits: RetrievalHit):
    return AssignmentContextBuilder().build(
        RetrievalContext(selected_hits=list(hits), sufficient=True)
    )


def test_routing_rule_hit_becomes_routing_rule_evidence():
    user_id = uuid4()
    context = _build(_hit(RetrieverType.ROUTING_RULE, assignee_user_id=str(user_id)))

    assert context.evidence[0].evidence_type == AssignmentEvidenceType.ROUTING_RULE
    assert context.evidence[0].assignee_user_id == user_id
    assert context.evidence[0].confirmed is True


def test_assignee_capability_hit_becomes_capability_evidence():
    user_id = uuid4()
    context = _build(_hit(RetrieverType.ASSIGNEE_CAPABILITY, assignee_user_id=str(user_id)))

    assert context.evidence[0].evidence_type == AssignmentEvidenceType.ASSIGNEE_CAPABILITY
    assert context.candidate_contexts[0].assignee_user_id == user_id


def test_similar_case_hit_becomes_similar_case_evidence():
    user_id = uuid4()
    context = _build(
        _hit(
            RetrieverType.SIMILAR_CASE,
            assignee_user_id=str(user_id),
            metadata={"assignment_confirmed": True},
        )
    )

    assert context.evidence[0].evidence_type == AssignmentEvidenceType.SIMILAR_CASE
    assert context.evidence[0].confirmed is True


def test_same_assignee_multiple_evidence_groups_into_one_candidate_context():
    user_id = uuid4()
    context = _build(
        _hit(RetrieverType.ROUTING_RULE, assignee_user_id=str(user_id), score=0.7),
        _hit(RetrieverType.ASSIGNEE_CAPABILITY, assignee_user_id=str(user_id), score=0.9),
    )

    assert len(context.candidate_contexts) == 1
    assert context.candidate_contexts[0].assignee_user_id == user_id
    assert len(context.candidate_contexts[0].evidence) == 2
    assert context.candidate_contexts[0].strongest_score == 0.9


def test_different_assignees_create_separate_candidate_contexts():
    first = uuid4()
    second = uuid4()
    context = _build(
        _hit(RetrieverType.ROUTING_RULE, assignee_user_id=str(first)),
        _hit(RetrieverType.ASSIGNEE_CAPABILITY, assignee_user_id=str(second)),
    )

    assert {item.assignee_user_id for item in context.candidate_contexts} == {first, second}


def test_duplicate_candidate_evidence_is_deduped():
    user_id = uuid4()
    source_id = uuid4()
    first = _hit(RetrieverType.ROUTING_RULE, assignee_user_id=str(user_id), source_id=source_id)
    duplicate = first.model_copy(deep=True)

    context = _build(first, duplicate)

    assert len(context.evidence) == 1
    assert len(context.candidate_contexts[0].evidence) == 1


def test_hit_without_assignee_does_not_create_candidate_context():
    context = _build(_hit(RetrieverType.EXACT))

    assert len(context.evidence) == 1
    assert context.evidence[0].assignee_user_id is None
    assert context.candidate_contexts == []
    assert "assignee_linked_evidence_missing" in context.missing_context


def test_malformed_assignee_metadata_warns_without_crashing():
    context = _build(_hit(RetrieverType.SIMILAR_CASE, assignee_user_id="not-a-uuid"))

    assert context.evidence[0].assignee_user_id is None
    assert "malformed_assignee_user_id" in context.warnings


def test_empty_selected_hits_returns_valid_empty_assignment_context():
    context = AssignmentContextBuilder().build(RetrievalContext())

    assert context.selected_hits == []
    assert context.evidence == []
    assert context.candidate_contexts == []
    assert "selected_hits_empty" in context.missing_context


def test_builder_does_not_mutate_existing_retrieval_hit():
    user_id = uuid4()
    hit = _hit(RetrieverType.SIMILAR_CASE, assignee_user_id=str(user_id))
    before = hit.model_dump(mode="json")

    AssignmentContextBuilder().build(RetrievalContext(selected_hits=[hit]))

    assert hit.model_dump(mode="json") == before

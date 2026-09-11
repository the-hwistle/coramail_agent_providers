from __future__ import annotations

from uuid import uuid4

import pytest

from app.schemas.mail_decision import (
    MailClassification,
    MailDecisionNode,
    MailDecisionRunState,
    MailDecisionStatus,
    MailImportance,
    MailUrgency,
    attention_quadrant_for,
)
from app.workflows.mail_decision.orchestrator import DEFAULT_SEQUENCE, MailDecisionOrchestrator


class MemoryStore:
    def __init__(self) -> None:
        self.saved: list[MailDecisionRunState] = []
        self.started: list[MailDecisionNode] = []
        self.completed: list[MailDecisionNode] = []
        self.failed: list[MailDecisionNode] = []

    def save_run(self, state: MailDecisionRunState) -> None:
        self.saved.append(state.model_copy(deep=True))

    def start_step(self, state: MailDecisionRunState, node: MailDecisionNode) -> None:
        self.started.append(node)

    def complete_step(self, state: MailDecisionRunState, node: MailDecisionNode) -> None:
        self.completed.append(node)

    def fail_step(self, state: MailDecisionRunState, node: MailDecisionNode, error: Exception) -> None:
        self.failed.append(node)


def _state() -> MailDecisionRunState:
    return MailDecisionRunState(
        run_id=uuid4(),
        email_message_id=uuid4(),
        workflow_version="mail-decision-v1",
        status=MailDecisionStatus.QUEUED,
    )


def test_orchestrator_runs_nodes_in_order() -> None:
    store = MemoryStore()
    handlers = {node: (lambda state: state) for node in DEFAULT_SEQUENCE}

    result = MailDecisionOrchestrator(store=store, handlers=handlers).run(_state())

    assert result.status == MailDecisionStatus.COMPLETED
    assert result.current_node is None
    assert store.started == list(DEFAULT_SEQUENCE)
    assert store.completed == list(DEFAULT_SEQUENCE)
    assert store.failed == []


def test_orchestrator_stops_for_human_review() -> None:
    store = MemoryStore()

    def handler(node: MailDecisionNode):
        def run(state: MailDecisionRunState) -> MailDecisionRunState:
            if node == MailDecisionNode.VALIDATE_DECISION:
                state.status = MailDecisionStatus.REVIEW_REQUIRED
            return state

        return run

    handlers = {node: handler(node) for node in DEFAULT_SEQUENCE}
    result = MailDecisionOrchestrator(store=store, handlers=handlers).run(_state())

    assert result.status == MailDecisionStatus.REVIEW_REQUIRED
    assert result.current_node == MailDecisionNode.VALIDATE_DECISION
    assert MailDecisionNode.PERSIST_RESULT not in store.started


def test_orchestrator_records_failed_node() -> None:
    store = MemoryStore()

    def handler(node: MailDecisionNode):
        def run(state: MailDecisionRunState) -> MailDecisionRunState:
            if node == MailDecisionNode.EXTRACT_FACTS:
                raise RuntimeError("fact extraction failed")
            return state

        return run

    handlers = {node: handler(node) for node in DEFAULT_SEQUENCE}

    with pytest.raises(RuntimeError, match="fact extraction failed"):
        MailDecisionOrchestrator(store=store, handlers=handlers).run(_state())

    assert store.failed == [MailDecisionNode.EXTRACT_FACTS]
    assert store.saved[-1].status == MailDecisionStatus.FAILED


def test_classification_rejects_invalid_candidate_score() -> None:
    with pytest.raises(ValueError, match="candidate scores"):
        MailClassification(
            business_area="order",
            primary_type="purchase_order",
            candidate_scores={"purchase_order": 1.2},
            confidence=0.9,
        )


def test_attention_quadrant_is_deterministic_from_urgency_and_importance() -> None:
    assert attention_quadrant_for(
        MailUrgency(level="high", confidence=0.9),
        MailImportance(level="high", confidence=0.9),
    ) == "urgent_important"
    assert attention_quadrant_for(
        MailUrgency(level="high", confidence=0.9),
        MailImportance(level="normal", confidence=0.9),
    ) == "urgent"
    assert attention_quadrant_for(
        MailUrgency(level="normal", confidence=0.9),
        MailImportance(level="high", confidence=0.9),
    ) == "important"

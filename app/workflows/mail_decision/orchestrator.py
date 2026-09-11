from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.schemas.mail_decision import MailDecisionNode, MailDecisionRunState, MailDecisionStatus


class MailDecisionStateStore(Protocol):
    def save_run(self, state: MailDecisionRunState) -> None: ...
    def start_step(self, state: MailDecisionRunState, node: MailDecisionNode) -> None: ...
    def complete_step(self, state: MailDecisionRunState, node: MailDecisionNode) -> None: ...
    def fail_step(self, state: MailDecisionRunState, node: MailDecisionNode, error: Exception) -> None: ...


NodeHandler = Callable[[MailDecisionRunState], MailDecisionRunState]


@dataclass(frozen=True)
class WorkflowNode:
    name: MailDecisionNode
    handler: NodeHandler


DEFAULT_SEQUENCE = (
    MailDecisionNode.LOAD_MAIL_CONTEXT,
    MailDecisionNode.ANALYZE_ATTACHMENTS,
    MailDecisionNode.EXTRACT_FACTS,
    MailDecisionNode.PLAN_RETRIEVAL,
    MailDecisionNode.RETRIEVE_CONTEXT,
    MailDecisionNode.EVALUATE_CONTEXT,
    MailDecisionNode.GENERATE_DECISION,
    MailDecisionNode.GENERATE_ROUTING_CANDIDATES,
    MailDecisionNode.VALIDATE_DECISION,
    MailDecisionNode.PERSIST_RESULT,
)


class MailDecisionOrchestrator:
    """Deterministic state machine; reasoning belongs inside bounded node handlers."""

    def __init__(self, *, store: MailDecisionStateStore, handlers: dict[MailDecisionNode, NodeHandler]):
        missing = [node.value for node in DEFAULT_SEQUENCE if node not in handlers]
        if missing:
            raise ValueError(f"missing mail decision handlers: {missing}")
        self.store = store
        self.handlers = handlers

    def run(self, state: MailDecisionRunState) -> MailDecisionRunState:
        state.status = MailDecisionStatus.RUNNING
        self.store.save_run(state)

        try:
            start_index = self._start_index(state.current_node)
            for node in DEFAULT_SEQUENCE[start_index:]:
                state.current_node = node
                self.store.start_step(state, node)
                try:
                    state = self.handlers[node](state)
                except Exception as exc:
                    self.store.fail_step(state, node, exc)
                    raise
                self.store.complete_step(state, node)
                self.store.save_run(state)

                if state.status == MailDecisionStatus.REVIEW_REQUIRED:
                    return state

            state.status = MailDecisionStatus.COMPLETED
            state.current_node = None
            self.store.save_run(state)
            return state
        except Exception:
            state.status = MailDecisionStatus.FAILED
            self.store.save_run(state)
            raise

    @staticmethod
    def _start_index(current_node: MailDecisionNode | None) -> int:
        if current_node is None:
            return 0
        try:
            return DEFAULT_SEQUENCE.index(current_node)
        except ValueError as exc:
            raise ValueError(f"unknown workflow node: {current_node}") from exc

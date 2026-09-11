from __future__ import annotations

from uuid import uuid4

from app.llm.gateway import LLMGatewayError
from app.retrieval.planner import RetrievalPlanner
from app.retrieval.service import AgenticRetrievalService
from app.schemas.mail_decision import MailFacts
from app.schemas.retrieval import RetrievalHit, RetrievalScope, RetrieverType


class FakePostgres:
    database_url = ""

    def __init__(self):
        self.traces = []

    def exact_search(self, query):
        return []

    def routing_rule_search(self, query):
        return []

    def capability_search(self, query):
        return [
            RetrievalHit(
                retriever_type=RetrieverType.ASSIGNEE_CAPABILITY,
                source_type="assignee_capability",
                source_id=uuid4(),
                title="담당자 역량",
                content=query.query_text,
                retrieval_score=0.9,
                metadata={"assignee_user_id": str(uuid4())},
            )
        ]

    def save_traces(self, run_id, cycle_number, query, hits):
        self.traces.append((run_id, cycle_number, query, hits))


class FakeQdrant:
    def search(self, query, scope=None):
        self.scope = scope
        return [
            RetrievalHit(
                retriever_type=RetrieverType.SIMILAR_CASE,
                source_type="similar_email_case",
                source_id=uuid4(),
                title="확정된 유사 사례",
                content="purchase order pump",
                retrieval_score=0.82,
                metadata={"assignee_user_id": str(uuid4()), "assignment_confirmed": True},
            )
        ]


class RetrievalServiceHarness(AgenticRetrievalService):
    def _mark_prompt_inclusion(self, run_id, selected_hits):
        self.marked = selected_hits


def _production_scope() -> RetrievalScope:
    return RetrievalScope(provider="gmail", dataset_type="production")


def test_planner_uses_only_extracted_facts():
    facts = MailFacts(
        sender_domain="customer.example",
        request_types=["purchase_order"],
        requested_actions=["confirm delivery"],
        part_numbers=["P-100"],
    )
    plan = RetrievalPlanner().plan(facts, cycle_number=1)

    query_texts = [query.query_text for query in plan.queries]
    assert "customer.example" in query_texts
    assert "purchase_order" in query_texts
    assert "P-100" in query_texts
    assert len(plan.queries) <= 12


def test_retrieval_stops_when_context_is_sufficient():
    postgres = FakePostgres()
    service = RetrievalServiceHarness(
        planner=RetrievalPlanner(),
        postgres=postgres,
        qdrant=FakeQdrant(),
        max_cycles=3,
        prompt_hit_limit=6,
    )
    facts = MailFacts(
        customer_candidates=["ACME"],
        request_types=["purchase_order"],
        requested_actions=["confirm order"],
        product_groups=["pump"],
    )

    context = service.execute(run_id=uuid4(), facts=facts, retrieval_scope=_production_scope())

    assert context.sufficient is True
    assert len(context.cycles) == 1
    assert context.selected_hits
    assert all(hit.included_in_prompt for hit in context.selected_hits)
    assert postgres.traces
    assert isinstance(service.qdrant.scope, RetrievalScope)


def test_retrieval_replans_up_to_three_cycles_when_insufficient():
    class EmptyPostgres(FakePostgres):
        def capability_search(self, query):
            return []

    class EmptyQdrant:
        def search(self, query, scope=None):
            return []

    service = RetrievalServiceHarness(
        planner=RetrievalPlanner(),
        postgres=EmptyPostgres(),
        qdrant=EmptyQdrant(),
        max_cycles=3,
    )

    context = service.execute(run_id=uuid4(), facts=MailFacts(), retrieval_scope=_production_scope())

    assert context.sufficient is False
    assert len(context.cycles) == 3
    assert "assignee_context" in context.missing_context


def test_retrieval_records_embedding_gateway_failure_without_failing_run():
    class FailingQdrant:
        def search(self, query, scope=None):
            raise LLMGatewayError("embedding model unavailable")

    service = RetrievalServiceHarness(
        planner=RetrievalPlanner(),
        postgres=FakePostgres(),
        qdrant=FailingQdrant(),
        max_cycles=1,
    )

    context = service.execute(
        run_id=uuid4(),
        facts=MailFacts(
            customer_candidates=["ACME"],
            request_types=["purchase_order"],
            requested_actions=["confirm order"],
            product_groups=["pump"],
        ),
        retrieval_scope=_production_scope(),
    )

    assert context.sufficient is True
    assert any(
        "embedding model unavailable" in reason
        for cycle in context.cycles
        for reason in cycle.reasons
    )

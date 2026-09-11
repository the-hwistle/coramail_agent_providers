from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from app.llm.gateway import LLMGatewayError
from app.repositories.postgres_retrieval_repository import PostgresRetrievalRepository
from app.retrieval.planner import RetrievalPlanner
from app.retrieval.qdrant_client import QdrantRetrievalError, QdrantSimilarCaseRetriever
from app.schemas.mail_decision import MailFacts
from app.schemas.retrieval import (
    RetrievalContext,
    RetrievalCycleResult,
    RetrievalHit,
    RetrievalQuery,
    RetrievalScope,
    RetrieverType,
)


class AgenticRetrievalService:
    def __init__(
        self,
        *,
        planner: RetrievalPlanner,
        postgres: PostgresRetrievalRepository,
        qdrant: QdrantSimilarCaseRetriever,
        max_cycles: int = 3,
        prompt_hit_limit: int = 6,
    ):
        self.planner = planner
        self.postgres = postgres
        self.qdrant = qdrant
        self.max_cycles = max(1, min(max_cycles, 3))
        self.prompt_hit_limit = max(1, prompt_hit_limit)

    def execute(self, *, run_id: UUID, facts: MailFacts, retrieval_scope: RetrievalScope | None = None) -> RetrievalContext:
        cycles: list[RetrievalCycleResult] = []
        all_hits: list[RetrievalHit] = []
        missing: list[str] | None = None

        for cycle_number in range(1, self.max_cycles + 1):
            plan = self.planner.plan(facts, cycle_number=cycle_number, missing_context=missing)
            cycle_hits: list[RetrievalHit] = []
            reasons: list[str] = []
            for query in plan.queries:
                try:
                    hits = self._run_query(query, retrieval_scope)
                except (QdrantRetrievalError, LLMGatewayError) as exc:
                    hits = []
                    reasons.append(str(exc))
                cycle_hits.extend(hits)
                self.postgres.save_traces(run_id, cycle_number, query, hits)

            all_hits.extend(cycle_hits)
            sufficient, missing, evaluation_reasons = self._evaluate(facts, all_hits)
            reasons.extend(evaluation_reasons)
            cycles.append(
                RetrievalCycleResult(
                    cycle_number=cycle_number,
                    plan=plan,
                    hits=cycle_hits,
                    sufficient=sufficient,
                    missing_context=missing,
                    reasons=reasons,
                )
            )
            if sufficient:
                break

        selected = self._select_hits(all_hits)
        selected_keys = {(hit.source_type, str(hit.source_id), hit.title) for hit in selected}
        for hit in all_hits:
            hit.included_in_prompt = (hit.source_type, str(hit.source_id), hit.title) in selected_keys
        self._mark_prompt_inclusion(run_id, selected)

        sufficient, final_missing, _ = self._evaluate(facts, selected)
        return RetrievalContext(
            cycles=cycles,
            selected_hits=selected,
            sufficient=sufficient,
            missing_context=final_missing,
        )

    def _run_query(self, query: RetrievalQuery, retrieval_scope: RetrievalScope | None) -> list[RetrievalHit]:
        if query.retriever_type == RetrieverType.EXACT:
            return self.postgres.exact_search(query)
        if query.retriever_type == RetrieverType.ROUTING_RULE:
            return self.postgres.routing_rule_search(query)
        if query.retriever_type == RetrieverType.ASSIGNEE_CAPABILITY:
            return self.postgres.capability_search(query)
        if query.retriever_type == RetrieverType.SIMILAR_CASE:
            return self.qdrant.search(query, retrieval_scope)
        return []

    @staticmethod
    def _evaluate(facts: MailFacts, hits: list[RetrievalHit]) -> tuple[bool, list[str], list[str]]:
        by_type: dict[RetrieverType, list[RetrievalHit]] = defaultdict(list)
        for hit in hits:
            by_type[hit.retriever_type].append(hit)

        missing: list[str] = []
        reasons: list[str] = []
        has_assignee = any(hit.metadata.get("assignee_user_id") for hit in hits)
        if not has_assignee:
            missing.append("assignee_context")
            reasons.append("no active assignee evidence")

        has_business_context = bool(by_type[RetrieverType.ROUTING_RULE] or facts.request_types or facts.requested_actions)
        if not has_business_context:
            missing.append("business_type_context")

        has_entity_context = bool(
            by_type[RetrieverType.EXACT]
            or facts.customer_name
            or facts.customer_candidates
            or facts.product_names
            or facts.product_groups
            or facts.part_numbers
        )
        if not has_entity_context:
            missing.append("customer_or_product_context")

        strong_hits = [hit for hit in hits if hit.retrieval_score >= 0.65]
        if not strong_hits:
            missing.append("strong_retrieval_evidence")
            reasons.append("no retrieval hit above 0.65")

        sufficient = not missing and has_assignee and len(strong_hits) >= 1
        return sufficient, list(dict.fromkeys(missing)), reasons

    def _select_hits(self, hits: list[RetrievalHit]) -> list[RetrievalHit]:
        deduped: dict[tuple[str, str, str], RetrievalHit] = {}
        for hit in hits:
            key = (hit.source_type, str(hit.source_id), hit.title)
            existing = deduped.get(key)
            if existing is None or hit.retrieval_score > existing.retrieval_score:
                deduped[key] = hit
        ranked = sorted(
            deduped.values(),
            key=lambda hit: (hit.rerank_score if hit.rerank_score is not None else hit.retrieval_score),
            reverse=True,
        )
        return ranked[: self.prompt_hit_limit]

    def _mark_prompt_inclusion(self, run_id: UUID, selected_hits: list[RetrievalHit]) -> None:
        import psycopg

        source_ids = [hit.source_id for hit in selected_hits if hit.source_id is not None]
        if not source_ids:
            return
        with psycopg.connect(self.postgres.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE retrieval_traces
                        SET included_in_prompt = TRUE
                        WHERE mail_decision_run_id = %(run_id)s
                          AND source_id = ANY(%(source_ids)s)
                        """,
                        {"run_id": run_id, "source_ids": source_ids},
                    )

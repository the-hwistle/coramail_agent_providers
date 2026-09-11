from __future__ import annotations

from app.schemas.mail_decision import MailFacts
from app.schemas.retrieval import RetrievalPlan, RetrievalQuery, RetrieverType


class RetrievalPlanner:
    """Builds bounded retrieval plans from verified MailFacts only."""

    def plan(self, facts: MailFacts, *, cycle_number: int, missing_context: list[str] | None = None) -> RetrievalPlan:
        queries: list[RetrievalQuery] = []
        missing = list(missing_context or self._initial_missing(facts))

        exact_values = self._exact_values(facts)
        for purpose, value in exact_values:
            queries.append(
                RetrievalQuery(
                    purpose=purpose,
                    retriever_type=RetrieverType.EXACT,
                    query_text=value,
                    filters={"match_type": purpose},
                    limit=5,
                )
            )

        for request_type in facts.request_types[:3]:
            queries.append(
                RetrievalQuery(
                    purpose="business_type_rule",
                    retriever_type=RetrieverType.ROUTING_RULE,
                    query_text=request_type,
                    filters={"request_type": request_type},
                    limit=8,
                )
            )

        capability_values = list(dict.fromkeys(
            facts.customer_candidates[:2]
            + facts.product_groups[:3]
            + facts.request_types[:3]
            + facts.project_numbers[:2]
        ))
        for value in capability_values:
            queries.append(
                RetrievalQuery(
                    purpose="assignee_capability",
                    retriever_type=RetrieverType.ASSIGNEE_CAPABILITY,
                    query_text=value,
                    limit=8,
                )
            )

        semantic_query = self._semantic_query(facts, missing)
        if semantic_query:
            queries.append(
                RetrievalQuery(
                    purpose="similar_confirmed_cases",
                    retriever_type=RetrieverType.SIMILAR_CASE,
                    query_text=semantic_query,
                    filters={"confirmed_only": True},
                    limit=8 if cycle_number == 1 else 12,
                )
            )

        # Later cycles broaden only the unresolved dimensions; they do not invent new facts.
        if cycle_number > 1 and missing:
            queries.append(
                RetrievalQuery(
                    purpose="broaden_unresolved_context",
                    retriever_type=RetrieverType.SIMILAR_CASE,
                    query_text=" | ".join(missing + facts.requested_actions[:2]),
                    filters={"confirmed_only": True, "broadened": True},
                    limit=12,
                )
            )

        return RetrievalPlan(cycle_number=cycle_number, queries=queries[:12], missing_context=missing)

    @staticmethod
    def _exact_values(facts: MailFacts) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        if facts.sender_domain:
            rows.append(("sender_domain", facts.sender_domain))
        for value in facts.customer_candidates[:2]:
            rows.append(("customer", value))
        for value in facts.part_numbers[:3]:
            rows.append(("part_number", value))
        for value in facts.project_numbers[:2]:
            rows.append(("project", value))
        for value in facts.vessel_names[:2]:
            rows.append(("vessel", value))
        return rows

    @staticmethod
    def _semantic_query(facts: MailFacts, missing: list[str]) -> str:
        parts = (
            facts.requested_actions[:3]
            + facts.request_types[:3]
            + facts.product_names[:3]
            + facts.product_groups[:2]
            + facts.urgency_signals[:2]
            + missing[:3]
        )
        return " | ".join(dict.fromkeys(part.strip() for part in parts if part and part.strip()))

    @staticmethod
    def _initial_missing(facts: MailFacts) -> list[str]:
        missing = list(facts.missing_information)
        if not facts.customer_name and not facts.customer_candidates and not facts.sender_domain:
            missing.append("customer_context")
        if not facts.request_types and not facts.requested_actions:
            missing.append("business_type_context")
        if not facts.product_groups and not facts.product_names and not facts.part_numbers:
            missing.append("product_context")
        missing.append("assignee_context")
        return list(dict.fromkeys(missing))

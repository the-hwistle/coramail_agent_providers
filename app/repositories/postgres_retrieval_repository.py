from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.schemas.retrieval import RetrievalHit, RetrievalQuery, RetrieverType


class PostgresRetrievalRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url.strip()

    def exact_search(self, query: RetrievalQuery) -> list[RetrievalHit]:
        import psycopg

        value = query.query_text.strip()
        match_type = str(query.filters.get("match_type") or "")
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                if match_type == "sender_domain":
                    cursor.execute(
                        """
                        SELECT m.id, m.subject, m.sender_address, ra.assignee_user_id, u.name AS assignee_name
                        FROM email_messages m
                        LEFT JOIN routing_assignments ra ON ra.email_message_id = m.id
                        LEFT JOIN users u ON u.id = ra.assignee_user_id
                        WHERE lower(split_part(m.sender_address, '@', 2)) = lower(%(value)s)
                          AND m.deleted_at IS NULL
                        ORDER BY m.received_at DESC NULLS LAST
                        LIMIT %(limit)s
                        """,
                        {"value": value, "limit": query.limit},
                    )
                else:
                    cursor.execute(
                        """
                        SELECT m.id, m.subject, m.sender_address, ra.assignee_user_id, u.name AS assignee_name
                        FROM email_messages m
                        LEFT JOIN routing_assignments ra ON ra.email_message_id = m.id
                        LEFT JOIN users u ON u.id = ra.assignee_user_id
                        WHERE m.deleted_at IS NULL
                          AND (
                              m.subject ILIKE %(pattern)s
                              OR m.body_text ILIKE %(pattern)s
                              OR EXISTS (
                                  SELECT 1 FROM mail_facts mf
                                  WHERE mf.email_message_id = m.id AND mf.is_current IS TRUE
                                    AND mf.facts_json::text ILIKE %(pattern)s
                              )
                          )
                        ORDER BY m.received_at DESC NULLS LAST
                        LIMIT %(limit)s
                        """,
                        {"pattern": f"%{value}%", "limit": query.limit},
                    )
                rows = cursor.fetchall()
        return [
            RetrievalHit(
                retriever_type=RetrieverType.EXACT,
                source_type="email_message",
                source_id=row["id"],
                title=str(row.get("subject") or ""),
                content=f"sender={row.get('sender_address')}; assignee={row.get('assignee_name') or 'unconfirmed'}",
                retrieval_score=1.0 if row.get("assignee_user_id") else 0.75,
                metadata={"assignee_user_id": str(row["assignee_user_id"]) if row.get("assignee_user_id") else None},
            )
            for row in rows
        ]

    def routing_rule_search(self, query: RetrievalQuery) -> list[RetrievalHit]:
        import psycopg

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT rr.id, c.code AS category_code, c.name AS category_name,
                           rr.assignee_user_id, u.name AS assignee_name, rr.priority
                    FROM routing_rules rr
                    JOIN categories c ON c.id = rr.category_id
                    JOIN users u ON u.id = rr.assignee_user_id
                    WHERE rr.is_active IS TRUE
                      AND u.status = 'active'
                      AND (c.code ILIKE %(pattern)s OR c.name ILIKE %(pattern)s)
                      AND (rr.effective_from IS NULL OR rr.effective_from <= now())
                      AND (rr.effective_to IS NULL OR rr.effective_to > now())
                    ORDER BY rr.priority, u.name
                    LIMIT %(limit)s
                    """,
                    {"pattern": f"%{query.query_text}%", "limit": query.limit},
                )
                rows = cursor.fetchall()
        return [
            RetrievalHit(
                retriever_type=RetrieverType.ROUTING_RULE,
                source_type="routing_rule",
                source_id=row["id"],
                title=f"{row['category_name']} → {row['assignee_name']}",
                content=f"category={row['category_code']}; priority={row['priority']}",
                retrieval_score=max(0.5, 1.0 - min(int(row["priority"]), 100) / 200),
                metadata={"assignee_user_id": str(row["assignee_user_id"]), "priority": row["priority"]},
            )
            for row in rows
        ]

    def capability_search(self, query: RetrievalQuery) -> list[RetrievalHit]:
        import psycopg

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT ac.id, ac.user_id, u.name, ac.capability_type, ac.capability_value, ac.priority
                    FROM assignee_capabilities ac
                    JOIN users u ON u.id = ac.user_id
                    WHERE u.status = 'active'
                      AND ac.capability_value ILIKE %(pattern)s
                      AND (ac.valid_from IS NULL OR ac.valid_from <= now())
                      AND (ac.valid_to IS NULL OR ac.valid_to > now())
                    ORDER BY ac.priority, u.name
                    LIMIT %(limit)s
                    """,
                    {"pattern": f"%{query.query_text}%", "limit": query.limit},
                )
                rows = cursor.fetchall()
        return [
            RetrievalHit(
                retriever_type=RetrieverType.ASSIGNEE_CAPABILITY,
                source_type="assignee_capability",
                source_id=row["id"],
                title=f"{row['name']} / {row['capability_type']}",
                content=str(row["capability_value"]),
                retrieval_score=max(0.5, 1.0 - min(int(row["priority"]), 100) / 200),
                metadata={"assignee_user_id": str(row["user_id"]), "capability_type": row["capability_type"]},
            )
            for row in rows
        ]

    def save_traces(self, run_id: UUID, cycle_number: int, query: RetrievalQuery, hits: list[RetrievalHit]) -> None:
        import psycopg

        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    if not hits:
                        cursor.execute(
                            """
                            INSERT INTO retrieval_traces (
                                id, mail_decision_run_id, cycle_number, purpose, query_text, filters_json,
                                retriever_type, source_type, source_id, retrieval_score, rerank_score,
                                included_in_prompt, created_at
                            ) VALUES (
                                %(id)s, %(run_id)s, %(cycle)s, %(purpose)s, %(query)s, %(filters)s,
                                %(retriever)s, NULL, NULL, NULL, NULL, FALSE, %(created_at)s
                            )
                            """,
                            {"id": uuid4(), "run_id": run_id, "cycle": cycle_number, "purpose": query.purpose,
                             "query": query.query_text, "filters": Jsonb(query.filters),
                             "retriever": query.retriever_type.value, "created_at": now},
                        )
                    for hit in hits:
                        cursor.execute(
                            """
                            INSERT INTO retrieval_traces (
                                id, mail_decision_run_id, cycle_number, purpose, query_text, filters_json,
                                retriever_type, source_type, source_id, retrieval_score, rerank_score,
                                included_in_prompt, created_at
                            ) VALUES (
                                %(id)s, %(run_id)s, %(cycle)s, %(purpose)s, %(query)s, %(filters)s,
                                %(retriever)s, %(source_type)s, %(source_id)s, %(retrieval_score)s,
                                %(rerank_score)s, %(included)s, %(created_at)s
                            )
                            """,
                            {"id": uuid4(), "run_id": run_id, "cycle": cycle_number, "purpose": query.purpose,
                             "query": query.query_text, "filters": Jsonb(query.filters),
                             "retriever": hit.retriever_type.value, "source_type": hit.source_type,
                             "source_id": hit.source_id, "retrieval_score": hit.retrieval_score,
                             "rerank_score": hit.rerank_score, "included": hit.included_in_prompt,
                             "created_at": now},
                        )

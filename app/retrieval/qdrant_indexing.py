from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4, uuid5

from psycopg.rows import dict_row


SIMILAR_CASE_SCHEMA_VERSION = 2
PRODUCTION_DATASET_TYPE = "production"
SIMILAR_CASE_NAMESPACE = UUID("9ea234d8-e53f-461c-9634-7a5cc899fc44")

CONFIRMED_ASSIGNMENT_STATUSES = {"assigned", "forwarded", "completed"}


class QdrantIndexingError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProductionSimilarCasePoint:
    point_id: str
    email_message_id: UUID
    vector_text: str
    payload: dict[str, Any]
    content_hash: str


class QdrantCaseIndexClient:
    def __init__(self, *, base_url: str, collection: str, timeout_seconds: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.collection = collection
        self.timeout_seconds = timeout_seconds

    def upsert_point(self, point: ProductionSimilarCasePoint, vector: list[float]) -> None:
        self._request(
            "PUT",
            f"/collections/{self.collection}/points?wait=true",
            {"points": [{"id": point.point_id, "vector": vector, "payload": point.payload}]},
        )

    def ensure_collection(self, vector_size: int) -> None:
        try:
            self._request("GET", f"/collections/{self.collection}")
            return
        except HTTPError as exc:
            if exc.code != 404:
                raise
        self._request(
            "PUT",
            f"/collections/{self.collection}",
            {"vectors": {"size": vector_size, "distance": "Cosine"}},
        )

    def verification_counts(self) -> dict[str, int]:
        return {
            "total": self._count({}),
            "missing_provider": self._count({"must": [{"is_empty": {"key": "provider"}}]}),
            "missing_dataset_type": self._count({"must": [{"is_empty": {"key": "dataset_type"}}]}),
            "missing_synthetic": self._count({"must": [{"is_empty": {"key": "synthetic"}}]}),
            "missing_evaluation": self._count({"must": [{"is_empty": {"key": "evaluation"}}]}),
            "missing_assignment_confirmed": self._count({"must": [{"is_empty": {"key": "assignment_confirmed"}}]}),
            "production": self._count({"must": [{"key": "dataset_type", "match": {"value": "production"}}]}),
            "demo": self._count({"must": [{"key": "dataset_type", "match": {"value": "demo"}}]}),
            "evaluation": self._count({"must": [{"key": "dataset_type", "match": {"value": "evaluation"}}]}),
            "production_invalid_synthetic": self._count(
                {
                    "must": [
                        {"key": "dataset_type", "match": {"value": "production"}},
                        {"key": "synthetic", "match": {"value": True}},
                    ]
                }
            ),
            "production_invalid_evaluation": self._count(
                {
                    "must": [
                        {"key": "dataset_type", "match": {"value": "production"}},
                        {"key": "evaluation", "match": {"value": True}},
                    ]
                }
            ),
            "production_missing_email_account_id": self._count(
                {
                    "must": [
                        {"key": "dataset_type", "match": {"value": "production"}},
                        {"is_empty": {"key": "email_account_id"}},
                    ],
                }
            ),
        }

    def _count(self, filter_payload: dict[str, Any]) -> int:
        payload: dict[str, Any] = {"exact": True}
        if filter_payload:
            payload["filter"] = filter_payload
        response = self._request("POST", f"/collections/{self.collection}/points/count", payload)
        return int((response.get("result") or {}).get("count") or 0)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}/{path.lstrip('/')}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except HTTPError:
            raise
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise QdrantIndexingError(f"Qdrant request failed: {method} {path}: {exc}") from exc


class ProductionSimilarCaseIndexer:
    def __init__(
        self,
        *,
        database_url: str,
        qdrant_client: QdrantCaseIndexClient,
        embedder: Callable[[list[str]], list[list[float]]],
        embedding_model: str,
    ):
        self.database_url = database_url.strip()
        self.qdrant_client = qdrant_client
        self.embedder = embedder
        self.embedding_model = embedding_model

    def index_email(self, email_message_id: UUID) -> ProductionSimilarCasePoint | None:
        row = self._load_email_case(email_message_id)
        if row is None:
            return None
        point = build_production_similar_case_point(row)
        vectors = self.embedder([point.vector_text])
        if not vectors:
            raise QdrantIndexingError("embedding provider returned no vector")
        self.qdrant_client.ensure_collection(len(vectors[0]))
        self.qdrant_client.upsert_point(point, vectors[0])
        self._save_index_record(point, len(vectors[0]))
        return point

    def reindex(
        self,
        *,
        provider: str = "gmail",
        email_account_id: UUID | None = None,
        limit: int | None = None,
        confirmed_only: bool = False,
    ) -> list[ProductionSimilarCasePoint]:
        rows = self._load_reindex_rows(
            provider=provider,
            email_account_id=email_account_id,
            limit=limit,
            confirmed_only=confirmed_only,
        )
        indexed: list[ProductionSimilarCasePoint] = []
        for row in rows:
            point = self.index_email(UUID(str(row["email_message_id"])))
            if point is not None:
                indexed.append(point)
        return indexed

    def verify_collection(self) -> dict[str, int]:
        return self.qdrant_client.verification_counts()

    def _load_email_case(self, email_message_id: UUID) -> dict[str, Any] | None:
        import psycopg

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute(_EMAIL_CASE_SQL + " AND m.id = %(email_message_id)s", {"email_message_id": email_message_id})
                row = cursor.fetchone()
                return dict(row) if row else None

    def _load_reindex_rows(
        self,
        *,
        provider: str,
        email_account_id: UUID | None,
        limit: int | None,
        confirmed_only: bool,
    ) -> list[dict[str, Any]]:
        import psycopg

        clauses = ["account.provider = %(provider)s", "m.deleted_at IS NULL"]
        params: dict[str, Any] = {"provider": provider}
        if email_account_id is not None:
            clauses.append("m.email_account_id = %(email_account_id)s")
            params["email_account_id"] = email_account_id
        if confirmed_only:
            clauses.append("ra.assignee_user_id IS NOT NULL")
            clauses.append("ra.status = ANY(%(confirmed_statuses)s)")
            params["confirmed_statuses"] = list(CONFIRMED_ASSIGNMENT_STATUSES)
        sql = f"{_EMAIL_CASE_SQL} AND {' AND '.join(clauses)} ORDER BY m.received_at DESC NULLS LAST, m.created_at DESC"
        if limit is not None:
            sql += " LIMIT %(limit)s"
            params["limit"] = max(0, limit)
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return [dict(row) for row in cursor.fetchall()]

    def _save_index_record(self, point: ProductionSimilarCasePoint, embedding_dimension: int) -> None:
        import psycopg

        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO qdrant_index_records (
                            id, source_type, email_message_id, collection_name, point_id, schema_version,
                            embedding_model, embedding_dimension, content_hash, status, indexed_at,
                            created_at, updated_at
                        ) VALUES (
                            %(id)s, 'email', %(email_message_id)s, %(collection)s, %(point_id)s,
                            %(schema_version)s, %(embedding_model)s, %(embedding_dimension)s, %(content_hash)s,
                            'indexed', %(indexed_at)s, %(created_at)s, %(updated_at)s
                        )
                        ON CONFLICT (collection_name, point_id) DO UPDATE SET
                            source_type = EXCLUDED.source_type,
                            email_message_id = EXCLUDED.email_message_id,
                            schema_version = EXCLUDED.schema_version,
                            embedding_model = EXCLUDED.embedding_model,
                            embedding_dimension = EXCLUDED.embedding_dimension,
                            content_hash = EXCLUDED.content_hash,
                            status = EXCLUDED.status,
                            indexed_at = EXCLUDED.indexed_at,
                            error_message = NULL,
                            updated_at = EXCLUDED.updated_at
                        """,
                        {
                            "email_message_id": point.email_message_id,
                            "id": uuid4(),
                            "collection": self.qdrant_client.collection,
                            "point_id": point.point_id,
                            "schema_version": SIMILAR_CASE_SCHEMA_VERSION,
                            "embedding_model": self.embedding_model,
                            "embedding_dimension": embedding_dimension,
                            "content_hash": point.content_hash,
                            "indexed_at": now,
                            "created_at": now,
                            "updated_at": now,
                        },
                    )


def build_production_similar_case_point(row: dict[str, Any]) -> ProductionSimilarCasePoint:
    email_message_id = UUID(str(row["email_message_id"]))
    assignment_confirmed = _assignment_confirmed(row)
    vector_text = _vector_text(row)
    payload = {
        "schema_version": SIMILAR_CASE_SCHEMA_VERSION,
        "email_message_id": str(email_message_id),
        "source_email_message_id": str(email_message_id),
        "email_account_id": str(row["email_account_id"]),
        "provider": str(row["provider"]),
        "dataset_type": PRODUCTION_DATASET_TYPE,
        "synthetic": False,
        "evaluation": False,
        "assignment_confirmed": assignment_confirmed,
        "assignment_status": str(row.get("assignment_status") or ""),
        "assignment_source": str(row.get("assignment_source") or ""),
        "subject": str(row.get("subject") or ""),
        "sender_domain": str(row.get("sender_domain") or ""),
        "summary": _summary(row),
        "indexed_source_updated_at": _iso(row.get("source_updated_at")),
    }
    if assignment_confirmed and row.get("assignee_user_id"):
        payload["historical_assignee_user_id"] = str(row["assignee_user_id"])
    business_type = str(row.get("business_type") or "")
    if assignment_confirmed and business_type:
        payload["historical_business_type"] = business_type
    for key in ("assigned_at", "fixed_at", "forwarded_at", "completed_at", "assignment_updated_at"):
        value = _iso(row.get(key))
        if value:
            payload[key] = value
    content_hash = hashlib.sha256(
        json.dumps({"vector_text": vector_text, "payload": payload}, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return ProductionSimilarCasePoint(
        point_id=production_similar_case_point_id(email_message_id),
        email_message_id=email_message_id,
        vector_text=vector_text,
        payload=payload,
        content_hash=content_hash,
    )


def production_similar_case_point_id(email_message_id: UUID) -> str:
    return str(uuid5(SIMILAR_CASE_NAMESPACE, f"production-similar-case:{email_message_id}"))


def _assignment_confirmed(row: dict[str, Any]) -> bool:
    return bool(row.get("assignee_user_id")) and str(row.get("assignment_status") or "") in CONFIRMED_ASSIGNMENT_STATUSES


def _vector_text(row: dict[str, Any]) -> str:
    pieces = [
        str(row.get("subject") or ""),
        str(row.get("sender_domain") or ""),
        str(row.get("business_type") or ""),
        str(row.get("facts_text") or ""),
        str(row.get("decision_summary") or ""),
        str(row.get("body_text") or "")[:4000],
    ]
    return "\n".join(piece for piece in pieces if piece.strip())


def _summary(row: dict[str, Any]) -> str:
    summary = str(row.get("decision_summary") or "").strip()
    if summary:
        return summary[:2000]
    snippet = str(row.get("snippet") or "").strip()
    if snippet:
        return snippet[:1000]
    return str(row.get("body_text") or "")[:1000]


def _iso(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else ""


_EMAIL_CASE_SQL = """
SELECT
    m.id AS email_message_id,
    m.email_account_id,
    account.provider,
    m.subject,
    m.body_text,
    m.snippet,
    lower(split_part(m.sender_address, '@', 2)) AS sender_domain,
    GREATEST(m.updated_at, COALESCE(ra.updated_at, m.updated_at)) AS source_updated_at,
    ra.assignee_user_id,
    ra.status AS assignment_status,
    ra.assignment_source,
    ra.assigned_at,
    ra.fixed_at,
    ra.forwarded_at,
    ra.completed_at,
    ra.updated_at AS assignment_updated_at,
    COALESCE(
        NULLIF((cr.result_json #>> '{primary_type}'), ''),
        NULLIF((mf.facts_json #>> '{request_types,0}'), '')
    ) AS business_type,
    COALESCE(
        NULLIF((sr.result_json #>> '{summary_text}'), ''),
        NULLIF(sr.result_text, '')
    ) AS decision_summary,
    mf.facts_json::text AS facts_text
FROM email_messages m
JOIN email_accounts account ON account.id = m.email_account_id
LEFT JOIN routing_assignments ra ON ra.email_message_id = m.id
LEFT JOIN mail_facts mf ON mf.email_message_id = m.id AND mf.is_current IS TRUE
LEFT JOIN email_analysis_results cr
  ON cr.email_message_id = m.id
 AND cr.analysis_type = 'classification'
 AND cr.is_current IS TRUE
LEFT JOIN email_analysis_results sr
  ON sr.email_message_id = m.id
 AND sr.analysis_type = 'executive_summary'
 AND sr.is_current IS TRUE
WHERE m.deleted_at IS NULL
"""

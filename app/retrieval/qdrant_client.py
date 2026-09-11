from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID

from app.llm.gateway import LocalLLMGateway
from app.schemas.retrieval import RetrievalHit, RetrievalQuery, RetrievalScope, RetrieverType


class QdrantRetrievalError(RuntimeError):
    pass


@dataclass(frozen=True)
class QdrantConfig:
    base_url: str = "http://127.0.0.1:6333"
    collection: str = "coramail_cases"
    timeout_seconds: float = 20.0


class QdrantSimilarCaseRetriever:
    def __init__(self, gateway: LocalLLMGateway, config: QdrantConfig):
        self.gateway = gateway
        self.config = config

    def search(self, query: RetrievalQuery, scope: RetrievalScope | None = None) -> list[RetrievalHit]:
        if scope is None:
            raise QdrantRetrievalError("Qdrant similar-case retrieval requires an explicit retrieval scope")
        vectors = self.gateway.embed([query.query_text])
        if not vectors:
            return []
        payload = {
            "vector": vectors[0],
            "limit": query.limit,
            "with_payload": True,
            "score_threshold": 0.45,
        }
        payload["filter"] = self.build_effective_filter(query, scope)
        response = self._post(f"/collections/{self.config.collection}/points/search", payload)
        rows = response.get("result") or []
        hits: list[RetrievalHit] = []
        for row in rows:
            source_id = None
            payload = row.get("payload") or {}
            raw_id = payload.get("email_message_id") or payload.get("source_email_message_id")
            try:
                source_id = UUID(str(raw_id)) if raw_id else None
            except ValueError:
                source_id = None
            score = max(0.0, min(1.0, float(row.get("score") or 0.0)))
            metadata = dict(payload)
            if "assignee_user_id" not in metadata and metadata.get("historical_assignee_user_id"):
                metadata["assignee_user_id"] = metadata["historical_assignee_user_id"]
            if "business_type" not in metadata and metadata.get("historical_business_type"):
                metadata["business_type"] = metadata["historical_business_type"]
            hits.append(
                RetrievalHit(
                    retriever_type=RetrieverType.SIMILAR_CASE,
                    source_type="similar_email_case",
                    source_id=source_id,
                    title=str(metadata.get("subject") or "similar confirmed case"),
                    content=str(metadata.get("summary") or metadata.get("content") or "")[:4000],
                    retrieval_score=score,
                    metadata=metadata,
                )
            )
        return hits

    def build_effective_filter(self, query: RetrievalQuery, scope: RetrievalScope) -> dict[str, Any]:
        """Merge query-specific filters with mandatory source isolation filters.

        Query filters can narrow results, but they cannot remove provider,
        dataset, synthetic/evaluation, or confirmed-assignment requirements.
        Conflicting query filters are intentionally preserved so Qdrant returns
        no rows instead of silently broadening the search.
        """

        query_filter = query.filters.get("qdrant_filter")
        effective: dict[str, Any] = {}
        if isinstance(query_filter, dict):
            effective = {
                key: list(value) if isinstance(value, list) else value
                for key, value in query_filter.items()
            }

        must = list(effective.get("must") or [])
        must.extend(self._mandatory_scope_must(scope))
        effective["must"] = must
        return effective

    @staticmethod
    def _mandatory_scope_must(scope: RetrievalScope) -> list[dict[str, Any]]:
        must: list[dict[str, Any]] = [
            {"key": "assignment_confirmed", "match": {"value": True}},
            {"key": "provider", "match": {"value": scope.provider}},
            {"key": "dataset_type", "match": {"value": scope.dataset_type}},
            {"key": "synthetic", "match": {"value": scope.allow_synthetic}},
        ]
        if scope.email_account_id is not None:
            must.append({"key": "email_account_id", "match": {"value": str(scope.email_account_id)}})
        if scope.dataset_version:
            must.append({"key": "dataset_version", "match": {"value": scope.dataset_version}})
        must.append({"key": "evaluation", "match": {"value": scope.allow_evaluation}})
        return must

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self.config.base_url.rstrip('/')}/{path.lstrip('/')}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise QdrantRetrievalError(f"Qdrant HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise QdrantRetrievalError(f"Qdrant request failed: {exc}") from exc

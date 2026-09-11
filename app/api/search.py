from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Protocol

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)


class SearchService(Protocol):
    def search(self, query: str, *, limit: int) -> dict[str, Any]: ...


SearchServiceFactory = Callable[[], SearchService]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=5, ge=1, le=20)
    with_answer: bool = True


def execute_search(request: SearchRequest, *, search_service: SearchServiceFactory) -> dict[str, object]:
    try:
        result = search_service().search(request.query, limit=request.limit)
    except Exception as exc:  # noqa: BLE001
        logger.exception("mail search API failed")
        raise HTTPException(status_code=503, detail=f"검색 저장소를 조회하지 못했습니다: {exc}") from exc
    if not request.with_answer:
        result["answer"] = ""
    return result


def build_search_router(*, search_service: SearchServiceFactory) -> APIRouter:
    """Build the search HTTP boundary while keeping service selection request-scoped."""
    router = APIRouter()

    @router.post("/api/search")
    def search(request: SearchRequest) -> dict[str, object]:
        return execute_search(request, search_service=search_service)

    return router

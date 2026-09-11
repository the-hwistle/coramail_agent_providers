from fastapi import FastAPI

from app.api.search import SearchRequest, build_search_router


class _SearchService:
    def search(self, query: str, *, limit: int) -> dict[str, object]:
        return {"query": query, "limit": limit, "answer": "ok", "results": []}


def test_search_router_registers_expected_path() -> None:
    router = build_search_router(search_service=lambda: _SearchService())
    app = FastAPI()
    app.include_router(router)

    assert set(app.openapi()["paths"]) == {"/api/search"}


def test_search_request_preserves_validation_contract() -> None:
    request = SearchRequest(query="mail", limit=5, with_answer=False)

    assert request.query == "mail"
    assert request.limit == 5
    assert request.with_answer is False

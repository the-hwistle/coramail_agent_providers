from __future__ import annotations

from fastapi import APIRouter


def build_demo_noop_router() -> APIRouter:
    router = APIRouter()

    @router.post("/api/classify")
    @router.post("/api/reindex")
    @router.post("/api/fetch")
    def demo_noop() -> dict[str, object]:
        return {"status": "demo_noop"}

    return router

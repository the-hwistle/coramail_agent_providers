from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Request


AssetVersionProvider = Callable[[], str]
UiStateProvider = Callable[..., dict[str, object]]
HealthProvider = Callable[[], dict[str, object]]


def build_system_router(
    *,
    asset_version: AssetVersionProvider,
    ui_state: UiStateProvider,
    health: HealthProvider,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/client-version")
    def client_version() -> dict[str, str]:
        return {"version": asset_version()}

    @router.get("/api/ui-state")
    def ui_state_endpoint(
        request: Request,
        view: str = "",
        q: str = "",
        category: str = "",
        status: str = "",
        selected_email_index: int | None = None,
        selected_email_uid: str = "",
    ) -> dict[str, object]:
        return ui_state(
            request=request,
            view=view,
            q=q,
            category=category,
            status=status,
            selected_email_index=selected_email_index,
            selected_email_uid=selected_email_uid,
        )

    @router.get("/api/health")
    def health_endpoint() -> dict[str, object]:
        payload = health()
        return {"status": str(payload.get("status") or "degraded")}

    @router.get("/api/health/details")
    def health_details_endpoint() -> dict[str, object]:
        return health()

    return router

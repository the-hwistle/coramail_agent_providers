from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


ManualAssign = Callable[..., dict[str, Any]]


class ManualRoutingRequest(BaseModel):
    assignee_user_id: UUID


def execute_manual_routing(
    email_ref: str,
    payload: ManualRoutingRequest,
    *,
    manual_assign: ManualAssign,
) -> dict[str, object]:
    try:
        assignment = manual_assign(
            email_ref=email_ref,
            assignee_user_id=payload.assignee_user_id,
            actor_label="api",
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "email_uid": email_ref,
        "routing_assignment": {
            "id": str(assignment.get("id") or ""),
            "email_message_id": str(assignment.get("email_message_id") or ""),
            "assignee_user_id": str(assignment.get("assignee_user_id") or ""),
            "assignee_name": assignment.get("assignee_name") or "",
            "assignee_email": assignment.get("assignee_email") or "",
            "status": assignment.get("status") or "",
            "assignment_source": assignment.get("assignment_source") or "",
            "review_resolved": bool(assignment.get("review_resolved")),
        },
    }


def build_manual_routing_router(*, manual_assign: ManualAssign) -> APIRouter:
    router = APIRouter()

    @router.patch("/api/emails/{email_ref}/routing")
    @router.post("/api/emails/{email_ref}/routing")
    def manual_routing(email_ref: str, payload: ManualRoutingRequest) -> dict[str, object]:
        return execute_manual_routing(email_ref, payload, manual_assign=manual_assign)

    return router

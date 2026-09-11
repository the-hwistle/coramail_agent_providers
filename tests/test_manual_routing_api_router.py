from uuid import UUID

import pytest
from fastapi import HTTPException

from app.api.manual_routing import ManualRoutingRequest, build_manual_routing_router, execute_manual_routing


def test_manual_routing_router_registers_post_and_patch() -> None:
    router = build_manual_routing_router(manual_assign=lambda **_: {})
    paths = {(route.path, method) for route in router.routes for method in route.methods}
    assert ("/api/emails/{email_ref}/routing", "POST") in paths
    assert ("/api/emails/{email_ref}/routing", "PATCH") in paths


def test_execute_manual_routing_preserves_payload_shape() -> None:
    assignee_id = UUID("11111111-1111-1111-1111-111111111111")
    result = execute_manual_routing(
        "mail-1",
        ManualRoutingRequest(assignee_user_id=assignee_id),
        manual_assign=lambda **kwargs: {
            "id": "assignment-1",
            "email_message_id": kwargs["email_ref"],
            "assignee_user_id": kwargs["assignee_user_id"],
            "assignee_name": "담당자",
            "assignee_email": "owner@example.com",
            "status": "assigned",
            "assignment_source": kwargs["actor_label"],
            "review_resolved": True,
        },
    )
    assert result["email_uid"] == "mail-1"
    assert result["routing_assignment"]["assignee_user_id"] == str(assignee_id)
    assert result["routing_assignment"]["review_resolved"] is True


def test_execute_manual_routing_maps_value_error_to_conflict() -> None:
    def fail(**_: object) -> dict[str, object]:
        raise ValueError("이미 배정된 메일입니다.")

    with pytest.raises(HTTPException) as exc_info:
        execute_manual_routing(
            "mail-1",
            ManualRoutingRequest(assignee_user_id=UUID("11111111-1111-1111-1111-111111111111")),
            manual_assign=fail,
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "이미 배정된 메일입니다."

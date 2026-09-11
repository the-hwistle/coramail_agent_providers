# ruff: noqa: F403, F405
from tests.ui_test_support import *  # noqa: F401,F403

def test_routing_overview_prefers_assignee_name_over_stale_uuid_routing_display():
    assignee_id = "10000000-0000-0000-0000-000000000001"
    overview = server.routing_overview(
        [
            {
                "routing_display": assignee_id,
                "assignee_user_id": assignee_id,
                "assignee_name": "김민수",
                "assignee_email": "m.kim@dawonict.co.kr",
                "routing_status": "forwarded",
            }
        ]
    )

    assert overview["assignee_labels"] == ["김민수"]
    assert overview["workload_assignees"][0]["label"] == "김민수"

def test_routing_overview_keeps_fixed_area_without_total_overlap():
    css = _app_css_source()
    workload_css = css.split(".routing-overview-workload {", 1)[1].split("}", 1)[0]

    assert ".floating-scrollbar" not in css
    assert ".scroll-managed" not in css
    assert "flex: 0 0 188px" in css
    assert "height: 188px" in css
    assert "height: 100%" in css
    assert "max-height: 188px" in css
    assert "scrollbar-gutter" not in workload_css
    assert "scrollbar-width: none" in workload_css
    assert ".routing-overview-workload::-webkit-scrollbar" in css
    assert ".routing-overview-total" in css
    assert "position: static" in css
    assert "align-self: flex-end" in css

def test_routing_overview_keeps_one_count_bar_visible():
    overview = server.routing_overview(
        [
            *({"routing_display": "김민수", "routing_status": "forwarded"} for _ in range(542)),
            {"routing_display": "정우석", "routing_status": "forwarded"},
        ]
    )
    tiny_bar = next(item for item in overview["workload_assignees"] if item["label"] == "정우석")
    html = server.templates.get_template("partials/dashboard_routing_overview.html").render(
        routing_overview=overview,
        routing_overview_all=overview,
        dashboard_scope_toggle_enabled=False,
    )

    assert tiny_bar["count"] == 1
    assert tiny_bar["bar_percent"] == 0
    assert tiny_bar["bar_display_percent"] == 2
    assert "width: 2%;" in html

def test_category_timeline_is_fixed_to_recent_seven_days_from_today():
    rows = [
        {"date": "2026-08-04T09:00:00+09:00", "mail_category": "문의"},
        {"date": "2026-08-05T09:00:00+09:00", "mail_category": "발주"},
        {"date": "2026-08-10T09:00:00+09:00", "mail_category": "문의"},
        {"date": "2026-08-03T09:00:00+09:00", "mail_category": "문의"},
        {"date": "2026-08-11T09:00:00+09:00", "mail_category": "발주"},
        {"date": "", "mail_category": "기타"},
    ]

    timeline = server.category_timeline(rows, today=date(2026, 8, 10))

    assert timeline["labels"] == ["08-04", "08-05", "08-06", "08-07", "08-08", "08-09", "08-10"]
    assert timeline["datasets"]["문의"] == [1, 0, 0, 0, 0, 0, 1]
    assert timeline["datasets"]["발주"] == [0, 1, 0, 0, 0, 0, 0]

def test_demo_dashboard_stats_and_timeline_use_latest_demo_data_day(monkeypatch):
    rows = [
        {"date": "2026-08-12T09:24:00+09:00", "mail_category": "문의"},
        {"date": "2026-08-12T09:10:00+09:00", "mail_category": "발주"},
        {"date": "2026-08-11T17:46:00+09:00", "mail_category": "서비스"},
    ]
    token = server._display_demo_mode.set(True)
    try:
        monkeypatch.setattr(server, "mail_service", lambda: type("Service", (), {"category_order": lambda self: ["발주", "문의", "서비스"]})())
        summary = server.dashboard_summary(rows)
        timeline = server.category_timeline(rows)
    finally:
        server._display_demo_mode.reset(token)

    assert summary["today_email_count"] == 2
    assert timeline["labels"][-1] == "08-12"
    assert sum(sum(values) for values in timeline["datasets"].values()) == summary["email_count"]

def test_fixture_demo_rows_share_status_across_overview_decision_and_monitoring(monkeypatch):
    token = server._display_demo_mode.set(True)
    try:
        row = server.demo_service().list_emails(limit=1)[0]
        detail = server.demo_service().email_detail_by_uid(str(row["email_uid"]))
        run = server.demo_service().mail_decision_run_by_uid(str(row["email_uid"]))
        ops = server.ops_row_view(row, attachments=[])
        panel = server.mail_decision_panel_view(
            run=run,
            steps=[],
            email_ref=str(row["email_uid"]),
            current_email=detail,
        )
    finally:
        server._display_demo_mode.reset(token)

    assert row["work_status"] == "forwarded"
    assert row["mail_decision_status"] == "auto_assigned"
    assert row["routing_status"] == "forwarded"
    assert row["manual_route_status"] == "sent"
    assert ops["decision"]["state"] == "auto_assigned"
    assert ops["routing"]["state"] == "completed"
    assert ops["forwarding"]["state"] == "completed"
    assert panel["status"] == "auto_assigned"
    assert panel["status_label"] == "전달 완료"

def test_postgres_mail_row_status_prioritizes_review_required_over_classification_complete():
    service = object.__new__(PostgresMailboxService)

    row = service._message_row(
        {
            "id": RUN_PAYLOAD["email_message_id"],
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "subject": "RFQ review",
            "snippet": "Please review",
            "sent_at": "2026-08-10T01:00:00+00:00",
            "received_at": "2026-08-10T01:00:00+00:00",
            "has_attachment": False,
            "attachment_count": 0,
            "mail_category": "문의",
            "category_source": "ai",
            "routing_status": "review_required",
            "mail_decision_status": "review_required",
        },
        0,
    )

    assert row["classification_state"] == "completed"
    assert row["work_status"] == "review_required"
    assert row["work_status_label"] == "검토 필요"
    assert row["routing_display"] == "미할당"

def test_postgres_mail_row_keeps_confirmed_assignment_ahead_of_pending_analysis():
    service = object.__new__(PostgresMailboxService)

    row = service._message_row(
        {
            "id": RUN_PAYLOAD["email_message_id"],
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "subject": "Assigned RFQ",
            "snippet": "Please review",
            "sent_at": "2026-08-10T01:00:00+00:00",
            "received_at": "2026-08-10T01:00:00+00:00",
            "has_attachment": False,
            "attachment_count": 0,
            "mail_category": "문의",
            "category_source": "ai",
            "classification_result_status": "pending",
            "routing_status": "assigned",
            "assignee_user_id": "10000000-0000-0000-0000-000000000001",
            "assignee_name": "김민수",
            "assignee_email": "minsu.kim@example.invalid",
        },
        0,
    )

    assert row["work_status"] == "assigned"
    assert row["work_status_label"] == "배정 완료"
    assert row["routing_display"] == "김민수"
    assert row["assignee_name"] == "김민수"


def test_postgres_mail_row_shows_completed_work_item_as_short_label():
    service = object.__new__(PostgresMailboxService)

    row = service._message_row(
        {
            "id": RUN_PAYLOAD["email_message_id"],
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "subject": "Completed RFQ",
            "snippet": "Done",
            "sent_at": "2026-08-10T01:00:00+00:00",
            "received_at": "2026-08-10T01:00:00+00:00",
            "has_attachment": False,
            "attachment_count": 0,
            "mail_category": "문의",
            "category_source": "ai",
            "classification_result_status": "success",
            "routing_status": "assigned",
            "assignee_user_id": "10000000-0000-0000-0000-000000000001",
            "assignee_name": "김민수",
            "assignee_email": "minsu.kim@example.invalid",
            "work_item_status": "completed",
        },
        0,
    )

    assert row["work_status"] == "completed"
    assert row["work_status_label"] == "완료"
    assert row["work_item_status_label"] == "완료"


def test_postgres_mail_row_shows_forwarded_work_status_after_manual_route_sent():
    service = object.__new__(PostgresMailboxService)

    row = service._message_row(
        {
            "id": RUN_PAYLOAD["email_message_id"],
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "subject": "Forwarded RFQ",
            "snippet": "Please review",
            "sent_at": "2026-08-10T01:00:00+00:00",
            "received_at": "2026-08-10T01:00:00+00:00",
            "has_attachment": False,
            "attachment_count": 0,
            "mail_category": "문의",
            "category_source": "ai",
            "mail_decision_status": "review_required",
            "routing_status": "assigned",
            "assignee_user_id": "10000000-0000-0000-0000-000000000001",
            "assignee_name": "김민수",
            "assignee_email": "minsu.kim@example.invalid",
            "manual_route_status": "sent",
            "manual_route_sent_at": "2026-08-10T01:02:00+00:00",
        },
        0,
    )

    assert row["work_status"] == "forwarded"
    assert row["work_status_label"] == "전달 완료"
    assert row["manual_route_status"] == "sent"
    assert row["manual_route_status_label"] == "전달 완료"
    assert row["manual_route_button_label"] == "전달 완료"
    assert row["routing_display"] == "김민수"

def test_postgres_mail_row_shows_forwarded_work_status_after_review_required_run():
    service = object.__new__(PostgresMailboxService)

    row = service._message_row(
        {
            "id": RUN_PAYLOAD["email_message_id"],
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "subject": "Forwarded RFQ",
            "snippet": "Please review",
            "sent_at": "2026-08-10T01:00:00+00:00",
            "received_at": "2026-08-10T01:00:00+00:00",
            "has_attachment": False,
            "attachment_count": 0,
            "mail_category": "문의",
            "category_source": "ai",
            "mail_decision_status": "review_required",
            "routing_status": "forwarded",
            "routing_forwarded_at": "2026-08-10T01:02:00+00:00",
            "assignee_user_id": "10000000-0000-0000-0000-000000000001",
            "assignee_name": "김민수",
            "assignee_email": "minsu.kim@example.invalid",
        },
        0,
    )

    assert row["work_status"] == "forwarded"
    assert row["work_status_label"] == "전달 완료"
    assert row["routing_forwarded_at"] == "2026-08-10T01:02:00+00:00"

def test_postgres_mail_row_keeps_confirmed_assignment_after_review_required_rerun():
    service = object.__new__(PostgresMailboxService)

    row = service._message_row(
        {
            "id": RUN_PAYLOAD["email_message_id"],
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "subject": "Assigned RFQ",
            "snippet": "Please review",
            "sent_at": "2026-08-10T01:00:00+00:00",
            "received_at": "2026-08-10T01:00:00+00:00",
            "has_attachment": False,
            "attachment_count": 0,
            "mail_category": "문의",
            "category_source": "ai",
            "mail_decision_status": "review_required",
            "routing_status": "assigned",
            "assignee_user_id": "10000000-0000-0000-0000-000000000001",
            "assignee_name": "김민수",
            "assignee_email": "minsu.kim@example.invalid",
        },
        0,
    )

    assert row["work_status"] == "assigned"
    assert row["work_status_label"] == "배정 완료"
    assert row["routing_display"] == "김민수"

def test_postgres_mail_row_shows_forwarded_work_status_after_routing_forwarded():
    service = object.__new__(PostgresMailboxService)

    row = service._message_row(
        {
            "id": RUN_PAYLOAD["email_message_id"],
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "subject": "Forwarded RFQ",
            "snippet": "Please review",
            "sent_at": "2026-08-10T01:00:00+00:00",
            "received_at": "2026-08-10T01:00:00+00:00",
            "has_attachment": False,
            "attachment_count": 0,
            "mail_category": "문의",
            "category_source": "ai",
            "classification_result_status": "pending",
            "routing_status": "forwarded",
            "assignee_user_id": "10000000-0000-0000-0000-000000000001",
            "assignee_name": "김민수",
            "assignee_email": "minsu.kim@example.invalid",
        },
        0,
    )

    assert row["work_status"] == "forwarded"
    assert row["work_status_label"] == "전달 완료"
    assert row["manual_route_status"] == "sent"
    assert row["routing_display"] == "김민수"

def test_postgres_mail_row_ignores_stale_forwarded_at_without_forwarded_status():
    service = object.__new__(PostgresMailboxService)

    row = service._message_row(
        {
            "id": RUN_PAYLOAD["email_message_id"],
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "subject": "Assigned RFQ",
            "snippet": "Please review",
            "sent_at": "2026-08-10T01:00:00+00:00",
            "received_at": "2026-08-10T01:00:00+00:00",
            "has_attachment": False,
            "attachment_count": 0,
            "mail_category": "문의",
            "category_source": "ai",
            "mail_decision_status": "auto_assigned",
            "routing_status": "assigned",
            "routing_forwarded_at": "2026-08-10T01:02:00+00:00",
            "assignee_user_id": "10000000-0000-0000-0000-000000000001",
            "assignee_name": "김민수",
            "assignee_email": "minsu.kim@example.invalid",
        },
        0,
    )

    assert row["work_status"] == "auto_assigned"
    assert row["work_status_label"] == "자동 배정"
    assert row["manual_route_status_label"] == "미전달"

def test_postgres_mail_list_auto_forwards_existing_auto_assigned_rows():
    service = PostgresMailboxService("postgresql://example.invalid/coramail", Path("."))
    calls = []

    class FakeRoutingRepository:
        def forward_auto_assigned_without_notification(self):
            calls.append("forward_auto_assigned_without_notification")

    class FakeMailRepository:
        def list_messages(self, *, q="", category="", limit=None):
            return []

    service.routing_repository = FakeRoutingRepository()
    service.repository = FakeMailRepository()

    assert service.list_emails() == []
    assert calls == ["forward_auto_assigned_without_notification"]

def test_postgres_mail_row_does_not_restore_attention_from_subject_or_business_type():
    service = object.__new__(PostgresMailboxService)

    row = service._message_row(
        {
            "id": RUN_PAYLOAD["email_message_id"],
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "subject": "[긴급 장애] 현장 네트워크 장비 통신 불안정",
            "snippet": "빠른 점검 요청",
            "sent_at": "2026-08-10T01:00:00+00:00",
            "received_at": "2026-08-10T01:00:00+00:00",
            "has_attachment": False,
            "attachment_count": 0,
            "mail_category": "서비스",
            "category_source": "ai",
            "classification_result_json": {"urgency": ""},
        },
        0,
    )

    assert row["urgency"] == "normal"
    assert row["importance"] == "normal"
    assert row["attention_quadrant"] == "normal"
    assert row["priority"] == "normal"
    assert row["classification"]["urgency"] == "normal"

def test_postgres_mail_row_uses_deterministic_attention_from_independent_axes():
    service = object.__new__(PostgresMailboxService)

    row = service._message_row(
        {
            "id": RUN_PAYLOAD["email_message_id"],
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "subject": "금일 중 견적 부탁드립니다",
            "snippet": "빠른 견적 요청",
            "sent_at": "2026-08-10T01:00:00+00:00",
            "received_at": "2026-08-10T01:00:00+00:00",
            "has_attachment": False,
            "attachment_count": 0,
            "mail_category": "문의",
            "category_source": "ai",
            "classification_result_json": {
                "urgency": {"level": "high", "confidence": 0.9, "reasons": ["금일 중 회신 요청"]},
                "importance": {"level": "normal", "confidence": 0.8, "reasons": []},
            },
        },
        0,
    )

    assert row["urgency"] == "high"
    assert row["importance"] == "normal"
    assert row["attention_quadrant"] == "urgent"
    assert row["priority"] == "urgent"

def test_dashboard_urgent_filter_includes_only_urgent_attention_quadrants():
    rows = [
        {"email_uid": "urgent-important", "attention_quadrant": "urgent_important"},
        {"email_uid": "urgent", "classification": {"attention_quadrant": "urgent"}},
        {"email_uid": "important", "attention_quadrant": "important"},
        {"email_uid": "normal", "attention_quadrant": "normal"},
    ]

    filtered = server.filter_dashboard_mail_rows(rows, "urgent")

    assert [row["email_uid"] for row in filtered] == ["urgent-important", "urgent"]

def test_dashboard_urgent_summary_uses_urgency_axis_before_attention_fallback():
    rows = [
        {"email_uid": "explicit-urgent", "urgency": "high", "attention_quadrant": "normal"},
        {
            "email_uid": "stale-attention",
            "subject": "[긴급] 과거 장애 전달 메일",
            "urgency": "normal",
            "attention_quadrant": "urgent",
        },
        {"email_uid": "legacy-attention", "classification": {"attention_quadrant": "urgent"}},
    ]

    summary = server.dashboard_summary(rows)
    filtered = server.filter_dashboard_mail_rows(rows, "urgent")

    assert summary["urgent_count"] == 2
    assert [row["email_uid"] for row in filtered] == ["explicit-urgent", "legacy-attention"]

def test_postgres_legacy_v2_result_is_displayed_as_conservative_normal_attention():
    service = object.__new__(PostgresMailboxService)

    row = service._message_row(
        {
            "id": RUN_PAYLOAD["email_message_id"],
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "subject": "decision-agent:v2 legacy result",
            "snippet": "legacy summary",
            "sent_at": "2026-08-10T01:00:00+00:00",
            "received_at": "2026-08-10T01:00:00+00:00",
            "has_attachment": False,
            "attachment_count": 0,
            "mail_category": "문의",
            "category_source": "ai",
            "classification_result_json": {
                "category_name": "문의",
                "generation_mode": "llm",
            },
        },
        0,
    )

    assert row["urgency"] == "normal"
    assert row["importance"] == "normal"
    assert row["attention_quadrant"] == "normal"
    assert row["priority"] == "normal"

def test_ops_row_view_marks_review_required_rerun_complete_when_forwarded():
    view = server.ops_row_view(
        {
            "email_uid": RUN_PAYLOAD["email_message_id"],
            "index": 0,
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "subject": "[견적서 송부] 방폭 제어반 예비품 및 릴레이 모듈",
            "received_at": "2026-08-10T01:00:00+00:00",
            "has_attachment": False,
            "attachment_count": 0,
            "business_label": "문의",
            "summary_state": "completed",
            "summary_state_label": "완료",
            "classification_state": "completed",
            "classification_state_label": "완료",
            "mail_decision_status": "review_required",
            "work_status": "forwarded",
            "work_status_label": "전달 완료",
            "routing_status": "forwarded",
            "routing_display": "김민수",
            "assignee_name": "김민수",
            "assignee_email": "minsu.kim@example.invalid",
            "manual_route_status": "sent",
            "manual_route_status_label": "전달 완료",
        },
        attachments=[],
    )

    assert view["decision"]["state"] == "completed"
    assert view["routing"]["state"] == "completed"
    assert view["forwarding"]["state"] == "completed"
    assert view["pipeline_status"]["state"] == "completed"

def test_postgres_mail_row_does_not_show_stale_assignee_for_unconfirmed_routing():
    service = object.__new__(PostgresMailboxService)

    row = service._message_row(
        {
            "id": RUN_PAYLOAD["email_message_id"],
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "subject": "Pending RFQ",
            "snippet": "Please review",
            "sent_at": "2026-08-10T01:00:00+00:00",
            "received_at": "2026-08-10T01:00:00+00:00",
            "has_attachment": False,
            "attachment_count": 0,
            "mail_category": "문의",
            "category_source": "ai",
            "classification_result_status": "pending",
            "routing_status": "pending",
            "assignee_user_id": "10000000-0000-0000-0000-000000000001",
            "assignee_name": "김민수",
            "assignee_email": "minsu.kim@example.invalid",
        },
        0,
    )

    assert row["work_status"] == "queued"
    assert row["work_status_label"] == "대기"
    assert row["routing_display"] == "미할당"
    assert row["assignee_name"] == ""
    assert row["assignee_email"] == ""

def test_postgres_mail_row_manual_route_pending_state_disables_button():
    service = object.__new__(PostgresMailboxService)

    row = service._message_row(
        {
            "id": RUN_PAYLOAD["email_message_id"],
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "subject": "Assigned RFQ",
            "snippet": "Please review",
            "sent_at": "2026-08-10T01:00:00+00:00",
            "received_at": "2026-08-10T01:00:00+00:00",
            "has_attachment": False,
            "attachment_count": 0,
            "mail_category": "문의",
            "category_source": "ai",
            "routing_status": "assigned",
            "assignee_user_id": "10000000-0000-0000-0000-000000000001",
            "assignee_name": "김민수",
            "assignee_email": "minsu.kim@example.invalid",
            "manual_route_status": "pending",
        },
        0,
    )

    assert row["manual_route_status"] == "pending"
    assert row["manual_route_status_label"] == "전달 중"
    assert row["manual_route_button_label"] == "전달 중"
    assert row["manual_route_button_variant"] == "pending"

def test_dashboard_mail_rows_exposes_pending_manual_route_status_for_polling():
    html = server.templates.get_template("partials/mail_rows.html").render(
        {
            **server.ui_globals(),
            "emails": [
                {
                    "index": 0,
                    "email_uid": RUN_PAYLOAD["email_message_id"],
                    "sender_name": "Buyer",
                    "sender_address": "buyer@example.invalid",
                    "subject": "Assigned RFQ",
                    "has_attachment": False,
                    "mail_category": "문의",
                    "classification": {"mail_category": "문의"},
                    "work_status": "assigned",
                    "work_status_label": "배정 완료",
                    "routing_display": "김민수",
                    "assignee_email": "minsu.kim@example.invalid",
                    "manual_route_status": "pending",
                    "manual_route_button_label": "전달 중",
                    "manual_route_button_variant": "pending",
                    "manual_route_button_title": "이미 전달 작업이 진행 중입니다.",
                    "date": "2026-08-10T01:00:00+00:00",
                }
            ],
            "mail_rows_mode": "dashboard",
            "selected_email_index": None,
            "selected_email_uid": "",
        }
    )

    assert "data-manual-route-button" in html
    assert 'data-manual-route-status="pending"' in html
    assert 'hx-include="#dashboardMailFilter"' not in html

def test_demo_dashboard_mail_rows_keep_existing_route_cell_after_auto_delivery():
    html = server.templates.get_template("partials/mail_rows.html").render(
        {
            **server.ui_globals(),
            "demo_mode": True,
            "emails": [
                {
                    "index": 0,
                    "email_uid": RUN_PAYLOAD["email_message_id"],
                    "sender_name": "Buyer",
                    "sender_address": "buyer@example.invalid",
                    "subject": "Assigned RFQ",
                    "has_attachment": False,
                    "mail_category": "문의",
                    "classification": {"mail_category": "문의"},
                    "work_status": "forwarded",
                    "work_status_label": "자동 배정",
                    "routing_display": "김민수",
                    "manual_route_status": "sent",
                    "manual_route_button_label": "전달 완료",
                    "manual_route_button_title": "전달이 완료되었습니다.",
                    "date": "2026-08-10T01:00:00+00:00",
                }
            ],
            "mail_rows_mode": "dashboard",
            "selected_email_index": None,
            "selected_email_uid": "",
        }
    )

    assert "전달 완료" in html
    assert 'data-manual-route-status="sent"' in html
    assert "data-manual-route-button" in html
    assert "/route-manual" in html

def test_dashboard_mail_row_passes_active_category_filter_to_inbox():
    html = server.templates.get_template("partials/mail_rows.html").render(
        {
            **server.ui_globals(),
            "emails": [
                {
                    "index": 0,
                    "email_uid": "mail-order",
                    "sender_name": "Buyer",
                    "sender_address": "buyer@example.invalid",
                    "subject": "PO attached",
                    "has_attachment": False,
                    "mail_category": "발주",
                    "classification": {"mail_category": "발주"},
                    "work_status": "assigned",
                    "work_status_label": "배정 완료",
                    "routing_display": "김민수",
                    "date": "2026-08-10T01:00:00+00:00",
                }
            ],
            "mail_rows_mode": "dashboard",
            "selected_email_index": None,
            "selected_email_uid": "",
        }
    )

    assert 'hx-post="/ui/inbox?email_index=0&email_uid=mail-order"' in html
    assert "hx-vals" not in html

def test_dashboard_category_filter_uses_sliding_segmented_control():
    html = server.templates.get_template("partials/category_filter_chips.html").render(
        category_order=["문의", "발주"],
        compact_filter_legend=True,
    )

    assert 'class="chip-legend mail-category-filter mail-status-filter compact"' in html
    assert 'class="mail-status-filter-highlight"' in html
    assert 'class="mail-status-filter-btn category-filter-chip is-active"' in html
    assert 'data-category-filter="문의"' in html
    assert "chip-dot" not in html
    assert "data-chip-bg" not in html

def test_dashboard_category_filter_is_scoped_to_dashboard_rows():
    html = server.templates.get_template("shell.html").render(
        **server.ui_globals(),
        request=request(),
        active_view="dashboard",
        initial_view_template="views/dashboard.html",
        summary={
            "email_count": 0,
            "today_email_count": 0,
            "classified_count": 0,
            "routed_count": 0,
            "attachment_count": 0,
            "mail_categories": {},
            "business_labels": {},
        },
        emails=[],
        mail_rows_mode="dashboard",
        category_timeline={"labels": [], "datasets": {}},
        routing_overview={
            "total": 0,
            "loaded_count": 0,
            "loaded_percent": 0,
            "unassigned_count": 0,
            "unassigned_percent": 0,
            "assignee_labels": [],
            "assignee_counts": [],
            "palette": [],
        },
    )

    assert 'document.querySelectorAll("#dashboardMailRows tr[data-business-label], #dashboardMailRows tr[data-mail-category]")' in html
    assert 'const emptyRow = dashboardRows.querySelector("#categoryFilterEmptyRow");' in html
    assert "email-row-hidden-by-category" in html
    assert "email-row-hidden-by-stat" in html
    assert "window.applyCategoryFilter = function (category)" in html
    assert "updateCategoryFilterButtons(document);" in html

def test_shell_schedules_manual_route_polling_for_pending_dashboard_rows():
    source = server.templates.get_template("shell.html").render(
        **server.ui_globals(),
        request=request(),
        active_view="dashboard",
        initial_view_template="views/dashboard.html",
        summary={
            "email_count": 0,
            "today_email_count": 0,
            "classified_count": 0,
            "routed_count": 0,
            "attachment_count": 0,
            "mail_categories": {},
            "business_labels": {},
        },
        emails=[],
        mail_rows_mode="dashboard",
        category_timeline={"labels": [], "datasets": {}},
        routing_overview={
            "total": 0,
            "loaded_count": 0,
            "loaded_percent": 0,
            "unassigned_count": 0,
            "unassigned_percent": 0,
            "assignee_labels": [],
            "assignee_counts": [],
            "palette": [],
        },
    )

    assert "function dashboardHasPendingManualRoutes()" in source
    assert "function scheduleManualRoutePoll(delayMs)" in source
    assert "[data-manual-route-button][data-manual-route-status='pending']" in source
    assert "function dashboardMailRowsUrl()" in source
    assert 'const workStatusFilter = document.getElementById("dashboardWorkStatusFilter");' in source
    assert 'url.searchParams.set("status", workStatusFilter.value);' in source
    assert 'target.closest("[data-mail-status-filter]")' in source
    assert "function updateSlidingFilterHighlight(group, activeButton)" in source
    assert 'group.style.setProperty("--mail-status-highlight-x"' in source
    assert 'group.style.setProperty("--mail-status-highlight-width"' in source
    assert "function updateCategoryFilterButtons(scope)" in source
    assert 'target.closest("[data-category-filter]")' in source
    assert 'refreshFragment(inboxPanelUrlForStatus(status), "#main-panel");' in source
    assert "function dashboardMailFilters()" in source
    assert "function setDashboardMailFilter(filter)" in source
    assert "function refreshDashboardMailRowsForFilter(filter)" in source
    assert "function applyDashboardMailStatFilter()" in source
    assert "function updateDashboardMailStreamEmptyState()" in source
    assert 'window.applyCategoryFilter("__all__");' in source
    assert 'const orderedFilters = ["today", "urgent"].filter(function (item) {' in source
    assert '(!activeFilters.has("today") || row.dataset.dashboardMailDate === today) &&' in source
    assert '(!activeFilters.has("urgent") || row.dataset.dashboardMailUrgent === "true");' in source
    assert 'return row.dataset.dashboardMailAttention === filter.replace("attention:", "");' not in source
    assert 'attention:' not in source
    assert 'button.classList.toggle("is-active", isActive);' in source
    assert 'button.setAttribute("aria-pressed", isActive ? "true" : "false");' in source
    assert 'url.searchParams.set("dashboard_mail_filter", dashboardMailFilter.value);' not in source
    assert 'row.classList.toggle("email-row-hidden-by-stat", !shouldShow);' in source
    assert 'refreshFragment(dashboardMailRowsUrl(), "#dashboardMailRows")' in source

def test_shell_refreshes_current_inbox_after_manual_assignment_completed():
    source = server.templates.get_template("shell.html").render(
        **server.ui_globals(),
        request=request(),
        active_view="dashboard",
        initial_view_template="views/dashboard.html",
        summary={
            "email_count": 0,
            "today_email_count": 0,
            "classified_count": 0,
            "routed_count": 0,
            "attachment_count": 0,
            "mail_categories": {},
            "business_labels": {},
        },
        emails=[],
        mail_rows_mode="dashboard",
        category_timeline={"labels": [], "datasets": {}},
        routing_overview={
            "total": 0,
            "loaded_count": 0,
            "loaded_percent": 0,
            "unassigned_count": 0,
            "unassigned_percent": 0,
            "assignee_labels": [],
            "assignee_counts": [],
            "palette": [],
        },
    )

    assert 'document.body.addEventListener("mail-manual-assignment-completed"' in source
    assert 'document.body.addEventListener("mail-read-state-changed"' in source
    assert "function markInboxRowReadOptimistically(row)" in source
    assert 'indicator.textContent = "drafts";' in source
    assert 'indicator.setAttribute("aria-label", "읽은 메일");' in source
    assert "markInboxRowReadOptimistically(row);" in source
    assert 'source.closest("#dashboardMailRows .clickable-row[data-email-uid]")' in source
    assert '#dashboardMailRows .clickable-row[data-email-uid]' in source
    assert "markInboxRowReadByUid((event.detail || {}).email_uid || \"\");" in source
    assert 'document.body.addEventListener("work-item-status-changed"' in source
    assert "function refreshCurrentAssigneeWork()" in source
    assert "refreshInboxDetail(payload.email_index, payload.email_uid)" in source
    assert "refreshInboxRows()" in source
    assert 'refreshFragment("/ui/stats", "#stats");' in source
    assert 'const workStatusFilter = document.getElementById("workStatusFilter");' in source
    assert 'if (workStatusFilter && workStatusFilter.value) url.searchParams.set("status", workStatusFilter.value);' in source
    assert '["q", "category", "limit", "email_index", "email_uid", "selected_email_uid", "assignee", "status", "session_id"]' in source
    assert 'document.body.addEventListener("htmx:configRequest"' in source
    assert 'source.closest("#dashboardMailRows .clickable-row")' in source
    assert "event.detail.parameters.category = activeCategory" in source

def test_ui_state_versions_change_when_mail_status_fields_change(monkeypatch):
    rows = [
        {
            "email_uid": "mail-1",
            "routing_display": "미할당",
            "routing_status": "pending",
            "work_status": "unassigned",
            "classification": "미분류",
            "mail_decision_status": "running",
        }
    ]

    monkeypatch.setattr(server, "mail_rows", lambda q="", category="", limit=None: list(rows))
    monkeypatch.setattr(server, "_email_detail_by_ref", lambda email_ref: dict(rows[0]))

    before = server.ui_state(request(), view="inbox", selected_email_uid="mail-1")
    rows[0] = {
        **rows[0],
        "routing_display": "김민수",
        "routing_status": "assigned",
        "work_status": "assigned",
        "classification": "문의",
        "mail_decision_status": "completed",
    }
    after = server.ui_state(request(), view="inbox", selected_email_uid="mail-1")

    assert before["versions"]["mail_rows"] != after["versions"]["mail_rows"]
    assert before["versions"]["detail"] != after["versions"]["detail"]

def test_shell_polls_monitoring_and_preserves_status_filter():
    source = server.templates.get_template("shell.html").render(
        **server.ui_globals(),
        request=request(),
        active_view="dashboard",
        initial_view_template="views/dashboard.html",
        summary={
            "email_count": 0,
            "today_email_count": 0,
            "classified_count": 0,
            "routed_count": 0,
            "attachment_count": 0,
            "mail_categories": {},
            "business_labels": {},
        },
        emails=[],
        mail_rows_mode="dashboard",
        category_timeline={"labels": [], "datasets": {}},
        routing_overview={
            "total": 0,
            "loaded_count": 0,
            "loaded_percent": 0,
            "unassigned_count": 0,
            "unassigned_percent": 0,
            "assignee_labels": [],
            "assignee_counts": [],
            "palette": [],
        },
    )

    assert 'view === "dashboard" || view === "inbox" || view === "monitoring" || view === "documents"' in source
    assert 'function monitoringStateUrl()' in source
    assert 'url.searchParams.set("view", "monitoring");' in source
    assert 'url.searchParams.set("status", status.value);' in source
    assert "applyMonitoringState(state)" in source
    assert 'scheduleUiPoll(view === "documents" ? 10000 : isDetailProgressActive() ? 1000 : 1500);' in source

def test_shell_renders_centered_manual_route_confirm_dialog():
    source = server.templates.get_template("shell.html").render(
        **server.ui_globals(),
        request=request(),
        active_view="dashboard",
        initial_view_template="views/dashboard.html",
        summary={
            "email_count": 0,
            "today_email_count": 0,
            "classified_count": 0,
            "routed_count": 0,
            "attachment_count": 0,
            "mail_categories": {},
            "business_labels": {},
        },
        emails=[],
        mail_rows_mode="dashboard",
        category_timeline={"labels": [], "datasets": {}},
        routing_overview={
            "total": 0,
            "loaded_count": 0,
            "loaded_percent": 0,
            "unassigned_count": 0,
            "unassigned_percent": 0,
            "assignee_labels": [],
            "assignee_counts": [],
            "palette": [],
        },
    )

    assert 'id="manualRouteConfirmModal"' in source
    assert 'aria-modal="true"' in source
    assert 'id="manualRouteConfirmTitle">담당자에게 전달할까요?' in source
    assert 'data-manual-route-confirm-submit' in source
    assert 'document.body.addEventListener("htmx:confirm"' in source
    assert '!source.matches("[data-manual-route-button], [data-work-complete-button], [data-mail-delete-button]")' in source
    assert 'issueRequest(true)' in source
    assert 'title: "업무를 완료할까요?"' in source
    assert 'submitLabel: "업무 완료"' in source
    assert 'title: "메일을 삭제할까요?"' in source
    assert 'variant: "danger"' in source

def test_postgres_mail_row_manual_route_failed_state_allows_retry():
    service = object.__new__(PostgresMailboxService)

    row = service._message_row(
        {
            "id": RUN_PAYLOAD["email_message_id"],
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "subject": "Assigned RFQ",
            "snippet": "Please review",
            "sent_at": "2026-08-10T01:00:00+00:00",
            "received_at": "2026-08-10T01:00:00+00:00",
            "has_attachment": False,
            "attachment_count": 0,
            "mail_category": "문의",
            "category_source": "ai",
            "routing_status": "assigned",
            "assignee_user_id": "10000000-0000-0000-0000-000000000001",
            "assignee_name": "김민수",
            "assignee_email": "minsu.kim@example.invalid",
            "manual_route_status": "failed",
            "manual_route_error": "Gmail send failed",
        },
        0,
    )

    assert row["manual_route_status"] == "failed"
    assert row["manual_route_status_label"] == "전달 실패"
    assert row["manual_route_button_label"] == "재전달"
    assert row["manual_route_button_variant"] == "failed"
    assert row["manual_route_button_title"] == "Gmail send failed"

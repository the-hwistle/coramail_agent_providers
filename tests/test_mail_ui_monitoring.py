# ruff: noqa: F403, F405
from tests.ui_test_support import *  # noqa: F401,F403

def test_assignee_view_derives_category_priority_from_capabilities():
    view = PostgresAssigneeAdminRepository._view(
        {
            "id": "10000000-0000-0000-0000-000000000001",
            "name": "김민수",
            "email": "m.kim@example.invalid",
            "status": "active",
            "notification_preferences": {},
            "business_types": ["quotation_request", "general_inquiry"],
            "business_type_priorities": [
                {"capability_value": "quotation_request", "priority": 7},
                {"capability_value": "general_inquiry", "priority": 3},
            ],
        }
    )

    assert view["mail_categories"] == ["문의"]
    assert view["category_priorities"] == {"문의": 3}

def test_settings_routing_reorder_persists_category_order(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "settings_context", lambda: {**server.ui_globals(), "category_order": ["문의", "미분류"], "route_assignments": []})
    monkeypatch.setattr(
        server._postgres_assignee_admin_repository,
        "reorder_category_assignees",
        lambda category, assignee_ids: calls.append((category, [str(item) for item in assignee_ids])),
    )

    response = asyncio.run(
        server.ui_settings_routing_reorder(
            request_with_body(
                "POST",
                "/ui/settings/routing-summary/reorder",
                b"category=%EB%AC%B8%EC%9D%98&assignee_ids=10000000-0000-0000-0000-000000000002&assignee_ids=10000000-0000-0000-0000-000000000001",
            )
        )
    )

    assert response.status_code == 200
    assert calls == [
        (
            "문의",
            [
                "10000000-0000-0000-0000-000000000002",
                "10000000-0000-0000-0000-000000000001",
            ],
        )
    ]

def test_shell_allows_drag_from_routing_assignee_name_and_sends_category():
    source = (
        Path("app/templates/shell.html").read_text()
        + Path("app/templates/partials/shell_runtime.html").read_text()
    )

    assert 'return Boolean(chip && !target.closest("[data-routing-active-toggle]"));' in source
    assert 'params.append("category", list.dataset.routingLabel || "");' in source

def test_auto_assignment_policy_partial_renders_current_thresholds():
    html = server.templates.get_template("partials/auto_assignment_policy.html").render(
        **server.ui_globals(),
        routing_policy=RoutingPolicySettings(
            auto_assign_threshold=0.64,
            minimum_margin=0.11,
            minimum_classification_confidence=0.73,
        ),
        routing_policy_message="저장됨",
        routing_policy_error="",
    )

    assert "저장됨" in html
    assert 'name="auto_assign_threshold"' in html
    assert 'value="0.64"' in html
    assert 'name="minimum_margin"' in html
    assert 'value="0.11"' in html
    assert 'name="minimum_classification_confidence"' in html
    assert 'value="0.73"' in html

def test_email_detail_renders_mail_decision_latest_lazy_load():
    html = server.templates.get_template("partials/email_detail.html").render(
        **server.ui_globals(),
        email={
            "index": 0,
            "email_uid": RUN_PAYLOAD["email_message_id"],
            "subject": "Synthetic request",
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "classification": {},
            "attachments": [],
        },
        related_emails=[],
        customer_history=[],
        classify_regenerate_state="ready",
        classification_regeneration={},
        summary_regenerate_state="ready",
        summary_regeneration={},
        attachment_reanalysis={},
        mail_decision={},
    )

    assert "Mail Decision" in html
    assert f"/ui/emails/{RUN_PAYLOAD['email_message_id']}/mail-decision-runs/latest" in html
    assert f'hx-post="/ui/emails/{RUN_PAYLOAD["email_message_id"]}/mail-decision-runs"' not in html
    assert 'hx-target="#mail-decision-panel"' not in html
    assert "route-now-btn--ready" not in html
    assert "재배정" not in html
    assert 'hx-trigger="load"' in html
    assert "최근 업무 판단 결과를 불러오는 중..." in html

def test_inbox_email_detail_places_work_actions_above_mail_overview_box():
    context = {**server.ui_globals(), "current_user_id": "2e63138e-8f0b-40a7-b35e-0c71d229d432"}
    html = server.templates.get_template("partials/email_detail.html").render(
        **context,
        email={
            "email_uid": RUN_PAYLOAD["email_message_id"],
            "index": 0,
            "subject": "RFQ",
            "sender_name": "Buyer",
            "sender_address": "buyer@example.com",
            "assignee_user_id": "2e63138e-8f0b-40a7-b35e-0c71d229d432",
            "classification": {},
            "attachments": [],
        },
        related_emails=[],
        customer_history=[],
        classify_regenerate_state="ready",
        classification_regeneration={},
        summary_regenerate_state="ready",
        summary_regeneration={},
        attachment_reanalysis={},
        mail_decision={},
    )

    detail_head = html.split('<div class="detail-head">', 1)[1].split('<div class="detail-layout">', 1)[0]
    analysis_before_overview = html.split('<section class="analysis-stack">', 1)[1].split('<div class="panel mail-overview-panel">', 1)[0]
    mail_overview = html.split('<div class="panel mail-overview-panel">', 1)[1].split('<div class="panel mail-decision-inspector">', 1)[0]

    assert "detail-delete-btn" in detail_head
    assert "detail-favorite-toggle" in detail_head
    assert "t-like-star" in detail_head
    assert "work-progress-toggle" in detail_head
    assert "t-toggle work-progress-toggle" in detail_head
    assert "data-work-in-progress-toggle" in detail_head
    assert "t-toggle-thumb" in detail_head
    assert 'role="switch"' in detail_head
    assert "답장" in detail_head
    assert "업무 완료" in detail_head
    assert detail_head.index("data-work-in-progress-toggle") < detail_head.index("reply-initiate")
    assert detail_head.index("reply-initiate") < detail_head.index("work/complete")
    assert detail_head.index("work/complete") < detail_head.index("detail-delete-btn")
    assert "mail-overview-action-bar" not in analysis_before_overview
    assert "data-work-in-progress-toggle" not in analysis_before_overview
    assert f'action="/ui/emails/{RUN_PAYLOAD["email_message_id"]}/work/reply-initiate"' not in analysis_before_overview
    assert f'hx-post="/ui/emails/{RUN_PAYLOAD["email_message_id"]}/work/complete"' not in analysis_before_overview
    assert "답장" not in mail_overview
    assert "업무 완료" not in mail_overview

def test_email_detail_body_frame_allows_content_height_measurement():
    html = server.templates.get_template("partials/email_detail.html").render(
        **server.ui_globals(),
        email={
            "index": 0,
            "email_uid": RUN_PAYLOAD["email_message_id"],
            "subject": "Synthetic request",
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "classification": {},
            "attachments": [],
            "body_html_srcdoc": "<p>본문</p>",
        },
        related_emails=[],
        customer_history=[],
        classify_regenerate_state="ready",
        classification_regeneration={},
        summary_regenerate_state="ready",
        summary_regeneration={},
        attachment_reanalysis={},
        mail_decision={},
    )

    assert 'class="email-body-frame"' in html
    assert 'sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"' in html
    assert 'scrolling="no"' in html

def test_email_detail_omits_attachment_details_when_no_extracted_information():
    html = server.templates.get_template("partials/email_detail.html").render(
        **server.ui_globals(),
        email={
            "index": 0,
            "email_uid": RUN_PAYLOAD["email_message_id"],
            "subject": "Synthetic request",
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "classification": {},
            "attachment_count": 1,
            "attachments": [
                {
                    "attachment_uid": "attachment-1",
                    "filename": "photo.png",
                    "preview_kind": "image",
                    "document_category_label": "현장 사진",
                    "size_label": "10 KB",
                    "exists": True,
                    "view_url": "/api/emails/email-1/attachments/0",
                    "download_url": "/api/emails/email-1/attachments/0?download=true",
                    "analysis_rows": [],
                }
            ],
        },
        related_emails=[],
        customer_history=[],
        classify_regenerate_state="ready",
        classification_regeneration={},
        summary_regenerate_state="ready",
        summary_regeneration={},
        attachment_reanalysis={},
        mail_decision={},
    )

    assert '<details class="attachment"' not in html
    assert 'class="attachment attachment--static"' in html
    assert "Details" not in html
    assert "표시할 정보 추출 결과가 없습니다." not in html
    assert "photo.png" in html
    assert "현장 사진" in html

def test_email_detail_keeps_attachment_details_for_business_extracted_information():
    html = server.templates.get_template("partials/email_detail.html").render(
        **server.ui_globals(),
        email={
            "index": 0,
            "email_uid": RUN_PAYLOAD["email_message_id"],
            "subject": "Synthetic request",
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "classification": {},
            "attachment_count": 1,
            "attachments": [
                {
                    "attachment_uid": "attachment-1",
                    "filename": "quote.pdf",
                    "preview_kind": "pdf",
                    "document_category_label": "견적서",
                    "exists": True,
                    "view_url": "/api/emails/email-1/attachments/0",
                    "download_url": "/api/emails/email-1/attachments/0?download=true",
                    "analysis_rows": [{"label": "Our Ref No", "value": "FM250016318"}],
                }
            ],
        },
        related_emails=[],
        customer_history=[],
        classify_regenerate_state="ready",
        classification_regeneration={},
        summary_regenerate_state="ready",
        summary_regeneration={},
        attachment_reanalysis={},
        mail_decision={},
    )

    assert '<details class="attachment"' in html
    assert html.index("견적서") < html.index("attachment-toggle")
    assert "Details" in html
    assert "거래처측 업무번호" in html
    assert "FM250016318" in html

def test_email_detail_polishes_demo_summary_key_request_for_screenshots():
    html = server.templates.get_template("partials/email_detail.html").render(
        **server.ui_globals(),
        email={
            "index": 0,
            "email_uid": RUN_PAYLOAD["email_message_id"],
            "subject": "[견적서 송부] 산업용 네트워크 장비 및 전원모듈",
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "classification": {
                "mail_category": "문의",
                "business_refs": ["QT-2026-0812-03"],
                "summary": (
                    "견적서 송부 QT-2026-0812-03 QT-2026-0812-03 "
                    "견적서 유효기간·납기·합계금액 확인 후 발주 가능 여부 또는 수정 요청 사항 회신"
                ),
            },
            "assignee_name": "김민수",
            "attachment_count": 0,
            "attachments": [],
        },
        related_emails=[],
        customer_history=[],
        classify_regenerate_state="ready",
        classification_regeneration={},
        summary_regenerate_state="ready",
        summary_regeneration={},
        attachment_reanalysis={},
        mail_decision={},
    )

    assert "견적서 송부 QT-2026-0812-03" not in html
    assert "QT-2026-0812-03 QT-2026-0812-03" not in html
    assert "QT-2026-0812-03 견적서 유효기간·납기·합계금액 확인 후 발주 가능 여부 또는 수정 요청 사항 회신" in html
    assert html.index("<td>카테고리</td>") < html.index("<td>담당자</td>")
    assert html.index("<td>담당자</td>") < html.index("<td>핵심 요청</td>")
    assert html.index("<td>핵심 요청</td>") < html.index("<td>업무번호</td>")
    assert 'data-copy-business-ref="QT-2026-0812-03"' in html
    assert 'aria-label="업무번호 QT-2026-0812-03 복사"' in html
    assert "Ref QT-2026-0812-03" not in html
    assert "QT-2026-0812-03" in html
    assert "<h3>Summary</h3>" not in html
    assert "mail-overview-body" not in html
    assert "executive-summary-list--overview" not in html

def test_email_detail_renders_attachment_line_items_as_field_grid():
    html = server.templates.get_template("partials/email_detail.html").render(
        **server.ui_globals(),
        email={
            "index": 0,
            "email_uid": RUN_PAYLOAD["email_message_id"],
            "subject": "Synthetic request",
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "classification": {},
            "attachment_count": 1,
            "attachments": [
                {
                    "attachment_uid": "attachment-1",
                    "filename": "quote.pdf",
                    "preview_kind": "pdf",
                    "document_category_label": "견적서",
                    "exists": True,
                    "view_url": "/api/emails/email-1/attachments/0",
                    "download_url": "/api/emails/email-1/attachments/0?download=true",
                    "analysis_rows": [
                        {
                            "label": "품목 1",
                            "value": "O-RING 5 EA 1,000 5,000",
                            "kind": "line_item",
                            "columns": [
                                {"label": "Description", "value": "O-RING"},
                                {"label": "Qty", "value": "5"},
                                {"label": "Unit", "value": "EA"},
                                {"label": "U/Price", "value": "1,000"},
                                {"label": "Amount", "value": "5,000"},
                            ],
                        }
                    ],
                }
            ],
        },
        related_emails=[],
        customer_history=[],
        classify_regenerate_state="ready",
        classification_regeneration={},
        summary_regenerate_state="ready",
        summary_regeneration={},
        attachment_reanalysis={},
        mail_decision={},
    )

    assert 'class="attachment-line-item-row"' in html
    assert 'colspan="2"' in html
    assert "품목 1" in html
    assert "Description" in html
    assert "Qty" in html
    assert "Unit" in html
    assert "U/Price" in html
    assert "Amount" in html
    assert "O-RING" in html
    assert "Description O-RING / Qty 5" not in html

def test_email_detail_renders_rfq_line_items_with_compact_no_column():
    html = server.templates.get_template("partials/email_detail.html").render(
        **server.ui_globals(),
        email={
            "index": 0,
            "email_uid": RUN_PAYLOAD["email_message_id"],
            "subject": "Synthetic RFQ",
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "classification": {},
            "attachment_count": 1,
            "attachments": [
                {
                    "attachment_uid": "attachment-1",
                    "filename": "rfq.pdf",
                    "preview_kind": "pdf",
                    "document_type": "rfq",
                    "document_category_label": "견적의뢰서",
                    "exists": True,
                    "view_url": "/api/emails/email-1/attachments/0",
                    "download_url": "/api/emails/email-1/attachments/0?download=true",
                    "analysis_rows": [
                        {
                            "label": "품목 1",
                            "value": "1 FILTER ELEMENT FE-100 20 EA",
                            "kind": "line_item",
                            "columns": [
                                {"label": "No", "value": "1"},
                                {"label": "Description", "value": "FILTER ELEMENT"},
                                {"label": "Code", "value": "FE-100"},
                                {"label": "Qty", "value": "20"},
                                {"label": "Unit", "value": "EA"},
                            ],
                        }
                    ],
                }
            ],
        },
        related_emails=[],
        customer_history=[],
        classify_regenerate_state="ready",
        classification_regeneration={},
        summary_regenerate_state="ready",
        summary_regeneration={},
        attachment_reanalysis={},
        mail_decision={},
    )

    assert "attachment-line-item-grid--rfq" in html
    assert "No" in html
    assert "FILTER ELEMENT" in html
    assert "FE-100" in html

def test_email_detail_attachment_line_item_grid_prevents_unit_price_overlap():
    css = _app_css_source()

    assert "grid-template-columns: minmax(72px, 24%) minmax(0, 1fr);" in css
    assert "grid-template-columns: minmax(112px, 1.8fr) minmax(40px, .44fr) minmax(44px, .46fr) minmax(82px, .9fr) minmax(82px, .9fr);" in css
    assert "grid-template-columns: minmax(24px, .24fr) minmax(220px, 2.7fr) minmax(112px, 1.1fr) minmax(36px, .36fr) minmax(48px, .5fr);" in css
    assert "width: 100%;" in css
    assert "word-break: break-word;" in css
    assert ".attachment-line-item-grid {\n    overflow-x: auto;\n  }" in css
    assert "width: 24%;" in css
    assert "width: 34%;" not in css

def test_email_detail_keeps_mail_overview_and_decision_panels_separate():
    html = server.templates.get_template("partials/email_detail.html").render(
        **server.ui_globals(),
        email={
            "index": 0,
            "email_uid": RUN_PAYLOAD["email_message_id"],
            "subject": "Synthetic request",
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "classification": {},
            "attachments": [],
        },
        related_emails=[],
        customer_history=[],
        classify_regenerate_state="ready",
        classification_regeneration={},
        summary_regenerate_state="ready",
        summary_regeneration={},
        attachment_reanalysis={},
        mail_decision={},
    )

    parser = _PanelNestingParser()
    parser.feed(html)

    assert "mail-overview-panel" in html
    assert "mail-decision-inspector" in html
    assert not parser.mail_decision_inside_overview
    assert "<h3>Summary</h3>" not in html
    assert "mail-overview-body" not in html
    assert "<h3>Message</h3>" not in html
    assert html.index("Mail Overview") < html.index("Mail Decision")
    assert "data-attachment-reanalyze-button" not in html
    assert "data-classification-regenerate-button" not in html
    assert "confidence" not in html
    assert 'aria-label="업무 판단 실행"' not in html
    assert "<td>긴급도</td>" not in html

def test_email_detail_omits_empty_assignee_submeta_placeholders():
    html = server.templates.get_template("partials/email_detail.html").render(
        **server.ui_globals(),
        email={
            "index": 0,
            "email_uid": RUN_PAYLOAD["email_message_id"],
            "subject": "Synthetic request",
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "assignee_name": "김민수",
            "classification": {},
            "attachments": [],
        },
        related_emails=[],
        customer_history=[],
        classify_regenerate_state="ready",
        classification_regeneration={},
        summary_regenerate_state="ready",
        summary_regeneration={},
        attachment_reanalysis={},
        mail_decision={},
    )

    assert "김민수" in html
    assert '<div class="info-submeta">' in html
    assert "<span>-</span>" not in html

def test_monitoring_attachment_stage_does_not_treat_downloaded_unclassified_file_as_ready():
    view = server.ops_row_view(
        {
            "email_uid": "email-1",
            "subject": "RFQ",
            "sender_name": "Buyer",
            "classification_state": "completed",
            "summary_state": "completed",
            "mail_decision_status": "completed",
            "routing_status": "assigned",
            "manual_route_status_label": "전달 완료",
            "manual_route_sent_at": "2026-08-10T01:02:00+00:00",
        },
        attachments=[
            {
                "filename": "unknown.pdf",
                "parse_status": "downloaded",
                "document_category_label": "미분류",
            }
        ],
    )

    assert view["attachment"]["state"] == "not_started"
    assert view["attachment"]["label"] == "1개 미분류"
    assert view["pipeline_status"]["state"] == "incomplete"
    assert view["pipeline_class"] == "is-blocked"

def test_dashboard_summary_excludes_unclassified_and_unassigned_rows():
    rows = [
        {
            "mail_category": "미분류",
            "business_label": "미분류",
            "classification_state": "unclassified",
            "classification": {"mail_category": "미분류"},
            "routing_display": "미할당",
        },
        {
            "mail_category": "문의",
            "business_label": "문의",
            "classification_state": "completed",
            "classification": {"mail_category": "문의", "attention_quadrant": "urgent"},
            "attention_quadrant": "urgent",
            "routing_display": "미할당",
            "routing_status": "review_required",
        },
        {
            "mail_category": "발주",
            "business_label": "발주",
            "classification_state": "completed",
            "classification": {"mail_category": "발주", "attention_quadrant": "important"},
            "attention_quadrant": "important",
            "routing_display": "김담당",
            "routing_status": "assigned",
            "assignee_name": "김담당",
            "manual_route_status_label": "전달 완료",
            "manual_route_sent_at": "2026-08-10T01:02:00+00:00",
        },
    ]

    summary = server.dashboard_summary(rows)
    overview = server.routing_overview(rows)

    assert summary["email_count"] == 3
    assert summary["urgent_count"] == 1
    assert summary["today_urgent_count"] == 0
    assert summary["attention_urgent_important_count"] == 0
    assert summary["attention_urgent_count"] == 1
    assert summary["attention_important_count"] == 1
    assert summary["attention_normal_count"] == 1
    assert summary["classified_count"] == 2
    assert summary["unclassified_count"] == 1
    assert summary["routed_count"] == 1
    assert summary["unrouted_count"] == 2
    assert summary["forwarded_count"] == 1
    assert summary["unforwarded_count"] == 2
    assert overview["loaded_count"] == 1
    assert overview["unassigned_count"] == 2
    assert overview["workload_assignees"] == [
        {"label": "김담당", "count": 1, "bar_percent": 100, "bar_display_percent": 100}
    ]

    stats_html = server.templates.get_template("partials/stats.html").render(summary=summary)
    routing_html = server.templates.get_template("partials/dashboard_routing_overview.html").render(
        routing_overview=overview
    )

    assert "Classified" in stats_html
    assert "Urgent Mails" in stats_html
    assert "stat stat-urgent" in stats_html
    assert "오늘 긴급 0건" in stats_html
    assert "Routed" in stats_html
    assert "Forwarded" in stats_html
    assert "Priority Map" not in stats_html
    assert "업무 우선 현황" not in stats_html
    assert "중요도 높음" not in stats_html
    assert "긴급성 높음" not in stats_html
    assert 'data-dashboard-mail-filter-action="attention:urgent_important"' not in stats_html
    assert 'data-dashboard-mail-filter-action="attention:urgent"' not in stats_html
    assert 'data-dashboard-mail-filter-action="attention:important"' not in stats_html
    assert 'data-dashboard-mail-filter-action="attention:normal"' not in stats_html
    assert "긴급O 중요O" not in stats_html
    assert "긴급O 중요X" not in stats_html
    assert "긴급X 중요O" not in stats_html
    assert "긴급 · 중요" not in stats_html
    assert "Mail Streams에 긴급하지만 중요도는 일반인 메일만 표시" not in stats_html
    assert "Mail Streams에 중요하지만 긴급하지 않은 메일만 표시" not in stats_html
    assert "긴급성과 중요도 기준으로 Mail Streams를 탐색합니다." not in stats_html
    assert "즉시 확인 필요" not in stats_html
    assert "빠른 확인 필요" not in stats_html
    assert "계획적으로 확인" not in stats_html
    assert "일반 업무" not in stats_html
    assert "분류 요망 1건" in stats_html
    assert "배정 요망 2건" in stats_html
    assert "전달 요망 2건" in stats_html
    assert "AI Auto-Classified" not in stats_html
    assert "AI Auto-Routed" not in stats_html
    assert "routing-overview-metric" not in routing_html
    assert "Assigned" not in routing_html
    assert "Unassigned" not in routing_html

def test_dashboard_mail_stat_filters_select_today_and_urgent_rows(monkeypatch):
    rows = [
        {
            "email_uid": "today-normal",
            "mail_category": "문의",
            "classification": {"mail_category": "문의"},
            "date": "2026-08-10T01:00:00+00:00",
        },
        {
            "email_uid": "today-urgent",
            "mail_category": "문의",
            "classification": {"mail_category": "문의", "attention_quadrant": "urgent"},
            "attention_quadrant": "urgent",
            "date": "2026-08-10T02:00:00+00:00",
        },
        {
            "email_uid": "older-urgent",
            "mail_category": "문의",
            "classification": {"mail_category": "문의", "attention_quadrant": "urgent"},
            "attention_quadrant": "urgent",
            "date": "2026-08-09T01:00:00+00:00",
        },
    ]

    monkeypatch.setattr(server, "demo_mode_enabled", lambda: True)

    assert [row["email_uid"] for row in server.filter_dashboard_mail_rows(rows, "today")] == [
        "today-normal",
        "today-urgent",
    ]
    assert [row["email_uid"] for row in server.filter_dashboard_mail_rows(rows, "urgent")] == [
        "today-urgent",
        "older-urgent",
    ]
    assert [row["email_uid"] for row in server.filter_dashboard_mail_rows(rows, "today,urgent")] == [
        "today-urgent",
    ]

def test_dashboard_attention_matrix_counts_and_filters_by_quadrant_only():
    rows = [
        {"email_uid": "urgent-important", "attention_quadrant": "urgent_important"},
        {"email_uid": "urgent", "classification": {"attention_quadrant": "urgent"}},
        {"email_uid": "important", "attention_quadrant": "important"},
        {"email_uid": "normal", "attention_quadrant": "normal"},
        {"email_uid": "missing"},
    ]

    summary = server.dashboard_summary(rows)

    assert summary["urgent_count"] == 2
    assert summary["attention_urgent_important_count"] == 1
    assert summary["attention_urgent_count"] == 1
    assert summary["attention_important_count"] == 1
    assert summary["attention_normal_count"] == 2
    assert [row["email_uid"] for row in server.filter_dashboard_mail_rows(rows, "attention:urgent")] == [
        "urgent"
    ]
    assert [row["email_uid"] for row in server.filter_dashboard_mail_rows(rows, "attention:normal")] == [
        "normal",
        "missing",
    ]

def test_dashboard_stats_cards_filter_mail_stream_rows():
    summary = {
        "email_count": 3,
        "today_email_count": 2,
        "urgent_count": 1,
        "today_urgent_count": 1,
        "classified_count": 2,
        "unclassified_count": 1,
        "routed_count": 1,
        "unrouted_count": 2,
        "forwarded_count": 1,
        "unforwarded_count": 2,
    }

    stats_html = server.templates.get_template("partials/stats.html").render(summary=summary)

    assert 'data-dashboard-mail-filter-action="today"' in stats_html
    assert 'data-dashboard-mail-filter-action="urgent"' in stats_html
    assert 'data-dashboard-mail-filter-action="attention:' not in stats_html
    assert 'aria-pressed="false"' in stats_html
    assert 'aria-label="Mail Streams에 오늘 수신 메일만 표시"' in stats_html
    assert 'aria-label="Mail Streams에 긴급 메일만 표시"' in stats_html
    assert "오늘 긴급 1건" in stats_html

def test_dashboard_stats_do_not_render_attention_matrix_from_rows():
    stats_html = server.templates.get_template("partials/stats.html").render(
        summary={
            "email_count": 4,
            "today_email_count": 4,
            "classified_count": 4,
            "routed_count": 4,
            "forwarded_count": 0,
            "attachment_count": 0,
            "mail_categories": {},
            "business_labels": {},
        },
        emails=[
            {"attention_quadrant": "urgent_important"},
            {"classification": {"attention_quadrant": "urgent"}},
            {"attention_quadrant": "important"},
            {"email_uid": "missing-attention"},
        ],
    )

    assert "Priority Map" not in stats_html
    assert "attention-matrix" not in stats_html
    assert 'data-dashboard-mail-filter-action="attention:' not in stats_html
    assert "긴급O" not in stats_html
    assert "중요O" not in stats_html

def test_dashboard_urgent_stat_uses_danger_tone():
    css = _app_css_source()
    urgent_card_css = css.split(".dashboard-view .stat-urgent {", 1)[1].split("}", 1)[0]

    assert ".dashboard-view .stat-urgent" in css
    assert "background:" not in urgent_card_css
    assert "border-color: rgba(239, 68, 68, 0.28);" in css
    assert ".dashboard-view .stat-urgent.is-active" in css
    assert ".dashboard-view button.stat:hover" not in css
    assert ".dashboard-view button.stat-action.is-active:hover" in css
    assert ".dashboard-view button.stat-urgent.is-active:hover" in css
    assert "border-color: #dc2626;" in css
    assert "inset 0 0 0 2px #dc2626" in css
    assert "inset 0 0 0 2px #2563eb" in css
    assert ".dashboard-view .stat-urgent .label,\n.dashboard-view .stat-urgent .stat-line strong" in css
    assert ".dashboard-view .stat-urgent .stat-line .material-symbols-outlined" in css
    assert "color: #dc2626;" in css

def test_dashboard_stat_helper_text_uses_readable_tone():
    css = _app_css_source()
    stat_css = css.split(".dashboard-view .stat {", 1)[1].split("}", 1)[0]
    stat_value_css = css.split(".dashboard-view .stat-line strong {", 1)[1].split("}", 1)[0]
    stat_label_css = css.split(".dashboard-view .stat .label {", 1)[1].split("}", 1)[0]
    helper_text_css = css.split(".dashboard-view .stat p {", 1)[1].split("}", 1)[0]

    assert "min-height: 88px;" in stat_css
    assert "font-size: 30px;" in stat_value_css
    assert "font-size: 12px;" in stat_label_css
    assert "color: #475569;" in helper_text_css
    assert "font-size: 13px;" in helper_text_css

def test_dashboard_stats_top_row_does_not_include_attention_matrix_css():
    css = _app_css_source()

    stats_priority_css = css.split(".dashboard-view #stats .stats-priority-row {", 1)[1].split("}", 1)[0]
    assert "grid-template-columns: 1fr;" in stats_priority_css
    assert "minmax(420px" not in stats_priority_css
    assert "grid-template-columns: repeat(6, minmax(0, 1fr));" in css
    assert "grid-template-columns: repeat(7, minmax(0, 1fr));" in css
    assert "attention-matrix" not in css

def test_dashboard_typography_keeps_table_and_auxiliary_areas_compact():
    css = _app_css_source()
    table_cell_css = css.rsplit(".dashboard-mail-table tbody td {", 1)[1].split("}", 1)[0]
    table_header_css = css.rsplit(".dashboard-mail-table thead th {", 1)[1].split("}", 1)[0]
    route_button_css = css.rsplit(".dashboard-mail-table tbody .route-now-btn {", 1)[1].split("}", 1)[0]
    mobile_css = css.split("@media (max-width: 640px)", 1)[1]

    assert "font-size: 14px;" in table_cell_css
    assert "line-height: 18px;" in table_cell_css
    assert "font-size: 11px;" in table_header_css
    assert "line-height: 14px;" in table_header_css
    assert "height: 28px;" in route_button_css
    assert "font-size: 12px;" in route_button_css
    assert "grid-template-columns: repeat(6, minmax(144px, 1fr));" in mobile_css

def test_non_dashboard_tabs_use_readable_typography_scale():
    css = _app_css_source()
    non_dashboard_css = css.split("/* Non-dashboard typography scale */", 1)[1].split(".mono {", 1)[0]

    for selector in [
        ".inbox-view",
        ".ops-view",
        ".assignee-work-view",
        ".document-types-view",
        ".search-view",
        ".chats-view",
        ".settings-view",
        ".evaluation-view",
        ".evaluation-case-view",
    ]:
        assert selector in non_dashboard_css

    assert "font-size: 14px;" in non_dashboard_css
    assert "font-size: 17px;" in non_dashboard_css
    assert "font-size: 11px;" in non_dashboard_css
    assert "font-size: 12px;" in non_dashboard_css

def test_non_dashboard_typography_protects_dense_layouts():
    css = _app_css_source()
    inbox_table_css = css.rsplit(".inbox-list table {", 1)[1].split("}", 1)[0]
    ops_table_css = css.rsplit(".ops-table {", 1)[1].split("}", 1)[0]
    ops_health_col_css = css.rsplit(".ops-health-col {", 1)[1].split("}", 1)[0]
    ops_subject_col_css = css.rsplit(".ops-subject-col {", 1)[1].split("}", 1)[0]
    ops_stage_pill_css = css.rsplit(".ops-stage-pill {", 1)[1].split("}", 1)[0]
    settings_table_css = css.rsplit(".settings-view .routing-table {", 1)[1].split("}", 1)[0]
    assignee_table_css = css.rsplit(".assignee-mail-table {", 1)[1].split("}", 1)[0]
    inbox_mobile_css = css.rsplit("@media (max-width: 900px)", 1)[1].split("@media (max-width: 640px)", 1)[0]

    assert "min-width: 822px;" in inbox_table_css
    assert "min-width: 1812px;" in ops_table_css
    assert "width: 64px;" in ops_health_col_css
    assert "width: 450px;" in ops_subject_col_css
    assert "min-height: 24px;" in ops_stage_pill_css
    assert "min-width: 1100px;" in settings_table_css
    assert "min-width: 760px;" in assignee_table_css
    assert "min-width: 720px;" in inbox_mobile_css

def test_my_work_large_regions_keep_fixed_frame_height():
    css = _app_css_source()
    layout_css = css.split(".assignee-work-layout {", 1)[1].split("}", 1)[0]
    panel_css = css.rsplit(".work-queue-rail,\n.assignee-next-panel,\n.assignee-mail-panel {", 1)[1].split("}", 1)[0]
    table_wrap_css = css.split(".assignee-mail-table-wrap {", 1)[1].split("}", 1)[0]
    next_panel_css = css.split(".assignee-next-panel {", 1)[1].split("}", 1)[0]

    assert "height: clamp(540px, calc(100vh - 278px), 760px);" in layout_css
    assert "height: 100%;" in panel_css
    assert "overflow: hidden;" in panel_css
    assert "height: 100%;" in table_wrap_css
    assert "overflow: auto;" in table_wrap_css
    assert "overflow: auto;" in next_panel_css

def test_inbox_detail_overview_and_decision_tables_share_field_spacing():
    css = _app_css_source()
    info_table_cell_css = css.split(".info-table td {", 1)[1].split("}", 1)[0]
    overview_table_css = css.rsplit(".inbox-detail-panel .mail-overview-panel > .info-table {", 1)[1].split("}", 1)[0]
    field_label_css = css.rsplit(".inbox-detail-panel .mail-overview-panel > .info-table td:first-child,", 1)[1].split("}", 1)[0]
    decision_body_css = css.rsplit(".inbox-detail-panel .mail-decision-inspector > .panel-body {", 1)[1].split("}", 1)[0]
    detail_action_row_css = css.rsplit(".detail-action-row {", 1)[1].split("}", 1)[0]
    overview_actions_css = css.rsplit(".mail-overview-actions {", 1)[1].split("}", 1)[0]
    overview_action_bar_css = css.rsplit(".mail-overview-action-bar {", 1)[1].split("}", 1)[0]
    overview_action_form_css = css.rsplit(".mail-overview-action-form {", 1)[1].split("}", 1)[0]

    assert "vertical-align: middle;" in info_table_cell_css
    assert "width: calc(100% - 32px);" in overview_table_css
    assert "margin: 0 16px 16px;" in overview_table_css
    assert ".inbox-detail-panel .mail-decision-summary > .info-table td:first-child" in field_label_css
    assert "padding-right: 16px;" in field_label_css
    assert "padding: 0 16px 16px;" in decision_body_css
    assert "width: 100%;" in detail_action_row_css
    assert "justify-content: flex-end;" in overview_actions_css
    assert "padding: 0;" in overview_action_bar_css
    assert "display: inline-flex;" in overview_action_form_css
    assert "margin: 0;" in overview_action_form_css

def test_search_and_settings_typography_refinement_targets_core_elements():
    css = _app_css_source()
    refinement_css = css.split("/* Search and Settings typography refinement */", 1)[1].split(".mono {", 1)[0]
    search_input_css = refinement_css.split(".search-view #searchQueryInput {", 1)[1].split("}", 1)[0]
    search_body_css = refinement_css.split(".search-view .prose,", 1)[1].split("}", 1)[0]
    settings_table_css = refinement_css.split(".settings-view .routing-table {", 1)[1].split("}", 1)[0]
    settings_input_css = refinement_css.split(".settings-view .routing-table .input,", 1)[1].split("}", 1)[0]

    assert "min-height: 46px;" in search_input_css
    assert "font-size: 16px;" in search_input_css
    assert "font-size: 14px;" in search_body_css
    assert "min-width: 1100px;" in settings_table_css
    assert "min-height: 40px;" in settings_input_css
    assert "font-size: 14px;" in settings_input_css

def test_monitoring_typography_refinement_keeps_rows_dense():
    css = _app_css_source()
    refinement_css = css.split("/* Monitoring typography refinement */", 1)[1].split(".mono {", 1)[0]
    table_header_css = refinement_css.rsplit(".ops-table th {", 1)[1].split("}", 1)[0]
    table_cell_css = refinement_css.rsplit(".ops-table td {", 1)[1].split("}", 1)[0]
    decision_col_css = refinement_css.rsplit(".ops-decision-col {", 1)[1].split("}", 1)[0]
    stage_cell_css = refinement_css.rsplit(".ops-stage-cell {", 1)[1].split("}", 1)[0]
    subject_css = refinement_css.split(".ops-subject-button strong {", 1)[1].split("}", 1)[0]
    stage_pill_css = refinement_css.split(".ops-stage-pill {", 1)[1].split("}", 1)[0]
    column_head_css = css.split(".ops-column-head {", 1)[1].split("}", 1)[0]
    detail_actions_css = css.split(".ops-detail-actions {", 1)[1].split("}", 1)[0]
    action_button_css = refinement_css.split(".ops-refresh-btn,", 1)[1].split("}", 1)[0]

    assert "font-size: 12px;" in table_header_css
    assert "line-height: 15px;" in table_header_css
    assert "text-align: center;" in table_header_css
    assert "font-size: 13px;" in table_cell_css
    assert "line-height: 17px;" in table_cell_css
    assert "text-align: center;" in table_cell_css
    assert "width: 184px;" in decision_col_css
    assert "text-align: center;" in stage_cell_css
    assert "font-size: 14px;" in subject_css
    assert "line-height: 18px;" in subject_css
    assert "min-height: 24px;" in stage_pill_css
    assert "font-size: 12px;" in stage_pill_css
    assert "justify-content: center;" in column_head_css
    assert "justify-content: flex-end;" in detail_actions_css
    assert "width: 24px;" in action_button_css
    assert "height: 24px;" in action_button_css

def test_monitoring_columns_are_resizable_from_headers_only():
    html = server.templates.get_template("views/ops.html").render(
        **server.ops_console_context(),
        request=request(),
        active_view="monitoring",
    )
    source = Path("app/templates/partials/shell_runtime.html").read_text(encoding="utf-8")
    css = _app_css_source()

    assert 'data-monitoring-column-resizer="subject"' in html
    assert 'data-monitoring-column-resizer="sender"' in html
    assert 'data-monitoring-column-resizer="forwarding"' not in html
    assert "data-monitoring-column-resizer" not in server.templates.get_template("partials/ops_rows.html").render(
        **server.ops_console_context(),
        request=request(),
        active_view="monitoring",
    )
    assert "coramail.monitoring.columnWidths.v1" in source
    assert "function initMonitoringColumnResize(view)" in source
    assert "function updateMonitoringTerminalColumn(view)" in source
    assert "function nextVisibleMonitoringColumnKey(header)" in source
    assert 'header.classList.contains("is-terminal-visible-column")' in source
    assert 'table.closest(".ops-table-wrap")' in source
    assert "Math.max(visibleWidth, frameWidth)" in source
    assert 'table.style.minWidth = visibleWidth + "px";' in source
    assert "widths[nextKey]" in source
    assert 'table.querySelectorAll("col[data-monitoring-column]")' in source
    assert 'handle.addEventListener("pointerdown"' in source
    assert "cursor: col-resize;" in css
    assert ".ops-table th.is-terminal-visible-column .ops-column-resizer" in css

def test_monitoring_columns_can_be_reordered_except_status_column():
    source = Path("app/templates/partials/shell_runtime.html").read_text(encoding="utf-8")
    css = _app_css_source()

    assert "coramail.monitoring.columnOrder.v1" in source
    assert "function monitoringColumnOrderDefaults()" in source
    assert '"health",' in source
    assert 'return ["health"].concat(ordered);' in source
    assert "function applyMonitoringColumnOrder(view)" in source
    assert 'appendOrdered(table.querySelector("colgroup"), "col");' in source
    assert 'appendOrdered(table.querySelector("thead tr"), "th");' in source
    assert 'appendOrdered(row, "td");' in source
    assert "function initMonitoringColumnReorder(view)" in source
    assert 'key === "health"' in source
    assert 'targetKey === "health"' in source
    assert 'longPressTimer = window.setTimeout(activate, 320);' in source
    assert 'initMonitoringColumnReorder(view);' in source
    assert "cursor: grab;" in css
    assert "cursor: grabbing;" in css
    assert ".ops-table.is-column-reordering" in css

def test_demo_dashboard_context_exposes_today_and_all_chart_scopes(monkeypatch):
    rows = [
        {
            "date": "2026-08-12T09:24:00+09:00",
            "mail_category": "문의",
            "business_label": "문의",
            "classification_state": "completed",
            "classification": {"mail_category": "문의"},
            "routing_display": "김민수",
            "assignee_name": "김민수",
            "routing_status": "assigned",
        },
        {
            "date": "2026-08-12T08:10:00+09:00",
            "mail_category": "발주",
            "business_label": "발주",
            "classification_state": "completed",
            "classification": {"mail_category": "발주"},
            "routing_display": "미할당",
            "routing_status": "review_required",
        },
        {
            "date": "2026-08-11T17:46:00+09:00",
            "mail_category": "서비스",
            "business_label": "서비스",
            "classification_state": "completed",
            "classification": {"mail_category": "서비스"},
            "routing_display": "이서연",
            "assignee_name": "이서연",
            "routing_status": "assigned",
        },
    ]
    token = server._display_demo_mode.set(True)
    try:
        monkeypatch.setattr(server, "mail_rows", lambda **_: rows)
        monkeypatch.setattr(
            server,
            "mail_service",
            lambda: type("Service", (), {"category_order": lambda self: ["발주", "문의", "서비스"]})(),
        )
        context = server.dashboard_context()
    finally:
        server._display_demo_mode.reset(token)

    assert context["dashboard_scope_toggle_enabled"] is True
    assert context["summary"]["email_count"] == 3
    assert context["category_distribution"]["email_count"] == 2
    assert context["category_distribution_all"]["email_count"] == 3
    assert context["routing_overview"]["total"] == 2
    assert context["routing_overview_all"]["total"] == 3

    distribution_html = server.templates.get_template("partials/dashboard_distribution.html").render(
        **context,
        request=request(),
    )
    routing_html = server.templates.get_template("partials/dashboard_routing_overview.html").render(
        **context,
        request=request(),
    )

    assert 'data-dashboard-distribution-scope="today"' in distribution_html
    assert 'data-dashboard-distribution-scope="all"' in distribution_html
    assert 'data-chart-total-today="2"' in distribution_html
    assert 'data-chart-total-all="3"' in distribution_html
    assert 'id="categoryDonutTooltip"' in distribution_html
    assert 'aria-hidden="true"' in distribution_html
    assert 'data-dashboard-routing-scope="today"' in routing_html
    assert 'data-dashboard-routing-scope="all"' in routing_html
    assert "총 2건" in routing_html
    assert 'data-dashboard-routing-total="2"' in routing_html
    assert 'data-dashboard-routing-total="3"' in routing_html

def test_assignee_login_dashboard_context_uses_only_assigned_work(monkeypatch):
    now = datetime.now(server.DISPLAY_TIMEZONE)
    rows = [
        {
            "email_uid": "kim-assigned",
            "date": now.isoformat(),
            "mail_category": "문의",
            "business_label": "문의",
            "classification_state": "completed",
            "classification": {"mail_category": "문의", "urgency": {"level": "high"}},
            "urgency": {"level": "high"},
            "routing_display": "김민수",
            "assignee_name": "김민수",
            "assignee_email": "m.kim@dawonict.co.kr",
            "routing_status": "assigned",
            "work_status": "assigned",
            "work_item_due_at": (now - timedelta(days=1)).isoformat(),
        },
        {
            "email_uid": "kim-completed",
            "date": (now - timedelta(days=1)).isoformat(),
            "mail_category": "발주",
            "business_label": "발주",
            "classification_state": "completed",
            "classification": {"mail_category": "발주"},
            "routing_display": "김민수",
            "assignee_name": "김민수",
            "assignee_email": "m.kim@dawonict.co.kr",
            "routing_status": "assigned",
            "work_status": "completed",
            "work_item_completed_at": now.isoformat(),
        },
        {
            "email_uid": "lee-assigned",
            "date": now.isoformat(),
            "mail_category": "서비스",
            "business_label": "서비스",
            "classification_state": "completed",
            "classification": {"mail_category": "서비스"},
            "routing_display": "이서연",
            "assignee_name": "이서연",
            "assignee_email": "lee@dawonict.co.kr",
            "routing_status": "assigned",
            "work_status": "in_progress",
        },
    ]
    monkeypatch.setattr(server, "mail_rows", lambda **_: rows)
    monkeypatch.setattr(server, "auth_cookie_username", lambda _cookie: "m.kim@dawonict.co.kr")
    monkeypatch.setattr(
        server,
        "mail_service",
        lambda: type("Service", (), {"category_order": lambda self: ["발주", "문의", "서비스"]})(),
    )

    context = server.dashboard_context(request())
    stats_html = server.templates.get_template("partials/stats.html").render(**context, request=request())

    assert context["dashboard_work_scope"] is True
    assert context["dashboard_scope_toggle_enabled"] is False
    assert [row["email_uid"] for row in context["emails"]] == ["kim-assigned", "kim-completed"]
    assert context["summary"]["email_count"] == 2
    assert context["summary"]["assigned_work_count"] == 1
    assert context["summary"]["completed_work_count"] == 1
    assert context["summary"]["in_progress_work_count"] == 0
    assert context["summary"]["overdue_work_count"] == 1
    assert context["summary"]["completed_today_work_count"] == 1
    assert context["my_work_aging"]["total"] == 2
    assert context["my_work_aging"]["active_count"] == 1
    assert context["my_work_aging"]["completed_today_count"] == 1
    assert context["my_work_aging"]["overdue_count"] == 1
    assert context["my_work_aging"]["buckets"] == [
        {
            "key": "overdue",
            "label": "기한 초과",
            "count": 1,
            "bar_percent": 100,
            "bar_display_percent": 100,
            "share_percent": 100,
            "share_display_percent": 100,
        },
        {
            "key": "today",
            "label": "오늘 수신",
            "count": 0,
            "bar_percent": 0,
            "bar_display_percent": 0,
            "share_percent": 0,
            "share_display_percent": 0,
        },
        {
            "key": "one_day",
            "label": "1일 경과",
            "count": 0,
            "bar_percent": 0,
            "bar_display_percent": 0,
            "share_percent": 0,
            "share_display_percent": 0,
        },
        {
            "key": "two_three_days",
            "label": "2-3일 경과",
            "count": 0,
            "bar_percent": 0,
            "bar_display_percent": 0,
            "share_percent": 0,
            "share_display_percent": 0,
        },
        {
            "key": "older",
            "label": "4일 이상",
            "count": 0,
            "bar_percent": 0,
            "bar_display_percent": 0,
            "share_percent": 0,
            "share_display_percent": 0,
        },
    ]
    assert context["routing_overview"]["workload_assignees"] == [
        {"label": "김민수", "count": 2, "bar_percent": 100, "bar_display_percent": 100}
    ]
    dashboard_html = server.templates.get_template("views/dashboard.html").render(**context, request=request())
    aging_html = server.templates.get_template("partials/dashboard_my_work_aging.html").render(
        **context,
        request=request(),
    )
    assert "Assigned Work" in stats_html
    assert "배정된 업무" in stats_html
    assert "김민수 담당 업무" not in stats_html
    assert "My Work" not in stats_html
    assert "Unacknowledged" in stats_html
    assert "Overdue" in stats_html
    assert "Work Priority" in dashboard_html
    assert "Routing Overview" not in dashboard_html
    assert "기한 초과" in aging_html
    assert "여유 있음" in aging_html
    assert "기한 초과" in aging_html
    assert "미완료 1건" in aging_html
    assert "오늘 완료 1건" in aging_html
    assert 'hx-post="/ui/my-work"' in stats_html
    assert 'aria-label="담당 업무 화면에서 배정된 업무 현황 확인"' in stats_html
    assert "Total Mails" not in stats_html
    assert 'data-dashboard-mail-filter-action="today"' not in stats_html

def test_routing_overview_renders_every_assignee_visible_in_mail_streams():
    rows = [
        {
            "routing_display": assignee,
            "assignee_name": assignee,
            "routing_status": "forwarded",
        }
        for assignee in ["김민수", "박지현", "최서연", "이준호", "강태훈", "최유진", "정우석"]
    ]
    overview = server.routing_overview(rows)
    html = server.templates.get_template("partials/dashboard_routing_overview.html").render(
        routing_overview=overview,
        routing_overview_all=overview,
        dashboard_scope_toggle_enabled=False,
    )

    assert overview["loaded_count"] == len(rows)
    assert [item["label"] for item in overview["workload_assignees"]] == sorted(
        [row["routing_display"] for row in rows]
    )
    for assignee in rows:
        assert str(assignee["routing_display"]) in html

# ruff: noqa: F403, F405
from tests.ui_test_support import *  # noqa: F401,F403

def test_shell_renders_topbar_display_mode_selector():
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

    assert 'class="mode-selector"' in html
    assert 'class="mode-selector" role="group" aria-label="메일 데이터 소스 선택" data-sliding-tabs' in html
    assert 'class="mode-selector-pill" data-sliding-tabs-pill aria-hidden="true"' in html
    assert html.count("data-sliding-tab") >= 4
    assert 'aria-label="메일 데이터 소스 선택"' in html
    assert 'hx-post="/ui/display-mode/toggle?display_mode=demo"' in html
    assert 'hx-post="/ui/display-mode/toggle?display_mode=gmail"' in html
    assert 'hx-post="/ui/display-mode/toggle?display_mode=naver"' in html
    assert 'hx-post="/ui/display-mode/toggle?display_mode=hiworks"' in html
    assert "mode-option-protocol" not in html
    assert ">Fixture<" not in html
    assert ">API<" not in html
    mode_selector = html.split('<div class="mode-selector"', 1)[1].split("</div>", 1)[0]
    assert ">IMAP<" not in mode_selector
    assert ">POP3<" not in mode_selector
    assert 'aria-pressed="true"' in html
    assert "Evaluation 탭 열기" not in html
    assert "monitoring</span>Evaluation" not in html


def test_react_shell_uses_sliding_display_and_fragment_tabs():
    source = Path("app/static/react/coramail-react.js").read_text(encoding="utf-8")

    assert "function SlidingModeTabs" in source
    assert '"data-sliding-tabs": true' in source
    assert 'className: "mode-selector-pill"' in source
    assert "document.fonts?.ready?.then(snap)" in source
    assert "updateSlidingTabs(root, true)" in source
    assert "function selectInboxRow(row" in source
    assert "function syncInboxSelection(" in source
    assert "centerInboxRow(selectedRow)" in source
    assert "function primeWorkProgressToggle(button)" in source
    assert "function prepareNextWorkProgressToggleValue(button)" in source
    assert "const input = button.closest(\"form\")?.querySelector(\"input[name='active']\");" in source
    assert 'if (input) input.value = button.dataset.on === "true" ? "false" : "true";' in source
    assert "primeWorkProgressToggle(progressToggle)" in source
    assert "prepareNextWorkProgressToggleValue(progressToggle)" in source
    assert "targetFor(trigger)?.id === \"email-detail\"" in source
    assert 'document.getElementById(targetName === "dashboard" ? "dashboardWorkStatusFilter" : "workStatusFilter")' in source
    assert "function LoadingPanel" in source
    assert "setViewLoading(true)" in source
    assert "startTransition" not in source

def test_shell_renders_monitoring_navigation():
    html = server.templates.get_template("shell.html").render(
        **server.ui_globals(),
        request=request(),
        active_view="monitoring",
        initial_view_template="views/ops.html",
        ops_rows=[],
        ops_query="",
        selected_category="",
        ops_summary={},
    )

    assert "Monitoring 탭 열기" in html
    assert 'hx-post="/ui/monitoring"' in html
    assert '"/ui/monitoring": "monitoring"' in html
    assert 'monitoring: "Monitoring"' in html
    assert 'ops: "Monitoring"' in html
    assert "function initMonitoringColumns(root)" in html
    assert "coramail.monitoring.visibleColumns.v1" in html
    assert "data-monitoring-bulk-action" in html
    assert "data-monitoring-row-action" in html
    assert "data-monitoring-bulk-confirm" in html

def test_shell_demo_navigation_prefetches_and_swaps_cached_tabs_immediately():
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

    assert 'hx-post="/ui/inbox" hx-target="#main-panel" hx-swap="innerHTML" hx-sync="#main-panel:replace"' in html
    assert "const demoMainViewCache = {" in html
    assert "function installDemoMainNavigationCache()" in html
    assert 'document.addEventListener("click", function (event) {' in html
    assert "event.stopImmediatePropagation();" in html
    assert "function demoMainViewNodesFromHtml(html)" in html
    assert "target.replaceChildren(...cached.nodes);" in html
    assert "cachedEntry: cached" in html
    assert "prefetchDemoMainViews();" in html
    assert "clearDemoMainViewCache();" in html

def test_shell_replaces_assignments_with_my_work_for_assignee_login(monkeypatch):
    monkeypatch.setattr(server, "auth_cookie_username", lambda _cookie: "m.kim@dawonict.co.kr")

    context = server.assignee_work_context(
        request(),
        work_view_name="my-work",
        work_endpoint="/ui/my-work",
        work_title="My Work",
    )
    html = server.templates.get_template("shell.html").render(
        **context,
        request=request(),
        active_view="my-work",
        initial_view_template="views/assignee_work.html",
    )

    assert 'hx-post="/ui/my-work"' in html
    assert "assignment_ind</span>My Work" in html
    assert "Assignments 탭 열기" not in html
    assert 'data-view="my-work"' in html
    assert '"my-work": "My Work"' in html

def test_shell_closes_open_popovers_on_outside_click():
    source = server.templates.get_template("shell.html").render(
        **server.ui_globals(),
        request=request(),
        active_view="monitoring",
        initial_view_template="views/ops.html",
        ops_rows=[],
        ops_query="",
        selected_category="",
        ops_summary={},
    )

    assert "function closeTransientPopovers(event)" in source
    assert (
        '"details.ops-detail-menu[open], details.ops-column-menu[open], details[data-cc-popover][open]"'
        in source
    )
    assert (
        'details.querySelector(".ops-detail-popover, .ops-attachment-popover, .ops-column-popover, .detail-head-cc-popover")'
        in source
    )
    assert 'details.querySelector("summary")' in source
    assert "if (summary && summary.contains(target)) return;" in source
    assert "details.open = false;" in source
    assert 'document.addEventListener("pointerdown", closeTransientPopovers, true);' in source

def test_ops_view_renders_pipeline_stages(monkeypatch):
    row = {
        "index": 0,
        "email_uid": "mail-1",
        "sender_name": "Buyer",
        "sender_address": "buyer@example.com",
        "subject": "PO attached",
        "date": "2026-08-11T01:00:00+00:00",
        "attachment_count": 1,
        "classification_state": "completed",
        "classification_state_label": "완료",
        "summary_state": "completed",
        "summary_state_label": "완료",
        "mail_decision_status": "review_required",
        "work_status": "review_required",
        "routing_display": "미할당",
        "mail_category": "발주",
        "business_label": "발주",
        "classification": {"summary": "발주서 확인 요청"},
    }
    monkeypatch.setattr(server, "mail_rows", lambda q="", category="", limit=None: [row])
    monkeypatch.setattr(
        server,
        "ops_attachments_by_uid",
        lambda rows: {
            "mail-1": [
                {
                    "parse_status": "completed",
                    "document_category_label": "발주서",
                }
            ]
        },
    )

    context = server.ops_console_context()
    html = server.templates.get_template("views/ops.html").render(**context, request=request())

    assert 'data-view="monitoring"' in html
    assert "data-monitoring-column-toggle" in html
    assert 'data-monitoring-column="subject"' in html
    assert "/ui/monitoring-rows" in html
    assert 'class="ops-metrics"' not in html
    assert "status=assigned" not in html
    assert "status=in_progress" not in html
    assert "status=responded" not in html
    assert "status=overdue" not in html
    assert "status=completed_today" not in html
    assert "/ui/monitoring/emails/mail-1" in html
    assert 'id="opsInspector"' in html
    assert "Pipeline Control Plane" not in html
    assert "PO attached" in html
    assert "첨부파일" in html
    assert "제목" in html
    assert "발신자" in html
    assert "업무 유형" in html
    assert "담당자" in html
    assert "수신일시" in html
    assert "라우팅" in html
    assert "Mail</th>" not in html
    assert "요약" in html
    assert "담당자 배정" in html
    assert "Mail Decision 실행" in html
    assert 'data-monitoring-column="control"' not in html
    assert 'class="icon-btn ops-stage-action"' in html
    assert 'data-monitoring-bulk-action="attachment"' in html
    assert 'data-monitoring-bulk-action="summary"' in html
    assert 'data-monitoring-bulk-action="classification"' in html
    assert 'data-monitoring-bulk-action="decision"' in html
    assert 'data-monitoring-bulk-action="review-confirm"' in html
    assert 'data-monitoring-bulk-action="forwarding"' in html
    assert 'data-monitoring-row-action="attachment"' in html
    assert 'data-monitoring-row-action="summary"' in html
    assert 'data-monitoring-row-action="classification"' in html
    assert 'data-monitoring-row-action="decision"' in html
    assert 'data-monitoring-row-action="review-confirm"' in html
    assert 'data-monitoring-row-action="forwarding"' in html
    assert "ops-detail-actions" in html
    assert "ops-stage-control" not in html
    assert "ops-workspace" in html
    assert "ops-attachment-popover" in html
    assert "ops-detail-popover" in html
    assert "ops-health-ring" in html
    assert 'role="img"' in html
    assert "검토 필요" in html
    assert "<strong>검토</strong>" not in html
    assert "--ops-score" not in html
    assert "subject" in html
    assert "label" in html

def test_monitoring_popovers_show_supplemental_metadata_without_repeating_column_text():
    completed = server.ops_stage("completed", "완료", "task_alt", "완료")
    row = {
        "email_uid": "mail-1",
        "index": 0,
        "sender": "Buyer",
        "sender_address": "buyer@example.com",
        "subject": "PO attached",
        "received_at": "2026-08-12T09:15:00+09:00",
        "received_detail": "2026-08-12 09:15",
        "business_label": "발주",
        "assignee": "김민수",
        "assignee_department": "영업팀",
        "assignee_position": "매니저",
        "assignee_email": "minsu@example.com",
        "assignee_user_id": "user-1",
        "attachments": [],
        "attachment": completed,
        "summary": completed,
        "classification": completed,
        "decision": completed,
        "routing": completed,
        "forwarding": completed,
        "summary_completed_at": "2026-08-12T09:16:00+09:00",
        "summary_duration_label": "12.00초",
        "classification_completed_at": "2026-08-12T09:16:30+09:00",
        "classification_duration_label": "8.00초",
        "mail_decision_started_at": "2026-08-12T09:16:30+09:00",
        "mail_decision_completed_at": "2026-08-12T09:17:00+09:00",
        "mail_decision_duration_label": "30.00초",
        "routing_assigned_at": "2026-08-12T09:17:20+09:00",
        "routing_fixed_at": "2026-08-12T09:17:30+09:00",
        "routing_forwarded_at": "2026-08-12T09:18:00+09:00",
        "routing_completed_at": "",
        "manual_route_sent_at": "2026-08-12T09:18:00+09:00",
        "manual_route_error": "",
        "pipeline_class": "is-ready",
        "pipeline_status": server.ops_pipeline_status([completed] * 6, pipeline_score=100),
        "control_disabled": False,
        "can_confirm_review_candidate": False,
    }

    html = server.templates.get_template("partials/ops_rows.html").render(
        **server.ui_globals(),
        request=request(),
        ops_rows=[row],
    )

    assert '<span class="label">담당자</span>' not in html
    assert '<strong>김민수</strong>' not in html
    assert '<strong>발주</strong>' not in html
    assert 'title="발주" aria-label="업무 유형 상세 보기"' in html
    assert 'aria-label="업무 유형 상세 보기">  ' not in html
    assert "소속/직책" in html
    assert "영업팀 · 매니저" in html
    assert "minsu@example.com" in html
    assert "분류 완료 시간" in html
    assert "분류 소요 시간" in html
    assert "12.00초" in html
    assert "전달 기록 시간" in html
    assert "ops-detail-popover--with-actions" in html
    assert ">완료</span>" not in html

def test_monitoring_duration_labels_keep_centiseconds():
    start = datetime(2026, 8, 12, 9, 15, 0)

    assert PostgresMailboxService._duration_label(start, start + timedelta(seconds=12, milliseconds=340)) == "12.34초"
    assert PostgresMailboxService._duration_label(start, start + timedelta(minutes=2, milliseconds=500)) == "2분 0.50초"
    assert PostgresMailboxService._duration_label(start, start + timedelta(hours=1)) == "1시간 0분 0.00초"

def test_monitoring_routing_and_forwarding_use_status_icons():
    routed = server.ops_routing_stage({"assignee_name": "김민수", "routing_display": "김민수"})
    forwarding = server.ops_forwarding_stage({"manual_route_status": "sent", "manual_route_status_label": "전달 완료"})

    assert routed["icon"] == server.ops_stage_icon("completed")
    assert forwarding["icon"] == server.ops_stage_icon("completed")

def test_monitoring_popover_actions_are_right_aligned():
    css = _app_css_source()
    popover_css = css.split(".ops-detail-popover--with-actions,", 1)[1].split("}", 1)[0]
    actions_css = css.split(".ops-detail-actions {", 1)[1].split("}", 1)[0]

    assert "grid-template-columns: minmax(0, 1fr) auto;" in popover_css
    assert "flex-direction: column;" in actions_css
    assert "border-left: 1px solid #edf1f5;" in actions_css
    assert "border-top" not in actions_css

def test_monitoring_summary_stage_shows_status_not_stale_summary_text():
    row = {
        "email_uid": "mail-1",
        "sender_name": "Buyer",
        "sender_address": "buyer@example.invalid",
        "subject": "Delivery question",
        "date": "2026-08-11T01:00:00+00:00",
        "classification_state": "completed",
        "summary_state": "completed",
        "summary_state_label": "완료",
        "mail_decision_status": "completed",
        "work_status": "assigned",
        "routing_display": "김민수",
        "assignee_name": "김민수",
        "classification": {"summary": "고객이 납품일정을 문의했으며, 최서연에게 전달되어 있습니다."},
    }

    ops_row = server.ops_row_view(row)

    assert ops_row["summary"]["detail"] == "요약문 생성 완료"
    assert "최서연" not in ops_row["summary"]["detail"]

def test_ops_console_context_uses_bulk_attachment_lookup(monkeypatch):
    rows = [
        {
            "email_uid": f"mail-{index}",
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "subject": f"PO attached {index}",
            "date": "2026-08-11T01:00:00+00:00",
            "attachment_count": 1,
            "classification_state": "completed",
            "classification_state_label": "완료",
            "summary_state": "completed",
            "summary_state_label": "완료",
            "mail_decision_status": "review_required",
            "work_status": "review_required",
            "routing_display": "미할당",
            "mail_category": "발주",
            "business_label": "발주",
            "classification": {"summary": "발주서 확인 요청"},
        }
        for index in range(3)
    ]
    detail_calls = []
    bulk_calls = []

    monkeypatch.setattr(server, "mail_rows", lambda q="", category="", limit=None: rows)
    monkeypatch.setattr(server, "_email_detail_by_ref", lambda email_ref: detail_calls.append(email_ref) or {})
    monkeypatch.setattr(
        server,
        "ops_attachments_by_uid",
        lambda received_rows: bulk_calls.append([row["email_uid"] for row in received_rows])
        or {
            row["email_uid"]: [
                {
                    "filename": f"attachment-{index}.pdf",
                    "parse_status": "completed",
                    "document_category_label": "발주서",
                }
            ]
            for index, row in enumerate(received_rows)
        },
    )

    context = server.ops_console_context()

    assert len(context["ops_rows"]) == 3
    assert detail_calls == []
    assert bulk_calls == [["mail-0", "mail-1", "mail-2"]]

def test_ops_console_context_falls_back_to_detail_attachments_when_bulk_lookup_is_empty(monkeypatch):
    row = {
        "email_uid": "mail-with-pdf",
        "sender_name": "Buyer",
        "sender_address": "buyer@example.invalid",
        "subject": "PO attached",
        "date": "2026-08-11T01:00:00+00:00",
        "has_attachment": True,
        "attachment_count": 1,
        "classification_state": "completed",
        "classification_state_label": "완료",
        "summary_state": "completed",
        "summary_state_label": "완료",
        "mail_decision_status": "review_required",
        "work_status": "review_required",
        "routing_display": "미할당",
        "mail_category": "발주",
        "business_label": "발주",
        "classification": {"summary": "발주서 확인 요청"},
    }
    monkeypatch.setattr(server, "mail_rows", lambda q="", category="", limit=None: [row])
    monkeypatch.setattr(server, "ops_attachments_by_uid", lambda received_rows: {})
    monkeypatch.setattr(
        server,
        "_email_detail_by_ref",
        lambda email_ref: {
            "attachments": [
                {
                    "filename": "purchase-order.pdf",
                    "parse_status": "completed",
                    "document_category_label": "발주서",
                    "view_url": "/api/emails/mail-with-pdf/attachments/0",
                }
            ]
        },
    )

    context = server.ops_console_context()
    html = server.templates.get_template("partials/ops_rows.html").render(**context)

    ops_row = context["ops_rows"][0]
    assert ops_row["attachment"]["label"] == "1개 완료"
    assert [item["filename"] for item in ops_row["attachments"]] == ["purchase-order.pdf"]
    assert "purchase-order.pdf" in html
    assert "/api/emails/mail-with-pdf/attachments/0" in html

def test_ops_row_view_uses_visible_attachment_rows_for_count():
    row = {
        "email_uid": "mail-with-inline-image",
        "sender_name": "Buyer",
        "sender_address": "buyer@example.invalid",
        "subject": "Inline image only",
        "date": "2026-08-11T01:00:00+00:00",
        "has_attachment": True,
        "attachment_count": 1,
        "classification_state": "completed",
        "classification_state_label": "완료",
        "summary_state": "completed",
        "summary_state_label": "완료",
        "mail_decision_status": "completed",
        "work_status": "assigned",
        "routing_display": "김민수",
        "mail_category": "문의",
        "business_label": "문의",
        "classification": {"summary": "본문 이미지 포함"},
    }

    view = server.ops_row_view(row, attachments=[])

    assert view["attachment_count"] == 0
    assert view["attachment"]["state"] == "skipped"
    assert view["attachment"]["detail"] == "분석 대상 첨부가 없습니다."

def test_ops_console_context_limits_employee_to_own_rows(monkeypatch):
    rows = [
        {
            "email_uid": "mail-1",
            "sender_name": "Buyer",
            "subject": "Kim RFQ",
            "assignee_name": "김민수",
            "assignee_email": "m.kim@dawonict.co.kr",
            "routing_display": "김민수",
            "work_status": "assigned",
            "classification_state": "completed",
            "summary_state": "completed",
            "mail_decision_status": "completed",
            "classification": {},
        },
        {
            "email_uid": "mail-2",
            "sender_name": "Buyer",
            "subject": "Park RFQ",
            "assignee_name": "박지현",
            "assignee_email": "jh.park@dawonict.co.kr",
            "routing_display": "박지현",
            "work_status": "assigned",
            "classification_state": "completed",
            "summary_state": "completed",
            "mail_decision_status": "completed",
            "classification": {},
        },
    ]
    monkeypatch.setattr(server, "mail_rows", lambda q="", category="", limit=None: rows)
    monkeypatch.setattr(server, "ops_attachments_by_uid", lambda received_rows: {})
    monkeypatch.setattr(server, "auth_cookie_username", lambda _cookie: "m.kim@dawonict.co.kr")

    context = server.ops_console_context(request())

    assert [row["email_uid"] for row in context["ops_rows"]] == ["mail-1"]
    assert context["ops_summary"]["unacknowledged"] == 1

def test_monitoring_default_view_lists_all_visible_assignee_rows(monkeypatch):
    kim_email = "m.kim@dawonict.co.kr"
    kim_rows = [
        {
            "email_uid": f"kim-mail-{index}",
            "sender_name": "Buyer",
            "subject": f"Kim RFQ {index}",
            "assignee_name": "김민수",
            "assignee_email": kim_email,
            "routing_display": "김민수",
            "work_status": "assigned",
            "classification_state": "completed",
            "summary_state": "completed",
            "mail_decision_status": "completed",
            "classification": {},
        }
        for index in range(120)
    ]

    def fake_mail_rows(q="", category="", limit=None):
        return kim_rows[:limit] if limit is not None else kim_rows

    monkeypatch.setattr(server, "mail_rows", fake_mail_rows)
    monkeypatch.setattr(server, "ops_attachments_by_uid", lambda received_rows: {})
    monkeypatch.setattr(server, "auth_cookie_username", lambda _cookie: kim_email)

    monitoring_context = server.ops_console_context(request())

    assert len(monitoring_context["ops_rows"]) == 120
    assert monitoring_context["ops_summary"]["unacknowledged"] == 120

def test_monitoring_status_filter_rows_match_assignee_metric(monkeypatch):
    kim_email = "m.kim@dawonict.co.kr"
    kim_rows = [
        {
            "email_uid": f"kim-mail-{index}",
            "sender_name": "Buyer",
            "subject": f"Kim RFQ {index}",
            "assignee_name": "김민수",
            "assignee_email": kim_email,
            "routing_display": "김민수",
            "work_status": "assigned",
            "classification_state": "completed",
            "summary_state": "completed",
            "mail_decision_status": "completed",
            "classification": {},
        }
        for index in range(120)
    ]
    rows = [
        *kim_rows,
        {
            "email_uid": "park-mail",
            "sender_name": "Buyer",
            "subject": "Park RFQ",
            "assignee_name": "박지현",
            "assignee_email": "jh.park@dawonict.co.kr",
            "routing_display": "박지현",
            "work_status": "assigned",
            "classification_state": "completed",
            "summary_state": "completed",
            "mail_decision_status": "completed",
            "classification": {},
        },
    ]

    def fake_mail_rows(q="", category="", limit=None):
        return rows[:limit] if limit is not None else rows

    monkeypatch.setattr(server, "mail_rows", fake_mail_rows)
    monkeypatch.setattr(server, "ops_attachments_by_uid", lambda received_rows: {})
    monkeypatch.setattr(server, "auth_cookie_username", lambda _cookie: kim_email)

    req = request()
    monitoring_context = server.ops_console_context(req, status="assigned")
    my_work_context = server.assignee_work_context(req, assignee=kim_email)

    assert len(monitoring_context["ops_rows"]) == 120
    assert monitoring_context["ops_summary"]["unacknowledged"] == 120
    assert monitoring_context["ops_summary"]["unacknowledged"] == my_work_context["assignee_summary"]["unacknowledged_count"]

def test_ops_pipeline_status_marks_delivery_pending_separately():
    completed = server.ops_stage("completed", "완료", "task_alt", "완료")
    delivery_pending = server.ops_pipeline_status(
        [completed, completed, completed, completed, completed, server.ops_stage("not_started", "미전달", "outbox", "미전달")],
        pipeline_score=83,
    )
    review_required = server.ops_pipeline_status(
        [completed, completed, completed, server.ops_stage("review_required", "검토 필요", "rate_review", "검토 필요"), completed, completed],
        pipeline_score=94,
    )
    delivery_complete = server.ops_pipeline_status(
        [completed, completed, completed, completed, completed, completed],
        pipeline_score=100,
    )

    assert delivery_pending["label"] == "전달 대기"
    assert delivery_pending["detail"] == "모든 처리 완료, 전달만 미완료"
    assert delivery_pending["class"] == "is-delivery-pending"
    assert review_required["label"] == "미완료"
    assert review_required["detail"] == "담당자 배정 미완료"
    assert review_required["class"] == "is-blocked"
    assert delivery_complete["label"] == "완료"
    assert delivery_complete["detail"] == "모든 처리 및 전달 완료"
    assert delivery_complete["class"] == "is-ready"

def test_ops_pipeline_status_uses_three_display_labels():
    completed = server.ops_stage("completed", "완료", "task_alt", "완료")
    failed = server.ops_stage("failed", "실패", "error", "실패")
    review = server.ops_stage("review_required", "검토 필요", "rate_review", "검토 필요")
    running = server.ops_stage("running", "실행 중", "progress_activity", "실행 중")

    labels = {
        server.ops_pipeline_status([completed, completed, completed, completed, completed, completed], pipeline_score=100)["label"],
        server.ops_pipeline_status([completed, completed, completed, completed, completed, failed], pipeline_score=83)["label"],
        server.ops_pipeline_status([completed, completed, completed, review, completed, completed], pipeline_score=94)["label"],
        server.ops_pipeline_status([completed, running, completed, completed, completed, completed], pipeline_score=92)["label"],
        server.ops_pipeline_status([completed, completed, completed, completed, completed, server.ops_stage("not_started", "미전달", "outbox", "미전달")], pipeline_score=83)["label"],
    }

    assert labels == {"완료", "전달 대기", "미완료"}

def test_ops_pipeline_status_keeps_forwarding_failure_blocked():
    completed = server.ops_stage("completed", "완료", "task_alt", "완료")
    failed = server.ops_stage("failed", "전달 실패", "error", "전달 실패")

    status = server.ops_pipeline_status(
        [completed, completed, completed, completed, completed, failed],
        pipeline_score=83,
    )

    assert status["label"] == "미완료"
    assert status["detail"] == "전달 미완료"
    assert status["class"] == "is-blocked"

def test_ops_pipeline_status_does_not_mark_unstarted_decision_as_normal():
    completed = server.ops_stage("completed", "완료", "task_alt", "완료")
    not_started = server.ops_stage("not_started", "미실행", "pending", "Mail Decision Run이 아직 없습니다.")

    status = server.ops_pipeline_status(
        [completed, completed, completed, not_started, completed, completed],
        pipeline_score=83,
    )

    assert status["label"] == "미완료"
    assert status["detail"] == "담당자 배정 미완료"
    assert status["class"] == "is-blocked"

def test_ops_row_view_requires_decision_before_normal_status():
    row = {
        "email_uid": "mail-without-decision",
        "sender_name": "Buyer",
        "sender_address": "buyer@example.invalid",
        "subject": "Forwarded without decision",
        "date": "2026-08-11T01:00:00+00:00",
        "attachment_count": 0,
        "classification_state": "completed",
        "classification_state_label": "완료",
        "summary_state": "completed",
        "summary_state_label": "완료",
        "mail_decision_status": "",
        "work_status": "forwarded",
        "routing_status": "forwarded",
        "routing_display": "김민수",
        "assignee_name": "김민수",
        "assignee_email": "minsu.kim@example.invalid",
        "manual_route_status": "sent",
        "manual_route_status_label": "전달 완료",
        "mail_category": "발주",
        "business_label": "발주",
        "classification": {"summary": "발주서 확인 요청"},
    }

    view = server.ops_row_view(row, attachments=[])

    assert view["decision"]["state"] == "not_started"
    assert view["forwarding"]["state"] == "completed"
    assert view["pipeline_status"]["label"] == "미완료"
    assert view["pipeline_status"]["detail"] == "담당자 배정 미완료"
    assert view["pipeline_class"] == "is-blocked"

def test_ops_classification_stage_labels_database_result_as_completed():
    stage = server.ops_classification_stage(
        {
            "classification_state": "completed",
            "classification_state_label": "DB",
            "business_label": "문의",
        }
    )

    assert stage["state"] == "completed"
    assert stage["label"] == "완료"
    assert stage["detail"] == "문의"

def test_mail_list_table_headers_use_korean_terms():
    dashboard_html = server.templates.get_template("views/dashboard.html").render(**server.dashboard_context())
    inbox_html = server.templates.get_template("views/inbox.html").render(**server.inbox_context(selected_index=None))

    dashboard_headers = [
        '<th class="mail-read-state-col" aria-label="읽음 상태"></th>',
        '<th class="dashboard-status-col">상태</th>',
        '<th class="dashboard-sender-col">발신자</th>',
        '<th class="subject-col">제목</th>',
        '<th class="dashboard-classification-col">업무 유형</th>',
        '<th class="dashboard-receiver-col">담당자</th>',
        '<th class="dashboard-time-col">수신일시</th>',
        '<th class="manual-route-col">수동 라우팅</th>',
    ]
    inbox_headers = [
        '<th class="mail-read-state-col" aria-label="읽음 상태"></th>',
        '<th class="inbox-status-col">상태</th>',
        '<th class="inbox-sender-col">발신자</th>',
        '<th class="subject-col inbox-subject-col">제목</th>',
        '<th class="inbox-classification-col">업무 유형</th>',
        '<th class="inbox-routing-col">담당자</th>',
        '<th class="inbox-time-col">수신일시</th>',
    ]

    assert [dashboard_html.index(header) for header in dashboard_headers] == sorted(
        dashboard_html.index(header) for header in dashboard_headers
    )
    assert 'id="dashboardMailRows"' in dashboard_html
    assert [inbox_html.index(header) for header in inbox_headers] == sorted(
        inbox_html.index(header) for header in inbox_headers
    )

def test_monitoring_email_inspector_renders_detail_drawer(monkeypatch):
    row = {
        "index": 0,
        "email_uid": "mail-1",
        "sender_name": "Buyer",
        "sender_address": "buyer@example.com",
        "subject": "PO attached",
        "body": "Please review attached PO.",
        "date": "2026-08-11T01:00:00+00:00",
        "classification": {"mail_category": "발주"},
        "attachments": [],
    }
    response = render_monitoring_email_inspector(
        request(),
        "mail-1",
        templates=server.templates,
        email_detail=lambda email_ref: row if email_ref == "mail-1" else None,
        ensure_can_view=server.ensure_can_view_work_email,
        ui_globals=server.ui_globals,
        related_emails=server.related_emails,
    )
    html = response.body.decode()

    assert "ops-inspector-shell" in html
    assert "data-ops-inspector-close" in html
    assert "Mail Detail" not in html
    assert "PO attached" in html
    assert "Please review attached PO." in html

def test_monitoring_inspector_flattens_outer_detail_card():
    css = _app_css_source()
    inspector_card_css = css.split(".ops-inspector-body .detail-card {", 1)[1].split("}", 1)[0]
    inspector_layout_css = css.split(".ops-inspector-body .detail-layout {", 1)[1].split("}", 1)[0]
    inspector_body_frame_css = css.split(".ops-inspector-body .email-body-frame {", 1)[1].split("}", 1)[0]

    assert "border: 0;" in inspector_card_css
    assert "border-radius: 0;" in inspector_card_css
    assert "background: transparent;" in inspector_card_css
    assert "box-shadow: none;" in inspector_card_css
    assert "padding: 0;" in inspector_layout_css
    assert "min-height: 160px;" in inspector_body_frame_css

def test_shell_resizes_email_body_frames_to_content_height():
    source = server.templates.get_template("shell.html").render(
        **server.ui_globals(),
        request=request(),
        active_view="monitoring",
        initial_view_template="views/ops.html",
        ops_rows=[],
        ops_query="",
        selected_category="",
        ops_summary={},
    )

    assert "function resizeEmailBodyFrames(root)" in source
    assert 'scope.querySelectorAll(".email-body-frame")' in source
    assert 'frame.addEventListener("load", applyHeight);' in source
    assert 'body.style.overflow = "hidden";' in source
    assert 'html.style.overflow = "hidden";' in source
    assert 'frame.style.height = "auto";' in source
    assert "frame.style.height = `${height + 8}px`;" in source
    assert "ResizeObserver" in source
    assert "window.setTimeout(applyHeight, 80);" in source
    assert "window.setTimeout(applyHeight, 300);" in source
    assert "resizeEmailBodyFrames(event.detail.target);" in source
    assert "resizeEmailBodyFrames(document);" in source

def test_monitoring_inspector_closes_on_outside_pointerdown():
    source = server.templates.get_template("shell.html").render(
        **server.ui_globals(),
        request=request(),
        active_view="monitoring",
        initial_view_template="views/ops.html",
        ops_rows=[],
        ops_query="",
        selected_category="",
        ops_summary={},
    )

    close_block = source.split("function closeTransientPopovers(event) {", 1)[1].split(
        "function resizeEmailBodyFrames", 1
    )[0]

    assert 'const inspector = document.getElementById("opsInspector");' in close_block
    assert "if (inspector.contains(target)) return;" in close_block
    assert 'if (target.closest("[data-ops-inspector-open]")) return;' in close_block
    assert "closeOpsInspector();" in close_block

def test_my_work_detail_drawer_closes_on_outside_pointerdown():
    source = server.templates.get_template("shell.html").render(
        **server.ui_globals(),
        request=request(),
        active_view="my-work",
        initial_view_template="views/assignee_work.html",
        assignee_contexts=[],
        assignee_rows=[],
        assignee_summary={},
    )

    close_block = source.split("function closeTransientPopovers(event) {", 1)[1].split(
        "function resizeEmailBodyFrames", 1
    )[0]

    assert 'const assigneeDrawer = document.getElementById("assigneeEmailDetailDrawer");' in close_block
    assert "if (assigneeDrawer.contains(target)) return;" in close_block
    assert 'if (target.closest("[data-assignee-detail-open]")) return;' in close_block
    assert "closeAssigneeDetailDrawer();" in close_block

def test_monitoring_table_cells_keep_native_table_layout():
    css = _app_css_source()
    text_cell_css = css.split(".ops-text-cell,\n.ops-time-cell {", 1)[1].split("}", 1)[0]
    text_summary_css = css.split(".ops-text-cell .ops-detail-menu > summary,", 1)[1].split("}", 1)[0]

    assert "display: block;" not in text_cell_css
    assert "display: block;" in text_summary_css
    assert "text-overflow: ellipsis;" in text_summary_css

def test_monitoring_inspector_overlays_inside_monitoring_view():
    css = _app_css_source()
    ops_view_css = css.split(".ops-view {", 1)[1].split("}", 1)[0]
    inspector_layout_css = css.split(".ops-view.has-inspector .ops-workspace {", 1)[1].split("}", 1)[0]
    inspector_css = css.split(".ops-inspector {", 1)[1].split("}", 1)[0]

    assert "position: relative;" in ops_view_css
    assert "grid-template-columns" not in inspector_layout_css
    assert "position: absolute;" in inspector_css
    assert "width: min(760px, calc(100vw - 96px));" in inspector_css

def test_gmail_settings_modal_refreshes_status_when_opened():
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

    assert 'fetch("{{ mail_settings_panel_url }}' not in html
    assert 'fetch("/ui/settings/gmail-sync"' in html or 'fetch("/ui/settings/naver-sync"' in html or 'fetch("/ui/settings/hiworks-sync"' in html
    assert 'cache: "no-store"' in html
    assert "await refreshGmailSettingsPanel();" in html
    assert "data-gmail-account-label" in html
    assert "bannerValue.textContent = accountLabel" in html

def test_inbox_search_controls_are_not_wrapped_in_toolbar_panel():
    html = server.templates.get_template("views/inbox.html").render(
        **server.inbox_context(selected_index=None),
        request=request(),
    )

    assert "toolbar-panel" not in html
    assert 'class="inbox-toolbar"' in html
    assert 'id="mailSearch"' in html
    assert 'id="categoryFilter"' in html

def test_inbox_category_filter_labels_all_option_as_korean_all(monkeypatch):
    monkeypatch.setattr(server, "mail_rows", lambda **_: [])

    html = server.templates.get_template("views/inbox.html").render(
        **server.inbox_context(selected_index=None),
        request=request(),
    )

    assert 'data-category-filter-target="inbox"' in html
    assert "<span data-category-filter-selected-label>업무 유형 전체</span>" in html
    assert 'class="dashboard-category-select-option is-active"' in html
    assert 'data-category-filter="__all__"' in html
    assert 'role="option"' in html

def test_receiver_chip_links_to_assignee_work_view():
    html = server.templates.get_template("partials/mail_rows.html").render(
        **server.ui_globals(),
        request=request(),
        emails=[
            {
                "index": 0,
                "email_uid": "mail-1",
                "sender_name": "Sender",
                "subject": "Subject",
                "mail_category": "발주",
                "work_status": "assigned",
                "work_status_label": "배정 완료",
                "routing_display": "김담당",
                "assignee_name": "김담당",
                "assignee_email": "kim@example.com",
                "classification": {"mail_category": "발주"},
                "date": "2026-08-20T09:00:00+09:00",
            }
        ],
        mail_rows_mode="inbox",
        selected_email_index=None,
        selected_email_uid="",
    )

    assert 'hx-post="/ui/assignees?assignee=kim%40example.com"' in html
    assert 'hx-on:click="event.stopPropagation()"' in html
    assert "김담당 담당 업무 보기" in html


def test_inbox_click_renders_pending_detail_before_server_swap():
    html = server.templates.get_template("partials/shell_runtime.html").render(
        **server.ui_globals(),
        request=request(),
    )

    assert 'targetSelector === "#email-detail"' in html
    assert "selectInboxRow(row);" in html
    assert "renderPendingInboxDetail(row);" in html
    assert "uiSyncState.detailRequestUid = uid;" in html
    assert "The click request is already loading this detail" in html
    assert "uiSyncState.detailRequestNeedsVersionSync = true;" in html
    assert "메일 상세를 불러오는 중..." in html
    assert "escapeHtml(subject)" in html
    assert 'event.detail.target.removeAttribute("aria-busy")' in html
    assert "renderInboxDetailRequestError(event.detail.xhr?.status);" in html
    assert "이 메일을 볼 권한이 없습니다." in html

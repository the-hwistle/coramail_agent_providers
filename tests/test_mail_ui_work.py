# ruff: noqa: F403, F405
import pytest

from tests.ui_test_support import *  # noqa: F401,F403


def _css_blocks(css: str, selector: str) -> list[str]:
    blocks = []
    remainder = css
    marker = f"{selector} {{"
    while marker in remainder:
        _, remainder = remainder.split(marker, 1)
        block, remainder = remainder.split("}", 1)
        blocks.append(block)
    return blocks


def test_receiver_chip_prefers_assignee_name_over_stale_uuid_routing_display():
    assignee_id = "10000000-0000-0000-0000-000000000001"
    html = server.templates.get_template("partials/mail_rows.html").render(
        **server.ui_globals(),
        request=request(),
        emails=[
            {
                "index": 0,
                "email_uid": "mail-1",
                "sender_name": "Sender",
                "subject": "Subject",
                "mail_category": "문의",
                "work_status": "assigned",
                "work_status_label": "배정 완료",
                "routing_display": assignee_id,
                "assignee_user_id": assignee_id,
                "assignee_name": "김민수",
                "assignee_email": "m.kim@dawonict.co.kr",
                "classification": {"mail_category": "문의", "routing_display": assignee_id},
                "date": "2026-08-20T09:00:00+09:00",
            }
        ],
        mail_rows_mode="inbox",
        selected_email_index=None,
        selected_email_uid="",
    )

    assert "김민수" in html
    assert f">{assignee_id}<" not in html
    assert 'hx-post="/ui/assignees?assignee=m.kim%40dawonict.co.kr"' in html
    assert "10000000-0000-0000-0000-000000000001" not in html


def test_inbox_rows_mark_read_mail_only_for_assignee_accounts(monkeypatch):
    row = {
        "index": 0,
        "email_uid": "mail-1",
        "sender_name": "Buyer",
        "subject": "Already opened RFQ",
        "mail_category": "문의",
        "work_status": "in_progress",
        "work_status_label": "진행중",
        "current_user_read_at": "2026-08-20T09:10:00+09:00",
        "classification": {"mail_category": "문의"},
        "date": "2026-08-20T09:00:00+09:00",
    }
    monkeypatch.setattr(server, "user_can_view_all_assignees", lambda username: username == "admin")
    monkeypatch.setattr(
        server,
        "current_authenticated_user",
        lambda _request: {
            "username": "m.kim@dawonict.co.kr",
            "user_id": "10000000-0000-0000-0000-000000000001",
            "name": "김민수",
            "role": "member",
            "email": "m.kim@dawonict.co.kr",
        },
    )
    monkeypatch.setattr(server, "auth_cookie_username", lambda _cookie: "m.kim@dawonict.co.kr")

    assignee_html = server.templates.get_template("partials/mail_rows.html").render(
        **server.ui_globals(request()),
        request=request(),
        emails=[row],
        mail_rows_mode="inbox",
        selected_email_index=None,
        selected_email_uid="",
    )
    unread_assignee_html = server.templates.get_template("partials/mail_rows.html").render(
        **server.ui_globals(request()),
        request=request(),
        emails=[dict(row, current_user_read_at="")],
        mail_rows_mode="inbox",
        selected_email_index=None,
        selected_email_uid="",
    )

    monkeypatch.setattr(server, "auth_cookie_username", lambda _cookie: "admin")
    admin_html = server.templates.get_template("partials/mail_rows.html").render(
        **server.ui_globals(request()),
        request=request(),
        emails=[row],
        mail_rows_mode="inbox",
        selected_email_index=None,
        selected_email_uid="",
    )

    assert "is-assignee-read" in assignee_html
    assert "mail-read-indicator" in assignee_html
    assert ">drafts</span>" in assignee_html
    assert "data-mail-favorite-toggle" in assignee_html
    assert 'onclick="event.preventDefault(); event.stopPropagation();"' not in assignee_html
    assert "t-like-star" in assignee_html
    assert 'class="mail-read-state-cell"' in assignee_html
    assert "is-assignee-read" not in unread_assignee_html
    assert 'class="mail-read-state-cell"' in unread_assignee_html
    assert ">mail</span>" in unread_assignee_html
    assert "is-assignee-read" not in admin_html
    assert "mail-read-indicator" not in admin_html


def test_dashboard_rows_use_fixed_mail_read_icon_column():
    row = {
        "index": 0,
        "email_uid": "mail-1",
        "sender_name": "Buyer",
        "subject": "Dashboard RFQ",
        "mail_category": "문의",
        "work_status": "assigned",
        "work_status_label": "미확인",
        "current_user_read_at": "",
        "classification": {"mail_category": "문의"},
        "date": "2026-08-20T09:00:00+09:00",
    }
    unread_html = server.templates.get_template("partials/mail_rows.html").render(
        **server.ui_globals(request()),
        request=request(),
        emails=[row],
        mail_rows_mode="dashboard",
        selected_email_index=None,
        selected_email_uid="",
    )
    read_html = server.templates.get_template("partials/mail_rows.html").render(
        **server.ui_globals(request()),
        request=request(),
        emails=[dict(row, current_user_read_at="2026-08-20T09:10:00+09:00")],
        mail_rows_mode="dashboard",
        selected_email_index=None,
        selected_email_uid="",
    )

    assert 'class="mail-read-state-cell"' in unread_html
    assert ">mail</span>" in unread_html
    assert "mono row-number" not in unread_html
    assert "is-assignee-read" in read_html
    assert ">drafts</span>" in read_html


def test_dashboard_rows_include_current_user_read_state(monkeypatch):
    row = {
        "index": 0,
        "email_uid": "mail-1",
        "sender_name": "Buyer",
        "subject": "Dashboard RFQ",
        "classification": {},
    }

    monkeypatch.setattr(server, "current_request_username", lambda request: "admin")
    monkeypatch.setattr(server, "user_can_view_all_assignees", lambda username: True)
    monkeypatch.setattr(
        server,
        "rows_with_current_user_read_state",
        lambda request, rows: [dict(rows[0], current_user_read_at="2026-08-20T09:10:00+09:00")],
    )

    rows = server.dashboard_rows_for_request(request(), [row])

    assert rows[0]["current_user_read_at"] == "2026-08-20T09:10:00+09:00"


def test_assignee_work_context_limits_non_admin_to_allowed_assignees(monkeypatch):
    rows = [
        {
            "email_uid": "mail-1",
            "assignee_name": "박담당",
            "assignee_email": "park@example.com",
            "assignee_user_id": "user-park",
            "routing_display": "박담당",
            "mail_category": "발주",
            "work_status": "assigned",
            "work_status_label": "배정 완료",
            "classification": {"mail_category": "발주"},
        },
        {
            "email_uid": "mail-2",
            "assignee_name": "김담당",
            "assignee_email": "kim@example.com",
            "assignee_user_id": "user-kim",
            "routing_display": "김담당",
            "mail_category": "기술",
            "work_status": "review_required",
            "work_status_label": "검토 필요",
            "classification": {"mail_category": "기술"},
        },
        {
            "email_uid": "mail-3",
            "assignee_name": "이담당",
            "assignee_email": "lee@example.com",
            "assignee_user_id": "user-lee",
            "routing_display": "이담당",
            "mail_category": "서비스",
            "work_status": "assigned",
            "work_status_label": "배정 완료",
            "classification": {"mail_category": "서비스"},
        },
    ]
    monkeypatch.setattr(server, "mail_rows", lambda **_: rows)
    monkeypatch.setattr(server, "auth_cookie_username", lambda _cookie: "park@example.com")
    monkeypatch.setenv("CORAMAIL_ASSIGNEE_ACCESS_JSON", '{"park@example.com": ["kim@example.com"]}')

    context = server.assignee_work_context(request(), assignee="kim@example.com")

    assert [item["name"] for item in context["assignees"]] == ["김담당", "박담당"]
    assert [row["email_uid"] for row in context["assignee_rows"]] == ["mail-2"]
    assert context["assignee_scope_all"] is False

def test_assignee_work_context_allows_admin_to_view_every_assignee(monkeypatch):
    rows = [
        {
            "email_uid": "mail-1",
            "assignee_name": "박담당",
            "assignee_email": "park@example.com",
            "routing_display": "박담당",
            "work_status": "assigned",
            "classification": {},
        },
        {
            "email_uid": "mail-2",
            "assignee_name": "김담당",
            "assignee_email": "kim@example.com",
            "routing_display": "김담당",
            "work_status": "assigned",
            "classification": {},
        },
    ]
    monkeypatch.setattr(server, "mail_rows", lambda **_: rows)
    monkeypatch.setattr(server, "auth_cookie_username", lambda _cookie: "admin")

    context = server.assignee_work_context(request(), assignee="kim@example.com")

    assert context["assignee_scope_all"] is True
    assert {item["name"] for item in context["assignees"]} == {"김담당", "박담당"}
    assert [row["email_uid"] for row in context["assignee_rows"]] == ["mail-2"]

def test_demo_duplicate_received_mail_is_visible_to_assignee_for_review():
    row = {
        "email_uid": "mail-new",
        "provider_message_id": "demo-duplicate-latest-20260826051302132232",
        "assignee_name": "",
        "assignee_email": "",
        "assignee_user_id": "",
        "routing_display": "미할당",
    }

    server.ensure_can_view_work_email(request(), row)
    assert server.visible_work_rows_for_request(request(), [row]) == [row]


def test_configured_auth_admin_can_view_all_assignees_after_username_change(monkeypatch):
    monkeypatch.setattr(server, "AUTH_USERNAME", "cora-admin")
    monkeypatch.setenv("CORAMAIL_ADMIN_USERNAMES", "admin")

    assert server.user_can_view_all_assignees("cora-admin") is True
    assert server.user_can_view_all_assignees("ordinary-user") is False

def test_admin_assignments_default_shows_all_assignee_work(monkeypatch):
    rows = [
        {
            "email_uid": "mail-1",
            "assignee_name": "박담당",
            "assignee_email": "park@example.com",
            "routing_display": "박담당",
            "work_status": "assigned",
            "classification": {},
        },
        {
            "email_uid": "mail-2",
            "assignee_name": "김담당",
            "assignee_email": "kim@example.com",
            "routing_display": "김담당",
            "work_status": "assigned",
            "classification": {},
        },
    ]
    monkeypatch.setattr(server, "mail_rows", lambda **_: rows)
    monkeypatch.setattr(server, "auth_cookie_username", lambda _cookie: "admin")

    context = server.assignee_work_context(request())
    html = server.templates.get_template("views/assignee_work.html").render(**context, request=request())

    assert context["assignee_scope_all"] is True
    assert context["assignee_query"] == ""
    assert context["selected_assignee"] == {}
    assert [row["email_uid"] for row in context["assignee_rows"]] == ["mail-1", "mail-2"]
    assert context["assignee_summary"]["mail_count"] == 2
    assert "전체 담당자 업무 현황" in html
    assert "전체 담당자" in html

def test_assignee_work_template_renders_selected_workload(monkeypatch):
    rows = [
        {
            "email_uid": "mail-1",
            "sender_name": "Buyer",
            "subject": "PO attached",
            "assignee_name": "박담당",
            "assignee_email": "park@example.com",
            "routing_display": "박담당",
            "mail_category": "발주",
            "work_status": "assigned",
            "work_status_label": "배정 완료",
            "classification": {"mail_category": "발주"},
            "date": "2026-08-20T09:00:00+09:00",
        }
    ]
    monkeypatch.setattr(server, "mail_rows", lambda **_: rows)
    monkeypatch.setattr(server, "auth_cookie_username", lambda _cookie: "admin")

    html = server.templates.get_template("views/assignee_work.html").render(
        **server.assignee_work_context(request(), assignee="park@example.com"),
        request=request(),
    )

    assert 'data-view="assignees"' in html
    assert 'class="work-queue-rail"' in html
    assert 'class="assignee-next-panel"' in html
    assert 'id="assigneeEmailDetailDrawer"' in html
    assert "/ui/my-work/emails/mail-1" in html
    assert 'data-assignee-detail-open' in html
    assert "업무 큐" in html
    assert "현재 할당 업무" in html
    assert "전체 1건" not in html
    assert "전체 업무 · 1건 표시" not in html
    assert "선택된 업무" in html
    assert "박담당" in html
    assert "PO attached" in html
    assert "배정 메일" in html
    assert "확인함" in html
    assert "긴급 메일" in html
    assert "전달 완료" in html
    assert "담당 메일 검색" in html

def test_my_work_email_drawer_renders_detail_side_tab(monkeypatch):
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
    monkeypatch.setattr(server, "_email_detail_by_ref", lambda email_ref: row if email_ref == "mail-1" else None)

    response = server.ui_my_work_email_drawer(request(), "mail-1")
    html = response.body.decode()

    assert "assignee-detail-drawer-shell" in html
    assert "data-assignee-detail-close" in html
    assert "PO attached" in html
    assert "Please review attached PO." in html

def test_assignee_work_template_prefers_email_over_user_id_for_navigation(monkeypatch):
    assignee_id = "10000000-0000-0000-0000-000000000001"
    rows = [
        {
            "email_uid": "mail-1",
            "sender_name": "Buyer",
            "subject": "RFQ attached",
            "assignee_name": "김민수",
            "assignee_email": "m.kim@dawonict.co.kr",
            "assignee_user_id": assignee_id,
            "routing_display": "김민수",
            "work_status": "assigned",
            "classification": {},
        }
    ]
    monkeypatch.setattr(server, "mail_rows", lambda **_: rows)
    monkeypatch.setattr(server, "auth_cookie_username", lambda _cookie: "admin")

    html = server.templates.get_template("views/assignee_work.html").render(
        **server.assignee_work_context(request(), assignee="m.kim@dawonict.co.kr"),
        request=request(),
    )

    assert "김민수" in html
    assert 'name="assignee" value="m.kim@dawonict.co.kr"' in html
    assert "assignee=m.kim%40dawonict.co.kr" in html
    assert assignee_id not in html

def test_assignee_work_status_stats_filter_rows(monkeypatch):
    rows = [
        {
            "email_uid": "mail-1",
            "sender_name": "Buyer",
            "subject": "Unacknowledged RFQ",
            "assignee_name": "김민수",
            "assignee_email": "m.kim@dawonict.co.kr",
            "work_status": "assigned",
            "work_status_label": "미확인",
            "classification": {},
        },
        {
            "email_uid": "mail-2",
            "sender_name": "Buyer",
            "subject": "Completed RFQ",
            "assignee_name": "김민수",
            "assignee_email": "m.kim@dawonict.co.kr",
            "work_status": "completed",
            "work_status_label": "완료",
            "classification": {},
        },
    ]
    monkeypatch.setattr(server, "mail_rows", lambda **_: rows)
    monkeypatch.setattr(server, "auth_cookie_username", lambda _cookie: "m.kim@dawonict.co.kr")

    context = server.assignee_work_context(request(), assignee="m.kim@dawonict.co.kr", status="assigned")
    html = server.templates.get_template("views/assignee_work.html").render(**context, request=request())

    assert context["assignee_summary"]["mail_count"] == 2
    assert [row["email_uid"] for row in context["assignee_rows"]] == ["mail-1"]
    assert "Unacknowledged RFQ" in html
    assert "Completed RFQ" not in html
    assert "status=assigned" in html
    assert 'class="assignee-work-stat assignee-work-stat--primary is-active"' in html

def test_assignee_work_template_keeps_actions_in_selected_work_panel(monkeypatch):
    assignee_id = "10000000-0000-0000-0000-000000000001"
    rows = [
        {
            "email_uid": "mail-1",
            "sender_name": "Buyer",
            "subject": "RFQ",
            "assignee_name": "김민수",
            "assignee_email": "m.kim@dawonict.co.kr",
            "assignee_user_id": assignee_id,
            "work_status": "in_progress",
            "work_status_label": "진행중",
            "classification": {},
        }
    ]
    monkeypatch.setattr(server, "mail_rows", lambda **_: rows)
    monkeypatch.setattr(server, "auth_cookie_username", lambda _cookie: "m.kim@dawonict.co.kr")
    monkeypatch.setattr(server, "current_authenticated_user", lambda request: {"username": "m.kim@dawonict.co.kr", "user_id": assignee_id, "name": "김민수", "role": "member", "email": "m.kim@dawonict.co.kr"})

    html = server.templates.get_template("views/assignee_work.html").render(
        **server.assignee_work_context(request(), assignee="m.kim@dawonict.co.kr"),
        request=request(),
    )

    assert "selected_email_uid=mail-1" in html
    assert 'hx-target="#main-panel"' in html
    assert "<th>작업</th>" not in html
    assert "assignee-action-cell" not in html
    assert 'hx-post="/ui/emails/mail-1/work/in-progress"' in html
    assert "data-work-in-progress-toggle" in html
    panel_head = html.split('<div class="assignee-next-panel-head">', 1)[1].split('<div class="assignee-next-summary">', 1)[0]
    panel_actions = html.split('<div class="assignee-next-actions" id="assigneeDetailPreview">', 1)[1].split("</div>", 1)[0]
    assert "work-progress-toggle" in panel_head
    assert "data-work-in-progress-toggle" in panel_head
    assert "t-toggle-thumb" in panel_head
    assert 'role="switch"' in panel_head
    assert 'data-on="true"' in panel_head
    assert "data-work-in-progress-toggle" not in panel_actions
    assert "진행중 끄기" not in html
    assert "진행중 켜기" not in html
    assert 'hx-post="/ui/emails/mail-1/work/reply-initiate"' in html
    assert 'hx-post="/ui/emails/mail-1/work/complete"' in html
    assert "data-work-complete-button" in html

def test_my_work_row_click_selects_work_panel(monkeypatch):
    rows = [
        {
            "email_uid": "mail-1",
            "sender_name": "Buyer",
            "subject": "RFQ",
            "assignee_name": "김민수",
            "assignee_email": "m.kim@dawonict.co.kr",
            "work_status": "assigned",
            "work_status_label": "미확인",
            "classification": {},
        }
    ]
    monkeypatch.setattr(server, "mail_rows", lambda **_: rows)
    monkeypatch.setattr(server, "auth_cookie_username", lambda _cookie: "m.kim@dawonict.co.kr")

    html = server.templates.get_template("views/assignee_work.html").render(
        **server.assignee_work_context(
            request(),
            assignee="m.kim@dawonict.co.kr",
            work_view_name="my-work",
            work_endpoint="/ui/my-work",
            work_title="My Work",
        ),
        request=request(),
    )

    assert "selected_email_uid=mail-1" in html
    assert "<h1>김민수</h1>" in html
    assert "<h1>My Work</h1>" not in html
    assert 'hx-target="#main-panel"' in html
    assert 'hx-target="#assigneeEmailDetailDrawer"' in html
    assert "<th>작업</th>" not in html
    assert "assignee-action-cell" not in html
    assert 'hx-post="/ui/inbox?email_uid=mail-1"' not in html

def test_my_work_selected_email_is_marked_read(monkeypatch):
    calls = []
    rows = [
        {
            "email_uid": "mail-1",
            "sender_name": "Buyer",
            "subject": "First RFQ",
            "assignee_name": "김민수",
            "assignee_email": "m.kim@dawonict.co.kr",
            "work_status": "assigned",
            "work_status_label": "미확인",
            "classification": {},
        },
        {
            "email_uid": "mail-2",
            "sender_name": "Buyer",
            "subject": "Second RFQ",
            "assignee_name": "김민수",
            "assignee_email": "m.kim@dawonict.co.kr",
            "work_status": "assigned",
            "work_status_label": "미확인",
            "classification": {},
        },
    ]
    monkeypatch.setattr(server, "mail_rows", lambda **_: rows)
    monkeypatch.setattr(server, "auth_cookie_username", lambda _cookie: "m.kim@dawonict.co.kr")
    monkeypatch.setattr(server, "_mark_mail_read_for_current_user", lambda request, email: calls.append(email["email_uid"]))

    context = server.assignee_work_context(
        request(),
        assignee="m.kim@dawonict.co.kr",
        selected_email_uid="mail-2",
        work_view_name="my-work",
        work_endpoint="/ui/my-work",
        work_title="My Work",
    )

    assert context["selected_assignee_work_uid"] == "mail-2"
    assert context["selected_assignee_work"]["subject"] == "Second RFQ"
    assert context["selected_assignee_work"]["work_status"] == "assigned"
    assert calls == ["mail-2"]

def test_assignee_roster_items_keep_text_separate_from_selection_background():
    css = _app_css_source()
    item_css = css.split(".assignee-roster-item {", 1)[1].split("}", 1)[0]
    active_css = css.split(".assignee-roster-item.is-active {", 1)[1].split("}", 1)[0]
    count_css = css.split(".assignee-roster-item strong {", 1)[1].split("}", 1)[0]
    active_count_css = css.split(".assignee-roster-item.is-active strong {", 1)[1].split("}", 1)[0]

    assert "background: #ffffff;" in item_css
    assert "color: #0f172a;" in item_css
    assert "background: #ffffff;" in active_css
    assert "box-shadow: inset 4px 0 0 #2563eb;" in active_css
    assert "background: #f8fafc;" in count_css
    assert "background: #eff6ff;" in active_count_css

def test_inbox_context_applies_selected_category_filter(monkeypatch):
    calls = []
    rows = [
        {
            "index": 1,
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
            "date": "2026-08-12T00:24:00+00:00",
        }
    ]

    def fake_mail_rows(**kwargs):
        calls.append(kwargs)
        if kwargs.get("category") == "발주":
            return rows
        return []

    monkeypatch.setattr(server, "mail_rows", fake_mail_rows)
    monkeypatch.setattr(
        server,
        "_email_detail_by_ref",
        lambda email_ref: next((dict(row, classification={}) for row in rows if row["email_uid"] == email_ref), None),
    )

    context = server.inbox_context(selected_index=None, category="발주")
    html = server.templates.get_template("views/inbox.html").render(
        **context,
        request=request(),
    )
    source = Path("app/templates/partials/shell_runtime.html").read_text(encoding="utf-8")
    css = _app_css_source()

    assert calls[0]["category"] == "발주"
    assert context["loaded_count"] == 1
    assert context["selected_category"] == "발주"
    assert 'id="categoryFilter" name="category" value="발주"' in html
    assert 'data-category-filter-target="inbox"' in html
    assert "<span data-category-filter-selected-label>발주</span>" in html
    assert 'class="dashboard-category-select-option is-active"' in html
    assert 'data-category-filter="발주"' in html
    assert 'dropdown.dataset.categoryFilterTarget || "dashboard"' in source
    assert 'refreshInboxRows();' in source
    inbox_filter_css = css.split(".inbox-filter-row {")[-1].split("}", 1)[0]
    inbox_category_css = css.split(".inbox-category-select-field {", 1)[1].split("}", 1)[0]
    assert "grid-template-columns: minmax(0, 1fr) 108px max-content;" in inbox_filter_css
    assert "width: 108px;" in inbox_category_css
    assert "max-width: 108px;" in inbox_category_css
    assert any("z-index: 8;" in block and "overflow: visible;" in block for block in _css_blocks(css, ".inbox-toolbar"))
    assert any("z-index: 1;" in block for block in _css_blocks(css, ".inbox-layout"))

def test_inbox_context_filters_mail_rows_by_work_status(monkeypatch):
    rows = [
        {
            "index": 0,
            "email_uid": "mail-assigned",
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "subject": "Waiting",
            "has_attachment": False,
            "mail_category": "문의",
            "classification": {"mail_category": "문의"},
            "work_status": "assigned",
            "work_status_label": "미확인",
            "routing_display": "김민수",
            "date": "2026-08-12T00:24:00+00:00",
        },
        {
            "index": 1,
            "email_uid": "mail-completed",
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "subject": "Done",
            "has_attachment": False,
            "mail_category": "문의",
            "classification": {"mail_category": "문의"},
            "work_status": "completed",
            "work_status_label": "완료",
            "routing_display": "김민수",
            "date": "2026-08-12T00:25:00+00:00",
        },
    ]

    monkeypatch.setattr(server, "mail_rows", lambda **_: list(rows))
    monkeypatch.setattr(server, "_email_detail_by_ref", lambda email_ref: {"email_uid": email_ref, "classification": {}})

    context = server.inbox_context(selected_index=None, selected_email_uid="mail-assigned", status="completed")
    html = server.templates.get_template("views/inbox.html").render(
        **context,
        request=request(),
    )

    assert [row["email_uid"] for row in context["emails"]] == ["mail-completed"]
    assert context["selected_work_status"] == "completed"
    assert context["selected_email_uid"] == "mail-completed"
    assert 'class="mail-status-filter-highlight"' in html
    assert 'data-mail-status-filter="completed"' in html
    assert 'class="mail-status-filter-btn is-active"' in html
    assert 'aria-pressed="true"' in html
    assert ">완료</button>" in html
    assert "Done" in html
    assert "Waiting" not in html


def test_inbox_context_filters_rows_to_current_assignee(monkeypatch):
    rows = [
        {
            "index": 0,
            "email_uid": "mail-other",
            "sender_name": "Other",
            "sender_address": "other@example.invalid",
            "subject": "Other assignee",
            "has_attachment": False,
            "mail_category": "문의",
            "classification": {"mail_category": "문의"},
            "work_status": "assigned",
            "work_status_label": "미확인",
            "routing_display": "박지현",
            "assignee_email": "jh.park@dawonict.co.kr",
            "date": "2026-08-12T00:24:00+00:00",
        },
        {
            "index": 1,
            "email_uid": "mail-me",
            "sender_name": "Mine",
            "sender_address": "mine@example.invalid",
            "subject": "My assignee",
            "has_attachment": False,
            "mail_category": "문의",
            "classification": {"mail_category": "문의"},
            "work_status": "assigned",
            "work_status_label": "미확인",
            "routing_display": "김민수",
            "assignee_email": "m.kim@dawonict.co.kr",
            "date": "2026-08-12T00:25:00+00:00",
        },
    ]

    monkeypatch.setattr(server, "mail_rows", lambda **_: list(rows))
    monkeypatch.setattr(
        server,
        "_email_detail_by_ref",
        lambda email_ref: next((dict(row, classification={}) for row in rows if row["email_uid"] == email_ref), None),
    )
    monkeypatch.setattr(server, "auth_cookie_username", lambda _cookie: "m.kim@dawonict.co.kr")

    context = server.inbox_context(request(), selected_index=None, selected_email_uid="mail-other")

    assert [row["email_uid"] for row in context["emails"]] == ["mail-me"]
    assert context["selected_email_uid"] == "mail-me"


def test_inbox_ui_state_uses_current_assignee_visible_rows(monkeypatch):
    calls = []
    rows = [
        {"index": 0, "email_uid": "mail-other", "assignee_email": "other@example.com", "work_status": "assigned"},
        {"index": 1, "email_uid": "mail-me", "assignee_email": "me@example.com", "work_status": "assigned"},
    ]

    monkeypatch.setattr(server, "mail_rows", lambda **_: list(rows))
    monkeypatch.setattr(server, "visible_work_rows_for_request", lambda _request, source_rows: [rows[1]])
    monkeypatch.setattr(server, "_selected_email_detail_digest", lambda source_rows, **kwargs: calls.append(source_rows) or "detail")

    state = server.ui_state(request(), view="inbox", selected_email_uid="mail-other")

    assert calls == [[rows[1]]]
    assert state["selected_email_index"] == 0
    assert state["selected_email_uid"] == "mail-me"


def test_dashboard_mail_stream_controls_use_category_select_before_status_filter():
    html = server.templates.get_template("views/dashboard.html").render(
        **server.dashboard_context(),
        request=request(),
    )
    source = Path("app/templates/partials/shell_runtime.html").read_text(encoding="utf-8")
    css = _app_css_source()

    category_select = 'data-category-filter-select'
    status_filter = 'class="mail-status-filter dashboard-work-status-filter"'
    assert category_select in html
    assert status_filter in html
    assert 'class="mail-status-filter dashboard-work-status-filter" aria-label="진행 상태 필터" data-sliding-tabs' in html
    assert 'class="mail-status-filter-highlight" data-sliding-tabs-pill aria-hidden="true"' in html
    assert html.index(category_select) < html.index(status_filter)
    assert "<span data-category-filter-selected-label>업무 유형 전체</span>" in html
    assert 'class="dashboard-category-select-menu"' in html
    assert 'class="dashboard-category-select-option" data-category-filter="__all__" role="option">업무 유형 전체</button>' in html
    assert '<span class="mail-status-filter-label">진행 상태</span>' not in html
    assert 'class="chip-legend mail-category-filter' not in html
    assert "target instanceof HTMLSelectElement" in source
    assert "function updateSlidingTabs(scope, snap)" in source
    assert "function updateSlidingTabHighlight(group, activeButton, snap)" in source
    assert "[data-category-filter-selected-label]" in source
    assert ".dashboard-category-select {" in css
    select_field_css = css.split(".dashboard-category-select-field {", 1)[1].split("}", 1)[0]
    select_css = css.split(".dashboard-category-select {", 1)[1].split("}", 1)[0]
    status_highlight_css = css.split(".mail-status-filter-highlight {", 1)[1].split("}", 1)[0]
    status_button_css = css.split(".mail-status-filter-btn:hover,\n.mail-status-filter-btn.is-active {", 1)[1].split("}", 1)[0]
    assert "flex: 0 0 108px;" in select_field_css
    assert "color: var(--secondary);" in select_css
    assert "text-align: center;" in select_css
    assert "text-align-last: center;" in select_css
    assert ".dashboard-category-select-option {" in css
    option_css = css.split(".dashboard-category-select-option {", 1)[1].split("}", 1)[0]
    assert "color: var(--secondary);" in option_css
    assert "font-weight: 800;" in option_css
    assert "text-align: center;" in option_css
    assert any(
        "position: relative;" in block and "z-index: 5;" in block and "overflow: visible;" in block
        for block in _css_blocks(css, ".dashboard-mail-panel > .panel-head")
    )
    assert any(
        "position: relative;" in block and "z-index: 1;" in block
        for block in _css_blocks(css, ".dashboard-mail-table-wrap")
    )
    assert any("z-index: 2;" in block for block in _css_blocks(css, ".dashboard-mail-table thead th"))
    assert "border: 0;" in status_highlight_css
    assert "border-radius: 48px;" in status_highlight_css
    assert "background: #ffffff;" in status_highlight_css
    assert "color: var(--secondary);" in status_button_css


def test_assignee_dashboard_work_stats_link_to_my_work_status_filters():
    html = server.templates.get_template("partials/stats.html").render(
        request=request(),
        dashboard_work_scope=True,
        dashboard_scope_label="김민수",
        summary={
            "email_count": 11,
            "assigned_work_count": 2,
            "acknowledged_work_count": 1,
            "in_progress_work_count": 3,
            "responded_work_count": 4,
            "completed_work_count": 5,
            "completed_today_work_count": 1,
            "overdue_work_count": 6,
        },
    )

    assert 'hx-post="/ui/my-work"' in html
    assert 'hx-post="/ui/my-work?status=assigned"' in html
    assert 'hx-post="/ui/my-work?status=acknowledged"' in html
    assert 'hx-post="/ui/my-work?status=in_progress"' in html
    assert 'hx-post="/ui/my-work?status=responded"' in html
    assert 'hx-post="/ui/my-work?status=completed"' in html
    assert 'hx-post="/ui/my-work?status=overdue"' in html
    assert html.count('hx-target="#main-panel"') == 7
    assert html.count('hx-swap="innerHTML"') == 7
    assert "stats-assignee" in html
    assert "Assigned Work" in html
    assert "배정된 업무" in html
    assert "김민수 담당 업무" not in html
    assert "My Work" not in html
    assert "담당 업무 화면에서 미확인 업무 확인" in html
    assert "담당 업무 화면에서 확인한 업무 확인" in html
    assert "확인함" in html
    assert "담당 업무 화면에서 진행중 업무 확인" in html
    assert "담당 업무 화면에서 회신된 업무 확인" in html
    assert "담당 업무 화면에서 완료 업무 확인" in html


def test_dashboard_mail_rows_route_filters_by_work_status(monkeypatch):
    rows = [
        {
            "index": 0,
            "email_uid": "mail-progress",
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "subject": "Still open",
            "has_attachment": False,
            "mail_category": "문의",
            "classification": {"mail_category": "문의"},
            "work_status": "in_progress",
            "work_status_label": "진행중",
            "routing_display": "김민수",
            "date": "2026-08-12T00:24:00+00:00",
        },
        {
            "index": 1,
            "email_uid": "mail-completed",
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "subject": "Done",
            "has_attachment": False,
            "mail_category": "문의",
            "classification": {"mail_category": "문의"},
            "work_status": "completed",
            "work_status_label": "완료",
            "routing_display": "김민수",
            "date": "2026-08-12T00:25:00+00:00",
        },
    ]

    monkeypatch.setattr(server, "mail_rows", lambda **_: list(rows))
    monkeypatch.setattr(server, "dashboard_rows_for_request", lambda request, source_rows: list(source_rows))

    response = render_mail_rows(
        request(),
        q="",
        category="",
        limit=None,
        view="dashboard",
        status="completed",
        selected_email_index=None,
        selected_email_uid="",
        mail_rows=server.mail_rows,
        dashboard_rows=server.dashboard_rows_for_request,
        visible_rows=server.visible_work_rows_for_request,
        status_matches=server.status_matches_work_filter,
        dashboard_reference_date=server._dashboard_reference_date,
        ui_globals=server.ui_globals,
        templates=server.templates,
    )
    html = response.body.decode("utf-8")

    assert "Done" in html
    assert "Still open" not in html

def test_inbox_initial_queue_renders_mail_rows(monkeypatch):
    email_uid = "0732e633-db61-536e-8ff3-b820826cf9a2"
    monkeypatch.setattr(
        server,
        "mail_rows",
        lambda **_: [
            {
                "index": 0,
                "email_uid": email_uid,
                "sender_name": "박서진",
                "sender_address": "sales@mirae-tech.example",
                "subject": "[견적서 송부] 산업용 네트워크 장비 및 전원모듈",
                "has_attachment": True,
                "mail_category": "문의",
                "classification": {"mail_category": "문의"},
                "classification_state": "completed",
                "classification_state_label": "DB",
                "work_status": "assigned",
                "work_status_label": "배정 완료",
                "routing_display": "김민수",
                "date": "2026-08-12T00:24:00+00:00",
            }
        ],
    )
    monkeypatch.setattr(
        server,
        "_email_detail_by_ref",
        lambda email_ref: {
            "index": 0,
            "email_uid": email_uid,
            "sender_name": "박서진",
            "sender_address": "sales@mirae-tech.example",
            "subject": "[견적서 송부] 산업용 네트워크 장비 및 전원모듈",
            "body": "안녕하세요. 미래산업기술 박서진입니다.",
            "body_html": "",
            "body_html_srcdoc": "<pre>안녕하세요. 미래산업기술 박서진입니다.</pre>",
            "date": "2026-08-12T00:24:00+00:00",
            "received_at": "2026-08-12T00:24:00+00:00",
            "cc": "",
            "attachments": [],
            "classification": {
                "mail_category": "문의",
                "summary": "QT-2026-0812-03 - 견적서 유효기간·납기·합계금액 확인",
                "business_refs": ["QT-2026-0812-03"],
                "vessel_names": [],
            },
            "mail_category": "문의",
            "business_label": "문의",
            "classification_state": "completed",
            "assignee_name": "김민수",
            "assignee_email": "m.kim@dawonict.co.kr",
            "manual_route_status_label": "미전달",
        }
        if email_ref == email_uid
        else None,
    )

    html = server.templates.get_template("views/inbox.html").render(
        **server.inbox_context(selected_index=None),
        request=request(),
    )

    assert "Inbox Queue" not in html
    assert "1 loaded" not in html
    assert "[견적서 송부] 산업용 네트워크 장비 및 전원모듈" in html
    assert "Selected Mail" in html
    assert "안녕하세요. 미래산업기술 박서진입니다." in html
    assert "메일 목록을 불러오는 중" not in html

def test_email_body_cid_images_rewrite_to_inline_attachment_urls():
    body_html = '<p><strong>Hello</strong> 😊</p><img src="cid:signature-image"><div style="background:url(cid:logo-image)"></div>'
    rewritten = rewrite_email_body_cid_images(
        body_html,
        [
            {"content_id": "signature-image", "view_url": "/api/emails/mail-1/attachments/0?inline=true"},
            {"content_id": "<logo-image>", "view_url": "/api/emails/mail-1/attachments/1?inline=true"},
        ],
    )

    assert "<strong>Hello</strong>" in rewritten
    assert "😊" in rewritten
    assert 'src="/api/emails/mail-1/attachments/0?inline=true"' in rewritten
    assert 'url("/api/emails/mail-1/attachments/1?inline=true")' in rewritten

def test_related_emails_skips_mail_rows_when_message_has_no_business_refs(monkeypatch):
    def fail_mail_rows(*_args, **_kwargs):
        raise AssertionError("mail_rows should not be loaded without business refs")

    monkeypatch.setattr(server, "mail_rows", fail_mail_rows)

    assert server.related_emails({"email_uid": "mail-1", "classification": {"business_refs": []}}) == []
    assert server.related_emails({"email_uid": "mail-1", "classification": {}}) == []

def test_email_body_srcdoc_marks_images_lazy_and_async():
    srcdoc = email_body_srcdoc(
        '<p>사진 확인 부탁드립니다.</p><img src="cid:photo"><img src="/signature.png" loading="eager" />',
        [{"content_id": "photo", "view_url": "/api/emails/mail-1/attachments/0?inline=true"}],
    )

    assert 'src="/api/emails/mail-1/attachments/0?inline=true" loading="lazy" decoding="async"' in srcdoc
    assert 'src="/signature.png" loading="eager" decoding="async" />' in srcdoc

def test_postgres_detail_renders_html_body_with_inline_images_excluded_from_attachment_list(tmp_path):
    email_uid = RUN_PAYLOAD["email_message_id"]
    inline_path = tmp_path / "signature.png"
    referenced_image_path = tmp_path / "logo.png"
    visible_path = tmp_path / "quote.pdf"
    inline_path.write_bytes(b"png")
    referenced_image_path.write_bytes(b"png")
    visible_path.write_bytes(b"pdf")

    class Repository:
        def __init__(self):
            self.attachment_calls = []

        def attachments_for_message(self, message_id, *, include_inline=False):
            self.attachment_calls.append(include_inline)
            attachments = [
                {
                    "id": "inline-1",
                    "filename": "signature.png",
                    "storage_uri": str(inline_path),
                    "content_type": "image/png",
                    "content_id": "signature-image",
                    "content_disposition": "inline",
                    "file_size": 3,
                    "is_inline": True,
                },
                {
                    "id": "referenced-image-1",
                    "filename": "logo.png",
                    "storage_uri": str(referenced_image_path),
                    "content_type": "image/png",
                    "content_id": "logo-image",
                    "content_disposition": "attachment",
                    "file_size": 3,
                    "is_inline": False,
                },
                {
                    "id": "attachment-1",
                    "filename": "quote.pdf",
                    "storage_uri": str(visible_path),
                    "content_type": "application/pdf",
                    "file_size": 3,
                    "is_inline": False,
                },
            ]
            return attachments if include_inline else [item for item in attachments if not item["is_inline"]]

        def recipients_for_message(self, message_id):
            return []

        def attachment_path(self, attachment):
            return Path(str(attachment["storage_uri"]))

    service = PostgresMailboxService.__new__(PostgresMailboxService)
    service.repository = Repository()
    detail = service._email_detail_payload(
        {
            "id": email_uid,
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "subject": "HTML body",
            "body_text": "Plain fallback",
            "body_html": '<p><strong>Hello</strong> 😊</p><img src="cid:signature-image"><img src="cid:logo-image">',
            "snippet": "Plain fallback",
            "sent_at": "2026-08-10T01:00:00+00:00",
            "received_at": "2026-08-10T01:00:00+00:00",
            "attachment_count": 1,
            "has_attachment": True,
        },
        0,
    )

    assert detail["attachment_count"] == 1
    assert [item["filename"] for item in detail["attachments"]] == ["quote.pdf"]
    assert service.repository.attachment_calls == [True]
    assert "<strong>Hello</strong>" in detail["body_html_srcdoc"]
    assert "😊" in detail["body_html_srcdoc"]
    assert f"/api/emails/{email_uid}/attachments/0?inline=true" in detail["body_html_srcdoc"]

def test_postgres_detail_preserves_plain_text_leading_newlines():
    class Repository:
        def attachments_for_message(self, message_id, *, include_inline=False):
            return []

        def recipients_for_message(self, message_id):
            return []

    service = PostgresMailboxService.__new__(PostgresMailboxService)
    service.repository = Repository()
    detail = service._email_detail_payload(
        {
            "id": "email-plain",
            "sender_name": "Sender",
            "sender_address": "sender@example.invalid",
            "subject": "Plain body",
            "body_text": "\n\n안녕하세요.",
            "body_html": "",
            "snippet": "안녕하세요.",
            "sent_at": "2026-08-10T01:00:00+00:00",
            "received_at": "2026-08-10T01:00:00+00:00",
            "attachment_count": 0,
            "has_attachment": False,
        },
        0,
    )

    assert "<pre>\n\n안녕하세요.</pre>" in detail["body_html_srcdoc"]
    assert "white-space: pre-wrap" in detail["body_html_srcdoc"]
    assert "overflow-x: hidden" in detail["body_html_srcdoc"]

def test_email_body_srcdoc_prevents_horizontal_overflow_for_long_body_content():
    srcdoc = email_body_srcdoc(
        '<p style="white-space: nowrap">https://example.invalid/'
        f'{"very-long-reference-" * 20}</p>'
        '<table style="width: 1800px"><tr><td>QT-2026-0812-03</td></tr></table>',
        [],
    )

    assert "width: auto !important" in srcdoc
    assert "max-width: 100% !important" in srcdoc
    assert "overflow-wrap: anywhere" in srcdoc
    assert "word-break: break-word" in srcdoc

def test_ui_auth_redirects_login_and_logout(monkeypatch):
    monkeypatch.setattr(server, "AUTH_ENABLED", True)
    monkeypatch.setattr(server, "AUTH_USERNAME", "admin")
    monkeypatch.setattr(server, "AUTH_PASSWORD", "coramail")
    monkeypatch.setattr(server, "AUTH_SECRET", "test-secret")
    monkeypatch.setattr(server, "AUTH_COOKIE_NAME", "test_coramail_session")

    unauthenticated = server.auth_required_response(request_with_body("GET", "/"))
    assert unauthenticated.status_code == 303
    assert unauthenticated.headers["location"] == "/login?next=/"

    failed = asyncio.run(
        server.login_submit(
            request_with_body(
                "POST",
                "/login",
                b"username=admin&password=wrong",
                headers=[(b"content-type", b"application/x-www-form-urlencoded")],
            )
        )
    )
    assert failed.status_code == 401
    assert "아이디 또는 비밀번호가 올바르지 않습니다." in failed.body.decode("utf-8")

    logged_in = asyncio.run(
        server.login_submit(
            request_with_body(
                "POST",
                "/login",
                b"username=admin&password=coramail",
                headers=[(b"content-type", b"application/x-www-form-urlencoded")],
            )
        )
    )
    assert logged_in.status_code == 303
    assert logged_in.headers["location"] == "/"
    assert "test_coramail_session=" in logged_in.headers["set-cookie"]
    cookie_value = logged_in.headers["set-cookie"].split("test_coramail_session=", 1)[1].split(";", 1)[0]
    cookie_request = request_with_body(
        "GET",
        "/",
        headers=[(b"cookie", f"test_coramail_session={cookie_value}".encode("ascii"))],
    )

    assert server.is_authenticated(cookie_request) is True
    html = server.templates.get_template("shell.html").render(
        **server.ui_globals(cookie_request),
        request=cookie_request,
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
    assert '<span class="current-user">admin</span>' in html

    logged_out = server.logout_submit()
    assert logged_out.status_code == 303
    assert logged_out.headers["location"] == "/login"
    assert "test_coramail_session=" in logged_out.headers["set-cookie"]
    assert "Max-Age=0" in logged_out.headers["set-cookie"]

def test_work_complete_requires_authenticated_assignee(monkeypatch):
    email_uid = "e9105ba1-da36-5ef8-9471-7bcee37b48e4"
    monkeypatch.setattr(server, "_email_detail_by_ref", lambda email_ref: {"email_uid": email_uid} if email_ref == email_uid else None)
    monkeypatch.setattr(server, "current_authenticated_user_id", lambda request: None)

    try:
        server.ui_work_complete(request("POST"), email_uid)
    except server.HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("non-DB authenticated user should not complete work")


def test_work_in_progress_toggle_updates_assignee_status(monkeypatch):
    email_uid = "e9105ba1-da36-5ef8-9471-7bcee37b48e4"
    calls = []

    class Repository:
        def set_in_progress(self, *, email_message_id, actor_user_id, active):
            calls.append((str(email_message_id), str(actor_user_id), active))
            return {"status": "in_progress" if active else "assigned"}

    monkeypatch.setattr(server, "_email_detail_by_ref", lambda email_ref: {"email_uid": email_uid} if email_ref == email_uid else None)
    monkeypatch.setattr(server, "current_authenticated_user_id", lambda request: UUID("10000000-0000-0000-0000-000000000001"))
    monkeypatch.setattr(server, "_postgres_work_tracking_repository", Repository())

    response = asyncio.run(server.ui_work_in_progress_toggle(request_with_body("POST", "/", b"active=true"), email_uid))

    assert response.status_code == 204
    assert calls == [(email_uid, "10000000-0000-0000-0000-000000000001", True)]
    trigger = json.loads(response.headers["HX-Trigger"])
    assert trigger == {
        "work-item-status-changed": {
            "email_uid": email_uid,
            "work_status": "in_progress",
        }
    }


def test_work_in_progress_toggle_requires_authenticated_assignee(monkeypatch):
    email_uid = "e9105ba1-da36-5ef8-9471-7bcee37b48e4"
    monkeypatch.setattr(server, "_email_detail_by_ref", lambda email_ref: {"email_uid": email_uid} if email_ref == email_uid else None)
    monkeypatch.setattr(server, "current_authenticated_user_id", lambda request: None)

    with pytest.raises(server.HTTPException) as exc_info:
        asyncio.run(server.ui_work_in_progress_toggle(request_with_body("POST", "/", b"active=true"), email_uid))

    assert exc_info.value.status_code == 403


def test_inbox_context_marks_selected_email_read_without_starting_work(monkeypatch):
    calls = []
    email = {
        "index": 0,
        "email_uid": "e9105ba1-da36-5ef8-9471-7bcee37b48e4",
        "subject": "RFQ",
        "work_status": "assigned",
        "work_status_label": "미확인",
        "classification": {},
    }
    monkeypatch.setattr(server, "mail_rows", lambda **_: [email])
    monkeypatch.setattr(server, "_email_detail_by_ref", lambda email_ref: email if email_ref == email["email_uid"] else None)
    monkeypatch.setattr(server, "ensure_can_view_work_email", lambda request, selected_email: calls.append(("guard", selected_email["email_uid"])))
    monkeypatch.setattr(server, "_mark_mail_read_for_current_user", lambda request, selected_email: calls.append(("read", selected_email["email_uid"])))

    context = server.inbox_context(request(), selected_email_uid=email["email_uid"])

    assert context["email"] == email
    assert context["email"]["work_status"] == "assigned"
    assert calls == [("guard", email["email_uid"]), ("read", email["email_uid"])]

def test_email_detail_triggers_mail_read_refresh(monkeypatch):
    email_uid = "e9105ba1-da36-5ef8-9471-7bcee37b48e4"
    email = {
        "index": 0,
        "email_uid": email_uid,
        "subject": "RFQ",
        "work_status": "assigned",
        "work_status_label": "미확인",
        "classification": {},
    }
    monkeypatch.setattr(server, "_email_detail_by_ref", lambda email_ref: email if email_ref == email_uid else None)
    monkeypatch.setattr(server, "ensure_can_view_work_email", lambda request, selected_email: None)

    response = render_email_detail(
        request(),
        email_uid,
        email_detail=server._email_detail_by_ref,
        ensure_can_view=server.ensure_can_view_work_email,
        mark_mail_read=lambda request, selected_email: {"was_unread": True},
        ui_globals=server.ui_globals,
        related_emails=server.related_emails,
        templates=server.templates,
    )

    trigger = json.loads(response.headers["HX-Trigger"])
    assert trigger == {"mail-read-state-changed": {"email_uid": email_uid}}

def test_email_detail_triggers_work_status_refresh_after_acknowledgement(monkeypatch):
    email_uid = "e9105ba1-da36-5ef8-9471-7bcee37b48e4"
    email = {
        "index": 0,
        "email_uid": email_uid,
        "subject": "RFQ",
        "work_status": "acknowledged",
        "work_status_label": "확인함",
        "classification": {},
    }
    monkeypatch.setattr(server, "_email_detail_by_ref", lambda email_ref: email if email_ref == email_uid else None)
    monkeypatch.setattr(server, "ensure_can_view_work_email", lambda request, selected_email: None)

    response = render_email_detail(
        request(),
        email_uid,
        email_detail=server._email_detail_by_ref,
        ensure_can_view=server.ensure_can_view_work_email,
        mark_mail_read=lambda request, selected_email: {
            "was_unread": True,
            "work_status_changed": True,
            "work_status": "acknowledged",
        },
        ui_globals=server.ui_globals,
        related_emails=server.related_emails,
        templates=server.templates,
    )

    trigger = json.loads(response.headers["HX-Trigger"])
    assert trigger == {
        "mail-read-state-changed": {"email_uid": email_uid},
        "work-item-status-changed": {"email_uid": email_uid, "work_status": "acknowledged"},
    }

def test_mark_mail_read_acknowledges_assignee_work(monkeypatch):
    email_uid = "e9105ba1-da36-5ef8-9471-7bcee37b48e4"
    actor_user_id = UUID("10000000-0000-0000-0000-000000000001")
    calls = []

    class ReadRepository:
        def mark_read(self, *, email_message_id, user_id):
            calls.append(("read", str(email_message_id), str(user_id)))
            return {"was_unread": True}

    class WorkRepository:
        def acknowledge_if_assignee(self, *, email_message_id, actor_user_id):
            calls.append(("acknowledge", str(email_message_id), str(actor_user_id)))
            return {"status": "acknowledged"}

    monkeypatch.setattr(server, "database_url", lambda: "postgresql://example")
    monkeypatch.setattr(server, "current_authenticated_user_id", lambda request: actor_user_id)
    monkeypatch.setattr(server, "_postgres_mail_read_repository", ReadRepository())
    monkeypatch.setattr(server, "_postgres_work_tracking_repository", WorkRepository())

    result = server._mark_mail_read_for_current_user(
        request(),
        {"email_uid": email_uid, "work_status": "assigned"},
    )

    assert result == {
        "was_unread": True,
        "work_status_changed": True,
        "work_status": "acknowledged",
    }
    assert calls == [
        ("read", email_uid, str(actor_user_id)),
        ("acknowledge", email_uid, str(actor_user_id)),
    ]

def test_employee_cannot_open_other_assignee_detail(monkeypatch):
    email = {
        "email_uid": "mail-2",
        "assignee_name": "박지현",
        "assignee_email": "jh.park@dawonict.co.kr",
        "routing_display": "박지현",
    }
    monkeypatch.setattr(server, "_email_detail_by_ref", lambda email_ref: email if email_ref == "mail-2" else None)
    monkeypatch.setattr(server, "auth_cookie_username", lambda _cookie: "m.kim@dawonict.co.kr")

    try:
        render_email_detail(
            request(),
            "mail-2",
            email_detail=server._email_detail_by_ref,
            ensure_can_view=server.ensure_can_view_work_email,
            mark_mail_read=server._mark_mail_read_for_current_user,
            ui_globals=server.ui_globals,
            related_emails=server.related_emails,
            templates=server.templates,
        )
    except server.HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("employee should not open another assignee detail")

def test_work_reply_initiate_redirects_to_gmail_after_recording(monkeypatch):
    email_uid = "e9105ba1-da36-5ef8-9471-7bcee37b48e4"
    actor_user_id = UUID("2e63138e-8f0b-40a7-b35e-0c71d229d432")
    calls = []

    class FakeWorkTrackingRepository:
        def initiate_reply(self, *, email_message_id, actor_user_id):
            calls.append((email_message_id, actor_user_id))
            return {"provider_thread_id": "thread-123"}

    monkeypatch.setattr(server, "_email_detail_by_ref", lambda email_ref: {"email_uid": email_uid} if email_ref == email_uid else None)
    monkeypatch.setattr(server, "current_authenticated_user_id", lambda request: actor_user_id)
    monkeypatch.setattr(server, "_postgres_work_tracking_repository", FakeWorkTrackingRepository())

    response = server.ui_work_reply_initiate(request_with_body("POST", "/", headers=[(b"hx-request", b"true")]), email_uid)

    assert response.status_code == 204
    assert response.headers["HX-Redirect"].endswith("/thread-123")
    assert calls == [(UUID(email_uid), actor_user_id)]

def test_work_reply_initiate_normal_post_redirects_to_gmail_for_new_tab(monkeypatch):
    email_uid = "e9105ba1-da36-5ef8-9471-7bcee37b48e4"
    actor_user_id = UUID("2e63138e-8f0b-40a7-b35e-0c71d229d432")

    class FakeWorkTrackingRepository:
        def initiate_reply(self, *, email_message_id, actor_user_id):
            return {"provider_thread_id": "thread-123"}

    monkeypatch.setattr(server, "_email_detail_by_ref", lambda email_ref: {"email_uid": email_uid} if email_ref == email_uid else None)
    monkeypatch.setattr(server, "current_authenticated_user_id", lambda request: actor_user_id)
    monkeypatch.setattr(server, "_postgres_work_tracking_repository", FakeWorkTrackingRepository())

    response = server.ui_work_reply_initiate(request("POST"), email_uid)

    assert response.status_code == 303
    assert response.headers["location"].endswith("/thread-123")

def test_operating_paths_require_authentication(monkeypatch):
    monkeypatch.setattr(server, "AUTH_ENABLED", True)

    for path in [
        "/ui/settings/gmail-sync",
        "/ui/settings/gmail/client-config",
        "/ui/settings/gmail/tokens",
        "/ui/settings/gmail/connect",
        "/ui/settings/gmail/disconnect",
        "/ui/settings/gmail/sync",
        "/ui/auto-sync/run",
        "/api/auto-sync",
        "/api/emails",
        "/api/emails/mail-1/attachments/0",
        "/api/emails/mail-1/routing",
        "/api/search",
        "/api/jobs/run-pending",
    ]:
        assert server.path_requires_auth(path) is True

    assert server.path_requires_auth("/") is True
    assert server.path_requires_auth("/ui/dashboard") is True
    assert server.path_requires_auth("/api/ui-state") is True
    assert server.path_requires_auth("/api/health") is False
    assert server.path_requires_auth("/api/health/details") is True
    assert server.path_requires_auth("/api/client-version") is False
    assert server.path_requires_auth("/auth/gmail/callback") is False

def test_self_mail_decision_runtime_client_forwards_auth_cookie(monkeypatch):
    monkeypatch.delenv("CORAMAIL_MAIL_DECISION_RUNTIME_URL", raising=False)
    cookie = server.auth_cookie_value("ops-admin", now=1000)
    runtime_client = server.mail_decision_runtime_client(
        request_with_body("POST", "/", headers=[(b"cookie", f"{server.AUTH_COOKIE_NAME}={cookie}".encode("ascii"))])
    )

    assert runtime_client.session.headers["Cookie"] == f"{server.AUTH_COOKIE_NAME}={cookie}"

def test_external_mail_decision_runtime_client_does_not_forward_ui_cookie(monkeypatch):
    monkeypatch.setenv("CORAMAIL_MAIL_DECISION_RUNTIME_URL", "http://runtime.internal")
    cookie = server.auth_cookie_value("ops-admin", now=1000)
    runtime_client = server.mail_decision_runtime_client(
        request_with_body("POST", "/", headers=[(b"cookie", f"{server.AUTH_COOKIE_NAME}={cookie}".encode("ascii"))])
    )

    assert "Cookie" not in runtime_client.session.headers

def test_settings_renders_demo_duplicate_receive_button_when_enabled():
    context = {
        **server.ui_globals(),
        "request": request(),
        "demo_duplicate_mail_enabled": True,
        "category_order": ["발주", "문의", "서비스", "기술", "기타", "미분류"],
        "route_assignments": [],
        "assignees": [],
        "routing_table_options": {"mail_categories": ["발주"], "business_labels": ["발주"]},
    }
    html = server.templates.get_template("views/settings.html").render(**context)

    assert 'action="/ui/settings/demo/receive-latest-duplicate"' in html
    assert "최신 메일 다시 수신" in html

def test_receive_latest_duplicate_demo_mail_redirects_to_new_inbox_mail(monkeypatch):
    started = []
    monkeypatch.setattr(server, "request_demo_mode", lambda request: True)
    monkeypatch.setattr(server, "duplicate_latest_demo_mail_for_review", lambda: "mail-new")
    monkeypatch.setattr(server, "_start_received_demo_mail_processing", lambda email_uid: started.append(email_uid))

    response = server.ui_receive_latest_duplicate_demo_mail(request("POST"))

    assert response.status_code == 303
    assert response.headers["location"] == "/?view=inbox&email_uid=mail-new"
    assert "coramail_display_mode=demo" in response.headers["set-cookie"]
    assert started == ["mail-new"]

def test_settings_renders_synthetic_assignees_as_read_only_data_in_both_modes():
    synthetic_assignees = PostgresAssigneeAdminRepository._synthetic_views(
        [
            {
                "id": "synthetic-1",
                "name": "합성 담당자 1",
                "email": "clean-v2-assignee1@coramail.invalid",
                "status": "active",
                "capability_type": "customer",
                "capability_value": "Synthetic Marine Customer 01",
            },
            {
                "id": "synthetic-1",
                "name": "합성 담당자 1",
                "email": "clean-v2-assignee1@coramail.invalid",
                "status": "active",
                "capability_type": "business_type",
                "capability_value": "repair_request",
            },
            {
                "id": "synthetic-1",
                "name": "합성 담당자 1",
                "email": "clean-v2-assignee1@coramail.invalid",
                "status": "active",
                "capability_type": "project",
                "capability_value": "PRJ-2026-001",
            },
        ]
    )
    template = server.templates.get_template("views/settings.html")
    context = {
        **server.ui_globals(),
        "demo_mode": True,
        "assignees": synthetic_assignees,
        "operating_assignee_count": 0,
        "synthetic_assignee_count": 1,
        "route_assignments": [],
        "routing_table_options": {"mail_categories": ["서비스"], "business_labels": ["서비스"]},
        "routing_policy": RoutingPolicySettings(
            auto_assign_threshold=0.82,
            minimum_margin=0.15,
            minimum_classification_confidence=0.78,
        ),
        "routing_policy_message": "",
        "routing_policy_error": "",
    }

    html = template.render(**context)

    assert "자동 배정 기준" not in html
    assert 'name="auto_assign_threshold"' not in html
    assert 'value="0.82"' not in html
    assert "평가용 합성 담당자" not in html
    assert "전체 1" in html
    assert "전체 1 · 운영 0 · 합성 1" not in html
    assert "합성 담당자 1" in html
    assert "평가 데이터" in html
    assert "서비스" in html
    assert "읽기 전용" in html
    assert 'data-synthetic-assignee' in html
    assert f"/ui/settings/routing-table/{synthetic_assignees[0]['assignee_id']}" not in html
    assert synthetic_assignees[0]["capability_count"] == 3

    gmail_html = template.render(**{**context, "demo_mode": False})
    assert "평가용 합성 담당자" not in gmail_html
    assert "합성 담당자 1" in gmail_html
    assert "읽기 전용" in gmail_html

def test_settings_route_assignments_follow_category_priority(monkeypatch):
    monkeypatch.setattr(server, "database_url", lambda: "postgresql://local/test")
    monkeypatch.setattr(
        server._postgres_assignee_admin_repository,
        "list_operating_assignees",
        lambda: [
            {
                "assignee_id": "10000000-0000-0000-0000-000000000001",
                "assignee_name": "김민수",
                "email_address": "m.kim@example.invalid",
                "mail_categories": ["문의"],
                "category_priorities": {"문의": 2},
                "is_active": True,
            },
            {
                "assignee_id": "10000000-0000-0000-0000-000000000002",
                "assignee_name": "박지영",
                "email_address": "j.park@example.invalid",
                "mail_categories": ["문의"],
                "category_priorities": {"문의": 1},
                "is_active": True,
            },
        ],
    )
    monkeypatch.setattr(server._postgres_assignee_admin_repository, "list_active_synthetic_assignees", lambda: [])

    inquiry = next(item for item in server.settings_context()["route_assignments"] if item["label"] == "문의")

    assert [item["assignee_name"] for item in inquiry["assignees"]] == ["박지영", "김민수"]

from __future__ import annotations

from pathlib import Path

from starlette.requests import Request

import app.server as server
from app.services.address_book_service import address_book_view


def request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [], "app": server.app})


def ui_context() -> dict[str, object]:
    return {
        "asset_version": "test",
        "demo_mode": False,
        "display_mode": "gmail",
        "display_mode_label": "Gmail",
        "display_mode_next_label": "Demo",
        "gmail_connected_account": "mailbox@example.invalid",
        "current_user": "admin",
        "current_user_id": "",
        "current_user_can_view_all_assignees": True,
        "category_order": [],
        "work_status_filter_options": [],
    }


def test_address_book_groups_sender_profiles_by_email_address():
    rows = [
        {
            "email_uid": "mail-1",
            "provider_thread_id": "thread-1",
            "sender_name": "김민수",
            "sender_address": "buyer@example.com",
            "subject": "견적 요청",
            "date": "2026-08-11T01:00:00+00:00",
            "mail_category": "문의",
            "classification": {"counterparty": "미래산업기술"},
        },
        {
            "email_uid": "mail-2",
            "provider_thread_id": "thread-1",
            "sender_name": "Kim Minsoo",
            "sender_address": "BUYER@example.com",
            "subject": "Re: 견적 요청",
            "date": "2026-08-10T01:00:00+00:00",
            "mail_category": "문의",
        },
        {
            "email_uid": "mail-3",
            "provider_thread_id": "thread-2",
            "sender_name": "박서진",
            "sender_address": "sales@example.com",
            "subject": "발주서 송부",
            "date": "2026-08-09T01:00:00+00:00",
            "mail_category": "발주",
            "mail_facts": {"customer_name": "새롬테크"},
        },
    ]

    view = address_book_view(rows)
    profiles = {profile["sender_address"].casefold(): profile for profile in view["address_book_profiles"]}

    assert view["address_book_profile_count"] == 2
    assert profiles["buyer@example.com"]["sender_name"] == "김민수"
    assert profiles["buyer@example.com"]["organization"] == "미래산업기술"
    assert profiles["buyer@example.com"]["email_count"] == 2
    assert profiles["buyer@example.com"]["thread_count"] == 1
    assert [item["subject"] for item in profiles["buyer@example.com"]["recent_emails"]] == [
        "견적 요청",
        "Re: 견적 요청",
    ]
    assert profiles["sales@example.com"]["organization"] == "새롬테크"


def test_address_book_limits_recent_emails_to_three_by_default():
    rows = [
        {
            "email_uid": f"mail-{index}",
            "provider_thread_id": f"thread-{index}",
            "sender_name": "김민수",
            "sender_address": "buyer@example.com",
            "subject": f"견적 요청 {index}",
            "date": f"2026-08-1{index}T01:00:00+00:00",
            "mail_category": "문의",
        }
        for index in range(1, 5)
    ]

    view = address_book_view(rows)
    profile = view["address_book_profiles"][0]

    assert [item["subject"] for item in profile["recent_emails"]] == [
        "견적 요청 1",
        "견적 요청 2",
        "견적 요청 3",
    ]


def test_address_book_filters_profiles_by_organization_and_keeps_organization_list():
    rows = [
        {
            "email_uid": "mail-0",
            "provider_thread_id": "thread-0",
            "sender_name": "이수정",
            "sender_address": "unknown@example.com",
            "subject": "확인 요청",
            "date": "2026-08-12T01:00:00+00:00",
            "mail_category": "문의",
        },
        {
            "email_uid": "mail-1",
            "provider_thread_id": "thread-1",
            "sender_name": "김민수",
            "sender_address": "buyer@example.com",
            "subject": "견적 요청",
            "date": "2026-08-11T01:00:00+00:00",
            "mail_category": "문의",
            "classification": {"counterparty": "미래산업기술"},
        },
        {
            "email_uid": "mail-2",
            "provider_thread_id": "thread-2",
            "sender_name": "박서진",
            "sender_address": "sales@example.com",
            "subject": "발주서 송부",
            "date": "2026-08-09T01:00:00+00:00",
            "mail_category": "발주",
            "mail_facts": {"customer_name": "새롬테크"},
        },
    ]

    view = address_book_view(rows, organization="미래산업기술")

    assert view["selected_organization"] == "미래산업기술"
    assert [item["label"] for item in view["address_book_organizations"]] == ["미래산업기술", "새롬테크", "미확인"]
    assert [profile["sender_name"] for profile in view["address_book_profiles"]] == ["김민수"]


def test_address_book_rejects_mail_type_labels_as_organization_names():
    rows = [
        {
            "email_uid": "mail-1",
            "provider_thread_id": "thread-1",
            "sender_name": "김민수",
            "sender_address": "buyer@example.com",
            "subject": "도면 승인 요청",
            "date": "2026-08-11T01:00:00+00:00",
            "mail_category": "도면 검토",
            "classification": {"counterparty": "도면 검토"},
            "mail_facts": {"customer_candidates": ["도면 검토", "미래산업기술"]},
        },
        {
            "email_uid": "mail-2",
            "provider_thread_id": "thread-2",
            "sender_name": "박서진",
            "sender_address": "support@example.com",
            "subject": "긴급 장애 지원 요청",
            "date": "2026-08-10T01:00:00+00:00",
            "mail_category": "긴급 장애",
            "mail_facts": {"customer_name": "긴급 장애", "customer_candidates": ["긴급 장애"]},
        },
    ]

    view = address_book_view(rows)
    profiles = {profile["sender_address"].casefold(): profile for profile in view["address_book_profiles"]}
    organizations = [item["label"] for item in view["address_book_organizations"]]

    assert profiles["buyer@example.com"]["organization"] == "미래산업기술"
    assert profiles["support@example.com"]["organization"] == "미확인"
    assert "도면 검토" not in organizations
    assert "긴급 장애" not in organizations


def test_address_book_view_renders_sender_name_email_and_thread_history():
    html = server.templates.get_template("views/address_book.html").render(
        **ui_context(),
        request=request(),
        query="",
        selected_organization="미래산업기술",
        address_book_organizations=[
            {"label": "미래산업기술", "count": 1},
            {"label": "새롬테크", "count": 1},
        ],
        address_book_profiles=[
            {
                "sender_name": "김민수",
                "sender_address": "buyer@example.com",
                "organization": "미래산업기술",
                "email_count": 2,
                "thread_count": 1,
                "last_seen": "2026-08-11T01:00:00+00:00",
                "top_categories": [{"label": "문의", "count": 2}],
                "recent_emails": [
                    {
                        "email_uid": "mail-1",
                        "subject": "견적 요청",
                        "date": "2026-08-11T01:00:00+00:00",
                        "mail_category": "문의",
                    }
                ],
            }
        ],
        address_book_profile_count=1,
        address_book_email_count=2,
        address_book_thread_count=1,
    )

    assert 'data-view="address-book"' in html
    assert "주소록" in html
    assert "Address Book" not in html
    assert "address-book-summary" not in html
    assert "<span>발신자</span>" not in html
    assert "<span>저장 메일</span>" not in html
    assert "<span>스레드</span>" not in html
    assert "address-organization-filter" in html
    assert "미래산업기술 <span>1</span>" in html
    assert 'hx-post="/ui/address-book?organization=' in html
    assert "김민수" in html
    assert "buyer@example.com" in html
    assert "미래산업기술" in html
    assert "최근 일시" in html
    assert "<dt>최근</dt>" not in html
    assert "이전 이메일 스레드" in html
    assert "address-history-subject" in html
    assert "address-history-meta" in html
    assert "address-history-time" in html
    assert 'class="mono address-history-time"' not in html
    assert "주요 업무 유형" not in html
    assert "문의 2" not in html
    assert "category-chip" in html
    assert "·" not in html
    assert 'hx-post="/ui/inbox?email_uid=mail-1"' in html


def test_address_book_cards_do_not_force_mobile_horizontal_overflow():
    css = Path("app/static/app-04.css").read_text(encoding="utf-8")

    grid_block = css.split(".address-book-grid {", 1)[1].split("}", 1)[0]
    search_input_block = css.split(".address-book-search .input {", 1)[1].split("}", 1)[0]
    header_text_block = css.split(".address-card-head > div {", 1)[1].split("}", 1)[0]
    email_block = css.split(".address-card-head p {", 1)[1].split("}", 1)[0]

    assert "grid-template-columns: repeat(auto-fill, minmax(min(100%, 340px), 380px));" in grid_block
    assert "width: 100%;" in search_input_block
    assert "min-width: 0;" in search_input_block
    assert "max-width: 100%;" in search_input_block
    assert "min-width: 0;" in header_text_block
    assert "min-width: 0;" in email_block
    assert "overflow: hidden;" in email_block
    assert "text-overflow: ellipsis;" in email_block
    assert "white-space: nowrap;" in email_block


def test_shell_has_address_book_navigation():
    html = server.templates.get_template("shell.html").render(
        **ui_context(),
        request=request(),
        active_view="address-book",
        initial_view_template="views/address_book.html",
        query="",
        selected_organization="",
        address_book_organizations=[],
        address_book_profiles=[],
        address_book_profile_count=0,
        address_book_email_count=0,
        address_book_thread_count=0,
    )

    assert "Contacts 탭 열기" in html
    assert ">Contacts" in html
    assert 'hx-post="/ui/address-book"' in html
    assert '"address-book": "/ui/address-book"' in html
    assert '"address-book": "Contacts"' in html


def test_address_book_routes_are_registered():
    assert str(server.app.url_path_for("address_book")) == "/ui/address-book"
    assert str(server.app.url_path_for("address_book_list")) == "/ui/address-book-list"


def test_mail_rows_render_sender_contact_popover_and_contacts_navigation():
    email = {
        "index": 0,
        "email_uid": "mail-1",
        "sender_name": "김민수",
        "sender_address": "buyer@example.com",
        "subject": "견적 요청",
        "date": "2026-08-11T01:00:00+00:00",
        "mail_category": "문의",
        "work_status": "assigned",
        "work_status_label": "미확인",
        "classification": {"mail_category": "문의"},
        "routing_display": "미할당",
        "sender_contact": {
            "sender_name": "김민수",
            "sender_address": "buyer@example.com",
            "organization": "미래산업기술",
            "email_count": 2,
            "thread_count": 1,
            "last_seen": "2026-08-11T01:00:00+00:00",
            "top_categories": [{"label": "문의", "count": 2}],
        },
    }

    html = server.templates.get_template("partials/mail_rows.html").render(
        **ui_context(),
        request=request(),
        emails=[email],
        mail_rows_mode="inbox",
        selected_email_uid="",
        selected_email_index=None,
    )

    assert "sender-contact-popover" in html
    assert "미래산업기술" in html
    assert "저장 메일 2건 · 스레드 1개" in html
    assert 'href="/?view=address-book' in html
    assert "q=buyer%40example.com" in html
    assert 'hx-post="/ui/address-book?q=buyer%40example.com"' in html
    assert 'hx-on:click="event.stopPropagation()"' in html


def test_selected_mail_header_renders_sender_contact_popover():
    email = {
        "index": 0,
        "email_uid": "mail-1",
        "sender_name": "김민수",
        "sender_address": "buyer@example.com",
        "subject": "견적 요청",
        "classification_state": "completed",
        "classification": {"mail_category": "문의"},
        "attachments": [],
        "sender_contact": {
            "sender_name": "김민수",
            "sender_address": "buyer@example.com",
            "organization": "미래산업기술",
            "email_count": 2,
            "thread_count": 1,
            "last_seen": "2026-08-11T01:00:00+00:00",
            "top_categories": [],
        },
    }

    html = server.templates.get_template("partials/email_detail.html").render(
        **ui_context(),
        request=request(),
        email=email,
        related_emails=[],
        customer_history=[],
    )

    assert "Selected Mail" in html
    assert "sender-contact-popover" in html
    assert "김민수 Contacts 보기" in html
    assert "미래산업기술" in html
    assert 'hx-post="/ui/address-book?q=buyer%40example.com"' in html

# ruff: noqa: F403, F405
from tests.ui_test_support import *  # noqa: F401,F403

def test_mail_rows_template_renders_work_status_before_classification_state():
    html = server.templates.get_template("partials/mail_rows.html").render(
        {
            **server.ui_globals(),
            "emails": [
                {
                    "index": 0,
                    "email_uid": RUN_PAYLOAD["email_message_id"],
                    "sender_name": "Buyer",
                    "sender_address": "buyer@example.invalid",
                    "subject": "RFQ review",
                    "has_attachment": False,
                    "mail_category": "문의",
                    "classification": {"mail_category": "문의"},
                    "classification_state": "completed",
                    "classification_state_label": "DB",
                    "work_status": "review_required",
                    "work_status_label": "검토 필요",
                    "routing_display": "미할당",
                    "date": "2026-08-10T01:00:00+00:00",
                }
            ],
            "mail_rows_mode": "inbox",
            "selected_email_index": None,
            "selected_email_uid": "",
        }
    )

    assert "row-status review_required" in html
    assert "검토 필요" in html
    assert "receiver-chip category-chip--unclassified" in html
    assert "미할당" in html
    assert ">DB<" not in html

def test_work_status_rows_define_distinct_visual_tones():
    css = _app_css_source()

    expected_rules = {
        ".row-status.assigned { color: #7c3aed; }",
        ".row-status.acknowledged { color: #0891b2; }",
        ".row-status.in_progress { color: #2563eb; }",
        ".row-status.responded { color: #0e7490; }",
        ".row-status.completed { color: var(--ok); }",
    }
    for rule in expected_rules:
        assert rule in css

    assert ".t-like[data-liked=\"true\"] .t-like-star path" in css
    assert "--like-color: #facc15;" in css
    assert "@keyframes t-like-burst" in css
    assert "@keyframes mail-row-click-pop" in css
    assert "@keyframes mail-row-cell-click-pop" in css
    assert "#mailRows .clickable-row.is-click-transition > td" in css
    assert "#dashboardMailRows .clickable-row.is-mail-favorite > td:first-child" in css
    assert "#dashboardMailRows .mail-favorite-toggle" in css
    assert "pointer-events: auto;" in css
    assert ".clickable-row.is-click-transition" in css
    assert ".t-toggle { transition: background var(--toggle-track) var(--toggle-ease); }" in css
    assert ".t-toggle[data-on=\"true\"] .t-toggle-thumb" in css
    assert "@keyframes t-toggle-on" in css
    assert "@keyframes t-toggle-off" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    progress_toggle_css = css.split(".work-progress-toggle {", 1)[1].split("}", 1)[0]
    detail_progress_toggle_css = css.split(".detail-action-row .work-progress-toggle {", 1)[1].split("}", 1)[0]
    favorite_toggle_css = css.split(".mail-favorite-toggle {", 1)[1].split("}", 1)[0]
    assert "border-radius: 999px;" in progress_toggle_css
    assert "background: #cbd5e1;" in progress_toggle_css
    assert "width: 34px;" in progress_toggle_css
    assert "height: 20px;" in progress_toggle_css
    assert "width: 34px;" in detail_progress_toggle_css
    assert "background: transparent;" in favorite_toggle_css


def test_settings_routing_priority_drag_has_no_drop_target_border_highlight():
    css = _app_css_source()

    assert ".settings-unified-rule-assignees.is-drop-target" not in css


def test_mail_rows_template_colors_receiver_by_business_category():
    categories = {
        "발주": "category-chip--order",
        "문의": "category-chip--inquiry",
        "서비스": "category-chip--service",
        "기술": "category-chip--technical",
        "기타": "category-chip--general",
    }
    html = server.templates.get_template("partials/mail_rows.html").render(
        {
            **server.ui_globals(),
            "emails": [
                {
                    "index": index,
                    "email_uid": f"mail-{index}",
                    "sender_name": "Buyer",
                    "sender_address": "buyer@example.invalid",
                    "subject": f"{category} request",
                    "has_attachment": False,
                    "mail_category": category,
                    "classification": {"mail_category": category},
                    "classification_state": "completed",
                    "work_status": "assigned",
                    "work_status_label": "배정 완료",
                    "routing_display": f"{category} 담당자",
                    "date": "2026-08-10T01:00:00+00:00",
                }
                for index, category in enumerate(categories.keys())
            ],
            "mail_rows_mode": "inbox",
            "selected_email_index": None,
            "selected_email_uid": "",
        }
    )

    for category, css_class in categories.items():
        assert f"receiver-chip {css_class}" in html
        assert f"{category} 담당자" in html

def test_attachment_reanalysis_uses_resolved_persistent_mailbox_service(monkeypatch):
    email_uid = RUN_PAYLOAD["email_message_id"]
    attachment_uid = "6b4d8519-a2ad-49de-bf12-c1d2637f0e43"
    gmail_attachment = {
        "id": attachment_uid,
        "filename": "field-site-photo.png",
        "content_type": "image/png",
        "storage_uri": "/tmp/field-site-photo.png",
    }

    class Repository:
        def __init__(self, attachments):
            self.attachments = attachments
            self.calls = []

        def attachments_for_message(self, message_id):
            self.calls.append(message_id)
            return list(self.attachments)

    class PersistentService:
        def __init__(self, email, attachments):
            self.email = email
            self.repository = Repository(attachments)

        def email_detail_by_uid(self, requested_uid):
            return self.email if requested_uid == email_uid else None

    gmail_service = PersistentService({"email_uid": email_uid, "index": 0}, [gmail_attachment])
    synthetic_service = PersistentService(None, [])
    monkeypatch.setattr(server, "_gmail_postgres_service", gmail_service)
    monkeypatch.setattr(server, "_postgres_service", synthetic_service)
    monkeypatch.setattr(server, "postgres_jobs_enabled", lambda: True)
    monkeypatch.setattr(
        server._attachment_parser_dispatcher,
        "analyze",
        lambda attachment: AttachmentAnalysisResult(
            attachment_id=attachment["id"],
            filename=attachment["filename"],
            content_type=attachment["content_type"],
            status=AttachmentAnalysisStatus.PARTIAL_SUCCESS,
            document_type="field_photo",
            document_type_confidence=0.55,
        ),
    )
    saved = []
    monkeypatch.setattr(server._postgres_attachment_analysis_repository, "save", lambda result: saved.append(result))

    result = server._reanalyze_email_attachments_by_ref(email_uid)

    assert result is not None
    assert result["attachment_count"] == 1
    assert gmail_service.repository.calls == [email_uid]
    assert synthetic_service.repository.calls == []
    assert saved[0].document_type == "field_photo"

def test_attachment_reanalysis_skips_llm_when_parser_recovers_fields(monkeypatch):
    email_uid = RUN_PAYLOAD["email_message_id"]
    attachment_uid = "6b4d8519-a2ad-49de-bf12-c1d2637f0e43"
    attachment = {
        "id": attachment_uid,
        "filename": "Quotation_QT-2026-0812-03.pdf",
        "content_type": "application/pdf",
        "storage_uri": "/tmp/Quotation_QT-2026-0812-03.pdf",
    }

    class Repository:
        def attachments_for_message(self, message_id):
            return [attachment]

    class PersistentService:
        repository = Repository()

        def email_detail_by_uid(self, requested_uid):
            return {"email_uid": email_uid, "index": 0} if requested_uid == email_uid else None

    def fail_enrich(result):
        raise AssertionError("parser-recovered business fields should not require LLM enrichment")

    saved = []
    monkeypatch.setattr(server, "_gmail_postgres_service", PersistentService())
    monkeypatch.setattr(server, "_postgres_service", PersistentService())
    monkeypatch.setattr(server, "postgres_jobs_enabled", lambda: True)
    monkeypatch.setattr(
        server._attachment_parser_dispatcher,
        "analyze",
        lambda _attachment: AttachmentAnalysisResult(
            attachment_id=attachment_uid,
            filename=attachment["filename"],
            content_type=attachment["content_type"],
            status=AttachmentAnalysisStatus.COMPLETED,
            document_type="quote",
            extracted_text="견적번호: QT-2026-0812-03",
            fields={"Our Ref No": "QT-2026-0812-03"},
        ),
    )
    monkeypatch.setattr(server._attachment_understanding_analyzer, "enrich", fail_enrich)
    monkeypatch.setattr(server._postgres_attachment_analysis_repository, "save", lambda result: saved.append(result))

    result = server._reanalyze_email_attachments_by_ref(email_uid)

    assert result is not None
    assert saved[0].fields == {"Our Ref No": "QT-2026-0812-03"}
    assert saved[0].error_message is None

def test_attachment_reanalysis_guard_rejects_concurrent_request():
    assert server._attachment_reanalysis_lock.acquire(blocking=False) is True
    try:
        try:
            server._reanalyze_email_attachments_guarded("email-1")
        except server.HTTPException as exc:
            assert exc.status_code == 409
            assert "첨부파일 재분석이 진행 중" in exc.detail
        else:
            raise AssertionError("concurrent attachment reanalysis should be rejected")
    finally:
        server._attachment_reanalysis_lock.release()

def test_mail_decision_panel_renders_review_required_without_candidates():
    view = server.mail_decision_panel_view(run=RUN_PAYLOAD, steps=STEPS, email_ref=RUN_PAYLOAD["email_message_id"])
    html = server.templates.get_template("partials/mail_decision_panel.html").render(mail_decision=view)

    assert "사람 검토 필요" in html
    assert "시스템 오류가 아니라 자동 판단에 필요한 정보가 충분하지 않아 사람의 검토가 필요합니다." not in html
    assert "관련 사례와 업무 문맥이 충분하지 않습니다." in html
    assert "판단되지 않음" in html
    assert "검토 필요" in html
    assert "Run ID" not in html
    assert "Candidate user IDs" not in html

def test_mail_decision_panel_replaces_demo_subject_label_customer_with_counterparty():
    run = {**RUN_PAYLOAD, "facts": {"customer_name": "견적서 송부"}}
    current_email = {"classification": {"counterparty": "다원"}}

    view = server.mail_decision_panel_view(
        run=run,
        steps=STEPS,
        email_ref=RUN_PAYLOAD["email_message_id"],
        current_email=current_email,
    )

    assert view["decision"]["customer_name"] == "다원"

def test_mail_decision_panel_replaces_demo_quotation_subject_label_without_counterparty():
    run = {
        **RUN_PAYLOAD,
        "email_message_id": server.DEMO_SCREENSHOT_QUOTATION_EMAIL_UID,
        "facts": {"customer_name": "견적서 송부"},
    }

    view = server.mail_decision_panel_view(
        run=run,
        steps=STEPS,
        email_ref=server.DEMO_SCREENSHOT_QUOTATION_EMAIL_UID,
        current_email={"subject": server.DEMO_SCREENSHOT_QUOTATION_SUBJECT},
    )

    assert view["decision"]["customer_name"] == "다원"

def test_mail_decision_panel_deduplicates_business_refs_for_display():
    run = {
        **RUN_PAYLOAD,
        "context": {
            "decision_output": {
                "summary": {
                    "business_refs": ["QT-2026-0812-03", "QT-2026-0812-03"],
                }
            }
        },
    }

    view = server.mail_decision_panel_view(run=run, steps=STEPS)
    html = server.templates.get_template("partials/mail_decision_panel.html").render(mail_decision=view)

    assert view["decision"]["business_refs"] == ["QT-2026-0812-03"]
    assert "업무번호" not in html
    assert "QT-2026-0812-03" not in html

def test_demo_mail_decision_panel_hides_candidate_score_percent_for_screenshots():
    token = server._display_demo_mode.set(True)
    try:
        run = {
            **RUN_PAYLOAD,
            "context": {
                "routing_decision": {
                    "candidates": [
                        {
                            "user_id": "10000000-0000-0000-0000-000000000001",
                            "total_score": 0.91,
                            "reasons": ["customer"],
                        }
                    ]
                },
                "routing_users": {
                    "10000000-0000-0000-0000-000000000001": {
                        "name": "김민수",
                        "email": "minsu.kim@example.invalid",
                        "areas": ["영업"],
                    }
                },
            },
        }
        view = server.mail_decision_panel_view(run=run, steps=STEPS)
    finally:
        server._display_demo_mode.reset(token)

    html = server.templates.get_template("partials/mail_decision_panel.html").render(mail_decision=view)

    assert view["hide_candidate_scores"] is True
    assert "김민수" in html
    assert "91%" not in html

def test_mail_decision_panel_resolves_candidate_name_from_assignment_options_without_routing_users():
    assignee_id = "10000000-0000-0000-0000-000000000001"
    run = {
        **RUN_PAYLOAD,
        "context": {
            "routing_decision": {
                "candidates": [
                    {
                        "user_id": assignee_id,
                        "total_score": 0.91,
                        "rank": 1,
                    }
                ]
            }
        },
    }

    view = server.mail_decision_panel_view(
        run=run,
        steps=STEPS,
        manual_assignment_options=[
            {
                "assignee_id": assignee_id,
                "assignee_name": "김민수",
                "email_address": "m.kim@dawonict.co.kr",
                "department": "국내영업1팀",
                "position": "대리",
            }
        ],
    )
    html = server.templates.get_template("partials/mail_decision_panel.html").render(mail_decision=view)

    assert "김민수" in html
    assert "m.kim@dawonict.co.kr" in html
    assert f"<strong>{assignee_id}</strong>" not in html

def test_demo_mail_decision_panel_hides_review_reason_for_screenshots():
    token = server._display_demo_mode.set(True)
    try:
        view = server.mail_decision_panel_view(run=RUN_PAYLOAD, steps=STEPS)
    finally:
        server._display_demo_mode.reset(token)

    html = server.templates.get_template("partials/mail_decision_panel.html").render(mail_decision=view)

    assert view["hide_review_reason"] is True
    assert "검토 상태" not in html

def test_mail_decision_panel_assigns_from_candidate_rows_for_review_required():
    view = server.mail_decision_panel_view(
        run=RUN_PAYLOAD,
        steps=STEPS,
        email_ref=RUN_PAYLOAD["email_message_id"],
        manual_assignment_options=[
            {
                "assignee_id": "10000000-0000-0000-0000-000000000001",
                "assignee_name": "김민수",
                "email_address": "minsu.kim@example.invalid",
                "priority": 1,
                "category": "서비스",
                "areas": ["서비스"],
                "department": "서비스운영팀",
                "position": "대리",
            },
            {
                "assignee_id": "10000000-0000-0000-0000-000000000002",
                "assignee_name": "박영업",
                "email_address": "sales.park@example.invalid",
                "priority": 2,
                "category": "영업",
                "areas": ["영업"],
                "department": "영업팀",
                "position": "과장",
            },
            {
                "assignee_id": "10000000-0000-0000-0000-000000000003",
                "assignee_name": "이기술",
                "email_address": "tech.lee@example.invalid",
                "priority": 3,
                "category": "기술",
                "areas": ["기술"],
                "department": "기술팀",
                "position": "차장",
            },
            {
                "assignee_id": "10000000-0000-0000-0000-000000000004",
                "assignee_name": "최제외",
                "email_address": "excluded.choi@example.invalid",
                "priority": 4,
                "category": "일반",
                "areas": ["일반"],
                "department": "운영팀",
                "position": "사원",
            },
        ],
    )
    html = server.templates.get_template("partials/mail_decision_panel.html").render(mail_decision=view)

    assert "담당 후보" in html
    assert f"/ui/emails/{RUN_PAYLOAD['email_message_id']}/routing/manual-assign" in html
    assert 'hx-disabled-elt="find button"' in html
    assert 'hx-on:click="event.stopPropagation()"' in html
    assert 'name="assignee_user_id"' in html
    assert 'value="10000000-0000-0000-0000-000000000001"' in html
    assert "김민수" in html
    assert "서비스운영팀" in html
    assert "대리" in html
    assert "박영업" in html
    assert "이기술" in html
    assert "최제외" not in html
    assert "excluded.choi@example.invalid" not in html
    assert "배정" in html
    assert "직접 배정" not in html
    assert 'name="reason"' not in html
    assert "검토 필요 상태를 담당자 확정으로 전환합니다." not in html

def test_mail_decision_panel_displays_current_delivery_status():
    run = {
        **RUN_PAYLOAD,
        "context": {
            **RUN_PAYLOAD["context"],
            "routing_decision": {
                "candidates": [
                    {
                        "user_id": "10000000-0000-0000-0000-000000000001",
                        "total_score": 0.91,
                        "rank": 1,
                    }
                ]
            },
            "routing_users": {
                "10000000-0000-0000-0000-000000000001": {
                    "name": "김민수",
                    "email": "minsu.kim@example.invalid",
                    "areas": ["서비스"],
                }
            },
        },
    }
    view = server.mail_decision_panel_view(
        run=run,
        steps=STEPS,
        email_ref=RUN_PAYLOAD["email_message_id"],
        current_email={
            "work_status": "forwarded",
            "work_status_label": "전달 완료",
            "manual_route_status_label": "전달 완료",
        },
        current_assignment={"assignee_name": "김민수", "status": "assigned"},
        manual_assignment_options=[
            {
                "assignee_id": "10000000-0000-0000-0000-000000000001",
                "assignee_name": "김민수",
                "email_address": "minsu.kim@example.invalid",
                "areas": ["서비스"],
            },
        ],
    )
    html = server.templates.get_template("partials/mail_decision_panel.html").render(mail_decision=view)

    assert view["status"] == "assigned"
    assert "<td>전달 상태</td>" in html
    assert "전달 완료" in html
    assert "배정 완료" not in html
    assert "사람 검토 필요" not in html
    assert "담당 후보" in html
    assert "김민수" in html
    assert "배정</button>" not in html
    assert f"/ui/emails/{RUN_PAYLOAD['email_message_id']}/routing/manual-assign" not in html

def test_latest_mail_decision_run_for_panel_uses_local_repository_without_runtime_self_call(monkeypatch):
    class FakeState:
        def model_dump(self, mode: str = "json"):
            assert mode == "json"
            return {**RUN_PAYLOAD, "status": "completed"}

    class FakeMailDecisionRepository:
        def __init__(self) -> None:
            self.resolved = False
            self.loaded = False

        def resolve_email_message_id(self, email_ref: str):
            assert email_ref == RUN_PAYLOAD["email_message_id"]
            self.resolved = True
            return RUN_PAYLOAD["email_message_id"]

        def get_latest_run_for_email(self, email_message_id):
            assert str(email_message_id) == RUN_PAYLOAD["email_message_id"]
            self.loaded = True
            return FakeState()

    fake_repository = FakeMailDecisionRepository()

    def fail_runtime_client(_request):
        raise AssertionError("manual assignment panel refresh should not call the runtime HTTP client")

    monkeypatch.setattr(server, "database_url", lambda: "postgresql://local/test")
    monkeypatch.setattr(
        server,
        "_email_detail_by_ref",
        lambda email_ref: {"email_uid": email_ref} if email_ref == RUN_PAYLOAD["email_message_id"] else None,
    )
    monkeypatch.setattr(server, "_postgres_mail_decision_repository", fake_repository)
    monkeypatch.setattr(server, "mail_decision_runtime_client", fail_runtime_client)

    run = server._latest_mail_decision_run_for_panel(request(), RUN_PAYLOAD["email_message_id"])

    assert run is not None
    assert run["status"] == "completed"
    assert fake_repository.resolved is True
    assert fake_repository.loaded is True

def test_manual_assignment_options_prioritize_settings_category_assignees(monkeypatch):
    monkeypatch.setattr(
        server._postgres_assignee_admin_repository,
        "list_operating_assignees",
        lambda: [
            {
                "assignee_id": "10000000-0000-0000-0000-000000000001",
                "assignee_name": "문의 담당",
                "email_address": "inquiry@example.invalid",
                "mail_categories": ["문의"],
                "department": "영업팀",
                "position": "대리",
                "is_active": True,
            },
            {
                "assignee_id": "10000000-0000-0000-0000-000000000002",
                "assignee_name": "서비스 담당",
                "email_address": "service@example.invalid",
                "mail_categories": ["서비스"],
                "department": "서비스운영팀",
                "position": "과장",
                "is_active": True,
            },
        ],
    )

    options = server.manual_assignment_options_for_email(
        email={"mail_category": "서비스"},
        run=RUN_PAYLOAD,
    )

    assert [option["assignee_name"] for option in options] == ["서비스 담당", "문의 담당"]
    assert options[0]["category"] == "서비스"
    assert options[0]["department"] == "서비스운영팀"
    assert options[0]["position"] == "과장"
    assert options[1]["category"] == ""

def test_mail_decision_panel_omits_confirmed_manual_assignment_banner_after_review():
    run = {**RUN_PAYLOAD, "status": "completed"}
    view = server.mail_decision_panel_view(
        run=run,
        steps=STEPS,
        email_ref=RUN_PAYLOAD["email_message_id"],
        current_assignment={"assignee_name": "김민수", "status": "assigned"},
    )
    html = server.templates.get_template("partials/mail_decision_panel.html").render(mail_decision=view)

    assert "김민수 담당자로 확정됨" not in html
    assert "manual-assignment-confirmed" not in html
    assert "manual-assignment-complete" not in html
    assert "배정 완료" in html
    assert "직접 배정" not in html

def test_manual_assignment_post_returns_completion_trigger(monkeypatch):
    assignee_id = "10000000-0000-0000-0000-000000000001"

    monkeypatch.setattr(server, "auth_cookie_username", lambda _cookie: "admin")
    monkeypatch.setattr(
        server,
        "_manual_assign_review_email",
        lambda **_kwargs: {"assignee_user_id": assignee_id, "assignee_name": "김민수"},
    )
    monkeypatch.setattr(
        server,
        "_email_detail_by_ref",
        lambda email_ref: {"email_uid": email_ref, "index": 7},
    )
    monkeypatch.setattr(server, "_latest_mail_decision_run_for_panel", lambda _request, _email_ref: {**RUN_PAYLOAD, "status": "completed"})

    response = asyncio.run(
        server.ui_manual_assign_review_email(
            request_with_body(
                "POST",
                f"/ui/emails/{RUN_PAYLOAD['email_message_id']}/routing/manual-assign",
                f"assignee_user_id={assignee_id}".encode("utf-8"),
            ),
            RUN_PAYLOAD["email_message_id"],
        )
    )

    trigger = json.loads(response.headers["HX-Trigger"])

    assert trigger["mail-manual-assignment-completed"]["email_uid"] == RUN_PAYLOAD["email_message_id"]
    assert trigger["mail-manual-assignment-completed"]["email_index"] == 7
    assert trigger["mail-manual-assignment-completed"]["assignee_name"] == "김민수"

def test_confirm_top_review_candidate_returns_completion_trigger(monkeypatch):
    assignee_id = "10000000-0000-0000-0000-000000000001"

    monkeypatch.setattr(server, "auth_cookie_username", lambda _cookie: "admin")
    monkeypatch.setattr(
        server,
        "_manual_assign_top_review_candidate_email",
        lambda **_kwargs: {"assignee_user_id": assignee_id, "assignee_name": "김민수"},
    )
    monkeypatch.setattr(
        server,
        "_email_detail_by_ref",
        lambda email_ref: {"email_uid": email_ref, "index": 7},
    )

    response = server.ui_confirm_top_review_candidate(request("POST"), RUN_PAYLOAD["email_message_id"])
    trigger = json.loads(response.headers["HX-Trigger"])

    assert response.status_code == 204
    assert trigger["mail-manual-assignment-completed"]["email_uid"] == RUN_PAYLOAD["email_message_id"]
    assert trigger["mail-manual-assignment-completed"]["email_index"] == 7
    assert trigger["mail-manual-assignment-completed"]["assignee_name"] == "김민수"

def test_demo_manual_route_delivery_marks_forwarded_without_gmail_send(monkeypatch):
    email_uid = RUN_PAYLOAD["email_message_id"]
    assignee_id = "10000000-0000-0000-0000-000000000001"
    calls = []

    class RoutingRepository:
        def current_assignment(self, email_message_id):
            calls.append(("current_assignment", str(email_message_id)))
            return {
                "assignee_user_id": assignee_id,
                "assignee_email": "m.kim@dawonict.co.kr",
            }

        def latest_manual_forward_notification(self, email_message_id):
            calls.append(("latest_manual_forward_notification", str(email_message_id)))
            return {}

        def create_manual_forward_notification(self, **kwargs):
            calls.append(("create_manual_forward_notification", kwargs))
            return UUID("20000000-0000-0000-0000-000000000001")

        def mark_manual_forward_sent(self, **kwargs):
            calls.append(("mark_manual_forward_sent", kwargs))

    class GmailService:
        @staticmethod
        def _manual_forward_subject(email):
            return f"Fwd: {email['subject']}"

        @staticmethod
        def _manual_forward_body(email):
            return email["body"]

        def start_manual_route_delivery(self, email_ref):
            raise AssertionError("demo manual routing must not send through Gmail")

    monkeypatch.setattr(server, "database_url", lambda: "postgresql://example")
    monkeypatch.setattr(
        server,
        "_email_detail_by_ref",
        lambda email_ref: {
            "email_uid": email_uid,
            "subject": "Demo subject",
            "body": "Demo body",
        },
    )
    monkeypatch.setattr(server, "_postgres_routing_repository", RoutingRepository())
    monkeypatch.setattr(server, "_gmail_service", GmailService())

    result = server._start_demo_manual_route_delivery(email_uid)

    assert result["status"] == "sent"
    assert ("current_assignment", email_uid) in calls
    assert calls[-1][0] == "mark_manual_forward_sent"
    assert calls[-1][1]["provider_message_id"].startswith("demo-manual-route:")

def test_mail_decision_panel_shows_candidate_email_area_department_and_position():
    run = {
        **RUN_PAYLOAD,
        "context": {
            "decision_output": {
                "summary": {"one_line_summary": "긴급 클레임 담당 후보를 검토합니다."},
                "classification": {"primary_type": "claim"},
            },
            "routing_decision": {
                "candidates": [
                    {
                        "user_id": "user-1",
                        "total_score": 0.91,
                        "rank": 1,
                    }
                ]
            },
            "routing_users": {
                "user-1": {
                    "name": "김담당",
                    "email": "owner@example.invalid",
                    "areas": ["서비스"],
                    "department": "서비스운영팀",
                    "position": "과장",
                }
            },
        },
    }

    view = server.mail_decision_panel_view(run=run, steps=STEPS, email_ref=RUN_PAYLOAD["email_message_id"])
    html = server.templates.get_template("partials/mail_decision_panel.html").render(mail_decision=view)

    assert "routing-ranking-identity" in html
    assert "owner@example.invalid" in html
    assert "서비스운영팀" in html
    assert "과장" in html
    assert "91%" in html
    assert "<p>owner@example.invalid</p>" not in html
    assert "판단 요약" not in html
    assert "필요 조치" not in html
    assert "<td>담당자</td>" not in html

def test_mail_decision_panel_shows_zero_percent_candidate_score():
    run = {
        **RUN_PAYLOAD,
        "context": {
            "routing_decision": {
                "candidates": [
                    {
                        "user_id": "user-1",
                        "total_score": 0,
                        "rank": 1,
                    }
                ]
            },
            "routing_users": {"user-1": {"name": "김담당", "email": "owner@example.invalid"}},
        },
    }

    view = server.mail_decision_panel_view(run=run, steps=STEPS, email_ref=RUN_PAYLOAD["email_message_id"])
    html = server.templates.get_template("partials/mail_decision_panel.html").render(mail_decision=view)

    assert "담당 후보" in html
    assert "김담당" in html
    assert "0%" in html

def test_mail_decision_panel_renders_status_inside_decision_info_table():
    view = server.mail_decision_panel_view(run=RUN_PAYLOAD, steps=STEPS)
    html = server.templates.get_template("partials/mail_decision_panel.html").render(mail_decision=view)

    assert '<tr>\n            <td>전달 상태</td>' in html
    assert "mail-decision-status-row" not in html
    assert html.index("<td>전달 상태</td>") < html.index("<td>업무 유형</td>")
    assert "사람 검토 필요" in html

def test_mail_decision_panel_renders_failed_run_and_step_error():
    run = {**RUN_PAYLOAD, "status": "failed", "context": {"failure_message": "boom"}}
    steps = [{"node_name": "extract_facts", "status": "failed", "error_message": "ValueError: boom"}]
    view = server.mail_decision_panel_view(run=run, steps=steps)
    html = server.templates.get_template("partials/mail_decision_panel.html").render(mail_decision=view)

    assert "실패" in html
    assert "Runtime 상태와 step 오류를 확인하세요." in html
    assert "ValueError: boom" in html

def test_mail_decision_panel_renders_empty_running_and_completed_states():
    empty = server.mail_decision_panel_view(run=None, steps=[], email_ref=RUN_PAYLOAD["email_message_id"])
    empty_html = server.templates.get_template("partials/mail_decision_panel.html").render(mail_decision=empty)
    assert "아직 실행된 업무 판단이 없습니다." in empty_html
    assert "업무 판단 실행" not in empty_html
    assert "분석 중..." not in empty_html
    assert "mail-decision-loading" not in empty_html

    running = server.mail_decision_panel_view(run={**RUN_PAYLOAD, "status": "running"}, steps=[])
    running_html = server.templates.get_template("partials/mail_decision_panel.html").render(mail_decision=running)
    assert "실행 중" in running_html
    assert "업무 판단 실행" not in running_html

    completed = server.mail_decision_panel_view(run={**RUN_PAYLOAD, "status": "completed"}, steps=[])
    completed_html = server.templates.get_template("partials/mail_decision_panel.html").render(mail_decision=completed)
    assert "완료" in completed_html

def test_mail_decision_panel_keeps_run_when_steps_fail():
    view = server.mail_decision_panel_view(run=RUN_PAYLOAD, steps=[], steps_error="실행 단계를 불러올 수 없습니다.")
    html = server.templates.get_template("partials/mail_decision_panel.html").render(mail_decision=view)

    assert RUN_PAYLOAD["run_id"] in html
    assert "실행 단계를 불러올 수 없습니다." in html

def test_ui_create_mail_decision_run_returns_result_partial(monkeypatch):
    class FakeClient:
        def create_run(self, email_message_id):
            assert email_message_id == RUN_PAYLOAD["email_message_id"]
            return RUN_PAYLOAD

        def get_steps(self, run_id):
            assert run_id == RUN_PAYLOAD["run_id"]
            return STEPS

    monkeypatch.setattr(server, "_email_detail_by_ref", lambda email_ref: {"email_uid": email_ref})
    monkeypatch.setattr(server, "mail_decision_runtime_client", lambda request: FakeClient())

    response = server.ui_create_mail_decision_run(request("POST"), RUN_PAYLOAD["email_message_id"])

    html = response.template.render(response.context)
    assert "mail-decision-panel" in html
    assert RUN_PAYLOAD["run_id"] in html
    assert "사람 검토 필요" in html

def test_ui_mail_decision_run_and_steps_routes_render_existing_run(monkeypatch):
    class FakeClient:
        def get_run(self, run_id):
            assert run_id == RUN_PAYLOAD["run_id"]
            return RUN_PAYLOAD

        def get_steps(self, run_id):
            assert run_id == RUN_PAYLOAD["run_id"]
            return STEPS

    monkeypatch.setattr(server, "mail_decision_runtime_client", lambda request: FakeClient())

    run_response = server.ui_mail_decision_run(request(), RUN_PAYLOAD["run_id"])
    run_html = run_response.template.render(run_response.context)
    assert RUN_PAYLOAD["run_id"] in run_html
    assert "관련 사례와 업무 문맥이 충분하지 않습니다." in run_html

    steps_response = server.ui_mail_decision_steps(request(), RUN_PAYLOAD["run_id"])
    steps_html = steps_response.template.render(steps_response.context)
    assert "메일 정보 불러오기" in steps_html
    assert "검색 결과 충분성 평가" in steps_html

def test_ui_latest_mail_decision_run_renders_existing_absent_and_step_failure(monkeypatch):
    class FakeClient:
        def __init__(self, run, steps_exc=None):
            self.run = run
            self.steps_exc = steps_exc

        def get_latest_run_for_email(self, email_message_id):
            assert email_message_id == RUN_PAYLOAD["email_message_id"]
            return self.run

        def get_steps(self, run_id):
            assert run_id == RUN_PAYLOAD["run_id"]
            if self.steps_exc:
                raise self.steps_exc
            return STEPS

    monkeypatch.setattr(server, "_email_detail_by_ref", lambda email_ref: {"email_uid": email_ref})

    monkeypatch.setattr(server, "mail_decision_runtime_client", lambda request: FakeClient(RUN_PAYLOAD))
    response = server.ui_latest_mail_decision_run(request(), RUN_PAYLOAD["email_message_id"])
    html = response.template.render(response.context)
    assert "사람 검토 필요" in html
    assert "관련 사례와 업무 문맥이 충분하지 않습니다." in html
    assert html.count("mail-decision-step-item") == 0

    monkeypatch.setattr(server, "mail_decision_runtime_client", lambda request: FakeClient(None))
    response = server.ui_latest_mail_decision_run(request(), RUN_PAYLOAD["email_message_id"])
    html = response.template.render(response.context)
    assert "아직 실행된 업무 판단이 없습니다." in html

    monkeypatch.setattr(
        server,
        "mail_decision_runtime_client",
        lambda request: FakeClient(RUN_PAYLOAD, MailDecisionRuntimeTimeoutError("slow")),
    )
    response = server.ui_latest_mail_decision_run(request(), RUN_PAYLOAD["email_message_id"])
    html = response.template.render(response.context)
    assert RUN_PAYLOAD["run_id"] in html
    assert "실행 단계를 불러올 수 없습니다." in html

def test_ui_latest_mail_decision_run_runtime_failure(monkeypatch):
    class FakeClient:
        def get_latest_run_for_email(self, email_message_id):
            raise MailDecisionRuntimeConnectionError("refused")

    monkeypatch.setattr(server, "_email_detail_by_ref", lambda email_ref: {"email_uid": email_ref})
    monkeypatch.setattr(server, "mail_decision_runtime_client", lambda request: FakeClient())

    response = server.ui_latest_mail_decision_run(request(), RUN_PAYLOAD["email_message_id"])

    html = response.template.render(response.context)
    assert "Mail Decision 결과를 불러올 수 없습니다." in html
    assert "업무 판단 실행" not in html

def test_ui_create_mail_decision_run_renders_connection_failure(monkeypatch):
    class FakeClient:
        def create_run(self, email_message_id):
            raise MailDecisionRuntimeConnectionError("refused")

    monkeypatch.setattr(server, "_email_detail_by_ref", lambda email_ref: {"email_uid": email_ref})
    monkeypatch.setattr(server, "mail_decision_runtime_client", lambda request: FakeClient())

    response = server.ui_create_mail_decision_run(request("POST"), RUN_PAYLOAD["email_message_id"])

    html = response.template.render(response.context)
    assert "Mail Decision Runtime에 연결할 수 없습니다." in html

def test_ui_create_mail_decision_run_renders_database_configuration_failure(monkeypatch):
    class FakeClient:
        def create_run(self, email_message_id):
            raise server.MailDecisionRuntimeServerError(
                '{"detail":"CORAMAIL_DATABASE_URL is not configured"}'
            )

    monkeypatch.setattr(server, "_email_detail_by_ref", lambda email_ref: {"email_uid": email_ref})
    monkeypatch.setattr(server, "mail_decision_runtime_client", lambda request: FakeClient())

    response = server.ui_create_mail_decision_run(request("POST"), RUN_PAYLOAD["email_message_id"])
    html = response.template.render(response.context)

    assert "CORAMAIL_DATABASE_URL이 설정되지 않았습니다" in html

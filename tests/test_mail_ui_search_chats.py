# ruff: noqa: F403, F405
from tests.ui_test_support import *  # noqa: F401,F403
from app.services.mail_chat_service import chat_evidence_policy

def test_evaluation_dashboard_missing_report_renders_command(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "EVALUATION_REPORT_PATH", tmp_path / "missing_report.json")
    monkeypatch.setattr(server, "EVALUATION_CASES_PATH", tmp_path / "missing_cases.csv")
    monkeypatch.setattr(server, "EVALUATION_TRACE_PATH", tmp_path / "missing_trace.jsonl")

    html = server.templates.get_template("views/evaluation.html").render(
        **server.ui_globals(),
        evaluation=server.evaluation_dashboard_view("default"),
    )

    assert "아직 생성된 평가 리포트가 없습니다." in html
    assert "uv run python -m app.tools.synthetic_evaluation score" in html

def test_evaluation_dashboard_and_case_detail_render_trace(monkeypatch, tmp_path):
    report_path = tmp_path / "evaluation_report.json"
    cases_path = tmp_path / "evaluation_cases.csv"
    trace_path = tmp_path / "evaluation_trace.jsonl"
    email_id = "email-1"
    report_path.write_text(
        """
        {
          "generated_at": "2026-07-30T00:00:00+00:00",
          "model_context": {"text_model": "qwen2.5:1.5b"},
          "metrics": {
            "values": {
              "total_cases": {"numerator": 1, "denominator": 1, "value": 1},
              "execution_success_count": {"numerator": 1, "denominator": 1, "value": 1},
              "failure_rate": {"numerator": 0, "denominator": 1, "value": 0},
              "review_required_rate": {"numerator": 1, "denominator": 1, "value": 1},
              "business_type_prediction_coverage": {"numerator": 0, "denominator": 1, "value": 0},
              "business_type_accuracy_overall": {"numerator": 0, "denominator": 1, "value": 0},
              "business_type_accuracy_when_predicted": {"numerator": 0, "denominator": 0, "value": 0},
              "selected_assignee_coverage": {"numerator": 0, "denominator": 1, "value": 0},
              "top1_assignee_accuracy_overall": {"numerator": 0, "denominator": 1, "value": 0},
              "candidate_recall_at_k": {"numerator": 0, "denominator": 1, "value": 0},
              "candidate_mrr": {"numerator": 0, "denominator": 1, "value": 0},
              "auto_assignment_rate": {"numerator": 0, "denominator": 1, "value": 0},
              "auto_assignment_accuracy": {"numerator": 0, "denominator": 0, "value": 0}
            },
            "primary_failure_stage_counts": {"retrieval_context_insufficient": 1},
            "review_reason_counts": {"retrieval_context_insufficient": 1}
          }
        }
        """,
        encoding="utf-8",
    )
    cases_path.write_text(
        "email_message_id,run_id,status,expected_business_type,predicted_business_type,business_type_correct,"
        "expected_assignee_user_id,candidate_user_ids,expected_assignee_rank,candidate_contains_expected,"
        "selected_user_id,selected_assignee_correct,auto_assigned,review_reason,primary_failure_stage,"
        "primary_failure_reason,error\n"
        f"{email_id},run-1,review_required,repair_request,,False,user-1,[],,"
        "False,,False,False,retrieval_context_insufficient,retrieval_context_insufficient,need context,\n",
        encoding="utf-8",
    )
    trace_path.write_text(
        (
            '{"email_message_id":"email-1","run_id":"run-1","input":{"subject":"<script>x</script>",'
            '"body_preview":"preview","body_length":7,"body_sha256":"hash","attachment_filenames":["a.pdf"]},'
            '"ground_truth":{"business_type":"repair_request","assignee_user_id":"user-1","customer":"Customer",'
            '"product_group":"pump","project":"PRJ"},"facts":{"values":{},'
            '"field_comparison":{"customer":{"expected":"Customer","actual":null,"present":false,"match":false}}},'
            '"attachments":[],"retrieval":{"cycles":[{"cycle":1,"strategy":"similar_case","hits":[{"strategy":"similar_case",'
            '"query_text":"q","candidate_id":"case-1","score":0.4,"included_in_prompt":false,'
            '"excluded_reason":"score_below_threshold"}]}]},"sufficiency":{"required_context":["business_type_context"],'
            '"resolved_context":[],"unresolved_context":["business_type_context"],"sufficient":false,'
            '"review_reason":"retrieval_context_insufficient"},"decision":{},"routing":{"candidates":[],"selected_user_id":null,'
            '"expected_assignee_rank":null},"evaluation":{"business_type_correct":false,'
            '"candidate_contains_expected":false,"selected_assignee_correct":false,'
            '"primary_failure_stage":"retrieval_context_insufficient","primary_failure_reason":"need context"}}\n'
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(server, "EVALUATION_REPORT_PATH", report_path)
    monkeypatch.setattr(server, "EVALUATION_CASES_PATH", cases_path)
    monkeypatch.setattr(server, "EVALUATION_TRACE_PATH", trace_path)

    dashboard_html = server.templates.get_template("views/evaluation.html").render(
        **server.ui_globals(),
        evaluation=server.evaluation_dashboard_view("default"),
    )
    case_html = server.templates.get_template("views/evaluation_case.html").render(
        **server.ui_globals(),
        evaluation_case=server.evaluation_case_view(email_id, "default"),
    )

    assert "1 / 1 (100.0%)" in dashboard_html
    assert "품질 기준 미달" in dashboard_html
    assert "합성 평가 데이터" in dashboard_html
    assert "측정 안 됨" in dashboard_html
    assert "케이스별 결과" in dashboard_html
    assert "retrieval_context_insufficient" in dashboard_html
    assert "Facts" in case_html
    assert "score_below_threshold" in case_html
    assert "&lt;script&gt;x&lt;/script&gt;" in case_html
    assert "<script>x</script>" not in case_html

def test_evaluation_report_registry_rejects_path_traversal():
    view = server.evaluation_dashboard_view("../clean-v2")

    assert view["report_id"] in {"clean-v2", "default"}
    assert "../clean-v2" not in {option["id"] for option in view.get("report_options", [])}

def test_search_ui_and_api_share_search_service(monkeypatch):
    expected = {
        "query": "FM250016318",
        "answer": "근거 기반 답변",
        "results": [
            {
                "source": "quote.pdf",
                "source_type": "attachment",
                "category": "문의",
                "document_category": "quotation",
                "business_refs": ["FM250016318"],
                "vessel_names": [],
                "preview": "납기 7 Days / 총액 KRW 518,000",
                "match_explanation": "첨부 분석에서 fm250016318 일치",
                "detail_url": "/ui/inbox?email_uid=mail-1",
                "payload": {"filename": "quote.pdf", "stored_name": ""},
            }
        ],
        "trace": {
            "strategy": "hybrid_embedding_llm_rag",
            "intent": "document_qa",
            "sort": "relevance",
            "candidate_count": 3,
            "selected_count": 1,
            "embedding_model": "test-embedding",
            "answer_model": "test-answer",
            "prompt_name": "mailbox_rag_answer",
            "prompt_version": "v2",
            "planner_prompt_name": "mailbox_query_planner",
            "planner_prompt_version": "v1",
        },
    }

    class FakeSearchService:
        def search(self, query, *, limit, conversation_context=""):
            assert query == "FM250016318"
            assert limit == 5
            assert conversation_context == ""
            return dict(expected)

    monkeypatch.setattr(server, "mail_search_service", lambda: FakeSearchService())

    response = server.ui_search_results(
        request_with_body("GET", "/ui/search-results", headers=[(b"hx-request", b"true")]),
        q="  FM250016318  ",
        limit=5,
    )
    html = response.template.render(response.context)
    api_result = execute_search(SearchRequest(query="FM250016318", limit=5), search_service=server.mail_search_service)

    assert "근거 기반 답변" in html
    assert "납기 7 Days" not in html
    assert "원본 메일 보기" in html
    assert 'hx-target="#main-panel"' not in html
    assert "test-answer · 후보 3개 중 근거 1개" not in html
    assert "채택 1 / 검토 3" not in html
    assert "채택" not in html
    assert "검토" not in html
    assert "test-answer" not in html
    assert "quotation" not in html
    assert "search-query-label" not in html
    assert api_result == expected

def test_demo_search_service_uses_demo_mailbox_documents_with_attachment_facts(monkeypatch):
    monkeypatch.setattr(server, "database_url", lambda: "")
    token = server._display_demo_mode.set(True)
    try:
        search_service = server.mail_search_service()
        documents = search_service.mailbox.search_documents()
    finally:
        server._display_demo_mode.reset(token)

    assert search_service.mailbox.__class__.__name__ == "DemoMailService"
    attachment = next(
        document
        for document in documents
        if document["source_type"] == "attachment"
        and document["source"] == "Quotation_QT-2026-0812-03.pdf"
    )
    assert attachment["business_refs"] == ["QT-2026-0812-03"]
    assert attachment["detail_url"] == "/?view=inbox&email_uid=0732e633-db61-536e-8ff3-b820826cf9a2"
    assert "expected_delivery: 발주 후 14일 이내" in attachment["preview"]
    assert "total_amount: 5,346,000원" in attachment["preview"]

def test_demo_inbox_high_priority_rows_are_visually_marked(monkeypatch):
    monkeypatch.setattr(server, "database_url", lambda: "")
    token = server._display_demo_mode.set(True)
    try:
        rows = server.mail_rows(q="URG-DEMO-2026-0810-01")
        html = server.templates.get_template("partials/mail_rows.html").render(
            **server.ui_globals(),
            emails=rows,
            mail_rows_mode="inbox",
            selected_email_index=None,
            selected_email_uid="",
        )
    finally:
        server._display_demo_mode.reset(token)

    assert len(rows) == 1
    assert rows[0]["mail_category"] == "긴급 장애"
    assert rows[0]["routing_display"] == "긴급 서비스"
    assert 'class="clickable-row is-attention-urgent-important' in html
    assert "긴급" in html
    assert "Ref URG-DEMO-2026-0810-01" not in html
    assert "URG-DEMO-2026-0810-01" not in html

def test_high_priority_route_buttons_do_not_blend_with_urgent_row_background():
    css = _app_css_source()

    assert "tr.is-attention-urgent-important .route-now-btn--" not in css

    ready_css = css.rsplit(".route-now-btn--ready {", 1)[1].split("}", 1)[0]
    sent_css = css.rsplit(".route-now-btn--sent {", 1)[1].split("}", 1)[0]

    assert "background: #eef2ff;" in ready_css
    assert "background: #ecfdf5;" in sent_css
    assert "background: rgba(" not in ready_css
    assert "background: rgba(" not in sent_css

def test_demo_high_priority_email_detail_keeps_urgency_out_of_overview(monkeypatch):
    monkeypatch.setattr(server, "database_url", lambda: "")
    token = server._display_demo_mode.set(True)
    try:
        rows = server.mail_rows(q="URG-DEMO-2026-0810-01")
        email = server.mail_service().email_detail_by_uid(rows[0]["email_uid"])
        html = server.templates.get_template("partials/email_detail.html").render(
            **server.ui_globals(),
            email=email,
            related_emails=[],
            customer_history=[],
            classify_regenerate_state="ready",
            classification_regeneration={},
            summary_regenerate_state="ready",
            summary_regeneration={},
            attachment_reanalysis={},
            mail_decision={},
        )
    finally:
        server._display_demo_mode.reset(token)

    assert email["classification"]["urgency"] == "high"
    assert email["classification"]["importance"] == "high"
    assert email["classification"]["attention_quadrant"] == "urgent_important"
    assert "<td>긴급도</td>" not in html
    assert "우선 확인" not in html
    assert "긴급 장애 · 긴급 서비스 기준으로 긴급 처리 대상입니다." not in html

def test_demo_normal_priority_email_detail_omits_urgency_row(monkeypatch):
    monkeypatch.setattr(server, "database_url", lambda: "")
    token = server._display_demo_mode.set(True)
    try:
        rows = server.mail_rows(q="QT-2026-0812-03")
        email = server.mail_service().email_detail_by_uid(rows[0]["email_uid"])
        html = server.templates.get_template("partials/email_detail.html").render(
            **server.ui_globals(),
            email=email,
            related_emails=[],
            customer_history=[],
            classify_regenerate_state="ready",
            classification_regeneration={},
            summary_regenerate_state="ready",
            summary_regeneration={},
            attachment_reanalysis={},
            mail_decision={},
        )
    finally:
        server._display_demo_mode.reset(token)

    assert email["classification"]["urgency"] == "normal"
    assert "<td>긴급도</td>" not in html
    assert "우선 확인" not in html

def test_demo_inbox_search_keeps_quotation_reference_out_of_rows(monkeypatch):
    monkeypatch.setattr(server, "database_url", lambda: "")
    token = server._display_demo_mode.set(True)
    try:
        rows = server.mail_rows(q="QT-2026-0812-03")
        html = server.templates.get_template("partials/mail_rows.html").render(
            **server.ui_globals(),
            emails=rows,
            mail_rows_mode="inbox",
            selected_email_index=None,
            selected_email_uid="",
        )
    finally:
        server._display_demo_mode.reset(token)

    assert len(rows) == 1
    assert rows[0]["email_uid"] == "0732e633-db61-536e-8ff3-b820826cf9a2"
    assert rows[0]["business_refs"] == ["QT-2026-0812-03"]
    assert "Ref QT-2026-0812-03" not in html
    assert "QT-2026-0812-03" not in html

def test_search_view_has_no_fake_prefilled_query():
    html = server.templates.get_template("views/search.html").render(
        **{**server.ui_globals(), "demo_mode": True},
        query="",
        result=None,
        error="",
    )

    assert 'action="/ui/search"' in html
    assert 'method="get"' in html
    assert 'hx-target="#search-results-body"' in html
    assert 'hx-indicator="#search-results"' in html
    assert 'value=""' in html
    assert 'placeholder="예: QT-2026-0812-03 견적서의 납기와 총액"' in html
    assert "메일함과 첨부 문서에서 확인할 내용을 질문해 주세요." in html
    assert "질문 분석·근거 검색·답변 생성 중" in html
    assert "search-hero-panel" not in html
    assert "질문을 입력하면 답변과 근거를 함께 정리합니다." not in html
    assert "일반 대화가 아니라" not in html
    assert "검색 질문 작성 도우미" not in html
    assert "범위" not in html
    assert 'data-search-context="가장 최근 메일의"' not in html
    assert 'data-search-topic="납기"' not in html
    assert 'data-search-template="FM250016318 견적서의 납기와 총액을 확인해줘"' not in html
    assert ">참조번호</button>" not in html
    assert ">메일·첨부 RAG 질문</label>" not in html
    assert "/ui/search-answer" not in html

def test_demo_search_view_exposes_presentation_examples():
    html = server.templates.get_template("views/search.html").render(
        **{**server.ui_globals(), "demo_mode": True},
        query="",
        result=None,
        error="",
    )

    assert 'data-search-example="QT-2026-0812-03 견적서의 납기와 총액"' in html
    assert 'data-search-example="URG-DEMO-2026-0810-01 긴급 장애 메일 찾아줘"' in html
    assert 'data-search-example="가장 최신 메일이 뭐야"' in html

def test_gmail_search_view_uses_generic_prompt_and_partial_fallback_action():
    html = server.templates.get_template("views/search.html").render(
        **{**server.ui_globals(), "demo_mode": False},
        query="",
        result=None,
        error="",
    )

    assert 'action="/ui/search-results"' in html
    assert 'method="get"' in html
    assert 'placeholder="예: 최근 견적서의 납기와 총액"' in html
    assert "QT-2026-0812-03" not in html

def test_chats_view_uses_search_service_contract_as_conversation_surface():
    html = server.templates.get_template("views/chats.html").render(
        **{**server.ui_globals(), "demo_mode": True},
        query="",
        result=None,
        error="",
    )

    assert 'data-view="chats"' in html
    assert 'id="chatQueryInput"' in html
    assert 'placeholder="' not in html
    assert 'action="/ui/chats"' in html
    assert 'hx-get="/ui/chats-results"' in html
    assert 'hx-target="#chat-results-body"' in html
    assert 'hx-indicator="#chat-results"' in html
    assert 'data-chat-thread' in html
    assert 'data-chat-composer' in html
    assert "chat-shell--with-examples" in html
    assert 'id="chatSessionInput"' in html
    assert 'name="session_id"' in html
    assert html.count('id="chatSessionInput"') == 1
    assert 'id="chatPendingTemplate"' in html
    assert 'data-chat-pending-query' in html
    assert "chat-typing-dots" in html
    assert "메일함과 첨부 문서에서 확인할 내용을 질문해 주세요." in html
    assert "답변 생성 중" in html
    assert 'data-search-input="#chatQueryInput"' in html
    assert 'data-search-example="QT-2026-0812-03 견적서의 납기와 총액"' in html

def test_gmail_chats_view_removes_example_row_without_reserved_gap():
    html = server.templates.get_template("views/chats.html").render(
        **{**server.ui_globals(), "demo_mode": False},
        query="",
        result=None,
        error="",
    )
    css = _app_css_source()

    assert 'data-view="chats"' in html
    assert "chat-shell--without-examples" in html
    assert "chat-shell--with-examples" not in html
    assert "chat-example-strip" not in html
    assert 'data-search-example="' not in html
    assert "grid-template-rows: minmax(420px, 1fr) auto;" in css
    assert ".chat-shell--with-examples" in css
    assert "max-height: calc(100vh - 198px);" in css

def test_chats_results_render_thread_messages_and_evidence():
    current_result = {
        "answer": "납기는 2026-08-30이고 총액은 1,200,000원입니다.",
        "results": [
            {
                "source": "QT-2026-0812-03.pdf",
                "email_uid": "demo",
                "payload": {"filename": "QT-2026-0812-03.pdf"},
                "match_explanation": "견적서 첨부의 납기와 총액 필드가 질문과 일치합니다.",
                "detail_url": "/ui/inbox?email_uid=demo",
            }
        ],
    }
    html = server.templates.get_template("partials/chats_results.html").render(
        **server.ui_globals(),
        turns=[
            {"query": "가장 최신 메일이 뭐야", "answer": "최신 메일은 QT-2026-0812-03입니다."},
            {
                "query": "그 견적서의 납기와 총액",
                "answer": current_result["answer"],
                "result": current_result,
                "error": "",
            },
        ],
        history_payload=json.dumps(
            [
                {"query": "가장 최신 메일이 뭐야", "answer": "최신 메일은 QT-2026-0812-03입니다."},
                {"query": "그 견적서의 납기와 총액", "answer": current_result["answer"]},
            ],
            ensure_ascii=False,
        ),
        session_id="session-test",
        include_session_oob=True,
        error="",
    )

    assert "chat-message-user" in html
    assert "chat-message-group chat-message-group-assistant" in html
    assert "chat-answer-bubble" in html
    assert "chat-evidence-panel" in html
    assert "근거" in html
    assert "가장 최신 메일이 뭐야" in html
    assert "최신 메일은 QT-2026-0812-03입니다." in html
    assert "QT-2026-0812-03.pdf" in html
    assert "원본 메일 보기" in html
    assert 'hx-get="/ui/chats/emails/demo"' in html
    assert 'hx-target="#chatEmailDetailDrawer"' in html
    assert "data-chat-email-drawer-open" in html
    assert 'href="/ui/inbox?email_uid=demo"' not in html
    assert "견적서 첨부의 납기와 총액 필드가 질문과 일치합니다." not in html
    assert 'id="chatSessionInput"' in html
    assert 'id="chatHistoryInput"' in html
    assert 'hx-swap-oob="true"' in html
    assert "같은 질문 다시 요청" in html
    assert 'data-chat-retry-query="그 견적서의 납기와 총액"' in html
    assert 'hx-get="/ui/chats-results"' in html
    assert 'hx-include="#chatSessionInput,#chatHistoryInput"' in html
    assert 'hx-vals=\'{"q":' in html

def test_chats_results_hides_empty_evidence_for_optional_chat_turn():
    result = {"answer": "아래처럼 더 공손하게 정리할 수 있습니다.", "results": []}
    html = server.templates.get_template("partials/chats_results.html").render(
        **server.ui_globals(),
        turns=[
            {
                "query": "이 문장을 더 공손하게 바꿔줘",
                "answer": result["answer"],
                "result": result,
                "error": "",
                "evidence_policy": "none",
            }
        ],
        session_id="session-test",
        include_session_oob=False,
        error="",
    )

    assert "아래처럼 더 공손하게 정리할 수 있습니다." in html
    assert "chat-answer-bubble" in html
    assert "chat-evidence-panel" not in html
    assert "근거 부족" not in html

def test_chats_results_shows_missing_evidence_for_required_chat_turn():
    result = {"answer": "질문과 관련된 메일 본문이나 첨부 분석 근거를 찾지 못했습니다.", "results": []}
    html = server.templates.get_template("partials/chats_results.html").render(
        **server.ui_globals(),
        turns=[
            {
                "query": "그 메일 납기는?",
                "answer": result["answer"],
                "result": result,
                "error": "",
                "evidence_policy": "required",
            }
        ],
        session_id="session-test",
        include_session_oob=False,
        error="",
    )

    assert "chat-evidence-panel chat-evidence-panel-empty" in html
    assert "근거 부족" in html
    assert "이 답변에 사용할 메일·첨부 근거를 찾지 못했습니다." in html

def test_chat_email_drawer_renders_original_mail_detail(monkeypatch):
    email = {
        "email_uid": "mail-1",
        "sender_name": "Buyer",
        "sender_address": "buyer@example.com",
        "subject": "Original RFQ",
        "body": "Please review this request.",
        "date": "2026-08-11T01:00:00+00:00",
        "classification": {"mail_category": "견적"},
        "attachments": [],
    }
    monkeypatch.setattr(server, "_email_detail_by_ref", lambda email_ref: email if email_ref == "mail-1" else None)
    monkeypatch.setattr(server, "ensure_can_view_work_email", lambda _request, _email: None)
    monkeypatch.setattr(server, "_mark_mail_read_for_current_user", lambda _request, _email: {})

    response = server.ui_chat_email_drawer(request(), "mail-1")
    html = response.body.decode()

    assert "chat-email-drawer-shell" in html
    assert "assignee-detail-drawer-body chat-email-drawer-body" in html
    assert "data-chat-email-drawer-close" in html
    assert "Original RFQ" in html
    assert "Please review this request." in html
    assert "detail-head" in html

def test_chats_view_contains_email_detail_drawer_target():
    html = server.templates.get_template("views/chats.html").render(
        **server.ui_globals(),
        request=request(),
        query="",
        turns=[],
        compact_turns=[],
        session_id="session-test",
    )

    assert 'id="chatEmailDetailDrawer"' in html
    assert 'class="assignee-detail-drawer chat-email-drawer"' in html
    assert "hidden" in html

def test_chat_evidence_policy_distinguishes_grounded_and_general_turns():
    assert chat_evidence_policy("그 메일 납기는?") == "required"
    assert chat_evidence_policy("QT-2026-0812-03 견적서 총액") == "required"
    assert chat_evidence_policy("고객에게 보낼 답장 초안 작성해줘") == "optional"
    assert chat_evidence_policy("이 문장을 더 공손하게 바꿔줘") == "none"

def test_chats_css_separates_evidence_from_next_user_query():
    css = _app_css_source()

    assert ".chat-message-group-assistant + .chat-message-user" in css
    adjacent_block = css.rsplit(".chat-message-group-assistant + .chat-message-user {", 1)[1].split("}", 1)[0]
    assert "margin-top: 12px;" in adjacent_block

    answer_block = css.split(".chat-answer-bubble {", 1)[1].split("}", 1)[0]
    assert "max-width: min(960px, calc(100% - 42px));" in answer_block
    assert "padding: 8px 40px;" in answer_block
    assert "line-height: 1.68;" in answer_block
    assert ".chat-bubble-actions {" in css
    assert ".chat-retry-button {" in css
    assert ".chat-retry-button .material-symbols-outlined {" in css

    evidence_card_block = css.split(".chat-evidence-card {", 1)[1].split("}", 1)[0]
    assert "padding: 11px 12px;" in evidence_card_block
    assert ".chat-evidence-panel-empty {" in css

    evidence_button_block = css.rsplit(
        ".chats-view .chat-evidence-body .result-detail-button {", 1
    )[1].split("}", 1)[0]
    assert "flex: 0 0 auto;" in evidence_button_block
    assert "width: fit-content;" in evidence_button_block
    assert "min-height: 28px;" in evidence_button_block
    assert ".chat-evidence-title {" in css
    assert "justify-content: space-between;" in css
    assert ".chats-view {" in css
    assert "position: relative;" in css.split(".chats-view {", 1)[1].split("}", 1)[0]
    assert ".assignee-detail-drawer {" in css
    assert ".assignee-detail-drawer-body .detail-head {" in css

def test_chats_email_drawer_runtime_contract():
    source = server.templates.get_template("shell.html").render(
        **server.ui_globals(),
        request=request(),
        active_view="chats",
        initial_view_template="views/chats.html",
        query="",
        turns=[],
        compact_turns=[],
        session_id="session-test",
    )
    close_block = source.split("function closeTransientPopovers(event) {", 1)[1].split(
        "function resizeEmailBodyFrames", 1
    )[0]

    assert "function openChatEmailDrawer()" in source
    assert "function closeChatEmailDrawer()" in source
    assert "function renderChatEmailDrawerLoading(source)" in source
    assert "function renderChatEmailDrawerError(status)" in source
    assert 'document.getElementById("chatEmailDetailDrawer")' in source
    assert 'if (event.detail.target.id === "chatEmailDetailDrawer")' in source
    assert "openChatEmailDrawer();" in source
    assert "playSideDrawerEnter(event.detail.target);" in source
    assert 'source.matches("[data-chat-email-drawer-open]")' in source
    assert "renderChatEmailDrawerLoading(source);" in source
    assert "renderChatEmailDrawerError(event.detail.xhr?.status);" in source
    assert 'source.matches("[data-chat-retry-query]")' in source
    assert 'renderChatPendingState(form, source.dataset.chatRetryQuery || "");' in source
    assert "event.detail.parameters.q = source.dataset.chatRetryQuery" in source
    assert "원본 메일 불러오는 중" in source
    assert ".chat-email-drawer-loading" in _app_css_source()
    assert 'if (target.closest("[data-chat-email-drawer-open]")) return;' in close_block
    assert "closeChatEmailDrawer();" in close_block
    assert 'scope.querySelectorAll("[data-chat-email-drawer-close]")' in source

def test_mail_chat_service_resolves_follow_up_without_exposing_history_payload():
    captured: dict[str, object] = {}

    class FakeChatSearchService:
        def search(self, query, *, limit, conversation_context=""):
            captured["query"] = query
            captured["limit"] = limit
            captured["conversation_context"] = conversation_context
            return {
                "answer": "이전 맥락의 QT-2026-0812-03 기준 납기는 2026-08-30입니다.",
                "results": [
                    {
                        "email_uid": "mail-quote-1",
                        "source_type": "attachment",
                        "source": "Quotation_QT-2026-0812-03.pdf",
                        "title": "[견적서 송부] 산업용 네트워크 장비",
                        "sender": "sales@example.com",
                        "category": "견적",
                        "received_at": "2026-08-12T09:00:00+09:00",
                        "business_refs": ["QT-2026-0812-03"],
                        "preview": "예상 납기: 2026-08-30",
                    }
                ],
            }

    chat_service = MailChatService(MailChatSessionStore())
    first = chat_service.ask(
        session_id="",
        query="가장 최신 메일이 뭐야",
        search_service=FakeChatSearchService(),
        limit=3,
    )
    captured.clear()
    second = chat_service.ask(
        session_id=first["session_id"],
        query="그 견적서 납기는?",
        search_service=FakeChatSearchService(),
        limit=3,
    )

    assert captured["limit"] == 3
    assert captured["query"] == "그 견적서 납기는? 관련 메일 UID: mail-quote-1"
    assert "이전 질문 1: 가장 최신 메일이 뭐야" in captured["conversation_context"]
    assert "QT-2026-0812-03" in captured["conversation_context"]
    assert "이전 근거 1-1: email_uid=mail-quote-1" in captured["conversation_context"]
    assert "source=Quotation_QT-2026-0812-03.pdf" in captured["conversation_context"]
    assert "preview=예상 납기: 2026-08-30" in captured["conversation_context"]
    assert [turn.query for turn in second["turns"]] == ["가장 최신 메일이 뭐야", "그 견적서 납기는?"]

def test_mail_chat_service_summarizes_gemini_quota_error():
    class QuotaSearchService:
        def search(self, query, *, limit, conversation_context=""):
            raise RuntimeError(
                'LLM HTTP 429: { "error": { "status": "RESOURCE_EXHAUSTED", "message": "quota exceeded" } }'
            )

    chat_service = MailChatService(MailChatSessionStore())
    context = chat_service.ask(
        session_id="",
        query="이거 담당자가 누구야?",
        search_service=QuotaSearchService(),
        limit=5,
    )

    turn = context["turns"][-1]
    assert turn.error == (
        "대화 근거를 조회하지 못했습니다: Gemini API 할당량이 초과되었습니다. "
        "잠시 후 다시 시도하거나 로컬 LLM 설정으로 전환해 주세요."
    )
    assert "RESOURCE_EXHAUSTED" not in turn.error


def test_mail_chat_service_hides_invalid_structured_llm_response_details():
    class InvalidStructuredSearchService:
        def search(self, query, *, limit, conversation_context=""):
            raise RuntimeError("invalid structured LLM response: Unterminated string starting at")

    chat_service = MailChatService(MailChatSessionStore())
    context = chat_service.ask(
        session_id="",
        query="이거 담당자가 누구야?",
        search_service=InvalidStructuredSearchService(),
        limit=5,
    )

    turn = context["turns"][-1]
    assert turn.error == "답변 생성 중 모델 응답 형식이 깨졌습니다. 검색된 근거 기준으로 다시 시도해 주세요."
    assert "Unterminated string" not in turn.error


def test_mail_chat_service_does_not_pollute_concrete_query_with_prior_session_turn():
    captured: dict[str, object] = {}

    class FakeChatSearchService:
        def search(self, query, *, limit, conversation_context=""):
            captured["query"] = query
            captured["limit"] = limit
            captured["conversation_context"] = conversation_context
            return {"answer": "긴급 장애 메일을 찾았습니다.", "results": []}

    chat_service = MailChatService(MailChatSessionStore())
    first = chat_service.ask(
        session_id="",
        query="가장 최신 메일이 뭐야",
        search_service=FakeChatSearchService(),
        limit=5,
    )
    captured.clear()
    chat_service.ask(
        session_id=first["session_id"],
        query="URG-DEMO-2026-0810-01 긴급 장애 메일 찾아줘",
        search_service=FakeChatSearchService(),
        limit=5,
    )

    assert captured["query"] == "URG-DEMO-2026-0810-01 긴급 장애 메일 찾아줘"
    assert "이전 질문 1: 가장 최신 메일이 뭐야" in captured["conversation_context"]

def test_chats_results_uses_server_session_for_follow_up_query(monkeypatch):
    captured: dict[str, object] = {}

    class FakeChatSearchService:
        def search(self, query, *, limit, conversation_context=""):
            captured["query"] = query
            captured["conversation_context"] = conversation_context
            return {
                "answer": "QT-2026-0812-03 기준 납기는 2026-08-30입니다.",
                "results": [],
            }

    chat_service = MailChatService(MailChatSessionStore())
    monkeypatch.setattr(server, "_mail_chat_service", chat_service)
    monkeypatch.setattr(server, "mail_search_service", lambda: FakeChatSearchService())
    first = chat_service.ask(
        session_id="",
        query="가장 최신 메일이 뭐야",
        search_service=FakeChatSearchService(),
        limit=5,
    )
    captured.clear()

    response = server.ui_chats_results(
        request_with_body("GET", "/ui/chats-results", headers=[(b"hx-request", b"true")]),
        q="그 견적서 납기는?",
        limit=5,
        session_id=first["session_id"],
    )
    html = response.body.decode()

    assert response.status_code == 200
    assert captured["query"] == "그 견적서 납기는? 관련 업무 식별자: QT-2026-0812-03"
    assert "이전 질문 1: 가장 최신 메일이 뭐야" in captured["conversation_context"]
    assert "가장 최신 메일이 뭐야" in html
    assert "그 견적서 납기는?" in html
    assert "QT-2026-0812-03 기준 납기는" in html
    assert 'id="chatSessionInput"' in html
    assert 'hx-swap-oob="true"' in html

def test_mail_chat_follow_up_prefers_previous_result_email_uid_for_original_mail_request():
    chat_service = MailChatService(MailChatSessionStore())
    session = chat_service.store.get_or_create("")
    session.append(
        MailChatTurn(
            query="QT-2026-0812-03 견적서의 납기와 총액",
            answer="QT-2026-0812-03 기준으로 납기는 발주 후 14일 이내이고, 총액은 5,346,000원입니다.",
            result={
                "results": [
                    {
                        "email_uid": "0732e633-db61-536e-8ff3-b820826cf9a2",
                        "source": "Quotation_QT-2026-0812-03.pdf",
                        "title": "[견적서 송부] 산업용 네트워크 장비 및 전원모듈",
                        "business_refs": ["QT-2026-0812-03"],
                    }
                ]
            },
        )
    )

    assert chat_service.resolve_search_query("원본 메일 요약해줘", session.turns) == (
        "원본 메일 요약해줘 관련 메일 UID: 0732e633-db61-536e-8ff3-b820826cf9a2"
    )

def test_chat_effective_query_ignores_lowercase_email_local_parts():
    chat_service = MailChatService(MailChatSessionStore())
    first = chat_service.store.get_or_create("")
    first.append(
        MailChatTurn(
            query="가장 최신 메일이 뭐야",
            answer="최신 메일은 sehwi999@dawonict.co.kr에서 받은 일반 문의입니다.",
        )
    )

    assert chat_service.resolve_search_query("그 메일 발신자는?", first.turns) == "그 메일 발신자는?"

def test_chat_follow_up_uses_previous_result_email_uid_when_answer_has_no_business_ref():
    chat_service = MailChatService(MailChatSessionStore())
    first = chat_service.store.get_or_create("")
    first.append(
        MailChatTurn(
            query="가장 최신 메일이 뭐야",
            answer="가장 최신 메일은 2026-07-02 13:59에 발신자만 표시된 일반 문의입니다.",
            result={
                "results": [
                    {
                        "email_uid": "889e6fa9-5052-5a38-b056-1b798ce84304",
                        "title": "일반 문의",
                        "source": "일반 문의",
                        "business_refs": [],
                    }
                ]
            },
        )
    )

    assert (
        chat_service.resolve_search_query("위 메일의 담당자", first.turns)
        == "위 메일의 담당자 관련 메일 UID: 889e6fa9-5052-5a38-b056-1b798ce84304"
    )

def test_shell_installs_search_fallback_when_htmx_cdn_is_unavailable():
    source = server.templates.get_template("shell.html").render(
        **server.ui_globals(),
        request=request(),
        active_view="search",
        initial_view_template="views/search.html",
        query="",
        result=None,
        error="",
    )

    assert "function installSearchFormFallback()" in source
    assert "function renderChatPendingState(form, queryOverride)" in source
    assert "function renderChatErrorState(form, message)" in source
    assert "function syncChatSessionInputFromResponse(form, target)" in source
    assert "function chatComposerForSource(source)" in source
    assert "function installSearchExamples()" in source
    assert 'event.target.closest("[data-search-example]")' in source
    assert 'button.dataset.searchInput || "#searchQueryInput"' in source
    assert "installSearchExamples();" in source
    assert 'form.matches("form.search-box")' in source
    assert 'if (window.htmx) return;' in source
    assert 'form.getAttribute("hx-get") || form.getAttribute("action")' in source
    assert 'fetch(url.toString(), { headers: { "HX-Request": "true" } })' in source
    assert "renderChatPendingState(form);" in source
    assert 'const CHAT_SESSION_STORAGE_KEY = "coramail.chat.session_id";' in source
    assert "function hydrateChatSessionInputs(root)" in source
    assert "function chatSessionUrl(url)" in source
    assert 'form.querySelector("#chatHistoryInput")' in source
    assert 'target.querySelector("#chatHistoryInput")' in source
    assert 'if (form.matches("[data-chat-composer]")) hydrateChatSessionInputs(form);' in source
    assert "form.dataset.chatPendingQuery = query;" in source
    assert "target.appendChild(fragment);" in source
    assert 'if (input) input.value = "";' in source
    assert "rememberChatSessionId(currentInput.value);" in source
    assert "delete source.dataset.chatPendingQuery;" in source
    assert 'source.matches("[data-chat-composer]")' in source
    assert "event.detail.parameters.session_id = sessionId;" in source
    assert "syncChatSessionInputFromResponse(source, chatResultsBodyForForm(source));" in source
    assert "scrollChatThreadToBottom(source);" in source
    after_request_body = source.split('document.body.addEventListener("htmx:afterRequest"', 1)[1]
    chat_after_request_body = after_request_body.split('if (source.matches("[data-classification-regenerate-button]"))', 1)[0]
    assert 'if (input) input.value = "";' not in chat_after_request_body
    assert "installSearchFormFallback();" in source
    assert 'data-copy-toast' in source
    assert "function showCopyToast(message)" in source
    assert "async function copyTextToClipboard(text)" in source
    assert 'event.target.closest("[data-copy-business-ref]")' in source
    assert 'showCopyToast("업무번호가 복사됐습니다.");' in source

    examples_body = source.split("function installSearchExamples()", 1)[1].split("function limitInboxRows()", 1)[0]
    assert "input.value = query;" in examples_body
    assert "input.dispatchEvent(new Event(\"input\", { bubbles: true }));" in examples_body
    assert "fetch(" not in examples_body
    assert "form.submit" not in examples_body

def test_chats_css_keeps_loading_inside_thread_without_hiding_body():
    css = _app_css_source()

    assert ".chat-thread-body" in css
    assert ".chat-loading-bubble" in css
    assert ".chat-typing-dots i" in css
    assert "@keyframes chat-dot-pulse" in css
    assert "#chat-results.htmx-request #chat-results-body" not in css
    assert ".chat-composer" in css
    assert "position: sticky;" in css
    assert ".chat-conversation + .chat-conversation-pending" in css

def test_shell_uses_single_htmx_path_for_main_navigation():
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

    nav_body = source.split("function installMainNavigation()", 1)[1].split("function installSearchFormFallback()", 1)[0]

    assert "function navButtonForPath(pathname)" in source
    assert "function setActiveMainNav(button)" in source
    assert "function setMainNavigationBusy(isBusy)" in source
    assert "function loadMainViewWithoutHtmx(button)" in source
    assert "if (!window.htmx)" in nav_body
    assert "loadMainViewWithoutHtmx(button);" in nav_body
    assert "setActiveMainNav(button);" in nav_body
    assert "setMainNavigationBusy(true);" in nav_body
    assert 'fetch(url, { headers: { "HX-Request": "true" } })' not in source
    assert 'fetch(url, { method: "POST", headers: { "HX-Request": "true" } })' in source
    assert 'source.matches(".nav button[hx-post][hx-target=\'#main-panel\']")' in source
    assert 'setActiveMainNav(navButtonForPath(requestUrl.pathname));' in source
    assert 'setMainNavigationBusy(false);' in source

def test_shell_keeps_fragment_routes_out_of_browser_history():
    source = server.templates.get_template("shell.html").render(
        **{**server.ui_globals(), "demo_mode": True},
        request=request(),
        active_view="search",
        initial_view_template="views/search.html",
        query="",
        result=None,
        error="",
    )

    assert "function mainViewHistoryUrl(fragmentUrl)" in source
    assert "const isDemoDisplayMode = true;" in source
    assert '"/ui/search": "search"' in source
    assert '"/ui/chats": "chats"' in source
    assert "if (isDemoDisplayMode)" in source
    assert 'window.history.pushState({}, "", mainViewHistoryUrl(url));' in source
    assert 'window.history.pushState({}, "", url);' not in source

def test_gmail_shell_does_not_push_fragment_routes_into_browser_history():
    source = server.templates.get_template("shell.html").render(
        **{**server.ui_globals(), "demo_mode": False},
        request=request(),
        active_view="search",
        initial_view_template="views/search.html",
        query="",
        result=None,
        error="",
    )

    assert "const isDemoDisplayMode = false;" in source
    assert "if (isDemoDisplayMode)" in source
    assert 'window.history.pushState({}, "", mainViewHistoryUrl(url));' in source
    assert 'window.history.pushState({}, "", url);' not in source

def test_root_can_render_search_view_without_ui_fragment_url():
    token = server._display_demo_mode.set(True)
    try:
        response = server.ui_root(request(), view="search", q="", limit=5)
        html = response.body.decode()
    finally:
        server._display_demo_mode.reset(token)

    assert 'data-view="search"' in html
    assert 'class="active" hx-post="/ui/search"' in html
    assert 'action="/ui/search"' in html

def test_root_can_render_chats_view_without_ui_fragment_url():
    token = server._display_demo_mode.set(True)
    try:
        response = server.ui_root(request(), view="chats", q="", limit=5)
        html = response.body.decode()
    finally:
        server._display_demo_mode.reset(token)

    assert 'data-view="chats"' in html
    assert 'class="active" hx-post="/ui/chats"' in html
    assert 'action="/ui/chats"' in html

def test_root_can_restore_chats_view_from_session_id(monkeypatch):
    chat_service = MailChatService(MailChatSessionStore())
    session = chat_service.store.get_or_create("0123456789ab")
    session.append(MailChatTurn(query="이전 질문", answer="이전 답변"))
    monkeypatch.setattr(server, "_mail_chat_service", chat_service)

    token = server._display_demo_mode.set(True)
    try:
        response = server.ui_root(request(), view="chats", q="", limit=5, session_id=session.session_id)
        html = response.body.decode()
    finally:
        server._display_demo_mode.reset(token)

    assert 'data-view="chats"' in html
    assert 'id="chatSessionInput" type="hidden" name="session_id" value="0123456789ab"' in html
    assert 'id="chatHistoryInput" type="hidden" name="chat_history"' in html
    assert "이전 질문" in html
    assert "이전 답변" in html

def test_chats_results_restores_compact_history_when_server_session_is_empty(monkeypatch):
    captured: dict[str, object] = {}

    class FakeChatSearchService:
        def search(self, query, *, limit, conversation_context=""):
            captured["query"] = query
            captured["conversation_context"] = conversation_context
            return {"answer": "이전 메일 기준 납기는 7 Days입니다.", "results": []}

    chat_service = MailChatService(MailChatSessionStore())
    monkeypatch.setattr(server, "_mail_chat_service", chat_service)
    monkeypatch.setattr(server, "mail_search_service", lambda: FakeChatSearchService())
    history = json.dumps(
        [
            {
                "query": "가장 최신 메일이 뭐야",
                "answer": "가장 최신 메일은 견적 요청입니다.",
                "search_query": "가장 최신 메일이 뭐야",
                "results": [
                    {
                        "email_uid": "mail-1",
                        "source_type": "mail",
                        "source": "견적 요청 FM250016318",
                        "title": "견적 요청 FM250016318",
                        "sender": "buyer@example.com",
                        "category": "문의",
                        "received_at": "2026-07-31T01:00:00+00:00",
                        "business_refs": "FM250016318",
                        "preview": "KANGRIM valve 견적을 요청합니다.",
                    }
                ],
            }
        ]
    )

    response = server.ui_chats_results(
        request_with_body("GET", "/ui/chats-results", headers=[(b"hx-request", b"true")]),
        q="그 메일 납기는?",
        limit=5,
        session_id="0123456789ab",
        chat_history=history,
    )
    html = response.body.decode()

    assert response.status_code == 200
    assert captured["query"] == "그 메일 납기는? 관련 메일 UID: mail-1"
    assert "이전 질문 1: 가장 최신 메일이 뭐야" in captured["conversation_context"]
    assert "이전 근거 1-1: email_uid=mail-1" in captured["conversation_context"]
    assert "가장 최신 메일이 뭐야" in html
    assert "그 메일 납기는?" in html
    assert 'id="chatHistoryInput"' in html
    assert 'hx-swap-oob="true"' in html

def test_direct_search_results_request_redirects_to_full_search_view():
    response = server.ui_search_results(
        request_with_body(
            "GET",
            "/ui/search-results",
            headers=[(b"cookie", f"{server.DISPLAY_MODE_COOKIE_NAME}=demo".encode("ascii"))],
        ),
        q="QT-2026-0812-03 납기",
        limit=5,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/ui/search?q=QT-2026-0812-03%20%EB%82%A9%EA%B8%B0&limit=5"

def test_gmail_direct_search_results_request_redirects_to_root_search_view():
    response = server.ui_search_results(
        request_with_body(
            "GET",
            "/ui/search-results",
            headers=[(b"cookie", f"{server.DISPLAY_MODE_COOKIE_NAME}=gmail".encode("ascii"))],
        ),
        q="최근 견적 납기",
        limit=5,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/?view=search&q=%EC%B5%9C%EA%B7%BC%20%EA%B2%AC%EC%A0%81%20%EB%82%A9%EA%B8%B0&limit=5"

def test_direct_chats_results_request_redirects_to_full_chats_view():
    response = server.ui_chats_results(
        request_with_body(
            "GET",
            "/ui/chats-results",
            headers=[(b"cookie", f"{server.DISPLAY_MODE_COOKIE_NAME}=demo".encode("ascii"))],
        ),
        q="QT-2026-0812-03 납기",
        limit=5,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/ui/chats?q=QT-2026-0812-03%20%EB%82%A9%EA%B8%B0&limit=5"

def test_direct_chats_results_request_preserves_session_id_in_redirect():
    response = server.ui_chats_results(
        request_with_body(
            "GET",
            "/ui/chats-results",
            headers=[(b"cookie", f"{server.DISPLAY_MODE_COOKIE_NAME}=demo".encode("ascii"))],
        ),
        q="그 메일 담당자",
        limit=5,
        session_id="0123456789ab",
    )

    assert response.status_code == 303
    assert (
        response.headers["location"]
        == "/ui/chats?session_id=0123456789ab&q=%EA%B7%B8%20%EB%A9%94%EC%9D%BC%20%EB%8B%B4%EB%8B%B9%EC%9E%90&limit=5"
    )

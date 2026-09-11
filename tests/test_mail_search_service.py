from __future__ import annotations

from app.llm.gateway import LLMGatewayError, LocalLLMConfig
from app.services.mail_search_service import (
    MailSearchPlan,
    SearchQueryRewrite,
    SearchRerankItem,
    SearchRerankResult,
    MailSearchService,
    SearchCitation,
    SearchIntent,
    SearchSort,
    SearchSynthesis,
    normalize_search_query,
    search_terms,
)


class FakeMailbox:
    def search_documents(self):
        return [
            {
                "email_uid": "mail-1",
                "source_type": "mail",
                "source": "견적 요청 FM250016318",
                "title": "견적 요청 FM250016318",
                "category": "문의",
                "document_category": "",
                "preview": "KANGRIM valve 견적을 요청합니다.",
                "sender": "buyer@example.com",
                "business_refs": ["FM250016318"],
                "vessel_names": ["NYK RUMINA"],
                "received_at": "2026-07-31T01:00:00+00:00",
                "detail_url": "/ui/inbox?email_uid=mail-1",
            },
            {
                "email_uid": "mail-1",
                "source_type": "attachment",
                "source": "FM250016318_quote.pdf",
                "title": "견적 요청 FM250016318",
                "category": "문의",
                "document_category": "quotation",
                "preview": "납기 7 Days / 총액 KRW 518,000",
                "sender": "buyer@example.com",
                "business_refs": ["FM250016318"],
                "vessel_names": ["NYK RUMINA"],
                "received_at": "2026-07-31T01:00:00+00:00",
                "detail_url": "/ui/inbox?email_uid=mail-1",
            },
            {
                "email_uid": "mail-2",
                "source_type": "mail",
                "source": "무관한 서비스 요청",
                "title": "무관한 서비스 요청",
                "category": "서비스",
                "document_category": "",
                "preview": "펌프 수리를 요청합니다.",
                "sender": "service@example.com",
                "business_refs": [],
                "vessel_names": [],
                "received_at": "2026-07-30T01:00:00+00:00",
                "detail_url": "/ui/inbox?email_uid=mail-2",
            },
        ]


class EmptyMailbox:
    def search_documents(self):
        return []


class FakeGateway:
    def __init__(
        self,
        *,
        citations: list[SearchCitation] | None = None,
        answer: str = "근거 기반 답변",
        insufficient: bool = False,
        plan: MailSearchPlan | None = None,
        rewrite: SearchQueryRewrite | None = None,
        rerank: SearchRerankResult | None = None,
        fail_synthesis: bool = False,
        fail_plan: bool = False,
    ):
        self.config = LocalLLMConfig(
            text_model="test-answer-model",
            embedding_model="test-embedding-model",
        )
        self.citations = citations or []
        self.answer = answer
        self.insufficient = insufficient
        self.plan = plan or MailSearchPlan(
            intent=SearchIntent.DOCUMENT_QA,
            semantic_query="",
            sort=SearchSort.RELEVANCE,
            result_limit=5,
            rationale="테스트 기본 계획",
        )
        self.rewrite = rewrite or SearchQueryRewrite(rewritten_queries=[])
        self.rerank = rerank or SearchRerankResult(rankings=[])
        self.fail_synthesis = fail_synthesis
        self.fail_plan = fail_plan
        self.generated_prompts: list[str] = []
        self.generated_messages: list[list[object]] = []
        self.generated_models: list[str | None] = []
        self.embedding_calls: list[list[str]] = []

    def embed(self, texts, *, model=None):
        self.embedding_calls.append(list(texts))
        return [[1.0, 0.0] for _ in texts]

    def generate_structured(
        self,
        *,
        system_prompt,
        user_prompt,
        output_schema,
        model=None,
        temperature=0.0,
    ):
        self.generated_prompts.append(user_prompt)
        self.generated_models.append(model)
        if output_schema is MailSearchPlan:
            if self.fail_plan:
                raise LLMGatewayError("invalid structured LLM response: Unterminated string starting at")
            return self.plan.model_copy(deep=True)
        if output_schema is SearchQueryRewrite:
            return self.rewrite.model_copy(deep=True)
        if output_schema is SearchRerankResult:
            return self.rerank.model_copy(deep=True)
        if output_schema is SearchSynthesis and self.fail_synthesis:
            raise LLMGatewayError("invalid structured LLM response: Unterminated string starting at")
        return SearchSynthesis(
            answer=self.answer,
            insufficient=self.insufficient,
            citations=self.citations,
        )

    def generate_structured_chat(
        self,
        *,
        messages,
        output_schema,
        model=None,
        temperature=0.0,
        role="text",
    ):
        self.generated_messages.append(list(messages))
        user_and_tool_content = "\n\n".join(str(message.content) for message in messages if message.role in {"user", "tool"})
        return self.generate_structured(
            system_prompt=next(str(message.content) for message in messages if message.role == "system"),
            user_prompt=user_and_tool_content,
            output_schema=output_schema,
            model=model,
            temperature=temperature,
        )


def service(
    *,
    mailbox=None,
    citations: list[SearchCitation] | None = None,
    answer: str = "근거 기반 답변",
    insufficient: bool = False,
    plan: MailSearchPlan | None = None,
    rewrite: SearchQueryRewrite | None = None,
    rerank: SearchRerankResult | None = None,
    answer_model: str = "",
    fail_synthesis: bool = False,
    fail_plan: bool = False,
):
    gateway = FakeGateway(
        citations=citations,
        answer=answer,
        insufficient=insufficient,
        plan=plan,
        rewrite=rewrite,
        rerank=rerank,
        fail_synthesis=fail_synthesis,
        fail_plan=fail_plan,
    )
    return MailSearchService(mailbox or FakeMailbox(), gateway, answer_model=answer_model), gateway


def citation(evidence_id: str, score: float = 0.9, reason: str = "질문의 값을 직접 포함합니다."):
    return SearchCitation(evidence_id=evidence_id, relevance_score=score, reason=reason)


def test_search_normalizes_query_and_removes_instruction_words():
    assert normalize_search_query("  FM250016318   납기를 찾아줘 ") == "FM250016318 납기를 찾아줘"
    assert search_terms("FM250016318 견적서의 납기와 총액을 찾아줘") == [
        "fm250016318",
        "견적서",
        "납기",
        "총액",
    ]


def test_search_uses_embedding_retrieval_and_llm_selected_attachment_evidence():
    search_service, gateway = service(
        citations=[citation("E2")],
        answer="FM250016318 견적의 납기는 7일이며 총액은 518,000원입니다.",
    )

    result = search_service.search("FM250016318 견적서의 납기와 총액을 찾아줘", limit=5)

    assert result["results"][0]["source"] == "FM250016318_quote.pdf"
    assert "납기 7 Days" in result["results"][0]["preview"]
    assert result["results"][0]["detail_url"] == "/ui/inbox?email_uid=mail-1"
    assert result["results"][0]["match_explanation"] == "질문의 값을 직접 포함합니다."
    assert result["answer"] == "FM250016318 기준으로 납기는 7 Days이고, 총액은 KRW 518,000입니다."
    trace = result["trace"]
    assert trace["strategy"] == "hybrid_embedding_llm_rag"
    assert trace["intent"] == "document_qa"
    assert trace["sort"] == "relevance"
    assert trace["candidate_count"] == 2
    assert trace["selected_count"] == 1
    assert trace["embedding_model"] == "test-embedding-model"
    assert trace["answer_model"] == "test-answer-model"
    assert trace["query_rewrite_module"] == "llm_guarded_query_rewrite_v1"
    assert trace["reranker_module"] == "llm_evidence_reranker_v1"
    assert trace["query_rewrite_prompt_name"] == "mailbox_query_rewriter"
    assert trace["reranker_prompt_name"] == "mailbox_evidence_reranker"
    assert trace["rewritten_queries"]
    assert trace["prompt_name"] == "mailbox_rag_answer"
    assert trace["prompt_version"] == "v2"
    assert trace["planner_prompt_name"] == "mailbox_query_planner"
    assert trace["planner_prompt_version"] == "v1"
    assert len(gateway.embedding_calls) == 2
    assert "User question" in gateway.generated_prompts[0]
    assert "Candidate evidence" in gateway.generated_prompts[-1]
    assert gateway.generated_models == ["test-answer-model"] * 4
    answer_messages = gateway.generated_messages[-1]
    assert [message.role for message in answer_messages] == ["system", "user", "tool"]
    assert answer_messages[1].name == "human_question"
    assert answer_messages[2].name == "candidate_evidence"


def test_search_separates_planner_rewrite_rerank_and_answer_message_roles():
    search_service, gateway = service(citations=[citation("E2")])

    search_service.search("FM250016318 견적서의 납기와 총액", limit=5)

    assert [[message.role for message in call] for call in gateway.generated_messages] == [
        ["system", "user"],
        ["system", "user"],
        ["system", "user", "tool"],
        ["system", "user", "tool"],
    ]
    assert gateway.generated_messages[0][1].name == "human_question"
    assert gateway.generated_messages[2][2].name == "candidate_evidence"
    assert "Candidate evidence" in str(gateway.generated_messages[2][2].content)


def test_search_falls_back_to_retrieved_evidence_when_answer_synthesis_json_is_invalid():
    search_service, _ = service(fail_synthesis=True)

    result = search_service.search("FM250016318 견적서의 납기와 총액", limit=5)

    assert result["results"][0]["source"] == "FM250016318_quote.pdf"
    assert result["answer"] == "FM250016318 기준으로 납기는 7 Days이고, 총액은 KRW 518,000입니다."
    assert "invalid structured LLM response" in result["trace"]["answer_error"]


def test_search_falls_back_to_context_evidence_when_context_answer_synthesis_json_is_invalid():
    search_service, _ = service(mailbox=EmptyMailbox(), fail_synthesis=True)

    result = search_service.search(
        "이전 메일 내용을 요약해줘",
        limit=5,
        conversation_context=(
            "이전 질문 1: 가장 최신 메일이 뭐야\n"
            "이전 답변 1: 가장 최신 메일은 Delivery Status Notification (Failure)입니다.\n"
            "이전 근거 1-1: email_uid=mail-1 | source_type=mail | "
            "source=Delivery Status Notification (Failure) | "
            "title=Delivery Status Notification (Failure) | sender=mailer-daemon@example.com | "
            "category=발주 | preview=주소를 찾을 수 없어서 메일이 반송되었습니다."
        ),
    )

    assert result["results"][0]["evidence_id"] == "CTX1"
    assert result["answer"].startswith("Delivery Status Notification (Failure) 기준으로 확인된 내용은")
    assert "invalid structured LLM response" in result["trace"]["answer_error"]


def test_search_falls_back_to_deterministic_plan_when_planner_json_is_invalid():
    search_service, _ = service(fail_plan=True, citations=[citation("E2")])

    result = search_service.search("FM250016318 견적서의 납기와 총액", limit=5)

    assert result["results"][0]["source"] == "FM250016318_quote.pdf"
    assert result["trace"]["intent"] == "document_qa"
    assert "invalid structured LLM response" in result["trace"]["planner_error"]


def test_search_can_use_dedicated_chat_answer_model_without_changing_embedding_model():
    search_service, gateway = service(
        citations=[citation("E2")],
        answer="FM250016318 견적의 납기는 7일이며 총액은 518,000원입니다.",
        answer_model="fast-chat-model",
    )

    result = search_service.search("FM250016318 견적서의 납기와 총액을 찾아줘", limit=5)

    assert gateway.generated_models == ["fast-chat-model"] * 4
    assert result["trace"]["answer_model"] == "fast-chat-model"
    assert result["trace"]["embedding_model"] == "test-embedding-model"


def test_search_accepts_conversation_context_without_replacing_current_question():
    search_service, gateway = service(
        citations=[citation("E2")],
        answer="FM250016318 견적의 납기는 7일입니다.",
    )

    result = search_service.search(
        "그 견적서 납기는? 관련 업무 식별자: FM250016318",
        limit=5,
        conversation_context="이전 질문 1: 가장 최신 메일이 뭐야\n이전 답변 1: 최신 메일은 FM250016318 견적 요청입니다.",
    )

    planner_prompt = gateway.generated_prompts[0]
    answer_prompt = gateway.generated_prompts[-1]
    assert result["results"][0]["source"] == "FM250016318_quote.pdf"
    assert "Conversation context from previous turns" in planner_prompt
    assert "do not replace the current question with this context" in planner_prompt
    assert "User question: 그 견적서 납기는? 관련 업무 식별자: FM250016318" in planner_prompt
    assert "Conversation context from previous turns" in answer_prompt
    assert "Question:\n그 견적서 납기는? 관련 업무 식별자: FM250016318" in answer_prompt


def test_search_uses_previous_context_uid_for_follow_up_without_replacing_question():
    search_service, gateway = service(
        citations=[citation("E2")],
        answer="이전 메일 기준 납기는 7 Days입니다.",
    )

    result = search_service.search(
        "납기는?",
        limit=5,
        conversation_context=(
            "이전 질문 1: 가장 최신 메일이 뭐야\n"
            "이전 답변 1: 가장 최신 메일은 견적 요청입니다.\n"
            "이전 근거 1-1: email_uid=mail-1 | source=견적 요청 FM250016318 | "
            "business_refs=FM250016318 | preview=KANGRIM valve 견적을 요청합니다."
        ),
    )

    planner_prompt = gateway.generated_prompts[0]
    answer_prompt = gateway.generated_prompts[-1]
    assert "User question: 납기는?" in planner_prompt
    assert "Question:\n납기는?" in answer_prompt
    assert result["results"][0]["email_uid"] == "mail-1"
    assert result["results"][0]["source"] == "FM250016318_quote.pdf"
    assert result["trace"]["candidate_count"] == 2


def test_search_keeps_context_uid_candidate_when_llm_omits_citation():
    search_service, _ = service(
        citations=[],
        insufficient=True,
        answer="근거가 부족합니다.",
    )

    result = search_service.search("원본 메일 요약해줘 관련 메일 UID: mail-1", limit=5)

    assert result["results"]
    assert result["results"][0]["email_uid"] == "mail-1"
    assert result["results"][0]["match_explanation"] == "이전 대화에서 특정된 메일과 일치하는 근거입니다."
    assert result["answer"] != "제공된 메일과 첨부 분석 근거만으로는 질문에 답할 수 없습니다."


def test_search_answers_with_previous_context_evidence_when_retrieval_has_no_candidates():
    search_service, gateway = service(
        mailbox=EmptyMailbox(),
        citations=[citation("CTX1")],
        insufficient=False,
        answer="이전 대화 근거 기준으로 메일은 주소를 찾을 수 없어 반송된 내용입니다.",
    )

    result = search_service.search(
        "이전 메일 내용을 요약해줘",
        limit=5,
        conversation_context=(
            "이전 질문 1: 가장 최신 메일이 뭐야\n"
            "이전 답변 1: 가장 최신 메일은 Delivery Status Notification (Failure)입니다.\n"
            "이전 근거 1-1: email_uid=mail-1 | source_type=mail | "
            "source=Delivery Status Notification (Failure) | "
            "title=Delivery Status Notification (Failure) | sender=mailer-daemon@example.com | "
            "category=발주 | preview=주소를 찾을 수 없어서 메일이 반송되었습니다."
        ),
    )

    assert result["answer"] == "이전 대화 근거 기준으로 메일은 주소를 찾을 수 없어 반송된 내용입니다."
    assert result["results"][0]["email_uid"] == "mail-1"
    assert result["results"][0]["evidence_id"] == "CTX1"
    assert result["trace"]["candidate_count"] == 1
    assert "[CTX1]" in gateway.generated_prompts[-1]
    assert "주소를 찾을 수 없어서 메일이 반송되었습니다." in gateway.generated_prompts[-1]


def test_search_wraps_bare_value_answer_as_chatbot_sentence():
    search_service, gateway = service(
        citations=[citation("E2")],
        answer="518,000원",
    )

    result = search_service.search("FM250016318 견적서의 납기와 총액을 찾아줘", limit=5)

    assert result["answer"] == "FM250016318 기준으로 납기는 7 Days이고, 총액은 KRW 518,000입니다."
    assert "complete sentence, not only a number" in gateway.generated_prompts[-1]


def test_search_repairs_missing_total_from_structured_attachment_evidence():
    class QuotationMailbox:
        def search_documents(self):
            return [
                {
                    "email_uid": "demo-received-quotation-004",
                    "source_type": "attachment",
                    "source": "Quotation_QT-2026-0812-03.pdf",
                    "title": "[견적서 송부] 산업용 네트워크 장비 및 전원모듈",
                    "category": "문의",
                    "document_category": "quotation",
                    "preview": "expected_delivery: 발주 후 14일 이내 total_amount: 5,346,000원",
                    "sender": "sales@mirae-tech.example",
                    "business_refs": ["QT-2026-0812-03"],
                    "vessel_names": [],
                    "received_at": "2026-08-12T09:10:00+09:00",
                    "detail_url": "/ui/inbox?email_uid=demo-received-quotation-004",
                }
            ]

    search_service, _ = service(
        mailbox=QuotationMailbox(),
        citations=[citation("E1")],
        answer="QT-2026-0812-03 기준으로 납기는 발주 후 14일 이내입니다.",
    )

    result = search_service.search("QT-2026-0812-03 견적서의 납기와 총액", limit=5)

    assert result["answer"] == "QT-2026-0812-03 기준으로 납기는 발주 후 14일 이내이고, 총액은 5,346,000원입니다."


def test_search_removes_trailing_confirmation_filler_from_answer():
    search_service, _ = service(
        citations=[citation("E2")],
        answer="견적서 총액은 518,000원입니다. 확인했습니다.",
    )

    result = search_service.search("FM250016318 견적서의 총액을 찾아줘", limit=5)

    assert result["answer"] == "FM250016318 기준으로 총액은 KRW 518,000입니다."


def test_search_preserves_original_identifier_when_planner_drops_it():
    search_service, gateway = service(
        plan=MailSearchPlan(
            intent=SearchIntent.DOCUMENT_QA,
            semantic_query="견적서 납기 총액",
            sort=SearchSort.RELEVANCE,
            result_limit=5,
            rationale="작은 모델이 참조번호를 누락한 계획",
        ),
        citations=[citation("E2")],
        answer="FM250016318 견적의 납기는 7일이며 총액은 518,000원입니다.",
    )

    result = search_service.search("FM250016318 견적서의 납기와 총액", limit=5)

    assert result["trace"]["candidate_count"] == 2
    assert result["results"][0]["source"] == "FM250016318_quote.pdf"
    assert "fm250016318" in gateway.embedding_calls[0][0]
    assert "delivery" in gateway.embedding_calls[0][0]
    assert "total" in gateway.embedding_calls[0][0]


def test_search_rewrites_query_with_original_planner_and_focused_variants():
    search_service, gateway = service(
        plan=MailSearchPlan(
            intent=SearchIntent.DOCUMENT_QA,
            semantic_query="견적서 납기 총액",
            sort=SearchSort.RELEVANCE,
            result_limit=5,
            rationale="planner rewrite",
        ),
        citations=[citation("E2")],
    )

    search_service.search("FM250016318 견적서의 납기와 총액", limit=5)

    assert gateway.embedding_calls[0][0].startswith("견적서 납기 총액 fm250016318")
    assert "견적서 납기 총액" in gateway.embedding_calls[0]
    assert "FM250016318 견적서의 납기와 총액" in gateway.embedding_calls[0]
    assert any(query.startswith("fm250016318") for query in gateway.embedding_calls[0])


def test_search_accepts_guarded_llm_query_rewrite_variants():
    search_service, gateway = service(
        plan=MailSearchPlan(
            intent=SearchIntent.DOCUMENT_QA,
            semantic_query="견적서 납기 총액",
            sort=SearchSort.RELEVANCE,
            result_limit=5,
            rationale="planner rewrite",
        ),
        rewrite=SearchQueryRewrite(
            rewritten_queries=[
                "FM250016318 delivery date grand total quotation",
                "FM000000000 invented identifier",
            ]
        ),
        citations=[citation("E2")],
    )

    result = search_service.search("FM250016318 견적서의 납기와 총액", limit=5)

    assert "FM250016318 delivery date grand total quotation" in gateway.embedding_calls[0]
    assert "FM000000000 invented identifier" not in gateway.embedding_calls[0]
    assert "FM250016318 delivery date grand total quotation" in result["trace"]["rewritten_queries"]


def test_search_reranks_field_attachment_above_same_identifier_mail_body():
    class FieldRerankMailbox:
        def search_documents(self):
            return [
                {
                    "email_uid": "mail-quote",
                    "source_type": "mail",
                    "source": "견적 요청 FM250016318",
                    "title": "견적 요청 FM250016318",
                    "category": "문의",
                    "document_category": "",
                    "preview": "FM250016318 견적 요청 본문입니다.",
                    "sender": "buyer@example.com",
                    "business_refs": ["FM250016318"],
                    "vessel_names": [],
                    "received_at": "2026-07-31T01:00:00+00:00",
                    "detail_url": "/ui/inbox?email_uid=mail-quote",
                },
                {
                    "email_uid": "mail-quote",
                    "source_type": "attachment",
                    "source": "quote.pdf",
                    "title": "견적 요청 FM250016318",
                    "category": "문의",
                    "document_category": "quotation",
                    "preview": "FM250016318 납기 7 Days / 총액 KRW 518,000",
                    "sender": "buyer@example.com",
                    "business_refs": ["FM250016318"],
                    "vessel_names": [],
                    "received_at": "2026-07-31T01:00:00+00:00",
                    "detail_url": "/ui/inbox?email_uid=mail-quote",
                },
            ]

    search_service, _ = service(
        mailbox=FieldRerankMailbox(),
        citations=[citation("E2"), citation("E1")],
    )

    result = search_service.search("FM250016318 납기와 총액 관련 근거 모두", limit=5)

    assert result["results"][0]["source"] == "quote.pdf"
    assert result["results"][0]["rerank_score"] > result["results"][1]["rerank_score"]


def test_search_uses_llm_reranker_with_validated_evidence_ids():
    mailbox = FakeMailbox()
    search_service, gateway = service(
        mailbox=mailbox,
        rerank=SearchRerankResult(
            rankings=[
                SearchRerankItem(evidence_id="E2", relevance_score=0.97, reason="납기와 총액 값을 직접 포함합니다."),
                SearchRerankItem(evidence_id="invented", relevance_score=1.0, reason="존재하지 않는 근거입니다."),
                SearchRerankItem(evidence_id="E1", relevance_score=0.4, reason="요청 본문만 포함합니다."),
            ]
        ),
        citations=[citation("E2")],
    )

    result = search_service.search("FM250016318 납기와 총액 관련 근거 모두", limit=5)

    assert result["results"][0]["source"] == "FM250016318_quote.pdf"
    assert result["results"][0]["rerank_explanation"] == "납기와 총액 값을 직접 포함합니다."
    assert all(item["evidence_id"] != "invented" for item in result["results"])


def test_search_expands_requested_field_aliases_for_non_fm_business_identifiers():
    class AliasMailbox:
        def search_documents(self):
            return [
                {
                    "email_uid": "mail-bk",
                    "source_type": "attachment",
                    "source": "BK2502044Q_order_ack.pdf",
                    "title": "발주 접수 완료 BK2502044Q",
                    "category": "발주",
                    "document_category": "purchase_order",
                    "preview": "Delivery date: 2025-02-28 / Grand total: USD 3,200",
                    "sender": "spare@example.com",
                    "business_refs": ["BK2502044Q"],
                    "vessel_names": ["BK OCEAN"],
                    "received_at": "2026-07-29T01:00:00+00:00",
                    "detail_url": "/ui/inbox?email_uid=mail-bk",
                }
            ]

    search_service, gateway = service(
        mailbox=AliasMailbox(),
        citations=[citation("E1")],
        answer="BK2502044Q의 납기는 2025-02-28이며 총액은 USD 3,200입니다.",
    )

    result = search_service.search("BK2502044Q 납기와 금액", limit=5)

    assert result["results"][0]["source"] == "BK2502044Q_order_ack.pdf"
    assert "Delivery date: 2025-02-28" in result["results"][0]["preview"]
    assert "Grand total: USD 3,200" in result["results"][0]["preview"]
    assert "delivery" in gateway.embedding_calls[0][0]
    assert "amount" in gateway.embedding_calls[0][0]


def test_search_does_not_require_planner_invented_identifier():
    class NoIdentifierMailbox:
        def search_documents(self):
            return [
                {
                    "email_uid": "mail-quote",
                    "source_type": "attachment",
                    "source": "quotation.pdf",
                    "title": "최근 견적서",
                    "category": "문의",
                    "document_category": "quotation",
                    "preview": "납기 5일 / 총액 KRW 900,000",
                    "sender": "buyer@example.com",
                    "business_refs": [],
                    "vessel_names": [],
                    "received_at": "2026-07-31T01:00:00+00:00",
                    "detail_url": "/ui/inbox?email_uid=mail-quote",
                }
            ]

    search_service, _ = service(
        mailbox=NoIdentifierMailbox(),
        plan=MailSearchPlan(
            intent=SearchIntent.DOCUMENT_QA,
            semantic_query="FM000000000 견적서 납기 총액",
            sort=SearchSort.RELEVANCE,
            result_limit=5,
            rationale="planner가 질문에 없는 식별자를 만든 상황",
        ),
        citations=[citation("E1")],
        answer="근거의 납기는 5일이며 총액은 KRW 900,000입니다.",
    )

    result = search_service.search("최근 견적서의 납기와 총액", limit=5)

    assert result["results"][0]["source"] == "quotation.pdf"


def test_search_excerpt_keeps_identifier_and_requested_fields_for_long_attachment_context():
    mailbox = FakeMailbox()
    documents = mailbox.search_documents()
    documents[1]["preview"] = (
        "FM250016318 견적서 "
        + ("상세 품목 설명 " * 160)
        + "납기 7 Days "
        + ("비고 " * 160)
        + "총액 KRW 518,000"
    )
    mailbox.search_documents = lambda: documents
    search_service, _ = service(mailbox=mailbox, citations=[citation("E2")])

    result = search_service.search("FM250016318 견적서의 납기와 총액", limit=5)

    assert len(result["results"][0]["preview"]) <= 1210
    assert "FM250016318" in result["results"][0]["preview"]
    assert "납기 7 Days" in result["results"][0]["preview"]
    assert "총액 KRW 518,000" in result["results"][0]["preview"]


def test_search_returns_explicit_empty_result_for_unknown_business_identifier_without_llm_call():
    search_service, gateway = service()

    result = search_service.search("FM999999999 견적서의 납기")

    assert result["results"] == []
    assert result["answer"] == "질문과 관련된 메일 본문이나 첨부 분석 근거를 찾지 못했습니다."
    assert gateway.embedding_calls == []
    assert len(gateway.generated_prompts) == 1


def test_search_does_not_return_documents_for_instruction_only_query():
    search_service, gateway = service()

    result = search_service.search("메일에서 찾아줘")

    assert result["results"] == []
    assert "검색에 사용할" in result["answer"]
    assert gateway.embedding_calls == []
    assert len(gateway.generated_prompts) == 1


def test_search_filters_low_relevance_and_unknown_llm_citations():
    search_service, _ = service(
        citations=[
            citation("E2", 0.8),
            citation("E3", 0.3),
            citation("invented", 1.0),
        ]
    )

    result = search_service.search("견적 납기")

    assert [item["evidence_id"] for item in result["results"]] == ["E2"]


def test_search_returns_no_evidence_when_llm_marks_context_insufficient():
    search_service, _ = service(
        citations=[citation("E3", 0.99)],
        answer="펌프 수리 메일입니다.",
        insufficient=True,
    )

    result = search_service.search("계약 금액은 얼마야")

    assert result["results"] == []
    assert result["answer"] == "제공된 메일과 첨부 분석 근거만으로는 질문에 답할 수 없습니다."


def test_search_clips_long_evidence_around_match():
    mailbox = FakeMailbox()
    documents = mailbox.search_documents()
    documents[0]["preview"] = ("앞부분 " * 400) + "특정키워드가 있는 근거" + (" 뒷부분" * 400)
    mailbox.search_documents = lambda: documents
    search_service, _ = service(mailbox=mailbox, citations=[citation("E1")])

    result = search_service.search("특정키워드")

    assert len(result["results"][0]["preview"]) <= 1202
    assert "특정키워드" in result["results"][0]["preview"]
    assert result["results"][0]["preview"].startswith("…")


def test_search_uses_llm_relevance_order_instead_of_recency():
    mailbox = FakeMailbox()
    documents = [mailbox.search_documents()[0]]
    documents.append(
        {
            **documents[0],
            "email_uid": "mail-new",
            "source": "최신 답변",
            "received_at": "2026-08-01T01:00:00+00:00",
        }
    )
    mailbox.search_documents = lambda: documents
    search_service, _ = service(
        mailbox=mailbox,
        citations=[
            citation("E1", 0.95, "질문에 더 직접적인 근거"),
            citation("E2", 0.75, "보조 근거"),
        ],
    )

    result = search_service.search("FM250016318 관련 근거 모두")

    assert result["results"][0]["source"] == "견적 요청 FM250016318"
    assert result["results"][1]["source"] == "최신 답변"


def test_search_tightens_single_question_to_one_best_evidence():
    mailbox = FakeMailbox()
    documents = [mailbox.search_documents()[0]]
    documents.append(
        {
            **documents[0],
            "email_uid": "mail-new",
            "source": "보조 답변",
            "received_at": "2026-08-01T01:00:00+00:00",
        }
    )
    mailbox.search_documents = lambda: documents
    search_service, _ = service(
        mailbox=mailbox,
        citations=[
            citation("E1", 0.95, "질문에 가장 직접적인 근거"),
            citation("E2", 0.9, "비슷하지만 보조 근거"),
        ],
    )

    result = search_service.search("FM250016318 납기는?")

    assert [item["source"] for item in result["results"]] == ["견적 요청 FM250016318"]
    assert result["trace"]["selected_count"] == 1


def test_latest_mail_question_uses_received_time_without_embedding_or_attachment_duplicates():
    search_service, gateway = service(
        plan=MailSearchPlan(
            intent=SearchIntent.DOCUMENT_QA,
            semantic_query="최신 메일",
            sort=SearchSort.RELEVANCE,
            result_limit=5,
            rationale="작은 모델이 잘못 분류한 상황",
        ),
        citations=[citation("E1")],
        answer="가장 최신 메일은 2026년 7월 31일 buyer@example.com에서 온 견적 요청입니다.",
    )

    result = search_service.search("가장 최신 메일이 뭐야", limit=5)

    assert result["answer"] == (
        "가장 최신 메일은 2026-07-31 10:00에 buyer@example.com에서 받은 "
        "“견적 요청 FM250016318”입니다."
    )
    assert [item["source_type"] for item in result["results"]] == ["mail"]
    assert result["results"][0]["source"] == "견적 요청 FM250016318"
    assert result["results"][0]["received_at"] == "2026-07-31T01:00:00+00:00"
    assert result["trace"]["intent"] == "mailbox_lookup"
    assert result["trace"]["sort"] == "received_at_desc"
    assert result["trace"]["candidate_count"] == 1
    assert gateway.embedding_calls == []
    assert "received_at: 2026-07-31T01:00:00+00:00" in gateway.generated_prompts[1]
    assert result["results"][0]["match_explanation"] == "수신 시각을 최신순으로 정렬한 메일함 근거입니다."


def test_mailbox_lookup_applies_sender_filter_and_oldest_sort():
    search_service, gateway = service(
        plan=MailSearchPlan(
            intent=SearchIntent.MAILBOX_LOOKUP,
            sender_filter="service@example.com",
            sort=SearchSort.RECEIVED_AT_ASC,
            result_limit=3,
            rationale="발신자별 오래된 메일 조회",
        ),
        citations=[citation("E3")],
        answer="service@example.com에서 온 가장 오래된 메일은 펌프 수리 요청입니다.",
    )

    result = search_service.search("service@example.com에서 온 가장 오래된 메일은?", limit=5)

    assert [item["email_uid"] for item in result["results"]] == ["mail-2"]
    assert result["trace"]["intent"] == "mailbox_lookup"
    assert result["trace"]["sort"] == "received_at_asc"
    assert gateway.embedding_calls == []


def test_latest_mail_content_question_keeps_document_qa_plan():
    search_service, gateway = service(
        plan=MailSearchPlan(
            intent=SearchIntent.DOCUMENT_QA,
            semantic_query="가장 최근 메일 납기",
            sort=SearchSort.RELEVANCE,
            result_limit=5,
            rationale="최신 메일 내부 사실 질문",
        ),
        citations=[citation("E2")],
        answer="최근 견적 첨부에 기재된 납기는 7일입니다.",
    )

    result = search_service.search("가장 최근 메일의 납기는?", limit=5)

    assert result["trace"]["intent"] == "document_qa"
    assert len(gateway.embedding_calls) == 2


def test_latest_mail_follow_up_field_question_keeps_document_qa_plan():
    search_service, gateway = service(
        plan=MailSearchPlan(
            intent=SearchIntent.MAILBOX_LOOKUP,
            semantic_query="최신 메일 발신자",
            sort=SearchSort.RECEIVED_AT_DESC,
            result_limit=1,
            rationale="작은 모델이 후속 필드 질문을 메일함 조회로 잘못 분류한 상황",
        ),
        citations=[citation("E1")],
        answer="해당 최신 메일의 발신자는 buyer@example.com입니다.",
    )

    result = search_service.search(
        "그 최신 메일 발신자는?",
        limit=5,
        conversation_context=(
            "이전 질문 1: 가장 최신 메일이 뭐야\n"
            "이전 답변 1: 가장 최신 메일은 견적 요청 FM250016318입니다."
        ),
    )

    assert result["trace"]["intent"] == "document_qa"
    assert result["answer"] == "FM250016318 기준으로 발신자는 buyer@example.com입니다."
    assert len(gateway.embedding_calls) == 2


def test_original_mail_summary_follow_up_prefers_mail_body_over_attachment():
    search_service, gateway = service(
        plan=MailSearchPlan(
            intent=SearchIntent.MAILBOX_LOOKUP,
            semantic_query="원본 메일 요약",
            sort=SearchSort.RECEIVED_AT_DESC,
            result_limit=1,
            rationale="작은 모델이 원본 메일 지시를 메일함 조회로 잘못 분류한 상황",
        ),
        citations=[citation("E1", reason="같은 메일 UID의 원본 본문입니다.")],
        answer="원본 메일은 KANGRIM valve 견적 요청 내용입니다.",
    )

    result = search_service.search("원본 메일 요약해줘 관련 메일 UID: mail-1", limit=5)

    assert result["trace"]["intent"] == "document_qa"
    assert [item["source_type"] for item in result["results"]] == ["mail"]
    assert result["results"][0]["source"] == "견적 요청 FM250016318"
    assert "KANGRIM valve 견적을 요청합니다." in gateway.generated_prompts[-1]
    assert "납기 7 Days / 총액 KRW 518,000" not in gateway.generated_prompts[1]


def test_mail_content_follow_up_prefers_mail_body_over_attachment():
    search_service, gateway = service(
        plan=MailSearchPlan(
            intent=SearchIntent.DOCUMENT_QA,
            semantic_query="메일 내용",
            sort=SearchSort.RELEVANCE,
            result_limit=5,
            rationale="메일 내용 후속 질문",
        ),
        citations=[citation("E1")],
        answer="메일 본문은 KANGRIM valve 견적 요청 내용입니다.",
    )

    result = search_service.search(
        "이전 메일 내용을 요약해줘",
        limit=5,
        conversation_context="이전 근거 1-1: email_uid=mail-1 | source=견적 요청 FM250016318",
    )

    assert [item["source_type"] for item in result["results"]] == ["mail"]
    assert result["results"][0]["source"] == "견적 요청 FM250016318"
    assert "KANGRIM valve 견적을 요청합니다." in gateway.generated_prompts[-1]
    assert "납기 7 Days / 총액 KRW 518,000" not in gateway.generated_prompts[1]


def test_identifier_field_question_keeps_document_qa_even_when_planner_uses_mailbox_lookup():
    search_service, gateway = service(
        plan=MailSearchPlan(
            intent=SearchIntent.MAILBOX_LOOKUP,
            semantic_query="FB25001 담당자",
            sort=SearchSort.RECEIVED_AT_DESC,
            result_limit=1,
            rationale="이전 최신 메일 맥락에 끌린 상황",
        ),
        citations=[citation("E1")],
        answer="FB25001 메일의 담당자 근거는 아직 제공되지 않았습니다.",
    )

    result = search_service.search("위 메일의 담당자 관련 업무 식별자: FM250016318", limit=5)

    assert result["trace"]["intent"] == "document_qa"
    assert len(gateway.embedding_calls) == 2


def test_assignee_field_question_uses_routing_metadata_without_llm_citation():
    class AssignmentMailbox(FakeMailbox):
        def search_documents(self):
            documents = super().search_documents()
            return [
                {
                    **documents[0],
                    "preview": f"{documents[0]['preview']} 현재 담당자: 김민수 라우팅 상태: assigned",
                }
            ]

    search_service, gateway = service(
        mailbox=AssignmentMailbox(),
        plan=MailSearchPlan(
            intent=SearchIntent.DOCUMENT_QA,
            semantic_query="FM250016318 담당자",
            sort=SearchSort.RELEVANCE,
            result_limit=5,
            rationale="담당자 필드 질문",
        ),
        citations=[],
        insufficient=True,
    )

    result = search_service.search("위 메일의 담당자 관련 업무 식별자: FM250016318", limit=5)

    assert result["answer"] == "FM250016318 기준으로 현재 담당자는 김민수입니다."
    assert result["results"][0]["match_explanation"] == "현재 라우팅 담당자 근거를 직접 포함합니다."
    assert result["trace"]["selected_count"] == 1
    assert len(gateway.generated_prompts) == 2

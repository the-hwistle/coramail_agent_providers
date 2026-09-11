from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from app.agents.fact_extraction_agent import FactExtractionAgent
from app.document_processing.vision_analyzer import VisionDocumentResult
from app.llm.gateway import LLMMessage, LocalLLMConfig, LocalLLMGateway
from app.mail_content import bracketed_customer
from app.schemas.mail_decision import MailFacts


class StubGateway(LocalLLMGateway):
    def __init__(self):
        self.config = LocalLLMConfig()
        self.payloads: list[dict[str, Any]] = []

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.payloads.append(payload)
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"sender_company":"한빛조선","customer_name":"한빛조선",'
                            '"request_types":["purchase_order"],'
                            '"requested_actions":["납기 확인"],'
                            '"po_numbers":["PO-2026-0184"],'
                            '"product_groups":["valve"],'
                            '"evidence":[],"missing_information":[],"contradictions":[]}'
                        )
                    }
                }
            ]
        }


class VLLMStubGateway(LocalLLMGateway):
    def __init__(self):
        self.config = LocalLLMConfig(
            provider="vllm",
            base_url="http://fallback.invalid/v1",
            text_base_url="http://text.invalid/v1",
            vision_base_url="http://vision.invalid/v1",
            embedding_base_url="http://embedding.invalid/v1",
        )
        self.requests: list[tuple[str, dict[str, Any], str]] = []

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None,
        role: str,
        operation: str,
        model: str = "",
    ) -> dict[str, Any]:
        self.requests.append((url, payload or {}, role))
        if role == "embedding":
            return {"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]}
        if url.endswith("/api/chat"):
            return {
                "message": {
                    "content": (
                        '{"sender_company":"한빛조선","customer_name":"한빛조선",'
                        '"request_types":["purchase_order"],'
                        '"requested_actions":["납기 확인"],'
                        '"po_numbers":["PO-2026-0184"],'
                        '"product_groups":["valve"],'
                        '"evidence":[],"missing_information":[],"contradictions":[]}'
                    )
                }
            }
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"sender_company":"한빛조선","customer_name":"한빛조선",'
                            '"request_types":["purchase_order"],'
                            '"requested_actions":["납기 확인"],'
                            '"po_numbers":["PO-2026-0184"],'
                            '"product_groups":["valve"],'
                            '"evidence":[],"missing_information":[],"contradictions":[]}'
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        }


def test_vision_gateway_builds_multimodal_message() -> None:
    gateway = StubGateway()
    result = gateway.generate_structured_vision(
        system_prompt="extract",
        user_prompt="read image",
        image_base64="YWJj",
        image_mime_type="image/png",
        output_schema=MailFacts,
    )

    assert result.customer_name == "한빛조선"
    content = gateway.payloads[0]["messages"][1]["content"]
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_gateway_keeps_internal_tool_context_as_separate_named_message() -> None:
    gateway = StubGateway()

    gateway.generate_structured_chat(
        messages=[
            LLMMessage(role="system", content="system rules"),
            LLMMessage(role="user", content="human question", name="human_question"),
            LLMMessage(role="tool", content="retrieved evidence", name="candidate_evidence"),
        ],
        output_schema=MailFacts,
    )

    messages = gateway.payloads[0]["messages"]
    assert messages[0] == {"role": "system", "content": "system rules"}
    assert messages[1] == {"role": "user", "content": "human question", "name": "human_question"}
    assert messages[2]["role"] == "user"
    assert messages[2]["name"] == "candidate_evidence"
    assert messages[2]["content"] == "Tool message (candidate_evidence):\nretrieved evidence"
    assert messages[-1]["name"] == "schema_contract"


def test_vllm_gateway_uses_json_schema_response_format_and_role_urls() -> None:
    gateway = VLLMStubGateway()

    result = gateway.generate_structured(
        system_prompt="extract",
        user_prompt="read mail",
        output_schema=MailFacts,
    )
    gateway.generate_structured_vision(
        system_prompt="extract",
        user_prompt="read image",
        image_base64="YWJj",
        image_mime_type="image/png",
        output_schema=MailFacts,
    )
    embedding = gateway.embed(["alpha"])[0]

    assert result.customer_name == "한빛조선"
    assert embedding == [0.1, 0.2, 0.3]
    assert gateway.requests[0][0] == "http://text.invalid/v1/chat/completions"
    assert gateway.requests[0][1]["response_format"]["type"] == "json_schema"
    assert gateway.requests[0][1]["response_format"]["json_schema"]["schema"]["title"] == "MailFacts"
    assert gateway.requests[1][0] == "http://vision.invalid/v1/chat/completions"
    assert gateway.requests[1][2] == "vision"
    assert gateway.requests[2][0] == "http://embedding.invalid/v1/embeddings"


def test_gateway_can_route_text_to_vllm_and_vision_embedding_to_ollama() -> None:
    gateway = VLLMStubGateway()
    gateway.config = LocalLLMConfig(
        provider="ollama",
        text_provider="vllm",
        vision_provider="ollama",
        embedding_provider="ollama",
        base_url="http://fallback.invalid/v1",
        text_base_url="http://text.invalid/v1",
        vision_base_url="http://vision.invalid/v1",
        embedding_base_url="http://embedding.invalid/v1",
    )

    gateway.generate_structured(
        system_prompt="extract",
        user_prompt="read mail",
        output_schema=MailFacts,
    )
    gateway.generate_structured_vision(
        system_prompt="extract",
        user_prompt="read image",
        image_base64="YWJj",
        image_mime_type="image/png",
        output_schema=MailFacts,
    )
    gateway.embed(["alpha"])

    assert gateway.requests[0][0] == "http://text.invalid/v1/chat/completions"
    assert gateway.requests[0][1]["response_format"]["type"] == "json_schema"
    assert gateway.requests[1][0] == "http://vision.invalid/api/chat"
    assert "format" in gateway.requests[1][1]
    assert gateway.requests[1][1]["think"] is False
    assert gateway.requests[1][1]["options"]["num_predict"] == 8192
    assert gateway.requests[1][1]["messages"][1]["content"].startswith("read image")
    assert gateway.requests[1][1]["messages"][1]["images"] == ["YWJj"]
    assert gateway.requests[2][0] == "http://embedding.invalid/v1/embeddings"


def test_vision_document_result_drops_unknown_fields_before_validation() -> None:
    result = VisionDocumentResult.model_validate(
        {
            "document_type": "mail request",
            "document_type_confidence": 0.8,
            "extracted_text": "Vessel: HORIZON\nCustomer: Seahold",
            "fields": {"Vessel": "HORIZON", "Customer": "Seahold"},
        }
    )

    assert result.fields == {"Vessel": "HORIZON"}
    assert "vision_unknown_field:Customer" in result.warnings


class GeminiStubGateway(LocalLLMGateway):
    def __init__(self):
        self.config = LocalLLMConfig(provider="gemini")
        self.requests: list[tuple[str, dict[str, Any]]] = []

    def _send(self, request):
        payload = json.loads((request.data or b"{}").decode("utf-8"))
        self.requests.append((request.full_url, payload))
        if request.full_url.endswith(":embedContent"):
            return {"embedding": {"values": [0.1, 0.2, 0.3]}}
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    '{"sender_company":"한빛조선","customer_name":"한빛조선",'
                                    '"request_types":["purchase_order"],'
                                    '"requested_actions":["납기 확인"],'
                                    '"po_numbers":["PO-2026-0184"],'
                                    '"product_groups":["valve"],'
                                    '"evidence":[],"missing_information":[],"contradictions":[]}'
                                )
                            }
                        ]
                    }
                }
            ]
        }


def test_gemini_gateway_generates_structured_text(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    gateway = GeminiStubGateway()

    result = gateway.generate_structured(
        system_prompt="extract",
        user_prompt="read mail",
        output_schema=MailFacts,
        model="gemini-2.5-flash",
    )

    assert result.customer_name == "한빛조선"
    url, payload = gateway.requests[0]
    assert url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    assert payload["systemInstruction"]["parts"][0]["text"] == "extract"
    assert payload["contents"][0]["parts"][0]["text"].startswith("read mail")
    assert payload["generationConfig"]["responseMimeType"] == "application/json"


def test_gemini_gateway_generates_structured_vision(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    gateway = GeminiStubGateway()

    gateway.generate_structured_vision(
        system_prompt="extract",
        user_prompt="read image",
        image_base64="YWJj",
        image_mime_type="image/png",
        output_schema=MailFacts,
        model="gemini-2.5-flash",
    )

    parts = gateway.requests[0][1]["contents"][0]["parts"]
    assert parts[0]["text"] == "read image"
    assert parts[1]["inlineData"] == {"mimeType": "image/png", "data": "YWJj"}


def test_gemini_gateway_embeds_each_text(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("CORAMAIL_QDRANT_VECTOR_SIZE", "768")
    gateway = GeminiStubGateway()

    embeddings = gateway.embed(["alpha", "beta"], model="gemini-embedding-001")

    assert embeddings == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]
    assert [payload["content"]["parts"][0]["text"] for _, payload in gateway.requests] == ["alpha", "beta"]
    assert [payload["outputDimensionality"] for _, payload in gateway.requests] == [768, 768]
    assert [payload["embedContentConfig"]["outputDimensionality"] for _, payload in gateway.requests] == [768, 768]


def test_fact_agent_preserves_sender_fallback() -> None:
    gateway = StubGateway()
    agent = FactExtractionAgent(gateway)
    facts = agent.extract(
        mail={
            "sender_name": "홍길동",
            "sender_address": "hong@hanbit.example",
            "subject": "PO 납기 확인",
            "body_text": "PO-2026-0184 납기를 확인해 주세요.",
        },
        attachment_results=[
            {
                "attachment_id": str(uuid4()),
                "filename": "po.pdf",
                "document_type": "purchase_order",
                "extracted_text": "PO-2026-0184 valve",
                "fields": {},
                "warnings": [],
            }
        ],
    )

    assert facts.sender_person == "홍길동"
    assert facts.sender_domain == "hanbit.example"
    assert facts.po_numbers == ["PO-2026-0184"]


class EmptyFactsGateway(LocalLLMGateway):
    def __init__(self):
        self.config = LocalLLMConfig()

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"customer_candidates":[],"request_types":[],"requested_actions":[],'
                            '"product_names":[],"product_groups":[],"part_numbers":[],"po_numbers":[],'
                            '"quotation_numbers":[],"project_numbers":[],"vessel_names":[],'
                            '"requested_dates":[],"urgency_signals":[],"importance_signals":[],"claim_signals":[],'
                            '"missing_information":[],"contradictions":[],"evidence":[]}'
                        )
                    }
                }
            ]
        }


class DocumentLabelCustomerGateway(LocalLLMGateway):
    def __init__(self):
        self.config = LocalLLMConfig()

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"customer_name":"견적서","customer_candidates":["견적서"],'
                            '"request_types":["quotation_followup"],"requested_actions":[],'
                            '"product_names":[],"product_groups":[],"part_numbers":[],"po_numbers":[],'
                            '"quotation_numbers":[],"project_numbers":[],"vessel_names":[],'
                            '"requested_dates":[],"urgency_signals":[],"importance_signals":[],"claim_signals":[],'
                            '"missing_information":[],"contradictions":[],"evidence":[]}'
                        )
                    }
                }
            ]
        }


class BusinessLabelCustomerGateway(LocalLLMGateway):
    def __init__(self):
        self.config = LocalLLMConfig()

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"customer_name":"견적 요청","customer_candidates":["견적 요청","안녕하세요. 네오팩토리솔루션"],'
                            '"request_types":["quotation_request"],"requested_actions":["견적과 납기 가능일 확인 후 회신"],'
                            '"product_names":[],"product_groups":[],"part_numbers":[],"po_numbers":[],'
                            '"quotation_numbers":[],"project_numbers":[],"vessel_names":[],'
                            '"requested_dates":[],"urgency_signals":[],"importance_signals":[],"claim_signals":[],'
                            '"missing_information":[],"contradictions":[],"evidence":[]}'
                        )
                    }
                }
            ]
        }


def test_fact_agent_fills_explicit_labeled_body_facts_when_llm_returns_empty() -> None:
    agent = FactExtractionAgent(EmptyFactsGateway())
    facts = agent.extract(
        mail={
            "sender_name": "Requester",
            "sender_address": "requester@customer12.invalid",
            "subject": "[PRJ-2026-001] quotation_request - engine REF-000120",
            "body_text": (
                "Customer: Synthetic Marine Customer 12\n"
                "Project: PRJ-2026-001\n"
                "Vessel: SYNTHETIC VESSEL 01\n"
                "Product group: engine\n"
                "Request type: quotation_request\n"
                "Reference: REF-000120\n"
                "Please review and respond.\n"
            ),
        },
        attachment_results=[],
    )

    assert facts.customer_name == "Synthetic Marine Customer 12"
    assert facts.customer_candidates == ["Synthetic Marine Customer 12"]
    assert facts.project_numbers == ["PRJ-2026-001"]
    assert facts.vessel_names == ["SYNTHETIC VESSEL 01"]
    assert facts.product_groups == ["engine"]
    assert facts.request_types == ["quotation_request"]
    assert facts.quotation_numbers == ["REF-000120"]
    assert facts.requested_actions == ["prepare quotation"]
    assert [item.source_type for item in facts.evidence] == ["email_body"] * 6


def test_bracketed_customer_ignores_document_type_labels_in_forwarded_subject() -> None:
    subject = (
        "Fw: [FW][FW][RE]FWD :<사양확인 요청건> [견적서] 플루맥스 FM240019488 / "
        "NYK RUMINA / Hyundai Samho Heavy Industries S376 / HF-240924078 / 김선영"
    )

    assert bracketed_customer(subject) is None


def test_bracketed_customer_ignores_business_type_labels() -> None:
    assert bracketed_customer("[견적 요청] 자동화 제어 부품 견적 확인") is None
    assert bracketed_customer("[납기 확인] 출고 예정일 및 부분 납품 문의") is None
    assert bracketed_customer("[발주서 접수] 현장 예비품 발주 요청") is None


def test_fact_agent_rejects_document_type_label_as_customer_name() -> None:
    agent = FactExtractionAgent(DocumentLabelCustomerGateway())
    facts = agent.extract(
        mail={
            "sender_name": "김선영",
            "sender_address": "sender@example.invalid",
            "subject": (
                "Fw: [FW][FW][RE]FWD :<사양확인 요청건> [견적서] 플루맥스 FM240019488 / "
                "NYK RUMINA / Hyundai Samho Heavy Industries S376 / HF-240924078 / 김선영"
            ),
            "body_text": "사양 확인 부탁드립니다.",
        },
        attachment_results=[],
    )

    assert facts.customer_name is None
    assert facts.customer_candidates == []
    assert "customer_name_rejected_non_customer_label" in facts.missing_information
    assert "customer_requires_review" in facts.missing_information


def test_fact_agent_replaces_business_label_customer_with_sender_company() -> None:
    agent = FactExtractionAgent(BusinessLabelCustomerGateway())
    facts = agent.extract(
        mail={
            "sender_name": "김하린",
            "sender_address": "harin@neofactory.example",
            "subject": "[견적 요청] 자동화 제어 부품 견적 확인",
            "body_text": (
                "안녕하세요. 네오팩토리솔루션 김하린입니다.\n\n"
                "자동화 제어 부품 견적과 납기 가능일 확인 요청.\n\n"
                "확인 후 회신 부탁드립니다.\n\n"
                "감사합니다.\n"
                "김하린\n"
                "네오팩토리솔루션"
            ),
        },
        attachment_results=[],
    )

    assert facts.customer_name == "네오팩토리솔루션"
    assert facts.customer_candidates == ["네오팩토리솔루션"]
    assert "견적 요청" not in facts.customer_candidates
    assert "customer_requires_review" not in facts.missing_information
    assert "customer_name_rejected_non_customer_label" in facts.missing_information


def test_fact_agent_uses_sender_company_instead_of_delivery_subject_label() -> None:
    agent = FactExtractionAgent(EmptyFactsGateway())
    facts = agent.extract(
        mail={
            "sender_name": "이도현",
            "sender_address": "dohyun@saerom-tech.example",
            "subject": "[납기 확인] 출고 예정일 및 부분 납품 문의",
            "body_text": (
                "안녕하세요. 새롬테크 이도현입니다.\n\n"
                "출고 예정일과 부분 납품 가능 여부 확인 요청.\n\n"
                "확인 후 회신 부탁드립니다.\n\n"
                "감사합니다.\n"
                "이도현\n"
                "새롬테크"
            ),
        },
        attachment_results=[],
    )

    assert facts.customer_name == "새롬테크"
    assert facts.customer_candidates == ["새롬테크"]
    assert facts.request_types == ["delivery_confirmation"]


def test_fact_agent_rejects_sent_quotation_subject_label_as_customer_name() -> None:
    agent = FactExtractionAgent(EmptyFactsGateway())
    facts = agent.extract_grounded(
        mail={
            "sender_name": "박서진",
            "sender_address": "sales@mirae-tech.example",
            "subject": "[견적서 송부] 산업용 네트워크 장비 및 전원모듈",
            "body_text": (
                "안녕하세요.\n\n"
                "미래산업기술 박서진입니다.\n\n"
                "표제 건 관련하여 요청하신 산업용 네트워크 장비 및 전원모듈 견적서를 첨부드립니다."
            ),
        },
        attachment_results=[],
        reason="demo_screenshot_fallback",
    )

    assert facts.customer_name == "미래산업기술"
    assert facts.customer_candidates == ["미래산업기술"]
    assert "customer_requires_review" not in facts.missing_information


def test_fact_agent_prioritizes_current_delivery_request_over_quoted_thread() -> None:
    agent = FactExtractionAgent(EmptyFactsGateway())
    facts = agent.extract(
        mail={
            "sender_name": "이희원",
            "sender_address": "buyer@example.invalid",
            "subject": "RE: [RE][한빛마린] FB26000001 / 납품일정문의",
            "body_text": (
                "표제의 긴급 건, 25일 이내로 납품 가능하실지 확인 부탁드립니다.\n"
                "From: FLUEMAX <sales@example.invalid>\n"
                "과거 견적 요청 및 발주 내용입니다."
            ),
        },
        attachment_results=[],
    )

    assert facts.customer_name == "한빛마린"
    assert facts.request_types == ["delivery_confirmation"]
    assert facts.requested_actions == ["25일이내 납품 가능 여부 확인 후 회신"]
    assert facts.requested_dates == ["25일이내"]
    assert facts.urgency_signals == []
    assert facts.quotation_numbers == ["FB26000001"]


def test_fact_agent_extracts_grounded_urgency_and_importance_phrases() -> None:
    agent = FactExtractionAgent(EmptyFactsGateway())
    facts = agent.extract_grounded(
        mail={
            "sender_name": "Chief Engineer",
            "sender_address": "chief@vessel.example",
            "subject": "Main Engine Control Unit 긴급 장애 지원 요청",
            "body_text": (
                "현재 운항 중인 선박의 Main Engine Control Unit 장애로 운항이 중단된 상태입니다.\n"
                "금일 14시 이전까지 기술 지원 및 교체 가능 여부를 회신 부탁드립니다."
            ),
        },
        attachment_results=[],
        reason="test",
    )

    assert any("금일 14시 이전까지" in signal for signal in facts.urgency_signals)
    assert any("운항이 중단" in signal or "장애" in signal for signal in facts.urgency_signals)
    assert any("운항이 중단" in signal or "장애" in signal for signal in facts.importance_signals)


def test_fact_agent_does_not_treat_bare_urgent_word_as_time_pressure() -> None:
    agent = FactExtractionAgent(EmptyFactsGateway())
    facts = agent.extract_grounded(
        mail={
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "subject": "카탈로그 요청",
            "body_text": "긴급하게 최신 카탈로그 전달 부탁드립니다.",
        },
        attachment_results=[],
        reason="test",
    )

    assert facts.urgency_signals == []
    assert facts.importance_signals == []


def test_fact_agent_ignores_resolved_past_failure_context() -> None:
    agent = FactExtractionAgent(EmptyFactsGateway())
    facts = agent.extract_grounded(
        mail={
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "subject": "장애 보고서 사본 요청",
            "body_text": "지난달 발생했던 장애 건은 이미 해결되었습니다. 관련 보고서 사본을 전달 부탁드립니다.",
        },
        attachment_results=[],
        reason="test",
    )

    assert facts.urgency_signals == []
    assert facts.importance_signals == []


def test_fact_agent_ignores_quoted_urgent_failure_history() -> None:
    agent = FactExtractionAgent(EmptyFactsGateway())
    facts = agent.extract_grounded(
        mail={
            "sender_name": "Buyer",
            "sender_address": "buyer@example.invalid",
            "subject": "RE: 보고서 사본 요청",
            "body_text": (
                "관련 보고서 사본 전달 부탁드립니다.\n\n"
                "On Thu, Aug 20, 2026 at 10:00 AM Buyer wrote:\n"
                "긴급 장애로 운항 중단 상태입니다. 금일 중 회신 부탁드립니다."
            ),
        },
        attachment_results=[],
        reason="test",
    )

    assert facts.urgency_signals == []
    assert facts.importance_signals == []


def test_fact_agent_does_not_mark_major_customer_brochure_as_important() -> None:
    agent = FactExtractionAgent(EmptyFactsGateway())
    facts = agent.extract_grounded(
        mail={
            "sender_name": "Sales",
            "sender_address": "sales@example.invalid",
            "subject": "브로슈어 요청",
            "body_text": "주요 고객사에서 제품 브로슈어를 다음 주 회의 전까지 요청했습니다.",
        },
        attachment_results=[],
        reason="test",
    )

    assert facts.urgency_signals == []
    assert facts.importance_signals == []

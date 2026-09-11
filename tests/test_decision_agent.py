from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.decision_agent import DecisionAgent, DecisionAgentOutput
from app.llm.gateway import LLMGatewayError
from app.presentation.summary_text import polish_korean_summary_text
from app.schemas.mail_decision import MailClassification, MailFacts, MailImportance, MailSummary, MailUrgency
from app.schemas.retrieval import RetrievalContext, RetrievalHit, RetrieverType
from app.services.postgres_mail_service import PostgresMailboxService


class StubGateway:
    def __init__(self, output: DecisionAgentOutput):
        self.output = output
        self.calls = []

    def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        return self.output


class FailingGateway:
    def generate_structured(self, **kwargs):
        raise LLMGatewayError("invalid structured output")


def _output(confidence: float = 0.9, unsupported: list[str] | None = None) -> DecisionAgentOutput:
    return DecisionAgentOutput(
        summary=MailSummary(
            one_line_summary="PO-100 납기 확인 요청",
            requested_actions=["납기 확인"],
            business_refs=["PO-100"],
            confidence=confidence,
        ),
        classification=MailClassification(
            business_area="order",
            primary_type="purchase_order",
            candidate_scores={"purchase_order": confidence},
            confidence=confidence,
        ),
        urgency=MailUrgency(level="normal", confidence=0.86, reasons=[]),
        importance=MailImportance(level="normal", confidence=0.86, reasons=[]),
        requested_actions=["납기 확인"],
        unsupported_claims=unsupported or [],
    )


def _retrieval() -> RetrievalContext:
    return RetrievalContext(
        selected_hits=[
            RetrievalHit(
                retriever_type=RetrieverType.EXACT,
                source_type="email_message",
                source_id=uuid4(),
                title="Past PO",
                content="confirmed assignee context",
                retrieval_score=0.9,
                metadata={"assignee_user_id": str(uuid4())},
            )
        ],
        sufficient=True,
    )


def test_low_confidence_forces_review():
    gateway = StubGateway(_output(confidence=0.7))
    result = DecisionAgent(gateway).decide(
        mail={"subject": "PO-100", "body_text": "Please confirm delivery"},
        facts=MailFacts(po_numbers=["PO-100"], requested_actions=["납기 확인"]),
        retrieval=_retrieval(),
    )
    assert result.review_required is True
    assert "classification_confidence_below_threshold" in result.review_reasons


def test_unsupported_claims_force_review():
    gateway = StubGateway(_output(unsupported=["unsupported delivery date"]))
    result = DecisionAgent(gateway).decide(
        mail={"subject": "PO-100", "body_text": "Please confirm delivery"},
        facts=MailFacts(po_numbers=["PO-100"]),
        retrieval=_retrieval(),
    )
    assert result.review_required is True
    assert "unsupported_claims_present" in result.review_reasons


def test_prompt_contains_allowed_taxonomy_and_retrieved_context():
    gateway = StubGateway(_output())
    DecisionAgent(gateway).decide(
        mail={"subject": "PO-100", "body_text": "Please confirm delivery"},
        facts=MailFacts(po_numbers=["PO-100"]),
        retrieval=_retrieval(),
    )
    prompt = gateway.calls[0]["user_prompt"]
    assert "purchase_order" in prompt
    assert "confirmed assignee context" in prompt
    assert "Urgency and Importance as independent high/normal axes" in gateway.calls[0]["system_prompt"]


def test_attention_quadrant_is_calculated_from_independent_axes():
    output = _output()
    output.urgency = MailUrgency(level="high", confidence=0.83, reasons=["금일 중 회신 요청"])
    output.importance = MailImportance(level="normal", confidence=0.81, reasons=[])
    output.attention_quadrant = "urgent_important"
    gateway = StubGateway(output)

    result = DecisionAgent(gateway).decide(
        mail={"subject": "금일 중 견적 부탁드립니다.", "body_text": "금일 중 견적 부탁드립니다."},
        facts=MailFacts(urgency_signals=["금일 중 회신 요청"], importance_signals=[]),
        retrieval=_retrieval(),
    )

    assert result.urgency.level == "high"
    assert result.importance.level == "normal"
    assert result.attention_quadrant == "urgent"


@pytest.mark.parametrize(
    ("urgency", "importance", "expected"),
    [
        ("high", "high", "urgent_important"),
        ("high", "normal", "urgent"),
        ("normal", "high", "important"),
        ("normal", "normal", "normal"),
    ],
)
def test_decision_agent_quadrants_follow_grounded_axes(urgency: str, importance: str, expected: str) -> None:
    output = _output()
    output.urgency = MailUrgency(level=urgency, confidence=0.9, reasons=["LLM reason"])
    output.importance = MailImportance(level=importance, confidence=0.9, reasons=["LLM reason"])
    output.attention_quadrant = "normal"
    gateway = StubGateway(output)

    facts = MailFacts(
        urgency_signals=["금일 14시 이전 회신 요청"] if urgency == "high" else [],
        importance_signals=["선박 운항 중단"] if importance == "high" else [],
    )
    result = DecisionAgent(gateway).decide(
        mail={"subject": "테스트", "body_text": "테스트"},
        facts=facts,
        retrieval=_retrieval(),
    )

    assert result.attention_quadrant == expected
    if urgency == "high":
        assert result.urgency.reasons == facts.urgency_signals
    if importance == "high":
        assert result.importance.reasons == facts.importance_signals


def test_decision_agent_downgrades_ungrounded_bare_urgent_high() -> None:
    output = _output()
    output.urgency = MailUrgency(level="high", confidence=0.92, reasons=["긴급합니다"])
    output.importance = MailImportance(level="high", confidence=0.91, reasons=["클레임입니다"])
    output.attention_quadrant = "urgent_important"
    gateway = StubGateway(output)

    result = DecisionAgent(gateway).decide(
        mail={"subject": "카탈로그 요청", "body_text": "긴급하게 최신 카탈로그 전달 부탁드립니다."},
        facts=MailFacts(request_types=["general_inquiry"], urgency_signals=[], importance_signals=[]),
        retrieval=_retrieval(),
    )

    assert result.urgency.level == "normal"
    assert result.importance.level == "normal"
    assert result.attention_quadrant == "normal"


def test_decision_agent_downgrades_broad_future_deadline_and_contract_copy_signals() -> None:
    output = _output()
    output.urgency = MailUrgency(level="high", confidence=0.93, reasons=["by next week meeting"])
    output.importance = MailImportance(level="high", confidence=0.92, reasons=["계약서 사본 요청"])
    output.attention_quadrant = "urgent_important"
    gateway = StubGateway(output)

    result = DecisionAgent(gateway).decide(
        mail={
            "subject": "계약서 사본 요청",
            "body_text": "다음 주 회의 전까지 계약서 사본 전달 부탁드립니다.",
        },
        facts=MailFacts(
            request_types=["general_inquiry"],
            urgency_signals=["by next week meeting"],
            importance_signals=["계약서 사본 요청"],
        ),
        retrieval=_retrieval(),
    )

    assert result.urgency.level == "normal"
    assert result.importance.level == "normal"
    assert result.attention_quadrant == "normal"


def test_decision_agent_downgrades_bare_today_signal_without_response_pressure() -> None:
    output = _output()
    output.urgency = MailUrgency(level="high", confidence=0.9, reasons=["오늘 자료 감사합니다"])
    output.attention_quadrant = "urgent"
    gateway = StubGateway(output)

    result = DecisionAgent(gateway).decide(
        mail={"subject": "자료 수신 확인", "body_text": "오늘 자료 감사합니다. 검토 후 연락드리겠습니다."},
        facts=MailFacts(request_types=["general_inquiry"], urgency_signals=["오늘 자료 감사합니다"]),
        retrieval=_retrieval(),
    )

    assert result.urgency.level == "normal"
    assert result.attention_quadrant == "normal"


def test_decision_agent_accepts_specific_same_day_and_contract_breach_signals() -> None:
    output = _output()
    output.urgency = MailUrgency(level="high", confidence=0.91, reasons=["by 14:00"])
    output.importance = MailImportance(level="high", confidence=0.9, reasons=["계약 위반 penalty 발생 가능"])
    output.attention_quadrant = "normal"
    gateway = StubGateway(output)

    result = DecisionAgent(gateway).decide(
        mail={
            "subject": "납품 지연 긴급 회신 요청",
            "body_text": "금일 14시까지 회신이 없으면 계약 위반 penalty 발생 가능성이 있습니다.",
        },
        facts=MailFacts(
            request_types=["delivery_delay"],
            urgency_signals=["금일 14시까지 회신"],
            importance_signals=["계약 위반 penalty 발생 가능"],
        ),
        retrieval=_retrieval(),
    )

    assert result.urgency.level == "high"
    assert result.importance.level == "high"
    assert result.attention_quadrant == "urgent_important"


def test_decision_fallback_keeps_urgent_and_important_axes_independent() -> None:
    urgent_only = DecisionAgent.fallback_decision(
        mail={"subject": "소모품 견적 요청", "body_text": "필터 및 퓨즈 소모품 견적을 금일 중 보내주시기 바랍니다."},
        facts=MailFacts(request_types=["quotation_request"], urgency_signals=["금일 중 보내주시기 바랍니다"], importance_signals=[]),
        reason="test",
    )
    important_only = DecisionAgent.fallback_decision(
        mail={"subject": "신규 선박 프로젝트 장비 공급 기술 검토 요청", "body_text": "예상 발주 규모는 기존 프로젝트보다 큰 수준입니다."},
        facts=MailFacts(
            request_types=["specification_review"],
            urgency_signals=[],
            importance_signals=["예상 발주 규모는 기존 프로젝트보다 큰 수준"],
        ),
        reason="test",
    )

    assert urgent_only.urgency.level == "high"
    assert urgent_only.importance.level == "normal"
    assert urgent_only.attention_quadrant == "urgent"
    assert important_only.urgency.level == "normal"
    assert important_only.importance.level == "high"
    assert important_only.attention_quadrant == "important"


def test_decision_is_aligned_to_grounded_current_mail_facts():
    output = _output(confidence=0.8)
    output.summary.one_line_summary = "RE: [한빛마린] FB26000001 / 납품일정문의"
    gateway = StubGateway(output)

    result = DecisionAgent(gateway).decide(
        mail={"subject": "RE: [한빛마린] FB26000001 / 납품일정문의", "body_text": "25일 이내 납품 확인 부탁드립니다."},
        facts=MailFacts(
            customer_name="한빛마린",
            request_types=["delivery_confirmation"],
            requested_actions=["25일이내 납품 가능 여부 확인 후 회신"],
            quotation_numbers=["FB26000001"],
        ),
        retrieval=_retrieval(),
    )

    assert result.classification.primary_type == "delivery_confirmation"
    assert result.classification.business_area == "order"
    assert result.summary.one_line_summary == "한빛마린 FB26000001 25일이내 납품 가능 여부 확인 후 회신"
    assert result.summary.requested_actions == ["25일이내 납품 가능 여부 확인 후 회신"]
    assert result.generation_mode == "llm_validated"


def test_decision_polishes_awkward_korean_scheduled_event_summary():
    output = _output(confidence=0.88)
    output.summary.one_line_summary = (
        "딘텍이 2/28일 이탈리아에서 드라이독을 예정하고, 2/22일로 원납기를 확인하도록 요청합니다."
    )
    output.requested_actions = ["2/22일 원납기 확인"]
    gateway = StubGateway(output)

    result = DecisionAgent(gateway).decide(
        mail={
            "subject": "[딘텍] FB24291770 / 납품일정문의",
            "body_text": "2/28일 이탈리아에서 드라이독 예정입니다. 2/22일 원납기 확인 부탁드립니다.",
        },
        facts=MailFacts(
            customer_name="딘텍",
            request_types=["delivery_confirmation"],
            requested_actions=["2/22일 원납기 확인"],
            quotation_numbers=["FB24291770"],
            requested_dates=["2/28", "2/22"],
        ),
        retrieval=_retrieval(),
    )

    assert result.summary.one_line_summary == (
        "딘텍이 2/28일 이탈리아에서 드라이독 예정이어서, 2/22일로 원납기를 확인하도록 요청합니다."
    )
    assert "드라이독을 예정하고" not in result.summary.one_line_summary
    assert result.generation_mode == "llm_validated"


def test_decision_replaces_send_only_quotation_summary_with_action():
    output = _output(confidence=0.88)
    output.summary.one_line_summary = "박서진이 미래산업기술의 산업용 네트워크 장비 견적서를 송부했습니다."
    gateway = StubGateway(output)

    result = DecisionAgent(gateway).decide(
        mail={
            "subject": "[견적서 송부] 산업용 네트워크 장비",
            "body_text": "첨부 견적서 확인 후 발주 가능 여부 또는 수정 요청 사항 회신 부탁드립니다.",
        },
        facts=MailFacts(
            sender_person="박서진",
            request_types=["quotation_followup"],
            requested_actions=["견적서 유효기간·납기·합계금액 확인 후 발주 가능 여부 또는 수정 요청 사항 회신"],
            quotation_numbers=["QT-2026-0812-03"],
            requested_dates=["2026-08-14"],
        ),
        retrieval=_retrieval(),
    )

    assert result.summary.one_line_summary == (
        "박서진 QT-2026-0812-03 견적서 유효기간·납기·합계금액 확인 후 발주 가능 여부 또는 수정 요청 사항 회신"
    )
    assert "송부했습니다" not in result.summary.one_line_summary
    assert result.generation_mode == "llm_validated"


def test_stored_summary_sections_are_polished_for_immediate_display():
    sections = PostgresMailboxService._summary_sections(
        {
            "summary_result_json": {
                "sections": [
                    {
                        "title": "핵심 요청",
                        "body": (
                            "딘텍이 2/28일 이탈리아에서 드라이독을 예정하고, "
                            "2/22일로 원납기를 확인하도록 요청합니다."
                        ),
                    }
                ]
            }
        }
    )

    assert sections == [
        {
            "title": "핵심 요청",
            "body": "딘텍이 2/28일 이탈리아에서 드라이독 예정이어서, 2/22일로 원납기를 확인하도록 요청합니다.",
        }
    ]


def test_summary_polish_removes_demo_quotation_prefix_and_repeated_business_ref():
    assert (
        polish_korean_summary_text(
            "견적서 송부 QT-2026-0812-03 QT-2026-0812-03 견적서 유효기간·납기·합계금액 확인 후 발주 가능 여부 또는 수정 요청 사항 회신"
        )
        == "QT-2026-0812-03 견적서 유효기간·납기·합계금액 확인 후 발주 가능 여부 또는 수정 요청 사항 회신"
    )


def test_decision_agent_does_not_report_fallback_as_ai_success_when_llm_schema_fails():
    with pytest.raises(LLMGatewayError, match="invalid structured output"):
        DecisionAgent(FailingGateway()).decide(
            mail={"subject": "[PRJ-2026-006] repair_request - automation REF-000121"},
            facts=MailFacts(
                sender_person="Requester 121",
                customer_name="Synthetic Marine Customer 01",
                request_types=["repair_request"],
                requested_actions=["coordinate repair request"],
                product_groups=["automation"],
                project_numbers=["PRJ-2026-006"],
            ),
            retrieval=_retrieval(),
        )

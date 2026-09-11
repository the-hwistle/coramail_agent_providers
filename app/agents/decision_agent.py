from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field, model_validator

from app.llm.gateway import LocalLLMGateway
from app.mail_content import current_message_body
from app.presentation.summary_text import polish_korean_summary_text
from app.schemas.mail_decision import (
    AttentionQuadrant,
    MailClassification,
    MailFacts,
    MailImportance,
    MailSummary,
    MailUrgency,
    attention_quadrant_for,
)
from app.schemas.retrieval import RetrievalContext


ALLOWED_PRIMARY_TYPES = {
    "quotation_request", "quotation_followup", "purchase_order", "order_change", "order_cancellation",
    "delivery_confirmation", "delivery_delay", "technical_inquiry", "drawing_review",
    "specification_review", "compatibility_check", "service_request", "repair_request", "claim",
    "urgent_failure", "invoice", "payment_inquiry", "certificate_request", "general_inquiry", "spam",
}


class DecisionAgentOutput(BaseModel):
    summary: MailSummary
    classification: MailClassification
    urgency: MailUrgency
    importance: MailImportance
    attention_quadrant: AttentionQuadrant = "normal"
    requested_actions: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    review_required: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    generation_mode: str = "llm"

    @model_validator(mode="after")
    def validate_taxonomy(self) -> DecisionAgentOutput:
        if self.classification.primary_type not in ALLOWED_PRIMARY_TYPES:
            raise ValueError(f"unsupported primary_type: {self.classification.primary_type}")
        return self


class DecisionAgent:
    def __init__(self, gateway: LocalLLMGateway):
        self.gateway = gateway

    def decide(self, *, mail: dict, facts: MailFacts, retrieval: RetrievalContext) -> DecisionAgentOutput:
        selected_context = [
            {
                "source_type": hit.source_type,
                "source_id": str(hit.source_id) if hit.source_id else None,
                "title": hit.title,
                "content": hit.content,
                "score": hit.rerank_score if hit.rerank_score is not None else hit.retrieval_score,
                "metadata": hit.metadata,
            }
            for hit in retrieval.selected_hits
        ]
        system_prompt = (
            "You are the CoRA Mail decision agent for Korean business-mail operators. Produce a concise Korean operational "
            "summary that tells the assigned worker what happened, what must be done next, and any deadline or business "
            "reference. Prioritize the current email over quoted history. Mention a useful attachment as 문서유형(파일명). "
            "Use only the supplied email, verified MailFacts, and retrieved context. Never invent customers, identifiers, "
            "dates, quantities, products, vessels, projects, or assignees. Every decisive statement must be supported. "
            "Use one allowed primary_type for business classification only. Do not put urgency or importance inside "
            "classification. Judge Urgency and Importance as independent high/normal axes. Urgency means how quickly "
            "the mail must be handled because of explicit time limits, imminent deadlines, current incidents, or "
            "rapidly increasing operational loss. Importance means the size of business, customer, monetary, "
            "contractual, safety, or operational impact. Do not infer importance merely because an email is urgent. "
            "Do not infer urgency merely because an email is important. Do not make importance high only because "
            "the primary_type is claim, and do not make urgency high only because the word 긴급 appears. "
            "Use facts.urgency_signals and facts.importance_signals as the primary evidence for those axes. "
            "Leave attention_quadrant as normal; the application overwrites it deterministically from urgency and importance. "
            "Mark review_required when evidence conflicts, important information is missing, "
            "classification confidence is below 0.78, or any claim is unsupported. "
            "For Korean schedule context, do not write awkward phrases like '드라이독을 예정하고'; write natural "
            "phrases like '드라이독 예정이어서' or '드라이독 예정이고'."
        )
        user_prompt = json.dumps(
            {
                "email": {
                    "sender_name": mail.get("sender_name"),
                    "sender_address": mail.get("sender_address"),
                    "subject": mail.get("subject"),
                    "body_text": current_message_body(mail),
                },
                "facts": facts.model_dump(mode="json"),
                "retrieved_context": selected_context,
                "allowed_primary_types": sorted(ALLOWED_PRIMARY_TYPES),
            },
            ensure_ascii=False,
        )
        output = self.gateway.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_schema=DecisionAgentOutput,
            temperature=0.0,
        )
        output.attention_quadrant = attention_quadrant_for(output.urgency, output.importance)
        output.requested_actions = list(dict.fromkeys(output.requested_actions or facts.requested_actions))
        output.summary.requested_actions = list(
            dict.fromkeys(facts.requested_actions or output.summary.requested_actions)
        )
        grounded_refs = list(
            dict.fromkeys(
                facts.project_numbers + facts.po_numbers + facts.quotation_numbers
            )
        )
        output.summary.business_refs = grounded_refs
        if facts.requested_dates:
            output.summary.deadlines = list(dict.fromkeys(facts.requested_dates))
        if not output.summary.requester:
            output.summary.requester = facts.sender_person
        grounded_types = [
            value for value in facts.request_types if value in ALLOWED_PRIMARY_TYPES
        ]
        if len(grounded_types) == 1 and output.classification.primary_type != grounded_types[0]:
            grounded_type = grounded_types[0]
            output.classification.primary_type = grounded_type
            output.classification.business_area = _business_area_for(grounded_type)
            output.classification.candidate_scores[grounded_type] = max(
                output.classification.confidence,
                output.classification.candidate_scores.get(grounded_type, 0),
            )
            output.review_required = True
            output.review_reasons.append("classification_aligned_to_grounded_mail_facts")
            output.generation_mode = "llm_validated"
        if (
            facts.requested_actions
            and output.summary.one_line_summary.strip().casefold()
            == str(mail.get("subject") or "").strip().casefold()
        ):
            context = facts.customer_name or facts.sender_person or ""
            refs = facts.project_numbers + facts.po_numbers + facts.quotation_numbers
            prefix = " ".join(value for value in (context, refs[0] if refs else "") if value)
            output.summary.one_line_summary = " ".join(
                value for value in (prefix, facts.requested_actions[0]) if value
            )
            output.generation_mode = "llm_validated"
        if _summary_misses_action(output.summary.one_line_summary, facts.requested_actions):
            context = facts.customer_name or facts.sender_person or ""
            refs = facts.project_numbers + facts.po_numbers + facts.quotation_numbers
            prefix = " ".join(value for value in (context, refs[0] if refs else "") if value)
            output.summary.one_line_summary = " ".join(
                value for value in (prefix, facts.requested_actions[0]) if value
            )
            output.generation_mode = "llm_validated"
        polished_summary = polish_korean_summary_text(output.summary.one_line_summary)
        if polished_summary != output.summary.one_line_summary:
            output.summary.one_line_summary = polished_summary
            if output.generation_mode == "llm":
                output.generation_mode = "llm_validated"
        if output.classification.confidence < 0.78:
            output.review_required = True
            output.review_reasons.append("classification_confidence_below_threshold")
        if facts.contradictions:
            output.review_required = True
            output.review_reasons.append("fact_contradictions_present")
        if output.unsupported_claims:
            output.review_required = True
            output.review_reasons.append("unsupported_claims_present")
        output.review_reasons = list(dict.fromkeys(output.review_reasons))
        output.urgency = _ground_urgency(output.urgency, facts)
        output.importance = _ground_importance(output.importance, facts)
        output.attention_quadrant = attention_quadrant_for(output.urgency, output.importance)
        return output

    @staticmethod
    def fallback_decision(*, mail: dict, facts: MailFacts, reason: str) -> DecisionAgentOutput:
        grounded_types = [value for value in facts.request_types if value in ALLOWED_PRIMARY_TYPES]
        primary_type = grounded_types[0] if grounded_types else "general_inquiry"
        business_refs = list(dict.fromkeys(facts.project_numbers + facts.po_numbers + facts.quotation_numbers))
        requested_actions = facts.requested_actions or [_fallback_action(primary_type)]
        subject = str(mail.get("subject") or "").strip()
        summary_parts = [
            facts.customer_name or facts.sender_person or "",
            business_refs[0] if business_refs else "",
            requested_actions[0] if requested_actions else subject,
        ]
        one_line_summary = " ".join(part for part in summary_parts if part).strip() or subject or "근거 기반 제한 판단"
        one_line_summary = polish_korean_summary_text(one_line_summary)
        missing_information = list(dict.fromkeys([*facts.missing_information, "llm_decision_unavailable"]))
        urgency = _fallback_urgency(facts)
        importance = _fallback_importance(facts)
        return DecisionAgentOutput(
            summary=MailSummary(
                one_line_summary=one_line_summary,
                requester=facts.sender_person,
                requested_actions=requested_actions,
                key_facts=_fallback_key_facts(facts),
                deadlines=list(dict.fromkeys(facts.requested_dates)),
                business_refs=business_refs,
                risks=["모델 호출 실패로 원문/첨부의 명시적 근거만 사용했습니다."],
                missing_information=missing_information,
                confidence=0.45,
            ),
            classification=MailClassification(
                business_area=_business_area_for(primary_type),
                primary_type=primary_type,
                candidate_scores={primary_type: 0.45},
                confidence=0.45,
                review_required=True,
            ),
            urgency=urgency,
            importance=importance,
            attention_quadrant=attention_quadrant_for(urgency, importance),
            requested_actions=requested_actions,
            review_required=True,
            review_reasons=list(dict.fromkeys([reason, "llm_decision_unavailable"])),
            generation_mode="fallback_llm_unavailable",
        )


def _business_area_for(primary_type: str) -> str:
    if primary_type in {"quotation_request", "quotation_followup"}:
        return "sales"
    if primary_type in {
        "purchase_order", "order_change", "order_cancellation", "delivery_confirmation", "delivery_delay",
    }:
        return "order"
    if primary_type in {"technical_inquiry", "drawing_review", "specification_review", "compatibility_check"}:
        return "technical"
    if primary_type in {"service_request", "repair_request", "claim", "urgent_failure"}:
        return "service"
    if primary_type in {"invoice", "payment_inquiry"}:
        return "finance"
    return "general"


def _summary_misses_action(summary: str, requested_actions: list[str]) -> bool:
    if not requested_actions:
        return False
    normalized_summary = summary.strip().casefold()
    action = requested_actions[0].strip()
    if not normalized_summary or not action:
        return False
    if any(token in normalized_summary for token in ("확인", "회신", "검토", "처리", "발주 가능")):
        return False
    return "송부" in normalized_summary and any(
        token in action for token in ("확인", "회신", "검토", "처리", "발주 가능")
    )


def _fallback_action(primary_type: str) -> str:
    actions = {
        "quotation_request": "견적 요청 내용 확인 후 회신",
        "quotation_followup": "견적서 내용 확인 후 후속 처리",
        "purchase_order": "발주서 내용 확인 후 처리",
        "delivery_confirmation": "납품 가능 일정 확인 후 회신",
        "payment_inquiry": "입금 또는 결제 관련 내용 확인",
        "technical_inquiry": "기술 문의 내용 확인 후 회신",
        "repair_request": "수리 요청 내용 확인 후 담당자 검토",
        "claim": "클레임 내용 확인 후 담당자 검토",
    }
    return actions.get(primary_type, "메일 내용 확인 후 담당자 검토")


def _fallback_key_facts(facts: MailFacts) -> list[str]:
    rows: list[str] = []
    if facts.customer_name:
        rows.append(f"Customer: {facts.customer_name}")
    if facts.vessel_names:
        rows.append(f"Vessel: {', '.join(facts.vessel_names[:3])}")
    refs = facts.project_numbers + facts.po_numbers + facts.quotation_numbers
    if refs:
        rows.append(f"Reference: {', '.join(dict.fromkeys(refs))}")
    if facts.product_names or facts.product_groups:
        rows.append(f"Product: {', '.join((facts.product_names + facts.product_groups)[:3])}")
    return rows


def _fallback_urgency(facts: MailFacts) -> MailUrgency:
    high_signals = [signal for signal in facts.urgency_signals if _supports_high_urgency(signal)]
    level = "high" if high_signals else "normal"
    reasons = high_signals or facts.urgency_signals[:3]
    confidence = 0.72 if level == "high" else 0.62
    return MailUrgency(level=level, confidence=confidence, reasons=list(dict.fromkeys(reasons)))


def _fallback_importance(facts: MailFacts) -> MailImportance:
    high_signals = [signal for signal in facts.importance_signals if _supports_high_importance(signal)]
    level = "high" if high_signals else "normal"
    reasons = high_signals or facts.importance_signals[:3]
    confidence = 0.72 if level == "high" else 0.62
    return MailImportance(level=level, confidence=confidence, reasons=list(dict.fromkeys(reasons)))


def _ground_urgency(urgency: MailUrgency, facts: MailFacts) -> MailUrgency:
    grounded_reasons = [signal for signal in facts.urgency_signals if _supports_high_urgency(signal)]
    if urgency.level == "high" and not grounded_reasons:
        return MailUrgency(level="normal", confidence=min(urgency.confidence, 0.64), reasons=list(dict.fromkeys(facts.urgency_signals[:3])))
    reasons = grounded_reasons if urgency.level == "high" else (urgency.reasons or facts.urgency_signals)
    return MailUrgency(level=urgency.level, confidence=urgency.confidence, reasons=list(dict.fromkeys(reasons)))


def _ground_importance(importance: MailImportance, facts: MailFacts) -> MailImportance:
    grounded_reasons = [signal for signal in facts.importance_signals if _supports_high_importance(signal)]
    if importance.level == "high" and not grounded_reasons:
        return MailImportance(level="normal", confidence=min(importance.confidence, 0.64), reasons=list(dict.fromkeys(facts.importance_signals[:3])))
    reasons = grounded_reasons if importance.level == "high" else (importance.reasons or facts.importance_signals)
    return MailImportance(level=importance.level, confidence=importance.confidence, reasons=list(dict.fromkeys(reasons)))


def _supports_high_urgency(signal: str) -> bool:
    normalized = signal.casefold()
    return any(
        re.search(pattern, normalized, flags=re.IGNORECASE)
        for pattern in (
            r"(?:오늘|금일)(?:\s*\d{1,2}\s*시(?:\s*\d{1,2}\s*분)?\s*)?(?:이전|전|까지|중)",
            r"(?:오늘|금일).{0,30}(?:대응|처리|조치|회신|지원|확인|교체|송부|보내)",
            r"내일(?:\s*\d{1,2}\s*시(?:\s*\d{1,2}\s*분)?\s*)?(?:이전|전|까지|중)",
            r"내일.{0,30}(?:대응|처리|조치|회신|지원|확인|교체|송부|보내)",
            r"(?:즉시|asap)(?:\s*(?:대응|처리|조치|회신|지원|확인|교체))?",
            r"due\s+today",
            r"by\s+\d{1,2}:\d{2}",
            r"within\s+\d+\s*(?:hour|hours|hr|hrs)",
            r"(?:출항|sailing|departure)\s*전",
            r"납기\s*임박",
            r"(?:현재|지금).{0,30}(?:장애|failure|중단|stopped)",
            r"(?:운항|생산|서비스|operation|service).{0,20}(?:중단|stopped)",
        )
    )


def _supports_high_importance(signal: str) -> bool:
    normalized = signal.casefold()
    return any(
        re.search(pattern, normalized, flags=re.IGNORECASE)
        for pattern in (
            r"(?:운항|생산|서비스|operation|service).{0,20}(?:중단|stopped)",
            r"(?:장애|failure).{0,30}(?:운항\s*중단|생산\s*중단|서비스\s*중단|operation\s+stopped)",
            r"(?:금전\s*)?손실|loss",
            r"안전|safety",
            r"(?:계약\s*위반|contract\s*breach|breach\s+of\s+contract)",
            r"penalty|위약",
            r"발주\s*규모.{0,20}(?:큰|대형|높|상당)",
            r"(?:대형|신규)\s*선박\s*프로젝트",
            r"선박\s*프로젝트.{0,40}(?:장비\s*공급|기술\s*사양|발주\s*규모)",
            r"장비\s*공급.{0,30}(?:프로젝트|계약|발주)",
        )
    )

from __future__ import annotations

import json
import re
from typing import Any

from app.llm.gateway import LocalLLMGateway
from app.mail_content import NON_CUSTOMER_SUBJECT_LABELS, bracketed_customer, current_message_body, subject_business_refs
from app.schemas.mail_decision import EvidenceRef, MailFacts


NORMALIZED_REQUEST_TYPES = {
    "quotation_request", "quotation_followup", "purchase_order", "order_change", "order_cancellation",
    "delivery_confirmation", "delivery_delay", "technical_inquiry", "drawing_review",
    "specification_review", "compatibility_check", "service_request", "repair_request", "claim",
    "urgent_failure", "invoice", "payment_inquiry", "certificate_request", "general_inquiry", "spam",
}


class FactExtractionAgent:
    def __init__(self, gateway: LocalLLMGateway):
        self.gateway = gateway

    def extract(self, *, mail: dict[str, Any], attachment_results: list[dict[str, Any]]) -> MailFacts:
        payload = {
            "mail": {
                "sender_name": mail.get("sender_name"),
                "sender_address": mail.get("sender_address"),
                "subject": mail.get("subject"),
                "body_text": current_message_body(mail),
                "sent_at": str(mail.get("sent_at") or ""),
            },
            "attachments": [
                {
                    "attachment_id": item.get("attachment_id"),
                    "filename": item.get("filename"),
                    "document_type": item.get("document_type"),
                    "extracted_text": item.get("extracted_text"),
                    "fields": item.get("fields"),
                    "warnings": item.get("warnings"),
                }
                for item in attachment_results
            ],
        }
        facts = self.gateway.generate_structured(
            system_prompt=(
                "You extract auditable business-mail facts. Use only the supplied mail and attachment content. "
                "Never invent customers, products, identifiers, quantities, dates, projects, vessels, or actions. "
                "Collect urgency_signals only for explicit time pressure, imminent deadlines, or current operational interruption. "
                "Collect importance_signals only for explicit business, customer, monetary, contractual, safety, or operational impact. "
                "Do not decide final urgency or importance; only extract supporting source phrases. "
                "Do not use document type or thread labels such as RE, FW, 견적서, 견적의뢰서, RFQ, PO, or invoice "
                "as customer names. Record uncertainty in missing_information and contradictions."
            ),
            user_prompt=(
                "Extract the unified MailFacts object from this input. Keep request_types concise and normalized. "
                "Evidence text must quote or closely preserve the supporting source text.\n\n"
                + json.dumps(payload, ensure_ascii=False, default=str)
            ),
            output_schema=MailFacts,
        )
        sender_address = str(mail.get("sender_address") or "")
        if not facts.sender_domain and "@" in sender_address:
            facts.sender_domain = sender_address.rsplit("@", 1)[-1].lower()
        if not facts.sender_person:
            facts.sender_person = mail.get("sender_name")
        self._merge_labeled_body_facts(facts, mail)
        self._merge_grounded_operational_signals(facts, mail)
        self._merge_attachment_facts(facts, attachment_results)
        self._sanitize_customer_facts(facts)
        return facts

    def extract_grounded(
        self,
        *,
        mail: dict[str, Any],
        attachment_results: list[dict[str, Any]],
        reason: str,
    ) -> MailFacts:
        """Build conservative facts from parsed mail/attachments when the LLM is unavailable."""
        sender_address = str(mail.get("sender_address") or "")
        facts = MailFacts(
            sender_person=mail.get("sender_name"),
            sender_domain=sender_address.rsplit("@", 1)[-1].lower() if "@" in sender_address else None,
            missing_information=["llm_fact_extraction_unavailable", reason],
        )
        self._merge_labeled_body_facts(facts, mail)
        self._merge_grounded_operational_signals(facts, mail)
        self._merge_attachment_facts(facts, attachment_results)
        self._sanitize_customer_facts(facts)
        if not facts.request_types:
            _append_unique(facts.request_types, "general_inquiry")
            facts.missing_information.append("business_type_requires_review")
        return facts

    @staticmethod
    def _merge_labeled_body_facts(facts: MailFacts, mail: dict[str, Any]) -> None:
        body = current_message_body(mail)
        if not body.strip():
            return
        labels = {
            "customer": _extract_labeled_value(body, "Customer"),
            "project": _extract_labeled_value(body, "Project"),
            "vessel": _extract_labeled_value(body, "Vessel"),
            "product_group": _extract_labeled_value(body, "Product group"),
            "request_type": _extract_labeled_value(body, "Request type"),
            "reference": _extract_labeled_value(body, "Reference"),
        }
        if labels["customer"] and not facts.customer_name:
            facts.customer_name = labels["customer"]
        _append_unique(facts.customer_candidates, labels["customer"])
        _append_unique(facts.project_numbers, labels["project"])
        _append_unique(facts.vessel_names, labels["vessel"])
        _append_unique(facts.product_groups, labels["product_group"])
        _append_unique(facts.request_types, labels["request_type"])
        _append_unique(facts.quotation_numbers, labels["reference"])
        _append_unique(facts.requested_actions, _infer_action(labels["request_type"]))
        for label, value in labels.items():
            if value:
                facts.evidence.append(
                    EvidenceRef(source_type="email_body", text=f"{label.replace('_', ' ').title()}: {value}")
                )

    @staticmethod
    def _merge_grounded_operational_signals(facts: MailFacts, mail: dict[str, Any]) -> None:
        subject = str(mail.get("subject") or "")
        body = current_message_body(mail)
        current_text = f"{subject}\n{body}"
        normalized = current_text.casefold()

        customer = bracketed_customer(subject)
        if customer and not facts.customer_name:
            facts.customer_name = customer
        _append_unique(facts.customer_candidates, customer)
        sender_company = _sender_company_from_body(body, facts.sender_person)
        if sender_company and not facts.customer_name:
            facts.customer_name = sender_company
        _append_unique(facts.customer_candidates, sender_company)
        for business_ref in subject_business_refs(subject):
            if business_ref.upper().startswith("PO"):
                _append_unique(facts.po_numbers, business_ref)
            else:
                _append_unique(facts.quotation_numbers, business_ref)

        quotation_context = "견적서" in normalized or "quotation" in normalized or "quote" in normalized
        if not quotation_context and any(signal in normalized for signal in ("납기", "납품", "delivery")) and any(
            signal in normalized for signal in ("확인", "가능", "confirm")
        ):
            _append_unique(facts.request_types, "delivery_confirmation")
            action = "납품 가능 일정 확인 후 회신"
            match = re.search(r"(\d+\s*일\s*이내)", current_text)
            if match:
                action = f"{match.group(1).replace(' ', '')} 납품 가능 여부 확인 후 회신"
                _append_unique(facts.requested_dates, match.group(1).replace(" ", ""))
            _append_unique(facts.requested_actions, action)
            facts.evidence.append(
                EvidenceRef(source_type="email_body", text=action)
            )
        if "견적서" in normalized and any(signal in normalized for signal in ("첨부", "송부")) and (
            "회신" in normalized or "확인" in normalized
        ):
            _append_unique(facts.request_types, "quotation_followup")
            action = "견적서 내용 확인 후 후속 처리"
            if "발주 가능 여부" in current_text and "수정 요청" in current_text:
                action = "견적서 유효기간·납기·합계금액 확인 후 발주 가능 여부 또는 수정 요청 사항 회신"
            _append_unique(facts.requested_actions, action)
            date_match = re.search(r"(20\d{2}[-./]\d{1,2}[-./]\d{1,2})\s*까지", current_text)
            if date_match:
                _append_unique(facts.requested_dates, date_match.group(1).replace(".", "-").replace("/", "-"))
            facts.evidence.append(EvidenceRef(source_type="email_body", text=action))
        urgency_patterns = (
            r"(?:금일|오늘)\s*(?:\d{1,2}\s*시(?:\s*\d{1,2}\s*분)?\s*)?(?:이전|전|까지|중)",
            r"(?:내일|출항\s*전|납기\s*임박|due\s+today|by\s+\d{1,2}:\d{2})",
            r"(?:asap|즉시)\s*(?:대응|처리|조치|회신|지원|확인|교체)",
        )
        for pattern in urgency_patterns:
            for signal in _matching_source_phrases(current_text, pattern):
                _append_unique(facts.urgency_signals, signal)
        current_interruption_patterns = (
            r"(?:현재|지금|운항\s*중|생산\s*중|사용\s*중).{0,30}(?:장애|failure|중단|stopped)",
            r"(?:장애|failure).{0,30}(?:발생|지원\s*요청|복구|교체|운항\s*중단)",
            r"(?:operation|service)\s+is\s+stopped",
            r"(?:운항|생산|서비스)\s*중단",
        )
        for pattern in current_interruption_patterns:
            for signal in _matching_source_phrases(current_text, pattern):
                if not _looks_resolved_or_historical(signal):
                    _append_unique(facts.urgency_signals, signal)
                    _append_unique(facts.importance_signals, signal)
        importance_patterns = (
            r"(?:안전|safety|계약\s*위반|contract breach|penalty|위약|금전\s*손실|손실)",
            r"(?:예상\s*)?발주\s*규모.{0,20}(?:큰|대형|높|상당)",
            r"(?:신규\s*)?선박\s*프로젝트.{0,40}(?:장비\s*공급|기술\s*사양|발주\s*규모)",
            r"(?:주요 고객|key customer|major customer).{0,40}(?:계약|발주|프로젝트|장애|중단|손실)",
        )
        for pattern in importance_patterns:
            for signal in _matching_source_phrases(current_text, pattern):
                _append_unique(facts.importance_signals, signal)
        facts.request_types = [
            request_type
            for request_type in dict.fromkeys(facts.request_types)
            if request_type in NORMALIZED_REQUEST_TYPES
        ]

    @staticmethod
    def _merge_attachment_facts(facts: MailFacts, attachment_results: list[dict[str, Any]]) -> None:
        for item in attachment_results:
            fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
            document_type = str(item.get("document_type") or "")
            filename = str(item.get("filename") or "attachment")
            if document_type in {"quote", "quotation"}:
                _append_unique(facts.request_types, "quotation_followup")
            elif document_type in {"rfq", "quotation_request", "request_for_quote"}:
                _append_unique(facts.request_types, "quotation_request")
            elif document_type == "payment_request":
                _append_unique(facts.request_types, "payment_inquiry")

            for label, value in fields.items():
                text = _field_text(value)
                if not text:
                    continue
                normalized_label = label.casefold()
                if label in {"Our Ref No", "Your Ref No", "Reference No."} or "ref" in normalized_label:
                    if text.upper().startswith("PO"):
                        _append_unique(facts.po_numbers, text)
                    else:
                        _append_unique(facts.quotation_numbers, text)
                elif label in {"Vessel", "VESSEL"} or "vessel" in normalized_label:
                    _append_unique(facts.vessel_names, text)
                elif label in {"Description", "Product", "Item"} or "description" in normalized_label:
                    _append_unique(facts.product_names, text)
                elif label in {"Total Price", "합계금액", "합계(VAT포함)"}:
                    facts.evidence.append(
                        EvidenceRef(source_type="attachment", text=f"{filename} {label}: {text}")
                    )
                    continue
                else:
                    continue
                facts.evidence.append(
                    EvidenceRef(source_type="attachment", text=f"{filename} {label}: {text}")
                )
        facts.request_types = [
            request_type
            for request_type in dict.fromkeys(facts.request_types)
            if request_type in NORMALIZED_REQUEST_TYPES
        ]

    @staticmethod
    def _sanitize_customer_facts(facts: MailFacts) -> None:
        original_name = facts.customer_name
        facts.customer_name = _normalize_customer_candidate(facts.customer_name)
        facts.customer_candidates = [
            value
            for value in dict.fromkeys(_normalize_customer_candidate(value) for value in facts.customer_candidates)
            if value and not _is_non_customer_label(value)
        ]
        if _is_non_customer_label(facts.customer_name):
            facts.customer_name = facts.customer_candidates[0] if facts.customer_candidates else None
        if not facts.customer_name and facts.customer_candidates:
            facts.customer_name = facts.customer_candidates[0]
        if original_name and original_name != facts.customer_name:
            _append_unique(facts.missing_information, "customer_name_rejected_non_customer_label")
        if not facts.customer_name and not facts.customer_candidates:
            _append_unique(facts.missing_information, "customer_requires_review")


def _extract_labeled_value(text: str, label: str) -> str | None:
    pattern = rf"(?im)^\s*{re.escape(label)}\s*:\s*(?P<value>.+?)\s*$"
    match = re.search(pattern, text)
    if not match:
        return None
    value = match.group("value").strip()
    return value or None


def _append_unique(values: list[str], value: str | None) -> None:
    if value and value not in values:
        values.append(value)


def _matching_source_phrases(text: str, pattern: str) -> list[str]:
    phrases: list[str] = []
    for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.DOTALL):
        start = max(0, match.start() - 20)
        end = min(len(text), match.end() + 20)
        phrase = re.sub(r"\s+", " ", text[start:end]).strip(" .,\n\t")
        if phrase:
            phrases.append(phrase[:120])
    return phrases


def _looks_resolved_or_historical(text: str) -> bool:
    normalized = text.casefold()
    return any(token in normalized for token in ("지난", "과거", "이미 해결", "해결되었습니다", "resolved", "closed"))


def _field_text(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, list):
        return ", ".join(_field_text(item) for item in value if _field_text(item))[:300]
    if isinstance(value, dict):
        return " / ".join(
            f"{key} {_field_text(item)}" for key, item in value.items() if _field_text(item)
        )[:300]
    return str(value).strip()[:300]


def _is_non_customer_label(value: str | None) -> bool:
    if not value:
        return False
    normalized = re.sub(r"\s+", " ", value).strip().casefold()
    return normalized in NON_CUSTOMER_SUBJECT_LABELS


def _normalize_customer_candidate(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"\s+", " ", value).strip(" .\t")
    normalized = re.sub(r"^(?:안녕하세요|안녕하십니까|안녕하세요\.|안녕하십니까\.)\s*", "", normalized).strip(" .\t")
    normalized = re.sub(r"^(?:주식회사|\(주\))\s*", "", normalized).strip(" .\t")
    if not normalized or _is_non_customer_label(normalized):
        return None
    return normalized


def _sender_company_from_body(body: str, sender_person: str | None) -> str | None:
    person = str(sender_person or "").strip()
    if not person:
        return None
    pattern = rf"(?m)^[ \t]*(?P<company>[가-힣A-Za-z0-9&().\- ]{{2,40}}?)[ \t]+{re.escape(person)}(?:입니다|드림|올림)?[.\t ]*$"
    match = re.search(pattern, body)
    if not match:
        return None
    company = _normalize_customer_candidate(match.group("company"))
    if not company:
        return None
    return company


def _infer_action(request_type: str | None) -> str | None:
    if not request_type:
        return None
    normalized = request_type.strip().lower()
    action_by_type = {
        "quotation_request": "prepare quotation",
        "quotation_followup": "follow up quotation",
        "purchase_order": "process purchase order",
        "order_change": "review order change",
        "technical_inquiry": "answer technical inquiry",
        "repair_request": "coordinate repair request",
        "claim": "review claim",
        "certificate_request": "prepare certificate",
    }
    return action_by_type.get(normalized, normalized.replace("_", " "))

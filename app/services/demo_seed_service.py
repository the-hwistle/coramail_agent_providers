from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid5

from app.repositories.demo_mail_repository import DemoMailRepository
from app.schemas.demo_mail import DemoAttachment, DemoMessage


DEMO_SEED_NAMESPACE = UUID("11111111-2222-3333-4444-555555555555")
CATEGORY_NAMESPACE = UUID("7f3b1189-41f7-5aac-87e4-bfc8de62cf81")
FOUNDATION_SEED_FILENAME = "mail_decision_foundation.seed.json"
DEMO_BULK_VOLUME_COUNTS = {
    "2026-08-12": 158,
    "2026-08-11": 205,
    "2026-08-10": 183,
    "2026-08-09": 150,
    "2026-08-08": 194,
    "2026-08-07": 141,
    "2026-08-06": 167,
}

DEFAULT_CATEGORIES = {
    "order": {"name": "발주", "sort_order": 10},
    "inquiry": {"name": "문의", "sort_order": 20},
    "service": {"name": "서비스", "sort_order": 30},
    "technical": {"name": "기술", "sort_order": 40},
    "general": {"name": "기타", "sort_order": 50},
    "unclassified": {"name": "미분류", "sort_order": 60},
}

BUSINESS_TYPE_CATEGORIES = {
    "purchase_order": "order",
    "order_change": "order",
    "order_cancellation": "order",
    "delivery_confirmation": "order",
    "delivery_delay": "order",
    "quotation_request": "inquiry",
    "quotation_followup": "inquiry",
    "general_inquiry": "inquiry",
    "certificate_request": "inquiry",
    "service_request": "service",
    "repair_request": "service",
    "claim": "service",
    "urgent_failure": "service",
    "technical_inquiry": "technical",
    "drawing_review": "technical",
    "specification_review": "technical",
    "compatibility_check": "technical",
    "invoice": "general",
    "payment_inquiry": "general",
    "spam": "general",
}

DEMO_MAIL_CATEGORY_CODES = {
    "purchase_delivery_followup": "order",
    "purchase_order": "order",
    "delivery_confirmation": "order",
    "delivery_delay": "order",
    "quotation_received": "inquiry",
    "quotation_request": "inquiry",
    "general_inquiry": "inquiry",
    "certificate_request": "inquiry",
    "service_request": "service",
    "repair_request": "service",
    "claim": "service",
    "urgent_failure": "service",
    "specification_check": "technical",
    "specification_recheck": "technical",
    "technical_inquiry": "technical",
    "drawing_review": "technical",
    "compatibility_check": "technical",
    "invoice": "general",
    "payment_inquiry": "general",
    "unclassified": "unclassified",
}

DEMO_CATEGORY_LABELS = {
    "order": "발주",
    "inquiry": "문의",
    "service": "서비스",
    "technical": "기술",
    "general": "기타",
    "unclassified": "미분류",
}

DEMO_ASSIGNEE_AREA_USER_IDS = {
    "sales": "10000000-0000-0000-0000-000000000001",
    "overseas_sales": "10000000-0000-0000-0000-000000000002",
    "technical": "10000000-0000-0000-0000-000000000003",
    "technical_sales": "10000000-0000-0000-0000-000000000004",
    "service": "10000000-0000-0000-0000-000000000005",
    "urgent_service": "10000000-0000-0000-0000-000000000006",
    "logistics": "10000000-0000-0000-0000-000000000007",
    "admin": "10000000-0000-0000-0000-000000000008",
}

FOUNDATION_USER_PROFILES = {
    "10000000-0000-0000-0000-000000000001": {"department": "국내영업1팀", "position": "대리"},
    "10000000-0000-0000-0000-000000000002": {"department": "해외영업팀", "position": "과장"},
    "10000000-0000-0000-0000-000000000003": {"department": "기술지원팀", "position": "과장"},
    "10000000-0000-0000-0000-000000000004": {"department": "기술영업팀", "position": "차장"},
    "10000000-0000-0000-0000-000000000005": {"department": "서비스운영팀", "position": "대리"},
    "10000000-0000-0000-0000-000000000006": {"department": "긴급대응팀", "position": "팀장"},
    "10000000-0000-0000-0000-000000000007": {"department": "구매물류팀", "position": "주임"},
    "10000000-0000-0000-0000-000000000008": {"department": "업무관리팀", "position": "팀장"},
}

DEMO_BULK_SCENARIOS = (
    {
        "mail_category": "quotation_request",
        "assignee_area": "sales",
        "priority": "normal",
        "company": "네오팩토리솔루션",
        "sender": "김하린",
        "email": "harin@neofactory.example",
        "subject": "[견적 요청] 자동화 제어 부품 견적 확인",
        "action": "자동화 제어 부품 견적과 납기 가능일 확인 요청.",
        "ref_prefix": "RFQ-DEMO",
        "equipment": ["Control Relay", "Signal Converter"],
    },
    {
        "mail_category": "purchase_order",
        "assignee_area": "sales",
        "priority": "normal",
        "company": "라온오토메이션",
        "sender": "한지우",
        "email": "jiwoo@raon-auto.example",
        "subject": "[발주서 접수] 현장 예비품 발주 요청",
        "action": "발주서 기준 재고와 출고 가능 일정 확인 요청.",
        "ref_prefix": "PO-DEMO",
        "equipment": ["Spare Parts Kit"],
    },
    {
        "mail_category": "delivery_confirmation",
        "assignee_area": "logistics",
        "priority": "normal",
        "company": "새롬테크",
        "sender": "이도현",
        "email": "dohyun@saerom-tech.example",
        "subject": "[납기 확인] 출고 예정일 및 부분 납품 문의",
        "action": "출고 예정일과 부분 납품 가능 여부 확인 요청.",
        "ref_prefix": "DL-DEMO",
        "equipment": ["Sensor Module"],
    },
    {
        "mail_category": "service_request",
        "assignee_area": "service",
        "priority": "normal",
        "company": "해밀엔지니어링",
        "sender": "오민재",
        "email": "minjae@haemil-eng.example",
        "subject": "[서비스 요청] 현장 장비 점검 일정 협의",
        "action": "현장 장비 점검 가능 일정과 방문 전 준비사항 회신 요청.",
        "ref_prefix": "SR-DEMO",
        "equipment": ["Field Control Unit"],
    },
    {
        "mail_category": "technical_inquiry",
        "assignee_area": "technical",
        "priority": "normal",
        "company": "온유시스템",
        "sender": "정서윤",
        "email": "seoyun@onue-system.example",
        "subject": "[기술 문의] 통신 설정값 확인 요청",
        "action": "통신 설정값과 현장 적용 가능 여부 확인 요청.",
        "ref_prefix": "TECH-DEMO",
        "equipment": ["Industrial Gateway"],
    },
    {
        "mail_category": "drawing_review",
        "assignee_area": "technical",
        "priority": "normal",
        "company": "유니온계측",
        "sender": "배수아",
        "email": "sua@union-measure.example",
        "subject": "[도면 검토] 배선도 승인 요청",
        "action": "배선도 검토 후 승인 또는 수정 의견 회신 요청.",
        "ref_prefix": "DWG-DEMO",
        "equipment": ["Terminal Block"],
    },
    {
        "mail_category": "urgent_failure",
        "assignee_area": "urgent_service",
        "priority": "high",
        "urgency": "high",
        "importance": "high",
        "attention_quadrant": "urgent_important",
        "company": "이음산업",
        "sender": "유나연",
        "email": "nayeon@ieum-industry.example",
        "subject": "[긴급 장애] 현장 네트워크 장비 통신 불안정",
        "action": "현장 네트워크 장비 통신 불안정으로 긴급 점검 가능 여부 문의.",
        "ref_prefix": "URG-DEMO",
        "equipment": ["Network Switch"],
    },
    {
        "mail_category": "payment_inquiry",
        "assignee_area": "admin",
        "priority": "normal",
        "company": "아크로테크",
        "sender": "서강준",
        "email": "kangjun@acro-tech.example",
        "subject": "[결제 문의] 세금계산서 발행 정보 확인",
        "action": "세금계산서 발행 정보와 입금 예정일 확인 요청.",
        "ref_prefix": "PAY-DEMO",
        "equipment": [],
    },
)

DEMO_BULK_SCENARIO_SEQUENCE = (
    0,
    1,
    2,
    0,
    1,
    3,
    4,
    0,
    2,
    6,
    7,
    0,
    1,
    5,
    0,
    2,
    3,
    4,
    7,
    0,
)


class DemoSeedValidationError(ValueError):
    pass


class DemoSeedService:
    """Builds deterministic PostgreSQL seed rows from demo fixtures.

    The service does not write to PostgreSQL yet. It prepares the table-shaped
    payload that a later database writer can insert in one transaction.
    """

    def __init__(self, repository: DemoMailRepository):
        self.repository = repository

    def build_seed_bundle(self, *, created_at: str | None = None) -> dict[str, list[dict[str, Any]]]:
        timestamp = created_at or datetime.now(timezone.utc).isoformat()
        fixtures = self.repository.fixtures()
        accounts_by_id: dict[str, dict[str, Any]] = {}
        email_messages: list[dict[str, Any]] = []
        email_recipients: list[dict[str, Any]] = []
        email_attachments: list[dict[str, Any]] = []
        email_category_assignments: list[dict[str, Any]] = []
        email_analysis_results: list[dict[str, Any]] = []
        mail_decision_runs: list[dict[str, Any]] = []
        routing_assignments: list[dict[str, Any]] = []
        work_items: list[dict[str, Any]] = []
        processing_jobs: list[dict[str, Any]] = []
        foundation = self._foundation_seed()
        demo_account_id = ""

        for fixture in fixtures:
            account = fixture.email_account
            if not demo_account_id and account.provider == "synthetic":
                demo_account_id = account.id
            accounts_by_id[account.id] = {
                "id": account.id,
                "provider": account.provider,
                "email_address": account.email_address,
                "display_name": account.display_name,
                "status": account.status,
                "credentials_reference": None,
                "sync_cursor": None,
                "last_synced_at": None,
                "last_error": None,
                "created_at": timestamp,
                "updated_at": timestamp,
            }
            for message in fixture.messages:
                email_messages.append(self._email_message_row(message, account.id, timestamp))
                email_recipients.extend(self._email_recipient_rows(message, timestamp))
                email_attachments.extend(self._email_attachment_rows(message, timestamp))
                email_category_assignments.append(self._email_category_assignment_row(message, timestamp))
                email_analysis_results.extend(self._email_analysis_result_rows(message, timestamp))
                mail_decision_runs.append(self._mail_decision_run_row(message, timestamp))
                routing_assignment = self._routing_assignment_row(message, timestamp)
                if routing_assignment:
                    routing_assignments.append(routing_assignment)
                    work_items.append(self._work_item_row(message, routing_assignment, timestamp))
                processing_jobs.append(self._processing_job_row(message, timestamp))

        for message in self._bulk_volume_messages():
            if not demo_account_id:
                break
            email_messages.append(self._email_message_row(message, demo_account_id, timestamp))
            email_recipients.extend(self._email_recipient_rows(message, timestamp))
            email_category_assignments.append(self._email_category_assignment_row(message, timestamp))
            email_analysis_results.extend(self._email_analysis_result_rows(message, timestamp))
            mail_decision_runs.append(self._mail_decision_run_row(message, timestamp))
            routing_assignment = self._routing_assignment_row(message, timestamp)
            if routing_assignment:
                routing_assignments.append(routing_assignment)
                work_items.append(self._work_item_row(message, routing_assignment, timestamp))
            processing_jobs.append(self._processing_job_row(message, timestamp))

        return {
            "categories": self._category_rows(timestamp),
            "users": self._foundation_user_rows(foundation, timestamp),
            "assignee_capabilities": self._foundation_capability_rows(foundation, timestamp),
            "routing_rules": self._foundation_routing_rule_rows(foundation, timestamp),
            "email_accounts": sorted(accounts_by_id.values(), key=lambda row: row["id"]),
            "email_messages": sorted(email_messages, key=lambda row: row["sent_at"], reverse=True),
            "email_recipients": sorted(
                email_recipients,
                key=lambda row: (row["email_message_id"], row["recipient_type"], row["address"]),
            ),
            "email_attachments": sorted(email_attachments, key=lambda row: (row["email_message_id"], row["filename"])),
            "email_category_assignments": sorted(
                email_category_assignments,
                key=lambda row: row["email_message_id"],
            ),
            "email_analysis_results": sorted(
                email_analysis_results,
                key=lambda row: (row["email_message_id"], row["analysis_type"]),
            ),
            "mail_decision_runs": sorted(mail_decision_runs, key=lambda row: row["email_message_id"]),
            "routing_assignments": sorted(routing_assignments, key=lambda row: row["email_message_id"]),
            "work_items": sorted(work_items, key=lambda row: row["email_message_id"]),
            "processing_jobs": sorted(processing_jobs, key=lambda row: row["source_id"]),
        }

    def validate_seed_bundle(self, bundle: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        messages = bundle["email_messages"]
        recipients = bundle["email_recipients"]
        attachments = bundle["email_attachments"]
        jobs = bundle["processing_jobs"]
        category_assignments = bundle.get("email_category_assignments", [])
        analysis_results = bundle.get("email_analysis_results", [])
        mail_decision_runs = bundle.get("mail_decision_runs", [])
        routing_assignments = bundle.get("routing_assignments", [])
        work_items = bundle.get("work_items", [])
        users = bundle.get("users", [])
        capabilities = bundle.get("assignee_capabilities", [])
        routing_rules = bundle.get("routing_rules", [])

        message_ids = {row["id"] for row in messages}
        user_ids = {row["id"] for row in users}
        category_ids = {row["id"] for row in bundle.get("categories", [])}
        missing_recipient_parents = sorted({row["email_message_id"] for row in recipients}.difference(message_ids))
        missing_attachment_parents = sorted({row["email_message_id"] for row in attachments}.difference(message_ids))
        missing_job_parents = sorted({row["source_id"] for row in jobs}.difference(message_ids))
        missing_assignment_parents = sorted(
            {row["email_message_id"] for row in category_assignments}.difference(message_ids)
        )
        missing_analysis_parents = sorted({row["email_message_id"] for row in analysis_results}.difference(message_ids))
        missing_mail_decision_run_parents = sorted(
            {row["email_message_id"] for row in mail_decision_runs}.difference(message_ids)
        )
        missing_routing_assignment_parents = sorted(
            {row["email_message_id"] for row in routing_assignments}.difference(message_ids)
        )
        missing_routing_assignment_users = sorted(
            {row["assignee_user_id"] for row in routing_assignments if row["assignee_user_id"]}.difference(user_ids)
        )
        missing_work_item_parents = sorted({row["email_message_id"] for row in work_items}.difference(message_ids))
        routing_assignment_ids = {row["id"] for row in routing_assignments}
        missing_work_item_routing_assignments = sorted(
            {row["routing_assignment_id"] for row in work_items}.difference(routing_assignment_ids)
        )
        missing_work_item_users = sorted(
            {row["assignee_user_id"] for row in work_items if row["assignee_user_id"]}.difference(user_ids)
        )
        missing_capability_users = sorted({row["user_id"] for row in capabilities}.difference(user_ids))
        missing_rule_users = sorted({row["assignee_user_id"] for row in routing_rules}.difference(user_ids))
        missing_rule_categories = sorted({row["category_id"] for row in routing_rules}.difference(category_ids))
        missing_files = sorted(
            row["storage_uri"]
            for row in attachments
            if not (self.repository.demo_dir.parent.parent / str(row["storage_uri"])).exists()
        )
        duplicate_provider_ids = self._duplicates(
            f"{row['email_account_id']}:{row['provider_message_id']}" for row in messages
        )

        errors = {
            "missing_recipient_parents": missing_recipient_parents,
            "missing_attachment_parents": missing_attachment_parents,
            "missing_job_parents": missing_job_parents,
            "missing_assignment_parents": missing_assignment_parents,
            "missing_analysis_parents": missing_analysis_parents,
            "missing_mail_decision_run_parents": missing_mail_decision_run_parents,
            "missing_routing_assignment_parents": missing_routing_assignment_parents,
            "missing_routing_assignment_users": missing_routing_assignment_users,
            "missing_work_item_parents": missing_work_item_parents,
            "missing_work_item_routing_assignments": missing_work_item_routing_assignments,
            "missing_work_item_users": missing_work_item_users,
            "missing_capability_users": missing_capability_users,
            "missing_rule_users": missing_rule_users,
            "missing_rule_categories": missing_rule_categories,
            "missing_files": missing_files,
            "duplicate_provider_ids": duplicate_provider_ids,
        }
        failed = {key: value for key, value in errors.items() if value}
        if failed:
            raise DemoSeedValidationError(json.dumps(failed, ensure_ascii=False, indent=2))
        return {
            "email_accounts": len(bundle["email_accounts"]),
            "email_messages": len(messages),
            "email_recipients": len(recipients),
            "email_attachments": len(attachments),
            "email_category_assignments": len(category_assignments),
            "email_analysis_results": len(analysis_results),
            "mail_decision_runs": len(mail_decision_runs),
            "routing_assignments": len(routing_assignments),
            "work_items": len(work_items),
            "processing_jobs": len(jobs),
            "users": len(users),
            "assignee_capabilities": len(capabilities),
            "routing_rules": len(routing_rules),
        }

    def _foundation_seed(self) -> dict[str, Any]:
        path = self.repository.demo_dir / FOUNDATION_SEED_FILENAME
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _bulk_volume_messages() -> list[DemoMessage]:
        messages: list[DemoMessage] = []
        global_index = 0
        for day_text, count in DEMO_BULK_VOLUME_COUNTS.items():
            day = datetime.fromisoformat(f"{day_text}T00:00:00+09:00")
            for day_index in range(count):
                scenario_index = DEMO_BULK_SCENARIO_SEQUENCE[global_index % len(DEMO_BULK_SCENARIO_SEQUENCE)]
                scenario = DEMO_BULK_SCENARIOS[scenario_index]
                received_at = day + timedelta(hours=8, minutes=59) - timedelta(minutes=day_index)
                message_id = str(uuid5(DEMO_SEED_NAMESPACE, f"bulk-mail:{day_text}:{day_index:04d}"))
                recipient_id = str(uuid5(DEMO_SEED_NAMESPACE, f"bulk-recipient:{day_text}:{day_index:04d}"))
                ref = f"{scenario['ref_prefix']}-{day_text.replace('-', '')}-{day_index + 1:04d}"
                action = str(scenario["action"])
                subject = str(scenario["subject"])
                sender = str(scenario["sender"])
                company = str(scenario["company"])
                messages.append(
                    DemoMessage.model_validate(
                        {
                            "id": message_id,
                            "provider_message_id": f"demo-volume-{day_text}-{day_index:04d}",
                            "provider_thread_id": f"thread-demo-volume-{day_text}-{day_index:04d}",
                            "rfc_message_id": f"<demo-volume-{day_text}-{day_index:04d}@coramail.local>",
                            "sender_name": sender,
                            "sender_address": scenario["email"],
                            "subject": subject,
                            "subject_normalized": subject,
                            "body_text": (
                                f"안녕하세요. {company} {sender}입니다.\n\n"
                                f"{action}\n\n"
                                "확인 후 회신 부탁드립니다.\n\n"
                                f"감사합니다.\n{sender}\n{company}"
                            ),
                            "snippet": action,
                            "sent_at": received_at.isoformat(),
                            "received_at": received_at.isoformat(),
                            "has_attachment": False,
                            "attachment_count": 0,
                            "processing_status": "received",
                            "recipients": [
                                {
                                    "id": recipient_id,
                                    "recipient_type": "to",
                                    "name": "다원",
                                    "address": "demo-sales@dawonict.co.kr",
                                }
                            ],
                            "attachments": [],
                            "expected_demo_labels": {
                                "mail_category": scenario["mail_category"],
                                "document_category": "",
                                "priority": scenario["priority"],
                                "urgency": scenario.get("urgency", "normal"),
                                "importance": scenario.get("importance", "normal"),
                                "attention_quadrant": scenario.get("attention_quadrant", ""),
                                "assignee_area": scenario["assignee_area"],
                                "business_refs": [ref],
                                "vessel_names": [],
                                "equipment": scenario["equipment"],
                                "key_spec_fields": {"requested_action": action},
                                "counterparty": company,
                            },
                        }
                    )
                )
                global_index += 1
        return messages

    @staticmethod
    def _category_rows(timestamp: str) -> list[dict[str, Any]]:
        return [
            {
                "id": str(uuid5(CATEGORY_NAMESPACE, code)),
                "code": code,
                "name": payload["name"],
                "description": f"CoRA Mail default category: {payload['name']}",
                "is_active": True,
                "sort_order": payload["sort_order"],
                "created_at": timestamp,
                "updated_at": timestamp,
            }
            for code, payload in DEFAULT_CATEGORIES.items()
        ]

    @staticmethod
    def _foundation_user_rows(foundation: dict[str, Any], timestamp: str) -> list[dict[str, Any]]:
        users: list[dict[str, Any]] = []
        for user in foundation.get("users") or []:
            profile = FOUNDATION_USER_PROFILES.get(
                str(user["id"]),
                {"department": "업무관리팀", "position": "담당"},
            )
            users.append(
                {
                    "id": user["id"],
                    "email": user["email"],
                    "name": user["name"],
                    "role": user.get("role") or "operator",
                    "status": user.get("status") or "active",
                    "phone_number": None,
                    "notification_preferences": {
                        "department": profile["department"],
                        "position": profile["position"],
                        "synthetic": True,
                        "seed_source": FOUNDATION_SEED_FILENAME,
                    },
                    "last_login_at": None,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "deleted_at": None,
                }
            )
        return users

    @staticmethod
    def _foundation_capability_rows(foundation: dict[str, Any], timestamp: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for capability in foundation.get("capabilities") or []:
            capability_type = str(capability["type"])
            if capability_type == "product_group":
                capability_type = "product"
            user_id = str(capability["user_id"])
            value = str(capability["value"])
            rows.append(
                {
                    "id": str(uuid5(DEMO_SEED_NAMESPACE, f"assignee_capability:{user_id}:{capability_type}:{value}")),
                    "user_id": user_id,
                    "capability_type": capability_type,
                    "capability_value": value,
                    "priority": int(capability.get("priority") or 10),
                    "valid_from": None,
                    "valid_to": None,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
            )
        return rows

    def _foundation_routing_rule_rows(self, foundation: dict[str, Any], timestamp: str) -> list[dict[str, Any]]:
        best_by_category_user: dict[tuple[str, str], int] = {}
        for capability in foundation.get("capabilities") or []:
            category_code = BUSINESS_TYPE_CATEGORIES.get(str(capability.get("value") or ""))
            if not category_code:
                continue
            user_id = str(capability["user_id"])
            key = (category_code, user_id)
            best_by_category_user[key] = min(
                best_by_category_user.get(key, 100),
                int(capability.get("priority") or 10),
            )

        fallback_user_id = next(
            (
                str(capability["user_id"])
                for capability in foundation.get("capabilities") or []
                if capability.get("type") == "fallback" and capability.get("value") == "review_required"
            ),
            "",
        )
        if fallback_user_id:
            best_by_category_user.setdefault(("general", fallback_user_id), 50)

        return [
            {
                "id": str(uuid5(DEMO_SEED_NAMESPACE, f"routing_rule:{category_code}:{user_id}")),
                "category_id": str(uuid5(CATEGORY_NAMESPACE, category_code)),
                "assignee_user_id": user_id,
                "priority": priority,
                "is_active": True,
                "effective_from": None,
                "effective_to": None,
                "created_at": timestamp,
                "updated_at": timestamp,
            }
            for (category_code, user_id), priority in sorted(best_by_category_user.items())
        ]

    def _email_message_row(self, message: DemoMessage, email_account_id: str, timestamp: str) -> dict[str, Any]:
        return {
            "id": message.id,
            "email_account_id": email_account_id,
            "provider_message_id": message.provider_message_id,
            "provider_thread_id": message.provider_thread_id or None,
            "rfc_message_id": message.rfc_message_id or None,
            "in_reply_to": None,
            "references": None,
            "sender_name": message.sender_name or None,
            "sender_address": message.sender_address,
            "subject": message.subject,
            "subject_normalized": message.subject_normalized or None,
            "body_text": message.body_text,
            "body_html": None,
            "snippet": message.snippet or None,
            "sent_at": message.sent_at,
            "received_at": message.received_at or None,
            "has_attachment": message.has_attachment,
            "attachment_count": message.attachment_count,
            "processing_status": message.processing_status,
            "content_hash": self._message_content_hash(message),
            "created_at": timestamp,
            "updated_at": timestamp,
            "deleted_at": None,
        }

    @staticmethod
    def _email_recipient_rows(message: DemoMessage, timestamp: str) -> list[dict[str, Any]]:
        return [
            {
                "id": recipient.id,
                "email_message_id": message.id,
                "recipient_type": recipient.recipient_type,
                "name": recipient.name or None,
                "address": recipient.address,
                "created_at": timestamp,
            }
            for recipient in message.recipients
        ]

    def _email_attachment_rows(self, message: DemoMessage, timestamp: str) -> list[dict[str, Any]]:
        return [
            {
                "id": attachment.id,
                "email_message_id": message.id,
                "provider_attachment_id": attachment.provider_attachment_id or None,
                "filename": attachment.filename,
                "storage_uri": attachment.storage_uri,
                "content_type": attachment.content_type,
                "file_group": attachment.file_group,
                "file_size": attachment.file_size,
                "checksum": attachment.checksum_sha256 or None,
                "is_inline": attachment.is_inline,
                "document_category_id": None,
                "processing_status": attachment.processing_status,
                "parse_error": None,
                "created_at": timestamp,
                "updated_at": timestamp,
                "deleted_at": None,
            }
            for attachment in message.attachments
        ]

    def _email_category_assignment_row(self, message: DemoMessage, timestamp: str) -> dict[str, Any]:
        category_code = DEMO_MAIL_CATEGORY_CODES.get(message.expected_demo_labels.mail_category, "unclassified")
        return {
            "id": str(uuid5(DEMO_SEED_NAMESPACE, f"email_category_assignment:{message.id}")),
            "email_message_id": message.id,
            "category_id": str(uuid5(CATEGORY_NAMESPACE, category_code)),
            "source": "demo_fixture",
            "confidence": 1,
            "model_name": "demo-fixture-labels",
            "reason": "Synthetic demo expected label seeded for display only.",
            "assigned_by_user_id": None,
            "is_current": True,
            "created_at": timestamp,
        }

    def _email_analysis_result_rows(self, message: DemoMessage, timestamp: str) -> list[dict[str, Any]]:
        labels = message.expected_demo_labels
        category_code = DEMO_MAIL_CATEGORY_CODES.get(labels.mail_category, "unclassified")
        category_name = DEMO_CATEGORY_LABELS.get(category_code, "미분류")
        summary_text = _demo_summary_text(message)
        return [
            {
                "id": str(uuid5(DEMO_SEED_NAMESPACE, f"email_analysis_result:classification:{message.id}")),
                "email_message_id": message.id,
                "analysis_type": "classification",
                "result_text": category_name,
                "result_json": {
                    "category_name": category_name,
                    "urgency": {
                        "level": labels.urgency or "normal",
                        "confidence": 1,
                        "reasons": [],
                    },
                    "urgency_level": labels.urgency or "normal",
                    "urgency_label": _level_label(labels.urgency or "normal"),
                    "importance": {
                        "level": labels.importance or "normal",
                        "confidence": 1,
                        "reasons": [],
                    },
                    "importance_level": labels.importance or "normal",
                    "importance_label": _level_label(labels.importance or "normal"),
                    "attention_quadrant": labels.attention_quadrant or _attention_quadrant(
                        labels.urgency or "normal",
                        labels.importance or "normal",
                    ),
                    "attention_label": _attention_label(
                        labels.attention_quadrant or _attention_quadrant(
                            labels.urgency or "normal",
                            labels.importance or "normal",
                        )
                    ),
                    "business_refs": labels.business_refs,
                    "vessel_names": labels.vessel_names,
                    "equipment": labels.equipment,
                    "counterparty": labels.counterparty,
                    "reason": "demo_fixture_expected_labels",
                },
                "model_name": "demo-fixture-labels",
                "prompt_version": "demo-fixture:v1",
                "status": "success",
                "error_message": None,
                "is_current": True,
                "created_at": timestamp,
                "updated_at": timestamp,
            },
            {
                "id": str(uuid5(DEMO_SEED_NAMESPACE, f"email_analysis_result:executive_summary:{message.id}")),
                "email_message_id": message.id,
                "analysis_type": "executive_summary",
                "result_text": summary_text,
                "result_json": {
                    "summary_text": summary_text,
                    "sections": [
                        {"title": "핵심 요청", "body": summary_text},
                        {"title": "업무번호", "body": ", ".join(labels.business_refs) or "-"},
                    ],
                },
                "model_name": "demo-fixture-labels",
                "prompt_version": "demo-fixture:v1",
                "status": "success",
                "error_message": None,
                "is_current": True,
                "created_at": timestamp,
                "updated_at": timestamp,
            },
        ]

    @staticmethod
    def _routing_assignment_row(message: DemoMessage, timestamp: str) -> dict[str, Any] | None:
        assignee_user_id = DEMO_ASSIGNEE_AREA_USER_IDS.get(message.expected_demo_labels.assignee_area)
        if not assignee_user_id:
            return None
        status = _demo_routing_status(message)
        return {
            "id": str(uuid5(DEMO_SEED_NAMESPACE, f"routing_assignment:{message.id}")),
            "email_message_id": message.id,
            "assignee_user_id": assignee_user_id,
            "status": status,
            "assignment_source": "demo_fixture",
            "routing_rule_id": None,
            "assigned_at": timestamp,
            "forwarded_at": message.received_at if status == "forwarded" else None,
            "fixed_at": None,
            "completed_at": None,
            "created_at": timestamp,
            "updated_at": timestamp,
        }

    @staticmethod
    def _work_item_row(
        message: DemoMessage,
        routing_assignment: dict[str, Any],
        timestamp: str,
    ) -> dict[str, Any]:
        assigned_at = _parse_seed_timestamp(timestamp)
        bucket = int(uuid5(DEMO_SEED_NAMESPACE, f"work-item-state:{message.id}").int % 100)
        if bucket < 46:
            status = "assigned"
            acknowledged_at = None
            responded_at = None
            completed_at = None
        elif bucket < 60:
            status = "acknowledged"
            acknowledged_at = assigned_at + timedelta(minutes=18)
            responded_at = None
            completed_at = None
        elif bucket < 74:
            status = "in_progress"
            acknowledged_at = assigned_at + timedelta(minutes=35)
            responded_at = None
            completed_at = None
        elif bucket < 88:
            status = "responded"
            acknowledged_at = assigned_at + timedelta(minutes=28)
            responded_at = assigned_at + timedelta(hours=2, minutes=15)
            completed_at = None
        else:
            status = "completed"
            acknowledged_at = assigned_at + timedelta(minutes=20)
            responded_at = assigned_at + timedelta(hours=1, minutes=50)
            completed_at = assigned_at + timedelta(hours=4, minutes=10)

        is_overdue = status in {"assigned", "acknowledged", "in_progress"} and bucket % 11 == 0
        due_at = assigned_at - timedelta(hours=3) if is_overdue else assigned_at + timedelta(hours=12 + bucket % 36)
        last_activity_at = completed_at or responded_at or acknowledged_at or assigned_at
        first_responded_at = responded_at if status in {"responded", "completed"} else None
        return {
            "id": str(uuid5(DEMO_SEED_NAMESPACE, f"work_item:{message.id}")),
            "email_message_id": message.id,
            "routing_assignment_id": routing_assignment["id"],
            "assignee_user_id": routing_assignment["assignee_user_id"],
            "status": status,
            "assigned_at": assigned_at.isoformat(),
            "acknowledged_at": acknowledged_at.isoformat() if acknowledged_at else None,
            "reply_initiated_at": None,
            "first_responded_at": first_responded_at.isoformat() if first_responded_at else None,
            "responded_at": responded_at.isoformat() if responded_at else None,
            "completed_at": completed_at.isoformat() if completed_at else None,
            "due_at": due_at.isoformat(),
            "last_activity_at": last_activity_at.isoformat(),
            "created_at": timestamp,
            "updated_at": timestamp,
        }

    def _mail_decision_run_row(self, message: DemoMessage, timestamp: str) -> dict[str, Any]:
        labels = message.expected_demo_labels
        assignee_user_id = DEMO_ASSIGNEE_AREA_USER_IDS.get(labels.assignee_area)
        primary_type = _demo_mail_decision_primary_type(labels.mail_category)
        summary_text = _demo_summary_text(message)
        context = {
            "decision_output": {
                "summary": {
                    "one_line_summary": summary_text,
                    "requested_actions": [labels.key_spec_fields.get("requested_action") or message.snippet],
                    "business_refs": labels.business_refs,
                    "key_facts": [
                        value
                        for value in [
                            labels.counterparty,
                            ", ".join(labels.vessel_names),
                            ", ".join(labels.equipment),
                        ]
                        if value
                    ],
                },
                "classification": {
                    "primary_type": primary_type,
                    "confidence": 1.0,
                    "review_required": False,
                },
                "requested_actions": [labels.key_spec_fields.get("requested_action") or message.snippet],
            },
            "routing_decision": {
                "decision": "auto_assign",
                "selected_user_id": assignee_user_id,
                "confidence": 1.0,
                "candidates": [
                    {
                        "user_id": assignee_user_id,
                        "total_score": 1.0,
                        "rank": 1,
                        "reasons": ["demo_fixture_expected_labels"],
                    }
                ]
                if assignee_user_id
                else [],
            },
            "assigned_user_id": assignee_user_id,
            "demo_source": "data/demo/*.fixture.json expected_demo_labels",
        }
        state_json = {
            "run_id": str(uuid5(DEMO_SEED_NAMESPACE, f"mail_decision_run:{message.id}")),
            "email_message_id": message.id,
            "workflow_version": "demo-fixture-mail-decision:v1",
            "status": "auto_assigned",
            "current_node": None,
            "retrieval_cycle": 0,
            "context": context,
            "facts": {
                "customer_name": labels.counterparty,
                "business_refs": labels.business_refs,
                "vessel_names": labels.vessel_names,
                "product_names": labels.equipment,
            },
            "result": None,
            "started_at": message.received_at,
            "completed_at": message.received_at,
        }
        return {
            "id": state_json["run_id"],
            "email_message_id": message.id,
            "workflow_version": "demo-fixture-mail-decision:v1",
            "status": "auto_assigned",
            "current_node": None,
            "input_hash": self._message_content_hash(message),
            "attempt_count": 1,
            "review_required": False,
            "failure_code": None,
            "failure_message": None,
            "started_at": message.received_at,
            "completed_at": message.received_at,
            "state_json": state_json,
            "created_at": timestamp,
            "updated_at": timestamp,
        }

    def _processing_job_row(self, message: DemoMessage, timestamp: str) -> dict[str, Any]:
        return {
            "id": str(uuid5(DEMO_SEED_NAMESPACE, f"processing_job:email_analysis:{message.id}")),
            "job_type": "email_analysis",
            "source_type": "email",
            "source_id": message.id,
            "status": "pending",
            "attempt_count": 0,
            "max_attempts": 3,
            "scheduled_at": timestamp,
            "started_at": None,
            "completed_at": None,
            "error_message": None,
            "metadata": {
                "seed_source": "data/demo/*.fixture.json",
                "expected_demo_labels_available": bool(message.expected_demo_labels),
            },
            "created_at": timestamp,
            "updated_at": timestamp,
        }

    @staticmethod
    def _message_content_hash(message: DemoMessage) -> str:
        payload = {
            "provider_message_id": message.provider_message_id,
            "rfc_message_id": message.rfc_message_id,
            "sender_address": message.sender_address,
            "subject": message.subject,
            "body_text": message.body_text,
            "sent_at": message.sent_at,
            "attachments": [DemoSeedService._attachment_hash_payload(attachment) for attachment in message.attachments],
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _attachment_hash_payload(attachment: DemoAttachment) -> dict[str, Any]:
        return {
            "filename": attachment.filename,
            "storage_uri": attachment.storage_uri,
            "checksum_sha256": attachment.checksum_sha256,
        }

    @staticmethod
    def _duplicates(values: Any) -> list[str]:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for value in values:
            if value in seen:
                duplicates.add(value)
            seen.add(value)
        return sorted(duplicates)


def _demo_summary_text(message: DemoMessage) -> str:
    labels = message.expected_demo_labels
    requested_action = labels.key_spec_fields.get("requested_action", "")
    base = requested_action or message.snippet or message.body_text.splitlines()[0]
    refs = ", ".join(labels.business_refs)
    return " - ".join(value for value in (refs, base) if value)


def _demo_routing_status(message: DemoMessage) -> str:
    return "forwarded"


def _parse_seed_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _demo_mail_decision_primary_type(mail_category: str) -> str:
    return {
        "purchase_delivery_followup": "delivery_confirmation",
        "quotation_received": "quotation_request",
        "specification_check": "specification_review",
        "specification_recheck": "specification_review",
    }.get(mail_category, mail_category)


def _level_label(level: str) -> str:
    return {"high": "높음", "normal": "보통"}.get(level, level)


def _attention_quadrant(urgency: str, importance: str) -> str:
    if urgency == "high" and importance == "high":
        return "urgent_important"
    if urgency == "high":
        return "urgent"
    if importance == "high":
        return "important"
    return "normal"


def _attention_label(quadrant: str) -> str:
    return {
        "urgent_important": "긴급·중요",
        "urgent": "긴급",
        "important": "중요",
        "normal": "일반",
    }.get(quadrant, quadrant)

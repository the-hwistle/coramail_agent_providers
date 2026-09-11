from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

NAMESPACE = UUID("fd2404be-7908-46c6-b2db-81504e48972e")
BUSINESS_TYPES = (
    "quotation_request",
    "purchase_order",
    "order_change",
    "delivery_delay",
    "technical_inquiry",
    "drawing_review",
    "service_request",
    "repair_request",
    "claim",
    "urgent_failure",
    "invoice",
    "certificate_request",
)
PRODUCT_GROUPS = ("engine", "pump", "valve", "automation", "deck", "electrical")


def stable_id(kind: str, value: str) -> str:
    return str(uuid5(NAMESPACE, f"{kind}:{value}"))


@dataclass(frozen=True)
class SyntheticDatasetConfig:
    seed: int = 20260730
    dataset_version: str = "synthetic-mail-decision-v1-leaky"
    id_prefix: str = ""
    clean_retrieval_cases: bool = False
    assignee_count: int = 8
    customer_count: int = 12
    product_group_count: int = 6
    project_count: int = 15
    email_count: int = 200
    attachment_count: int = 120
    ground_truth_count: int = 100


class SyntheticEvaluationDatasetGenerator:
    def __init__(self, config: SyntheticDatasetConfig | None = None):
        self.config = config or SyntheticDatasetConfig()
        self.random = random.Random(self.config.seed)

    def generate(self) -> dict[str, Any]:
        assignees = self._assignees()
        customers = self._customers()
        products = self._products()
        projects = self._projects(customers)
        emails = self._emails(customers, products, projects, assignees)
        capabilities = self._capabilities(assignees, emails)
        attachments = self._attachments(emails)
        ground_truth = [self._truth(email) for email in emails[: self.config.ground_truth_count]]
        if self.config.clean_retrieval_cases:
            source_emails = emails[self.config.ground_truth_count : self.config.ground_truth_count * 2]
            cases = [self._clean_qdrant_case(email, index) for index, email in enumerate(source_emails, start=1)]
        else:
            cases = [self._qdrant_case(email) for email in emails[: self.config.ground_truth_count]]
        return {
            "metadata": {
                "synthetic": True,
                "seed": self.config.seed,
                "dataset_version": self.config.dataset_version,
                "generator_seed": self.config.seed,
                "leakage_policy_version": 1 if self.config.clean_retrieval_cases else 0,
                "config": asdict(self.config),
            },
            "assignees": assignees,
            "customers": customers,
            "product_groups": products,
            "projects": projects,
            "assignee_capabilities": capabilities,
            "emails": emails,
            "attachments": attachments,
            "ground_truth": ground_truth,
            "qdrant_cases": cases,
        }

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.generate(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _assignees(self) -> list[dict[str, Any]]:
        email_prefix = self.config.id_prefix.replace("-", "") if self.config.id_prefix else ""
        return [
            {
                "id": stable_id("user", f"{self.config.id_prefix}assignee-{index}"),
                "email": f"{email_prefix}assignee{index}@coramail.invalid",
                "name": f"합성 담당자 {index}",
                "role": "operator" if index < 8 else "admin",
                "status": "active",
            }
            for index in range(1, self.config.assignee_count + 1)
        ]

    def _customers(self) -> list[dict[str, Any]]:
        return [
            {
                "id": stable_id("customer", f"{self.config.id_prefix}customer-{index}"),
                "name": f"Synthetic Marine Customer {index:02d}",
                "domain": f"customer{index:02d}.invalid",
            }
            for index in range(1, self.config.customer_count + 1)
        ]

    def _products(self) -> list[dict[str, Any]]:
        return [
            {"id": stable_id("product", f"{self.config.id_prefix}{name}"), "code": name.upper(), "name": name}
            for name in PRODUCT_GROUPS[: self.config.product_group_count]
        ]

    def _projects(self, customers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        projects = []
        for index in range(1, self.config.project_count + 1):
            customer = customers[(index - 1) % len(customers)]
            projects.append(
                {
                    "id": stable_id("project", f"{self.config.id_prefix}project-{index}"),
                    "code": f"PRJ-{2026}-{index:03d}",
                    "vessel_name": f"SYNTHETIC VESSEL {index:02d}",
                    "customer_id": customer["id"],
                }
            )
        return projects

    def _capabilities(self, assignees, emails) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        owned_values: dict[str, dict[str, set[str]]] = {
            assignee["id"]: {
                "customer": set(),
                "product": set(),
                "business_type": set(),
                "project": set(),
            }
            for assignee in assignees
        }
        for email in emails:
            owner = owned_values[email["expected_assignee_user_id"]]
            owner["customer"].add(email["customer_name"])
            owner["product"].add(email["product_group"])
            owner["business_type"].add(email["business_type"])
            owner["project"].add(email["project_code"])
        for assignee in assignees:
            for capability_type, values in owned_values[assignee["id"]].items():
                for priority, value in enumerate(sorted(values), start=1):
                    rows.append(
                        {
                            "id": stable_id("capability", f"{self.config.id_prefix}{assignee['id']}:{capability_type}:{value}"),
                            "user_id": assignee["id"],
                            "capability_type": capability_type,
                            "capability_value": value,
                            "priority": priority,
                        }
                    )
        return rows

    def _emails(self, customers, products, projects, assignees) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for index in range(1, self.config.email_count + 1):
            customer_index = (index - 1) % len(customers)
            customer = customers[customer_index]
            product = products[(index * 3) % len(products)]
            project = projects[(index * 5) % len(projects)]
            business_type = BUSINESS_TYPES[(index * 7) % len(BUSINESS_TYPES)]
            assignee = assignees[customer_index % len(assignees)]
            urgent = business_type in {"urgent_failure", "claim", "delivery_delay"} and index % 2 == 0
            identifier = f"PO-{index:06d}" if business_type == "purchase_order" else f"REF-{index:06d}"
            subject = f"[{project['code']}] {business_type} - {product['name']} {identifier}"
            body = (
                f"Customer: {customer['name']}\nProject: {project['code']}\nVessel: {project['vessel_name']}\n"
                f"Product group: {product['name']}\nRequest type: {business_type}\nReference: {identifier}\n"
                + ("URGENT: operation is stopped.\n" if urgent else "Please review and respond.\n")
            )
            rows.append(
                {
                    "id": stable_id("email", f"{self.config.id_prefix}email-{index}"),
                    "provider_message_id": f"{self.config.id_prefix}synthetic-{index}",
                    "sender_name": f"Requester {index:03d}",
                    "sender_address": f"requester{index:03d}@{customer['domain']}",
                    "subject": subject,
                    "body_text": body,
                    "customer_name": customer["name"],
                    "product_group": product["name"],
                    "project_code": project["code"],
                    "vessel_name": project["vessel_name"],
                    "business_type": business_type,
                    "reference": identifier,
                    "urgent": urgent,
                    "expected_assignee_user_id": assignee["id"],
                }
            )
        return rows

    def _attachments(self, emails) -> list[dict[str, Any]]:
        formats = ("pdf", "xlsx", "docx", "png", "txt")
        rows = []
        for index in range(self.config.attachment_count):
            email = emails[index % len(emails)]
            suffix = formats[index % len(formats)]
            rows.append(
                {
                    "id": stable_id("attachment", f"{self.config.id_prefix}attachment-{index + 1}"),
                    "email_message_id": email["id"],
                    "filename": f"synthetic-{index + 1:03d}.{suffix}",
                    "content_type": {
                        "pdf": "application/pdf",
                        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        "png": "image/png",
                        "txt": "text/plain",
                    }[suffix],
                    "synthetic_text": email["body_text"],
                }
            )
        return rows

    @staticmethod
    def _truth(email: dict[str, Any]) -> dict[str, Any]:
        return {
            "email_message_id": email["id"],
            "business_type": email["business_type"],
            "expected_assignee_user_id": email["expected_assignee_user_id"],
            "customer_name": email["customer_name"],
            "product_group": email["product_group"],
            "project_code": email["project_code"],
            "urgent": email["urgent"],
        }

    @staticmethod
    def _qdrant_case(email: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": stable_id("qdrant-case", email["id"]),
            "text": f"{email['subject']}\n{email['body_text']}",
            "payload": {
                "email_message_id": email["id"],
                "business_type": email["business_type"],
                "assignee_user_id": email["expected_assignee_user_id"],
                "assignment_confirmed": True,
                "synthetic": True,
                "provider": "synthetic",
                "dataset_type": "evaluation",
                "evaluation": True,
            },
        }

    def _clean_qdrant_case(self, email: dict[str, Any], index: int) -> dict[str, Any]:
        historical_ref = f"HIST-{index:06d}"
        source_id = email["id"]
        text = (
            f"Historical routing note {historical_ref}\n"
            f"Work type: {email['business_type']}\n"
            f"Equipment family: {email['product_group']}\n"
            f"Past resolution: confirmed owner handled a comparable request with separate source data.\n"
            f"Routing factors: customer relationship, product capability, and project history were reviewed."
        )
        return {
            "id": stable_id("qdrant-case", f"{self.config.id_prefix}clean:{source_id}"),
            "source_email_message_id": source_id,
            "text": text,
            "payload": {
                "source_email_message_id": source_id,
                "historical_business_type": email["business_type"],
                "historical_assignee_user_id": email["expected_assignee_user_id"],
                "historical_reference": historical_ref,
                "assignment_confirmed": True,
                "synthetic": True,
                "provider": "synthetic",
                "dataset_type": "evaluation",
                "evaluation": True,
                "dataset_version": self.config.dataset_version,
                "summary": text,
            },
        }

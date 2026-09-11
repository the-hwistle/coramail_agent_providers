from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from app.agents.decision_agent import DecisionAgentOutput


class PostgresDecisionResultRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url.strip()

    def save(self, *, email_message_id: UUID, output: DecisionAgentOutput, model_name: str) -> None:
        import psycopg

        now = datetime.now(timezone.utc)
        category_code, category_name = _category_for(output.classification.primary_type)
        summary_json = output.summary.model_dump(mode="json")
        summary_json.update(
            {
                "summary_text": output.summary.one_line_summary,
                "sections": _summary_sections(output),
                "requested_action": "; ".join(output.requested_actions),
                "generation_mode": output.generation_mode,
                "review_required": output.review_required,
                "review_reasons": output.review_reasons,
            }
        )
        classification_json = output.classification.model_dump(mode="json")
        classification_json.update(
            {
                "category_code": category_code,
                "category_name": category_name,
                "label_scores": output.classification.candidate_scores,
                "urgency": output.urgency.model_dump(mode="json"),
                "urgency_level": output.urgency.level,
                "urgency_label": _level_label(output.urgency.level),
                "importance": output.importance.model_dump(mode="json"),
                "importance_level": output.importance.level,
                "importance_label": _level_label(output.importance.level),
                "attention_quadrant": output.attention_quadrant,
                "attention_label": _attention_label(output.attention_quadrant),
                "reason": "; ".join(output.review_reasons),
                "generation_mode": output.generation_mode,
                "review_required": output.review_required,
            }
        )
        urgency_json = {
            **output.urgency.model_dump(mode="json"),
            "attention_quadrant": output.attention_quadrant,
        }
        importance_json = {
            **output.importance.model_dump(mode="json"),
            "attention_quadrant": output.attention_quadrant,
        }
        attention_json = {
            "attention_quadrant": output.attention_quadrant,
            "attention_label": _attention_label(output.attention_quadrant),
            "urgency": output.urgency.model_dump(mode="json"),
            "importance": output.importance.model_dump(mode="json"),
        }
        payloads = {
            "executive_summary": (output.summary.one_line_summary, summary_json),
            "classification": (category_name, classification_json),
            "urgency": (output.urgency.level, urgency_json),
            "importance": (output.importance.level, importance_json),
            "attention": (output.attention_quadrant, attention_json),
            "requested_actions": ("; ".join(output.requested_actions), {"requested_actions": output.requested_actions}),
        }
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    for analysis_type, (result_text, result_json) in payloads.items():
                        cursor.execute(
                            """
                            UPDATE email_analysis_results
                            SET is_current = FALSE, updated_at = %(updated_at)s
                            WHERE email_message_id = %(email_message_id)s
                              AND analysis_type = %(analysis_type)s
                              AND is_current IS TRUE
                            """,
                            {"updated_at": now, "email_message_id": email_message_id, "analysis_type": analysis_type},
                        )
                        cursor.execute(
                            """
                            INSERT INTO email_analysis_results (
                                id, email_message_id, analysis_type, result_text, result_json, model_name,
                                prompt_version, status, error_message, is_current, created_at, updated_at
                            ) VALUES (
                                %(id)s, %(email_message_id)s, %(analysis_type)s, %(result_text)s, %(result_json)s,
                                %(model_name)s, 'decision-agent:v3', 'success', NULL, TRUE, %(created_at)s, %(updated_at)s
                            )
                            """,
                            {
                                "id": uuid4(), "email_message_id": email_message_id, "analysis_type": analysis_type,
                                "result_text": result_text, "result_json": Jsonb(result_json), "model_name": model_name,
                                "created_at": now, "updated_at": now,
                            },
                        )
                    cursor.execute(
                        """
                        SELECT id FROM categories
                        WHERE code = %(category_code)s AND is_active IS TRUE
                        ORDER BY created_at
                        LIMIT 1
                        """,
                        {"category_code": category_code},
                    )
                    category = cursor.fetchone()
                    if category is not None:
                        cursor.execute(
                            """
                            UPDATE email_category_assignments
                            SET is_current = FALSE
                            WHERE email_message_id = %(email_message_id)s
                              AND is_current IS TRUE
                            """,
                            {"email_message_id": email_message_id},
                        )
                        cursor.execute(
                            """
                            INSERT INTO email_category_assignments (
                                id, email_message_id, category_id, source, confidence, model_name,
                                reason, assigned_by_user_id, is_current, created_at
                            )
                            VALUES (
                                %(id)s, %(email_message_id)s, %(category_id)s, 'ai', %(confidence)s,
                                %(model_name)s, %(reason)s, NULL, TRUE, %(created_at)s
                            )
                            """,
                            {
                                "id": uuid4(),
                                "email_message_id": email_message_id,
                                "category_id": category[0],
                                "confidence": output.classification.confidence,
                                "model_name": model_name,
                                "reason": "; ".join(output.review_reasons) or "Mail Decision AI classification",
                                "created_at": now,
                            },
                        )


def _summary_sections(output: DecisionAgentOutput) -> list[dict[str, str]]:
    sections = [{"title": "핵심 요청", "body": output.summary.one_line_summary}]
    if output.summary.requested_actions:
        sections.append({"title": "필요 조치", "body": ", ".join(output.summary.requested_actions)})
    if output.summary.business_refs:
        sections.append({"title": "업무번호", "body": ", ".join(output.summary.business_refs)})
    if output.summary.deadlines:
        sections.append({"title": "기한", "body": ", ".join(output.summary.deadlines)})
    if output.summary.risks:
        sections.append({"title": "주의사항", "body": ", ".join(output.summary.risks)})
    return sections


def _category_for(primary_type: str) -> tuple[str, str]:
    if primary_type in {
        "purchase_order", "order_change", "order_cancellation", "delivery_confirmation", "delivery_delay",
    }:
        return "order", "발주"
    if primary_type in {"quotation_request", "quotation_followup", "general_inquiry", "certificate_request"}:
        return "inquiry", "문의"
    if primary_type in {"service_request", "repair_request", "claim", "urgent_failure"}:
        return "service", "서비스"
    if primary_type in {"technical_inquiry", "drawing_review", "specification_review", "compatibility_check"}:
        return "technical", "기술"
    return "general", "기타"


def _level_label(level: str) -> str:
    return {"high": "높음", "normal": "보통"}.get(level, level)


def _attention_label(quadrant: str) -> str:
    return {
        "urgent_important": "긴급·중요",
        "urgent": "긴급",
        "important": "중요",
        "normal": "일반",
    }.get(quadrant, quadrant)

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


CATEGORY_BUSINESS_TYPES = {
    "발주": ["purchase_order", "order_change", "order_cancellation", "delivery_confirmation", "delivery_delay"],
    "문의": ["quotation_request", "quotation_followup", "general_inquiry", "certificate_request"],
    "서비스": ["service_request", "repair_request", "claim", "urgent_failure"],
    "기술": ["technical_inquiry", "drawing_review", "specification_review", "compatibility_check"],
    "기타": ["invoice", "payment_inquiry", "spam"],
}


class PostgresAssigneeAdminRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def list_operating_assignees(self) -> list[dict[str, Any]]:
        import psycopg

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT u.id, u.name, u.email, u.status, u.notification_preferences,
                           COALESCE(array_agg(ac.capability_value) FILTER (
                               WHERE ac.capability_type = 'business_type'
                                 AND (ac.valid_to IS NULL OR ac.valid_to > now())
                           ), ARRAY[]::varchar[]) AS business_types,
                           COALESCE(jsonb_agg(jsonb_build_object(
                               'capability_value', ac.capability_value,
                               'priority', ac.priority
                           )) FILTER (
                               WHERE ac.capability_type = 'business_type'
                                 AND (ac.valid_to IS NULL OR ac.valid_to > now())
                           ), '[]'::jsonb) AS business_type_priorities
                    FROM users u
                    LEFT JOIN assignee_capabilities ac ON ac.user_id = u.id
                    WHERE u.deleted_at IS NULL
                      AND u.email NOT LIKE '%%@coramail.invalid'
                    GROUP BY u.id
                    ORDER BY u.name
                    """
                )
                return [self._view(dict(row)) for row in cursor.fetchall()]

    def list_active_synthetic_assignees(self) -> list[dict[str, Any]]:
        """Return evaluation-only assignees for a read-only Settings view."""
        import psycopg

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT u.id, u.name, u.email, u.status,
                           ac.capability_type, ac.capability_value
                    FROM users u
                    LEFT JOIN assignee_capabilities ac
                      ON ac.user_id = u.id
                     AND (ac.valid_to IS NULL OR ac.valid_to > now())
                    WHERE u.deleted_at IS NULL
                      AND u.status = 'active'
                      AND u.email LIKE '%%@coramail.invalid'
                    ORDER BY u.name, ac.capability_type, ac.capability_value
                    """
                )
                return self._synthetic_views([dict(row) for row in cursor.fetchall()])

    def create(self, *, name: str, email: str, department: str, position: str, category: str) -> UUID:
        import psycopg

        user_id = uuid4()
        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO users (
                            id, email, name, role, status, notification_preferences, created_at, updated_at
                        ) VALUES (
                            %(id)s, %(email)s, %(name)s, 'operator', 'active',
                            %(preferences)s, %(created_at)s, %(updated_at)s
                        )
                        """,
                        {
                            "id": user_id,
                            "email": email,
                            "name": name,
                            "preferences": Jsonb({"department": department, "position": position}),
                            "created_at": now,
                            "updated_at": now,
                        },
                    )
                    self._replace_category(cursor, user_id, category, now)
        return user_id

    def update(self, user_id: UUID, *, name: str, email: str, department: str, position: str, category: str) -> None:
        import psycopg

        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE users
                        SET name = COALESCE(NULLIF(%(name)s, ''), name),
                            email = COALESCE(NULLIF(%(email)s, ''), email),
                            notification_preferences = %(preferences)s,
                            updated_at = %(updated_at)s
                        WHERE id = %(id)s
                          AND deleted_at IS NULL
                          AND email NOT LIKE '%%@coramail.invalid'
                        """,
                        {
                            "id": user_id,
                            "name": name,
                            "email": email,
                            "preferences": Jsonb({"department": department, "position": position}),
                            "updated_at": now,
                        },
                    )
                    if cursor.rowcount and category:
                        self._replace_category(cursor, user_id, category, now)

    def set_active(self, user_id: UUID, active: bool) -> None:
        self._update_status(user_id, "active" if active else "inactive")

    def toggle_active(self, user_id: UUID) -> None:
        import psycopg

        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE users
                        SET status = CASE WHEN status = 'active' THEN 'inactive' ELSE 'active' END,
                            updated_at = %(now)s
                        WHERE id = %(id)s
                          AND deleted_at IS NULL
                          AND email NOT LIKE '%%@coramail.invalid'
                        """,
                        {"id": user_id, "now": datetime.now(timezone.utc)},
                    )

    def delete(self, user_id: UUID) -> None:
        import psycopg

        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE users
                        SET status = 'inactive', deleted_at = %(now)s, updated_at = %(now)s
                        WHERE id = %(id)s
                          AND email NOT LIKE '%%@coramail.invalid'
                        """,
                        {"id": user_id, "now": now},
                    )

    def reorder_category_assignees(self, category: str, user_ids: list[UUID]) -> None:
        business_types = CATEGORY_BUSINESS_TYPES.get(category)
        if not business_types or not user_ids:
            return

        import psycopg

        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    for priority, user_id in enumerate(user_ids, start=1):
                        cursor.execute(
                            """
                            UPDATE assignee_capabilities ac
                            SET priority = %(priority)s,
                                updated_at = %(updated_at)s
                            FROM users u
                            WHERE ac.user_id = %(user_id)s
                              AND ac.user_id = u.id
                              AND u.deleted_at IS NULL
                              AND u.email NOT LIKE '%%@coramail.invalid'
                              AND ac.capability_type = 'business_type'
                              AND ac.capability_value = ANY(%(business_types)s)
                            """,
                            {
                                "user_id": user_id,
                                "priority": priority,
                                "updated_at": now,
                                "business_types": business_types,
                            },
                        )

    def _update_status(self, user_id: UUID, status: str) -> None:
        import psycopg

        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE users
                        SET status = %(status)s, updated_at = %(now)s
                        WHERE id = %(id)s
                          AND deleted_at IS NULL
                          AND email NOT LIKE '%%@coramail.invalid'
                        """,
                        {"id": user_id, "status": status, "now": datetime.now(timezone.utc)},
                    )

    @staticmethod
    def _replace_category(cursor: Any, user_id: UUID, category: str, now: datetime) -> None:
        cursor.execute(
            "DELETE FROM assignee_capabilities WHERE user_id = %(user_id)s AND capability_type = 'business_type'",
            {"user_id": user_id},
        )
        for business_type in CATEGORY_BUSINESS_TYPES.get(category, []):
            cursor.execute(
                """
                INSERT INTO assignee_capabilities (
                    id, user_id, capability_type, capability_value, priority, created_at, updated_at
                ) VALUES (%(id)s, %(user_id)s, 'business_type', %(value)s, 10, %(now)s, %(now)s)
                """,
                {"id": uuid4(), "user_id": user_id, "value": business_type, "now": now},
            )

    @staticmethod
    def _view(row: dict[str, Any]) -> dict[str, Any]:
        preferences = row.get("notification_preferences") or {}
        business_types = set(row.get("business_types") or [])
        business_type_priorities: dict[str, int] = {}
        for item in row.get("business_type_priorities") or []:
            value = str(item.get("capability_value") or "").strip()
            if not value:
                continue
            try:
                priority = int(item.get("priority") or 100)
            except (TypeError, ValueError):
                priority = 100
            business_type_priorities[value] = min(priority, business_type_priorities.get(value, priority))
        categories = [
            category for category, values in CATEGORY_BUSINESS_TYPES.items() if business_types.intersection(values)
        ]
        category_priorities = {
            category: min(business_type_priorities.get(value, 100) for value in values if value in business_types)
            for category, values in CATEGORY_BUSINESS_TYPES.items()
            if business_types.intersection(values)
        }
        return {
            "assignee_id": str(row["id"]),
            "assignee_name": row.get("name") or "",
            "email_address": row.get("email") or "",
            "department": preferences.get("department") or "",
            "position": preferences.get("position") or "",
            "mail_categories": categories,
            "business_labels": categories,
            "category_priorities": category_priorities,
            "is_active": row.get("status") == "active",
            "is_synthetic": False,
        }

    @staticmethod
    def _synthetic_views(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        assignees: dict[str, dict[str, Any]] = {}
        for row in rows:
            assignee_id = str(row["id"])
            assignee = assignees.setdefault(
                assignee_id,
                {
                    "assignee_id": assignee_id,
                    "assignee_name": row.get("name") or "",
                    "email_address": row.get("email") or "",
                    "department": "평가 데이터",
                    "position": "합성 담당자",
                    "is_active": row.get("status") == "active",
                    "is_synthetic": True,
                    "capabilities": {},
                    "capability_count": 0,
                },
            )
            capability_type = str(row.get("capability_type") or "").strip()
            capability_value = str(row.get("capability_value") or "").strip()
            if capability_type and capability_value:
                assignee["capabilities"].setdefault(capability_type, []).append(capability_value)
                assignee["capability_count"] += 1
        for assignee in assignees.values():
            business_types = set(assignee["capabilities"].get("business_type", []))
            categories = [
                category
                for category, values in CATEGORY_BUSINESS_TYPES.items()
                if business_types.intersection(values)
            ]
            assignee["mail_categories"] = categories
            assignee["business_labels"] = categories
        return list(assignees.values())

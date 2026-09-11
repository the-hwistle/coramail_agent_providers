from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from app.repositories.demo_mail_repository import DemoMailRepository
from app.repositories.postgres_assignee_admin_repository import PostgresAssigneeAdminRepository
from app.repositories.postgres_seed_writer import PostgresSeedWriter, PostgresSeedWriterError
from app.services.demo_seed_service import DemoSeedService


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEMO_DIR = PROJECT_DIR / "data" / "demo"


def test_demo_seed_bundle_includes_fake_assignees_capabilities_and_routing_rules():
    service = DemoSeedService(DemoMailRepository(DEMO_DIR))
    bundle = service.build_seed_bundle(created_at="2026-08-07T00:00:00+00:00")
    counts = service.validate_seed_bundle(bundle)

    assert counts["users"] == 8
    assert counts["email_messages"] == 1213
    assert counts["email_attachments"] == 4
    assert counts["mail_decision_runs"] == 1213
    assert counts["routing_assignments"] == 1213
    assert counts["work_items"] == 1213
    assert counts["assignee_capabilities"] >= 21
    assert counts["routing_rules"] >= 5
    assert {row["code"] for row in bundle["categories"]} >= {
        "order",
        "inquiry",
        "service",
        "technical",
        "general",
        "unclassified",
    }
    assert all(row["email"].endswith("@dawonict.co.kr") for row in bundle["users"])
    assert all(row["notification_preferences"]["synthetic"] is True for row in bundle["users"])
    assert {row["capability_type"] for row in bundle["assignee_capabilities"]} >= {
        "customer",
        "product",
        "business_type",
    }
    assert bundle["email_messages"][0]["subject"] == "[견적서 송부] 산업용 네트워크 장비 및 전원모듈"
    assert bundle["email_attachments"][0]["filename"] == "Quotation_QT-2026-0812-03.pdf"
    assert all(row["status"] == "forwarded" for row in bundle["routing_assignments"])
    assert all(row["forwarded_at"] for row in bundle["routing_assignments"])
    assert all(row["status"] == "auto_assigned" for row in bundle["mail_decision_runs"])
    assert all(row["state_json"]["context"]["demo_source"] for row in bundle["mail_decision_runs"])
    work_statuses = Counter(row["status"] for row in bundle["work_items"])
    assert work_statuses == {
        "assigned": 571,
        "acknowledged": 161,
        "in_progress": 155,
        "responded": 179,
        "completed": 147,
    }
    work_items_by_message = {row["email_message_id"]: row for row in bundle["work_items"]}
    routing_by_message = {row["email_message_id"]: row for row in bundle["routing_assignments"]}
    assert set(work_items_by_message) == set(routing_by_message)
    assert all(
        row["routing_assignment_id"] == routing_by_message[row["email_message_id"]]["id"]
        for row in bundle["work_items"]
    )

    messages_by_day: dict[str, int] = defaultdict(int)
    category_names = {row["id"]: row["name"] for row in bundle["categories"]}
    category_by_message = {
        row["email_message_id"]: category_names[row["category_id"]]
        for row in bundle["email_category_assignments"]
    }
    categories = Counter(category_by_message[row["id"]] for row in bundle["email_messages"])
    classification_by_message = {
        row["email_message_id"]: row["result_json"]
        for row in bundle["email_analysis_results"]
        if row["analysis_type"] == "classification"
    }
    for row in bundle["email_messages"]:
        messages_by_day[datetime.fromisoformat(row["received_at"]).date().isoformat()] += 1

    assert dict(sorted(messages_by_day.items())) == {
        "2026-08-06": 168,
        "2026-08-07": 142,
        "2026-08-08": 196,
        "2026-08-09": 151,
        "2026-08-10": 184,
        "2026-08-11": 207,
        "2026-08-12": 165,
    }
    assert round((categories["발주"] + categories["문의"]) / counts["email_messages"] * 100, 1) == 59.9
    latest_demo_day = "2026-08-12"
    latest_day_messages = [
        row
        for row in bundle["email_messages"]
        if datetime.fromisoformat(row["received_at"]).date().isoformat() == latest_demo_day
    ]
    latest_day_urgent_messages = [
        row
        for row in latest_day_messages
        if classification_by_message[row["id"]]["attention_quadrant"] in {"urgent", "urgent_important"}
    ]
    urgent_failure_rows = [
        row
        for row in latest_day_messages
        if category_by_message[row["id"]] == "서비스"
        and row["subject"] == "[긴급 장애] 현장 네트워크 장비 통신 불안정"
    ]
    assert len(latest_day_urgent_messages) == 9
    assert len(urgent_failure_rows) == 8
    assert all(
        classification_by_message[row["id"]]["attention_quadrant"] == "urgent_important"
        for row in urgent_failure_rows
    )


def test_fake_assignee_seed_rows_render_as_settings_operating_assignees():
    service = DemoSeedService(DemoMailRepository(DEMO_DIR))
    bundle = service.build_seed_bundle(created_at="2026-08-07T00:00:00+00:00")
    capability_by_user: dict[str, list[str]] = {}
    for capability in bundle["assignee_capabilities"]:
        if capability["capability_type"] == "business_type":
            capability_by_user.setdefault(capability["user_id"], []).append(capability["capability_value"])

    views = [
        PostgresAssigneeAdminRepository._view(
            {
                **user,
                "business_types": capability_by_user.get(user["id"], []),
            }
        )
        for user in bundle["users"]
    ]

    assert len(views) == 8
    assert any("발주" in view["mail_categories"] for view in views)
    assert any("문의" in view["mail_categories"] for view in views)
    assert any("서비스" in view["mail_categories"] for view in views)
    assert any("기술" in view["mail_categories"] for view in views)
    assert any("기타" in view["mail_categories"] for view in views)
    by_name = {view["assignee_name"]: view for view in views}
    assert by_name["김민수"]["department"] == "국내영업1팀"
    assert by_name["김민수"]["position"] == "대리"
    assert by_name["박지현"]["department"] == "기술지원팀"
    assert by_name["박지현"]["position"] == "과장"
    assert by_name["최서연"]["department"] == "구매물류팀"
    assert by_name["최서연"]["position"] == "주임"
    assert by_name["강태훈"]["department"] == "업무관리팀"
    assert by_name["강태훈"]["position"] == "팀장"
    assert by_name["강태훈"]["mail_categories"] == ["기타"]
    assert len({view["department"] for view in views}) >= 6
    assert len({view["position"] for view in views}) >= 4
    assert all(view["is_synthetic"] is False for view in views)


def test_postgres_seed_writer_upserts_assignee_capabilities_by_business_key():
    sql = PostgresSeedWriter._upsert_sql(
        "assignee_capabilities",
        ["id", "user_id", "capability_type", "capability_value", "priority", "created_at", "updated_at"],
    )

    assert 'ON CONFLICT ("user_id", "capability_type", "capability_value") DO UPDATE' in sql
    assert '"priority" = EXCLUDED."priority"' in sql
    assert '"id" = EXCLUDED."id"' not in sql


def test_postgres_seed_writer_preserves_existing_user_seed_rows():
    sql = PostgresSeedWriter._upsert_sql(
        "users",
        ["id", "email", "name", "role", "status", "created_at", "updated_at"],
    )

    assert 'ON CONFLICT ("id") DO NOTHING' in sql
    assert '"email" = EXCLUDED."email"' not in sql


def test_postgres_seed_writer_updates_demo_fixture_or_synthetic_routing_assignments_only():
    sql = PostgresSeedWriter._upsert_sql(
        "routing_assignments",
        [
            "id",
            "email_message_id",
            "assignee_user_id",
            "status",
            "assignment_source",
            "forwarded_at",
            "created_at",
            "updated_at",
        ],
    )

    assert 'ON CONFLICT ("email_message_id") DO UPDATE' in sql
    assert '"status" = EXCLUDED."status"' in sql
    assert '"forwarded_at" = EXCLUDED."forwarded_at"' in sql
    assert 'WHERE "routing_assignments"."assignment_source" = \'demo_fixture\'' in sql
    assert "email_accounts.provider = 'synthetic'" in sql
    assert '"id" = EXCLUDED."id"' not in sql


def test_postgres_seed_writer_updates_demo_work_items_by_email_message():
    sql = PostgresSeedWriter._upsert_sql(
        "work_items",
        [
            "id",
            "email_message_id",
            "routing_assignment_id",
            "assignee_user_id",
            "status",
            "assigned_at",
            "due_at",
            "last_activity_at",
            "created_at",
            "updated_at",
        ],
    )

    assert 'ON CONFLICT ("email_message_id") DO UPDATE' in sql
    assert '"status" = EXCLUDED."status"' in sql
    assert '"due_at" = EXCLUDED."due_at"' in sql
    assert '"id" = EXCLUDED."id"' not in sql


def test_postgres_seed_writer_skips_work_items_without_persisted_demo_assignment():
    class Cursor:
        def __init__(self):
            self.executed = []

        def execute(self, sql, params):
            self.executed.append((sql, params))

        def fetchall(self):
            return [("email-kept", "assignment-kept", "user-kept")]

    rows = [
        {
            "email_message_id": "email-kept",
            "routing_assignment_id": "generated-assignment-kept",
            "assignee_user_id": "generated-user-kept",
            "status": "assigned",
        },
        {
            "email_message_id": "email-skipped",
            "routing_assignment_id": "generated-assignment-skipped",
            "assignee_user_id": "generated-user-skipped",
            "status": "assigned",
        },
    ]

    kept = PostgresSeedWriter._work_item_rows_with_persisted_demo_assignments(Cursor(), rows)

    assert kept == [
        {
            "email_message_id": "email-kept",
            "routing_assignment_id": "assignment-kept",
            "assignee_user_id": "user-kept",
            "status": "assigned",
        }
    ]


def test_postgres_seed_writer_skips_capabilities_for_locally_edited_seed_users():
    class Cursor:
        def __init__(self):
            self.executed = []

        def execute(self, sql, params):
            self.executed.append((sql, params))

        def fetchall(self):
            return [("user-edited",)]

    rows = [
        {"id": "cap-1", "user_id": "user-edited", "capability_type": "business_type", "capability_value": "quote"},
        {"id": "cap-2", "user_id": "user-seeded", "capability_type": "business_type", "capability_value": "order"},
    ]

    kept = PostgresSeedWriter._rows_after_preserving_local_assignee_edits(
        Cursor(),
        "assignee_capabilities",
        rows,
    )

    assert kept == [rows[1]]


def test_postgres_seed_writer_rejects_missing_business_key_columns():
    try:
        PostgresSeedWriter._upsert_sql(
            "assignee_capabilities",
            ["id", "user_id", "capability_type", "priority", "created_at", "updated_at"],
        )
    except PostgresSeedWriterError as exc:
        assert "capability_value" in str(exc)
    else:
        raise AssertionError("expected missing seed conflict column to fail")

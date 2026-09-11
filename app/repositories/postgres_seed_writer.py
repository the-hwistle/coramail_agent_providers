from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence


class PostgresSeedWriterError(RuntimeError):
    pass


TABLE_ORDER = (
    "categories",
    "users",
    "assignee_capabilities",
    "routing_rules",
    "email_accounts",
    "email_messages",
    "email_recipients",
    "email_attachments",
    "email_category_assignments",
    "email_analysis_results",
    "mail_decision_runs",
    "routing_assignments",
    "work_items",
    "processing_jobs",
)


JSONB_COLUMNS = {
    ("users", "notification_preferences"),
    ("email_analysis_results", "result_json"),
    ("mail_decision_runs", "state_json"),
    ("processing_jobs", "metadata"),
}

UPSERT_CONFLICT_COLUMNS = {
    "assignee_capabilities": ("user_id", "capability_type", "capability_value"),
    "routing_assignments": ("email_message_id",),
    "work_items": ("email_message_id",),
}

PRESERVE_EXISTING_TABLES = {"users"}


@dataclass(frozen=True)
class SeedWriteResult:
    table_counts: dict[str, int]

    @property
    def total_rows(self) -> int:
        return sum(self.table_counts.values())


class PostgresSeedWriter:
    """Writes deterministic demo seed bundles into an existing PostgreSQL schema."""

    def __init__(self, database_url: str):
        self.database_url = database_url

    def write_bundle(self, bundle: Mapping[str, Sequence[Mapping[str, Any]]]) -> SeedWriteResult:
        psycopg, json_adapter = self._load_psycopg()
        table_counts: dict[str, int] = {}

        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    self._delete_stale_synthetic_messages(cursor, bundle)
                    for table in TABLE_ORDER:
                        rows = list(bundle.get(table, ()))
                        if not rows:
                            table_counts[table] = 0
                            continue
                        table_counts[table] = self._upsert_rows(cursor, table, rows, json_adapter)

        return SeedWriteResult(table_counts=table_counts)

    @staticmethod
    def _delete_stale_synthetic_messages(cursor: Any, bundle: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
        synthetic_account_ids = {
            str(row.get("id") or "")
            for row in bundle.get("email_accounts", ())
            if str(row.get("provider") or "") == "synthetic" and row.get("id")
        }
        if not synthetic_account_ids:
            return

        message_ids = {
            str(row.get("id") or "")
            for row in bundle.get("email_messages", ())
            if str(row.get("email_account_id") or "") in synthetic_account_ids and row.get("id")
        }
        if not message_ids:
            return

        cursor.execute(
            """
            DELETE FROM email_messages
            WHERE email_account_id = ANY(%(account_ids)s::uuid[])
              AND NOT (id = ANY(%(message_ids)s::uuid[]))
            """,
            {"account_ids": sorted(synthetic_account_ids), "message_ids": sorted(message_ids)},
        )

    @staticmethod
    def _load_psycopg() -> tuple[Any, Any]:
        try:
            import psycopg
            from psycopg.types.json import Jsonb
        except ImportError as exc:
            raise PostgresSeedWriterError(
                "PostgreSQL seed loading requires psycopg. Install psycopg in the runtime environment first."
            ) from exc
        return psycopg, Jsonb

    def _upsert_rows(self, cursor: Any, table: str, rows: Sequence[Mapping[str, Any]], json_adapter: Any) -> int:
        rows = self._rows_after_preserving_local_assignee_edits(cursor, table, rows)
        if not rows:
            return 0
        columns = self._columns_for_rows(rows)
        self._retire_conflicting_current_rows(cursor, table, rows)
        sql = self._upsert_sql(table, columns)
        values = [self._row_values(table, row, columns, json_adapter) for row in rows]
        cursor.executemany(sql, values)
        return len(rows)

    @staticmethod
    def _rows_after_preserving_local_assignee_edits(
        cursor: Any, table: str, rows: Sequence[Mapping[str, Any]]
    ) -> list[Mapping[str, Any]]:
        if table == "work_items":
            return PostgresSeedWriter._work_item_rows_with_persisted_demo_assignments(cursor, rows)
        if table not in {"assignee_capabilities", "routing_rules"}:
            return list(rows)

        user_column = "user_id" if table == "assignee_capabilities" else "assignee_user_id"
        user_ids = sorted({str(row.get(user_column) or "") for row in rows if row.get(user_column)})
        if not user_ids:
            return list(rows)

        cursor.execute(
            """
            SELECT id::text
            FROM users
            WHERE id::text = ANY(%(user_ids)s)
              AND COALESCE(notification_preferences->>'seed_source', '') = ''
            """,
            {"user_ids": user_ids},
        )
        locally_edited_user_ids = {str(row[0]) for row in cursor.fetchall()}
        if not locally_edited_user_ids:
            return list(rows)
        return [row for row in rows if str(row.get(user_column) or "") not in locally_edited_user_ids]

    @staticmethod
    def _work_item_rows_with_persisted_demo_assignments(
        cursor: Any,
        rows: Sequence[Mapping[str, Any]],
    ) -> list[Mapping[str, Any]]:
        email_ids = sorted({str(row.get("email_message_id") or "") for row in rows if row.get("email_message_id")})
        if not email_ids:
            return []
        cursor.execute(
            """
            SELECT email_message_id::text, id::text, assignee_user_id::text
            FROM routing_assignments
            WHERE email_message_id::text = ANY(%(email_ids)s)
              AND assignment_source = 'demo_fixture'
            """,
            {"email_ids": email_ids},
        )
        assignments_by_email = {
            str(email_id): {"routing_assignment_id": str(assignment_id), "assignee_user_id": str(assignee_user_id)}
            for email_id, assignment_id, assignee_user_id in cursor.fetchall()
        }
        kept_rows: list[Mapping[str, Any]] = []
        for row in rows:
            assignment = assignments_by_email.get(str(row.get("email_message_id") or ""))
            if not assignment:
                continue
            kept_rows.append(dict(row) | assignment)
        return kept_rows

    @staticmethod
    def _retire_conflicting_current_rows(cursor: Any, table: str, rows: Sequence[Mapping[str, Any]]) -> None:
        if table == "email_category_assignments":
            for row in rows:
                if not row.get("is_current"):
                    continue
                cursor.execute(
                    """
                    UPDATE email_category_assignments
                    SET is_current = FALSE
                    WHERE email_message_id = %(email_message_id)s
                      AND is_current IS TRUE
                      AND id <> %(id)s
                    """,
                    {"email_message_id": row.get("email_message_id"), "id": row.get("id")},
                )
        elif table == "email_analysis_results":
            for row in rows:
                if not row.get("is_current"):
                    continue
                cursor.execute(
                    """
                    UPDATE email_analysis_results
                    SET is_current = FALSE
                    WHERE email_message_id = %(email_message_id)s
                      AND analysis_type = %(analysis_type)s
                      AND is_current IS TRUE
                      AND id <> %(id)s
                    """,
                    {
                        "email_message_id": row.get("email_message_id"),
                        "analysis_type": row.get("analysis_type"),
                        "id": row.get("id"),
                    },
                )

    @staticmethod
    def _columns_for_rows(rows: Sequence[Mapping[str, Any]]) -> list[str]:
        first_row = rows[0]
        return list(first_row.keys())

    @staticmethod
    def _row_values(table: str, row: Mapping[str, Any], columns: Sequence[str], json_adapter: Any) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for column in columns:
            value = row.get(column)
            if (table, column) in JSONB_COLUMNS and value is not None:
                values[column] = json_adapter(value)
            else:
                values[column] = value
        return values

    @staticmethod
    def _upsert_sql(table: str, columns: Sequence[str]) -> str:
        quoted_columns = ", ".join(_quote_identifier(column) for column in columns)
        placeholders = ", ".join(f"%({column})s" for column in columns)
        conflict_columns = UPSERT_CONFLICT_COLUMNS.get(table, ("id",))
        missing_conflict_columns = set(conflict_columns) - set(columns)
        if missing_conflict_columns:
            missing = ", ".join(sorted(missing_conflict_columns))
            raise PostgresSeedWriterError(f"seed rows for {table} are missing conflict column(s): {missing}")

        update_columns = [column for column in columns if column != "id" and column not in conflict_columns]
        conflict_target = ", ".join(_quote_identifier(column) for column in conflict_columns)
        if table in PRESERVE_EXISTING_TABLES:
            return (
                f"INSERT INTO {_quote_identifier(table)} ({quoted_columns}) "
                f"VALUES ({placeholders}) "
                f"ON CONFLICT ({conflict_target}) DO NOTHING"
            )
        if table == "routing_assignments":
            update_clause = ", ".join(
                f"{_quote_identifier(column)} = EXCLUDED.{_quote_identifier(column)}" for column in update_columns
            )
            return (
                f"INSERT INTO {_quote_identifier(table)} ({quoted_columns}) "
                f"VALUES ({placeholders}) "
                f"ON CONFLICT ({conflict_target}) DO UPDATE SET {update_clause} "
                f"WHERE {_quote_identifier(table)}.{_quote_identifier('assignment_source')} = 'demo_fixture' "
                f"OR {_quote_identifier(table)}.{_quote_identifier('email_message_id')} IN ("
                "SELECT email_messages.id "
                "FROM email_messages "
                "JOIN email_accounts ON email_accounts.id = email_messages.email_account_id "
                "WHERE email_accounts.provider = 'synthetic'"
                ")"
            )
        update_clause = ", ".join(
            f"{_quote_identifier(column)} = EXCLUDED.{_quote_identifier(column)}" for column in update_columns
        )
        if not update_clause:
            update_clause = f"{_quote_identifier(conflict_columns[0])} = EXCLUDED.{_quote_identifier(conflict_columns[0])}"
        return (
            f"INSERT INTO {_quote_identifier(table)} ({quoted_columns}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_target}) DO UPDATE SET {update_clause}"
        )


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def ordered_table_counts(bundle: Mapping[str, Iterable[Mapping[str, Any]]]) -> dict[str, int]:
    return {table: len(list(bundle.get(table, ()))) for table in TABLE_ORDER}

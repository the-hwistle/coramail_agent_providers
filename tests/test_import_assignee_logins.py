from __future__ import annotations

from app.tools.import_assignee_logins import _apply_login_rows


class CursorStub:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.rowcount = 0
        self._fetch_values = [2, 8]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql: str, params=None) -> None:
        self.statements.append(sql)
        if "UPDATE users AS u" in sql:
            self.rowcount = 2

    def executemany(self, sql: str, rows) -> None:
        self.statements.append(sql)
        self.inserted_rows = list(rows)

    def fetchone(self):
        return (self._fetch_values.pop(0),)


class ConnectionStub:
    def __init__(self, cursor: CursorStub) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def transaction(self):
        return self

    def cursor(self):
        return self._cursor


class PsycopgStub:
    def __init__(self, cursor: CursorStub) -> None:
        self.cursor = cursor

    def connect(self, database_url: str):
        self.database_url = database_url
        return ConnectionStub(self.cursor)


def test_apply_login_rows_updates_only_login_fields():
    cursor = CursorStub()
    psycopg = PsycopgStub(cursor)

    result = _apply_login_rows(
        psycopg,
        "postgresql://target",
        [
            {"id": "10000000-0000-0000-0000-000000000001", "username": "m.kim@example.com", "password_hash": "hash"},
            {"id": "10000000-0000-0000-0000-000000000002", "username": "s.yoon@example.com", "password_hash": "hash2"},
        ],
        dry_run=False,
    )

    update_sql = next(statement for statement in cursor.statements if "UPDATE users AS u" in statement)
    assert "SET username = i.username" in update_sql
    assert "password_hash = i.password_hash" in update_sql
    assert "email =" not in update_sql
    assert "\n                            name =" not in update_sql
    assert result.source_users == 2
    assert result.matched_target_users == 2
    assert result.updated_target_users == 2
    assert result.login_ready_users == 8


def test_apply_login_rows_dry_run_does_not_update_users():
    cursor = CursorStub()
    psycopg = PsycopgStub(cursor)

    result = _apply_login_rows(
        psycopg,
        "postgresql://target",
        [{"id": "10000000-0000-0000-0000-000000000001", "username": "m.kim@example.com", "password_hash": "hash"}],
        dry_run=True,
    )

    assert not any("UPDATE users AS u" in statement for statement in cursor.statements)
    assert result.source_users == 1
    assert result.updated_target_users == 0

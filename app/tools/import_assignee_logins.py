from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class LoginImportResult:
    source_users: int
    matched_target_users: int
    updated_target_users: int
    login_ready_users: int

    @property
    def missing_target_users(self) -> int:
        return max(self.source_users - self.matched_target_users, 0)


def import_assignee_logins(
    *,
    source_database_url: str,
    target_database_url: str,
    dry_run: bool = False,
) -> LoginImportResult:
    source_database_url = source_database_url.strip()
    target_database_url = target_database_url.strip()
    if not source_database_url:
        raise ValueError("source_database_url is required")
    if not target_database_url:
        raise ValueError("target_database_url is required")

    psycopg = _load_psycopg()
    source_rows = _load_source_login_rows(psycopg, source_database_url)
    return _apply_login_rows(psycopg, target_database_url, source_rows, dry_run=dry_run)


def _load_source_login_rows(psycopg: Any, source_database_url: str) -> list[dict[str, str]]:
    from psycopg.rows import dict_row

    with psycopg.connect(source_database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::text AS id,
                       COALESCE(NULLIF(username, ''), email)::text AS username,
                       password_hash::text AS password_hash
                FROM users
                WHERE deleted_at IS NULL
                  AND status = 'active'
                  AND password_hash IS NOT NULL
                  AND COALESCE(NULLIF(username, ''), email) IS NOT NULL
                ORDER BY id
                """
            )
            return [dict(row) for row in cursor.fetchall()]


def _apply_login_rows(
    psycopg: Any,
    target_database_url: str,
    source_rows: Sequence[dict[str, str]],
    *,
    dry_run: bool,
) -> LoginImportResult:
    with psycopg.connect(target_database_url) as conn:
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TEMP TABLE imported_login_users (
                        id UUID PRIMARY KEY,
                        username TEXT NOT NULL,
                        password_hash TEXT NOT NULL
                    ) ON COMMIT DROP
                    """
                )
                if source_rows:
                    cursor.executemany(
                        """
                        INSERT INTO imported_login_users (id, username, password_hash)
                        VALUES (%(id)s, %(username)s, %(password_hash)s)
                        """,
                        list(source_rows),
                    )
                matched_target_users = _single_int(
                    cursor,
                    """
                    SELECT COUNT(*)
                    FROM users u
                    JOIN imported_login_users i ON i.id = u.id
                    WHERE u.deleted_at IS NULL
                      AND u.status = 'active'
                    """,
                )
                updated_target_users = 0
                if not dry_run:
                    cursor.execute(
                        """
                        UPDATE users AS u
                        SET username = i.username,
                            password_hash = i.password_hash,
                            updated_at = now()
                        FROM imported_login_users AS i
                        WHERE u.id = i.id
                          AND u.deleted_at IS NULL
                          AND u.status = 'active'
                          AND (
                            u.username IS DISTINCT FROM i.username
                            OR u.password_hash IS DISTINCT FROM i.password_hash
                          )
                        """,
                    )
                    updated_target_users = int(cursor.rowcount or 0)
                login_ready_users = _single_int(
                    cursor,
                    """
                    SELECT COUNT(*)
                    FROM users
                    WHERE deleted_at IS NULL
                      AND status = 'active'
                      AND username IS NOT NULL
                      AND password_hash IS NOT NULL
                    """,
                )
    return LoginImportResult(
        source_users=len(source_rows),
        matched_target_users=matched_target_users,
        updated_target_users=updated_target_users,
        login_ready_users=login_ready_users,
    )


def _single_int(cursor: Any, sql: str) -> int:
    cursor.execute(sql)
    row = cursor.fetchone()
    if row is None:
        return 0
    return int(row[0])


def _load_psycopg() -> Any:
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Importing assignee logins requires psycopg in the runtime environment.") from exc
    return psycopg


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Copy assignee login usernames and password hashes from another CoRA Mail PostgreSQL database."
    )
    parser.add_argument(
        "--source-database-url",
        default=os.getenv("CORAMAIL_LOGIN_IMPORT_SOURCE_DATABASE_URL", ""),
        help="Source PostgreSQL URL. Defaults to CORAMAIL_LOGIN_IMPORT_SOURCE_DATABASE_URL.",
    )
    parser.add_argument(
        "--target-database-url",
        default=os.getenv("CORAMAIL_DATABASE_URL", ""),
        help="Target PostgreSQL URL. Defaults to CORAMAIL_DATABASE_URL.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Count matching users without updating target rows.")
    args = parser.parse_args(argv)

    result = import_assignee_logins(
        source_database_url=args.source_database_url,
        target_database_url=args.target_database_url,
        dry_run=args.dry_run,
    )
    print(
        "source_users={source_users} matched_target_users={matched_target_users} "
        "updated_target_users={updated_target_users} missing_target_users={missing_target_users} "
        "login_ready_users={login_ready_users}".format(
            source_users=result.source_users,
            matched_target_users=result.matched_target_users,
            updated_target_users=result.updated_target_users,
            missing_target_users=result.missing_target_users,
            login_ready_users=result.login_ready_users,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row


class PostgresUserRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url.strip()

    @property
    def enabled(self) -> bool:
        return bool(self.database_url)

    def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        user = self.find_login_user(username)
        if not user or not user.get("password_hash"):
            return None
        if not verify_password(password, str(user["password_hash"])):
            return None
        self.mark_login(UUID(str(user["id"])))
        return user

    def find_login_user(self, username: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        import psycopg

        value = username.strip().casefold()
        try:
            with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT id, username, email, name, role, status, password_hash
                        FROM users
                        WHERE deleted_at IS NULL
                          AND status = 'active'
                          AND (
                            lower(COALESCE(username, '')) = %(value)s
                            OR lower(email) = %(value)s
                          )
                        LIMIT 1
                        """,
                        {"value": value},
                    )
                    row = cursor.fetchone()
        except Exception as exc:
            if type(exc).__name__ in {"UndefinedColumn", "UndefinedTable"}:
                return None
            raise
        return dict(row) if row else None

    def user_by_login(self, username: str) -> dict[str, Any] | None:
        user = self.find_login_user(username)
        if user:
            user.pop("password_hash", None)
        return user

    def mark_login(self, user_id: UUID) -> None:
        if not self.enabled:
            return
        import psycopg

        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE users
                    SET last_login_at = %(last_login_at)s,
                        updated_at = %(updated_at)s
                    WHERE id = %(id)s
                    """,
                    {"id": user_id, "last_login_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)},
                )


def hash_password(password: str, *, iterations: int = 210_000) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${iterations}${salt}${digest}".format(
        iterations=iterations,
        salt=base64.urlsafe_b64encode(salt).decode("ascii"),
        digest=base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)

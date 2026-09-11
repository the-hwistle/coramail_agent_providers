from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.request import Request, urlopen
from uuid import UUID, uuid5

from psycopg.types.json import Jsonb

SEED_NAMESPACE = UUID("2fc41bcb-51eb-4f8a-92df-47a62cf0bc0d")


class SyntheticEvaluationLoader:
    def __init__(self, *, database_url: str, qdrant_url: str, collection: str, embedder):
        self.database_url = database_url.strip()
        self.qdrant_url = qdrant_url.rstrip("/")
        self.collection = collection
        self.embedder = embedder

    def load(self, dataset: dict[str, Any]) -> dict[str, int]:
        counts = self._load_postgres(dataset)
        counts["qdrant_cases"] = self._load_qdrant(dataset.get("qdrant_cases") or [])
        return counts

    def _load_postgres(self, dataset: dict[str, Any]) -> dict[str, int]:
        import psycopg

        now = datetime.now(timezone.utc)
        account_id = uuid5(SEED_NAMESPACE, "synthetic-email-account")
        counts: dict[str, int] = {}
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    assignees = list(dataset.get("assignees") or [])
                    assignee_ids = [UUID(str(user["id"])) for user in assignees]
                    cursor.execute(
                        """
                        UPDATE users
                        SET status = 'inactive', updated_at = %s
                        WHERE email LIKE '%%@coramail.invalid'
                          AND NOT (id = ANY(%s))
                          AND status <> 'inactive'
                        """,
                        (now, assignee_ids),
                    )
                    counts["inactive_synthetic_assignees"] = cursor.rowcount
                    if assignee_ids:
                        cursor.execute(
                            "DELETE FROM assignee_capabilities WHERE user_id = ANY(%s)",
                            (assignee_ids,),
                        )
                    cursor.execute(
                        """
                        INSERT INTO email_accounts (
                            id, provider, email_address, display_name, status, created_at, updated_at
                        ) VALUES (%s, 'synthetic', 'evaluation@coramail.invalid', 'Synthetic Evaluation', 'active', %s, %s)
                        ON CONFLICT (provider, email_address) DO UPDATE SET updated_at = EXCLUDED.updated_at
                        """,
                        (account_id, now, now),
                    )
                    for user in assignees:
                        cursor.execute(
                            """
                            INSERT INTO users (id, email, name, role, status, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (id) DO UPDATE SET
                                email = EXCLUDED.email, name = EXCLUDED.name, role = EXCLUDED.role,
                                status = EXCLUDED.status, updated_at = EXCLUDED.updated_at
                            """,
                            (user["id"], user["email"], user["name"], user["role"], user["status"], now, now),
                        )
                    counts["assignees"] = len(assignees)
                    for capability in dataset.get("assignee_capabilities") or []:
                        cursor.execute(
                            """
                            INSERT INTO assignee_capabilities (
                                id, user_id, capability_type, capability_value, priority, created_at, updated_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (user_id, capability_type, capability_value) DO UPDATE SET
                                priority = EXCLUDED.priority, updated_at = EXCLUDED.updated_at
                            """,
                            (
                                capability["id"], capability["user_id"], capability["capability_type"],
                                capability["capability_value"], capability["priority"], now, now,
                            ),
                        )
                    counts["capabilities"] = len(dataset.get("assignee_capabilities") or [])
                    for email in dataset.get("emails") or []:
                        content_hash = __import__("hashlib").sha256(email["body_text"].encode("utf-8")).hexdigest()
                        cursor.execute(
                            """
                            INSERT INTO email_messages (
                                id, email_account_id, provider_message_id, sender_name, sender_address,
                                subject, body_text, snippet, sent_at, received_at, has_attachment,
                                attachment_count, processing_status, content_hash, created_at, updated_at
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                FALSE, 0, 'pending', %s, %s, %s
                            )
                            ON CONFLICT (email_account_id, provider_message_id) DO UPDATE SET
                                subject = EXCLUDED.subject, body_text = EXCLUDED.body_text,
                                sender_address = EXCLUDED.sender_address, updated_at = EXCLUDED.updated_at
                            """,
                            (
                                email["id"], account_id, email["provider_message_id"], email["sender_name"],
                                email["sender_address"], email["subject"], email["body_text"], email["body_text"][:240],
                                now, now, content_hash, now, now,
                            ),
                        )
                    counts["emails"] = len(dataset.get("emails") or [])
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS evaluation_ground_truth (
                            email_message_id UUID PRIMARY KEY REFERENCES email_messages(id) ON DELETE CASCADE,
                            truth_json JSONB NOT NULL,
                            dataset_seed INTEGER NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL,
                            updated_at TIMESTAMPTZ NOT NULL
                        )
                        """
                    )
                    seed = int(dataset.get("metadata", {}).get("seed") or 0)
                    for truth in dataset.get("ground_truth") or []:
                        cursor.execute(
                            """
                            INSERT INTO evaluation_ground_truth (
                                email_message_id, truth_json, dataset_seed, created_at, updated_at
                            ) VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (email_message_id) DO UPDATE SET
                                truth_json = EXCLUDED.truth_json, dataset_seed = EXCLUDED.dataset_seed,
                                updated_at = EXCLUDED.updated_at
                            """,
                            (truth["email_message_id"], Jsonb(truth), seed, now, now),
                        )
                    counts["ground_truth"] = len(dataset.get("ground_truth") or [])
        return counts

    def _load_qdrant(self, cases: list[dict[str, Any]]) -> int:
        if not cases:
            return 0
        self._ensure_collection()
        vectors = self.embedder([case["text"] for case in cases])
        points = [
            {
                "id": case["id"],
                "vector": vector,
                "payload": {
                    **case["payload"],
                    "provider": str(case.get("payload", {}).get("provider") or "synthetic"),
                    "dataset_type": str(case.get("payload", {}).get("dataset_type") or "evaluation"),
                    "evaluation": bool(case.get("payload", {}).get("evaluation", True)),
                    "text": case["text"],
                },
            }
            for case, vector in zip(cases, vectors, strict=True)
        ]
        self._request("PUT", f"/collections/{self.collection}/points?wait=true", {"points": points})
        return len(points)

    def _ensure_collection(self) -> None:
        try:
            self._request("GET", f"/collections/{self.collection}")
            return
        except RuntimeError:
            probe = self.embedder(["dimension probe"])[0]
            self._request(
                "PUT",
                f"/collections/{self.collection}",
                {"vectors": {"size": len(probe), "distance": "Cosine"}},
            )

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.qdrant_url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=120) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except Exception as exc:
            raise RuntimeError(f"Qdrant request failed: {method} {path}: {exc}") from exc

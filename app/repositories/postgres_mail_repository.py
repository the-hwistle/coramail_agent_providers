from __future__ import annotations

from pathlib import Path
from typing import Any

from psycopg.rows import dict_row


class PostgresMailRepository:
    def __init__(self, database_url: str, project_dir: Path, *, provider: str = ""):
        self.database_url = database_url
        self.project_dir = project_dir
        self.provider = provider.strip().casefold()

    def list_messages(self, *, q: str = "", category: str = "", limit: int | None = None) -> list[dict[str, Any]]:
        query = " ".join(q.split()).casefold()
        rows = self._fetch_message_rows(limit=None if query or category else limit)
        if query:
            rows = [
                row
                for row in rows
                if query
                in " ".join(
                    [
                        str(row.get("sender_name") or ""),
                        str(row.get("sender_address") or ""),
                        str(row.get("subject") or ""),
                        str(row.get("snippet") or ""),
                        str(row.get("body_text") or ""),
                        str(row.get("mail_category") or ""),
                    ]
                ).casefold()
            ]
        if category:
            rows = [row for row in rows if str(row.get("mail_category") or "미분류") == category]
        return rows[:limit] if limit else rows

    def message_by_index(self, index: int) -> dict[str, Any] | None:
        rows = self.list_messages()
        if index < 0 or index >= len(rows):
            return None
        return rows[index]

    def message_by_uid(self, email_uid: str) -> tuple[int, dict[str, Any]] | None:
        for index, row in enumerate(self._fetch_message_rows(limit=None)):
            if str(row.get("id") or "") == email_uid:
                return index, row
        return None

    def recipients_for_message(self, email_message_id: str) -> list[dict[str, Any]]:
        sql = """
            SELECT id, email_message_id, recipient_type, name, address, created_at
            FROM email_recipients
            WHERE email_message_id = %(email_message_id)s
            ORDER BY recipient_type, address
        """
        return self._fetch_all(sql, {"email_message_id": email_message_id})

    def attachments_for_message(self, email_message_id: str, *, include_inline: bool = False) -> list[dict[str, Any]]:
        inline_clause = "" if include_inline else self._visible_attachment_clause()
        sql = """
            SELECT
                a.id,
                a.email_message_id,
                a.provider_attachment_id,
                a.filename,
                a.storage_uri,
                a.content_type,
                a.content_id,
                a.content_disposition,
                a.file_group,
                a.file_size,
                a.checksum,
                a.is_inline,
                a.document_category_id,
                a.processing_status,
                a.parse_error,
                a.created_at,
                a.updated_at,
                a.deleted_at,
                ar.status AS analysis_status,
                ar.result_text AS analysis_result_text,
                ar.result_json AS analysis_result_json,
                ar.error_message AS analysis_error_message,
                ar.model_name AS analysis_model_name,
                ar.updated_at AS analysis_updated_at
            FROM email_attachments a
            JOIN email_messages m ON m.id = a.email_message_id
            LEFT JOIN attachment_analysis_results ar
                ON ar.attachment_id = a.id
               AND ar.analysis_type = 'document_understanding'
               AND ar.is_current IS TRUE
            WHERE a.email_message_id = %(email_message_id)s
              AND a.deleted_at IS NULL
              {inline_clause}
            ORDER BY a.is_inline DESC, a.filename
        """.format(inline_clause=inline_clause)
        return self._fetch_all(sql, {"email_message_id": email_message_id})

    def attachments_for_messages(
        self,
        email_message_ids: list[str],
        *,
        include_inline: bool = False,
    ) -> list[dict[str, Any]]:
        if not email_message_ids:
            return []
        inline_clause = "" if include_inline else self._visible_attachment_clause()
        sql = """
            SELECT
                a.id,
                a.email_message_id,
                a.provider_attachment_id,
                a.filename,
                a.storage_uri,
                a.content_type,
                a.content_id,
                a.content_disposition,
                a.file_group,
                a.file_size,
                a.checksum,
                a.is_inline,
                a.document_category_id,
                a.processing_status,
                a.parse_error,
                a.created_at,
                a.updated_at,
                a.deleted_at,
                ar.status AS analysis_status,
                ar.result_text AS analysis_result_text,
                ar.result_json AS analysis_result_json,
                ar.error_message AS analysis_error_message,
                ar.model_name AS analysis_model_name,
                ar.updated_at AS analysis_updated_at
            FROM email_attachments a
            JOIN email_messages m ON m.id = a.email_message_id
            LEFT JOIN attachment_analysis_results ar
                ON ar.attachment_id = a.id
               AND ar.analysis_type = 'document_understanding'
               AND ar.is_current IS TRUE
            WHERE a.email_message_id = ANY(%(email_message_ids)s::uuid[])
              AND a.deleted_at IS NULL
              {inline_clause}
            ORDER BY a.email_message_id, a.is_inline DESC, a.filename
        """.format(inline_clause=inline_clause)
        return self._fetch_all(sql, {"email_message_ids": email_message_ids})

    @staticmethod
    def _visible_attachment_clause() -> str:
        return """
              AND a.is_inline IS FALSE
              AND NOT (
                  LEFT(LOWER(COALESCE(a.content_type, '')), 6) = 'image/'
                  AND NULLIF(BTRIM(BTRIM(COALESCE(a.content_id, ''), '<>')), '') IS NOT NULL
                  AND POSITION(
                      LOWER('cid:' || BTRIM(BTRIM(COALESCE(a.content_id, ''), '<>')))
                      IN LOWER(COALESCE(m.body_html, ''))
                  ) > 0
              )
        """

    def search_documents(self) -> list[dict[str, Any]]:
        sql = """
            SELECT
                m.id AS email_uid,
                'mail' AS source_type,
                COALESCE(NULLIF(m.subject, ''), '(제목 없음)') AS source,
                COALESCE(m.subject, '') AS title,
                COALESCE(c.name, '미분류') AS category,
                '' AS document_category,
                CONCAT_WS(' ', m.subject, m.body_text, m.snippet, summary_result.result_text,
                          classification_result.result_json::text, mf.facts_json::text,
                          CASE
                            WHEN assignee.name IS NOT NULL
                            THEN CONCAT('현재 담당자: ', assignee.name, ' 라우팅 상태: ', COALESCE(ra.status, ''))
                            ELSE NULL
                          END) AS preview,
                CONCAT_WS(' ', m.sender_name, m.sender_address) AS sender,
                COALESCE(classification_result.result_json->'business_refs', '[]'::jsonb) AS business_refs,
                COALESCE(classification_result.result_json->'vessel_names', '[]'::jsonb) AS vessel_names,
                m.received_at
            FROM email_messages m
            JOIN email_accounts account ON account.id = m.email_account_id
            LEFT JOIN email_category_assignments eca
              ON eca.email_message_id = m.id AND eca.is_current IS TRUE
            LEFT JOIN categories c ON c.id = eca.category_id
            LEFT JOIN email_analysis_results classification_result
              ON classification_result.email_message_id = m.id
             AND classification_result.analysis_type = 'classification'
             AND classification_result.is_current IS TRUE
            LEFT JOIN email_analysis_results summary_result
              ON summary_result.email_message_id = m.id
             AND summary_result.analysis_type = 'executive_summary'
             AND summary_result.is_current IS TRUE
            LEFT JOIN mail_facts mf
              ON mf.email_message_id = m.id AND mf.is_current IS TRUE
            LEFT JOIN routing_assignments ra
              ON ra.email_message_id = m.id
            LEFT JOIN users assignee
              ON assignee.id = ra.assignee_user_id
            WHERE m.deleted_at IS NULL
              AND (%(provider)s = '' OR account.provider = %(provider)s)

            UNION ALL

            SELECT
                m.id AS email_uid,
                'attachment' AS source_type,
                COALESCE(NULLIF(a.filename, ''), 'attachment') AS source,
                COALESCE(m.subject, '') AS title,
                COALESCE(c.name, '미분류') AS category,
                COALESCE(ar.result_json->>'document_type', '') AS document_category,
                CONCAT_WS(' ', a.filename, ar.result_text, ar.result_json::text, mf.facts_json::text,
                          CASE
                            WHEN assignee.name IS NOT NULL
                            THEN CONCAT('현재 담당자: ', assignee.name, ' 라우팅 상태: ', COALESCE(ra.status, ''))
                            ELSE NULL
                          END) AS preview,
                CONCAT_WS(' ', m.sender_name, m.sender_address) AS sender,
                COALESCE(classification_result.result_json->'business_refs', '[]'::jsonb) AS business_refs,
                COALESCE(classification_result.result_json->'vessel_names', '[]'::jsonb) AS vessel_names,
                m.received_at
            FROM email_attachments a
            JOIN email_messages m ON m.id = a.email_message_id
            JOIN email_accounts account ON account.id = m.email_account_id
            LEFT JOIN attachment_analysis_results ar
              ON ar.attachment_id = a.id
             AND ar.analysis_type = 'document_understanding'
             AND ar.is_current IS TRUE
            LEFT JOIN email_category_assignments eca
              ON eca.email_message_id = m.id AND eca.is_current IS TRUE
            LEFT JOIN categories c ON c.id = eca.category_id
            LEFT JOIN email_analysis_results classification_result
              ON classification_result.email_message_id = m.id
             AND classification_result.analysis_type = 'classification'
             AND classification_result.is_current IS TRUE
            LEFT JOIN mail_facts mf
              ON mf.email_message_id = m.id AND mf.is_current IS TRUE
            LEFT JOIN routing_assignments ra
              ON ra.email_message_id = m.id
            LEFT JOIN users assignee
              ON assignee.id = ra.assignee_user_id
            WHERE m.deleted_at IS NULL
              AND a.deleted_at IS NULL
              AND a.is_inline IS FALSE
              AND (%(provider)s = '' OR account.provider = %(provider)s)
            ORDER BY received_at DESC NULLS LAST
        """
        rows = self._fetch_all(sql, {"provider": self.provider})
        for row in rows:
            row["detail_url"] = f"/ui/inbox?email_uid={row['email_uid']}"
        return rows

    def attachment_path(self, attachment: dict[str, Any]) -> Path:
        storage_uri = str(attachment.get("storage_uri") or "")
        path = Path(storage_uri)
        if not path.is_absolute():
            path = self.project_dir / path
        return path.resolve()

    def provider_message_id(self, email_message_id: str) -> str | None:
        rows = self._fetch_all(
            """
            SELECT provider_message_id
            FROM email_messages
            WHERE id = %(id)s AND deleted_at IS NULL
            """,
            {"id": email_message_id},
        )
        return str(rows[0]["provider_message_id"]) if rows else None

    def mark_trashed(self, email_message_id: str) -> None:
        import psycopg

        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE email_messages
                        SET deleted_at = now(), updated_at = now()
                        WHERE id = %(id)s AND deleted_at IS NULL
                        """,
                        {"id": email_message_id},
                    )

    def _fetch_message_rows(self, *, limit: int | None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "provider": self.provider}
        limit_clause = "LIMIT %(limit)s" if limit else ""
        provider_clause = "AND account.provider = %(provider)s" if self.provider else ""
        if self._work_tracking_available():
            work_columns = """
                wi.id AS work_item_id,
                wi.status AS work_item_status,
                wi.assigned_at AS work_item_assigned_at,
                wi.acknowledged_at AS work_item_acknowledged_at,
                wi.reply_initiated_at AS work_item_reply_initiated_at,
                wi.first_responded_at AS work_item_first_responded_at,
                wi.responded_at AS work_item_responded_at,
                wi.completed_at AS work_item_completed_at,
                wi.due_at AS work_item_due_at,
                wi.last_activity_at AS work_item_last_activity_at,
            """
            work_join = "LEFT JOIN work_items wi ON wi.email_message_id = m.id"
        else:
            work_columns = """
                NULL AS work_item_id,
                NULL AS work_item_status,
                NULL AS work_item_assigned_at,
                NULL AS work_item_acknowledged_at,
                NULL AS work_item_reply_initiated_at,
                NULL AS work_item_first_responded_at,
                NULL AS work_item_responded_at,
                NULL AS work_item_completed_at,
                NULL AS work_item_due_at,
                NULL AS work_item_last_activity_at,
            """
            work_join = ""
        sql = f"""
            SELECT
                m.id,
                m.email_account_id,
                m.provider_message_id,
                m.provider_thread_id,
                m.rfc_message_id,
                m.sender_name,
                m.sender_address,
                m.subject,
                m.subject_normalized,
                m.body_text,
                m.body_html,
                m.snippet,
                m.sent_at,
                m.received_at,
                m.has_attachment,
                m.attachment_count,
                m.processing_status,
                m.content_hash,
                m.created_at,
                m.updated_at,
                COALESCE(c.name, '미분류') AS mail_category,
                eca.confidence AS category_confidence,
                eca.source AS category_source,
                classification_result.status AS classification_result_status,
                classification_result.result_text AS classification_result_text,
                classification_result.result_json AS classification_result_json,
                classification_result.created_at AS classification_result_created_at,
                classification_result.updated_at AS classification_result_updated_at,
                summary_result.status AS summary_result_status,
                summary_result.result_text AS summary_result_text,
                summary_result.result_json AS summary_result_json,
                summary_result.created_at AS summary_result_created_at,
                summary_result.updated_at AS summary_result_updated_at,
                mf.facts_json AS mail_facts_json,
                latest_run.status AS mail_decision_status,
                latest_run.started_at AS mail_decision_started_at,
                latest_run.completed_at AS mail_decision_completed_at,
                ra.status AS routing_status,
                ra.assigned_at AS routing_assigned_at,
                ra.fixed_at AS routing_fixed_at,
                ra.forwarded_at AS routing_forwarded_at,
                ra.completed_at AS routing_completed_at,
                ra.assignee_user_id,
                assignee.name AS assignee_name,
                assignee.email AS assignee_email,
                assignee.notification_preferences AS assignee_notification_preferences,
                {work_columns}
                latest_manual_forward.status AS manual_route_status,
                latest_manual_forward.sent_at AS manual_route_sent_at,
                latest_manual_forward.error_message AS manual_route_error,
                pj.status AS analysis_job_status
            FROM email_messages m
            JOIN email_accounts account
              ON account.id = m.email_account_id
            LEFT JOIN email_category_assignments eca
                ON eca.email_message_id = m.id
               AND eca.is_current IS TRUE
            LEFT JOIN categories c
                ON c.id = eca.category_id
            LEFT JOIN email_analysis_results classification_result
                ON classification_result.email_message_id = m.id
               AND classification_result.analysis_type = 'classification'
               AND classification_result.is_current IS TRUE
            LEFT JOIN email_analysis_results summary_result
                ON summary_result.email_message_id = m.id
               AND summary_result.analysis_type = 'executive_summary'
               AND summary_result.is_current IS TRUE
            LEFT JOIN mail_facts mf
                ON mf.email_message_id = m.id
               AND mf.is_current IS TRUE
            LEFT JOIN LATERAL (
                SELECT status, started_at, completed_at
                FROM mail_decision_runs
                WHERE email_message_id = m.id
                ORDER BY created_at DESC
                LIMIT 1
            ) latest_run ON TRUE
            LEFT JOIN routing_assignments ra
                ON ra.email_message_id = m.id
            LEFT JOIN users assignee
                ON assignee.id = ra.assignee_user_id
            {work_join}
            LEFT JOIN LATERAL (
                SELECT status, sent_at, error_message
                FROM notifications
                WHERE email_message_id = m.id
                  AND notification_type = 'manual_route_forward'
                ORDER BY created_at DESC
                LIMIT 1
            ) latest_manual_forward ON TRUE
            LEFT JOIN LATERAL (
                SELECT status
                FROM processing_jobs
                WHERE source_type = 'email'
                  AND source_id = m.id
                  AND job_type = 'email_analysis'
                ORDER BY created_at DESC
                LIMIT 1
            ) pj ON TRUE
            WHERE m.deleted_at IS NULL
              {provider_clause}
            ORDER BY m.sent_at DESC, m.created_at DESC
            {limit_clause}
        """
        return self._fetch_all(sql, params)

    def _work_tracking_available(self) -> bool:
        rows = self._fetch_all(
            """
            SELECT to_regclass('public.work_items') IS NOT NULL AS available
            """,
            {},
        )
        return bool(rows and rows[0].get("available"))

    def _fetch_all(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        import psycopg

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return [dict(row) for row in cursor.fetchall()]

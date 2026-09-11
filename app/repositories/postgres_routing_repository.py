from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.schemas.mail_decision import RoutingDecision


class PostgresRoutingRepository:
    def __init__(
        self,
        database_url: str,
        *,
        assignment_indexer: Any | None = None,
        work_tracking_repository: Any | None = None,
    ):
        self.database_url = database_url.strip()
        self.assignment_indexer = assignment_indexer
        self.work_tracking_repository = work_tracking_repository

    def load_active_users_with_capabilities(self, *, include_synthetic: bool = True) -> list[dict[str, Any]]:
        import psycopg

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT u.id, u.name, u.email, u.status, u.notification_preferences,
                           COALESCE(
                               jsonb_agg(
                                   jsonb_build_object(
                                       'capability_type', ac.capability_type,
                                       'capability_value', ac.capability_value,
                                       'priority', ac.priority
                                   ) ORDER BY ac.priority
                               ) FILTER (WHERE ac.id IS NOT NULL),
                               '[]'::jsonb
                           ) AS capabilities
                    FROM users u
                    LEFT JOIN assignee_capabilities ac
                      ON ac.user_id = u.id
                     AND (ac.valid_from IS NULL OR ac.valid_from <= now())
                     AND (ac.valid_to IS NULL OR ac.valid_to > now())
                    WHERE u.status = 'active' AND u.deleted_at IS NULL
                      AND (%(include_synthetic)s OR u.email NOT LIKE '%%@coramail.invalid')
                    GROUP BY u.id, u.name, u.email, u.status, u.notification_preferences
                    ORDER BY u.name
                    """,
                    {"include_synthetic": include_synthetic},
                )
                return [dict(row) for row in cursor.fetchall()]

    def save_candidates(self, *, run_id: UUID, email_message_id: UUID, decision: RoutingDecision) -> None:
        import psycopg

        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM routing_candidates WHERE mail_decision_run_id = %(run_id)s", {"run_id": run_id})
                    for candidate in decision.candidates:
                        components = candidate.component_scores
                        cursor.execute(
                            """
                            INSERT INTO routing_candidates (
                                id, mail_decision_run_id, email_message_id, candidate_user_id,
                                customer_score, product_score, business_type_score, project_score,
                                history_score, similarity_score, availability_score,
                                total_score, rank, reasons_json, created_at
                            ) VALUES (
                                %(id)s, %(run_id)s, %(email_message_id)s, %(user_id)s,
                                %(customer)s, %(product)s, %(business_type)s, %(project)s,
                                %(history)s, %(similarity)s, %(availability)s,
                                %(total)s, %(rank)s, %(reasons)s, %(created_at)s
                            )
                            """,
                            {
                                "id": uuid4(),
                                "run_id": run_id,
                                "email_message_id": email_message_id,
                                "user_id": candidate.user_id,
                                "customer": components.get("customer", 0),
                                "product": components.get("product", 0),
                                "business_type": components.get("business_type", 0),
                                "project": components.get("project", 0),
                                "history": components.get("history", 0),
                                "similarity": components.get("similarity", 0),
                                "availability": components.get("availability", 0),
                                "total": candidate.total_score,
                                "rank": candidate.rank,
                                "reasons": Jsonb(candidate.reasons),
                                "created_at": now,
                            },
                        )

    def apply_decision(self, *, email_message_id: UUID, decision: RoutingDecision) -> None:
        import psycopg

        now = datetime.now(timezone.utc)
        assignment: dict[str, Any] | None = None
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO routing_assignments (
                            id, email_message_id, assignee_user_id, status, assignment_source,
                            assigned_at, created_at, updated_at
                        ) VALUES (
                            %(id)s, %(email_message_id)s, %(assignee_user_id)s, %(status)s,
                            'mail_decision_policy', %(assigned_at)s, %(created_at)s, %(updated_at)s
                        )
                        ON CONFLICT (email_message_id) DO UPDATE SET
                            assignee_user_id = EXCLUDED.assignee_user_id,
                            status = EXCLUDED.status,
                            assignment_source = EXCLUDED.assignment_source,
                            assigned_at = EXCLUDED.assigned_at,
                            updated_at = EXCLUDED.updated_at
                        RETURNING id, assignee_user_id, assigned_at, status
                        """,
                        {
                            "id": uuid4(),
                            "email_message_id": email_message_id,
                            "assignee_user_id": decision.selected_user_id,
                            "status": "assigned" if decision.decision == "auto_assign" else "review_required",
                            "assigned_at": now if decision.decision == "auto_assign" else None,
                            "created_at": now,
                            "updated_at": now,
                        },
                    )
                    row = cursor.fetchone()
                    assignment = {
                        "id": row[0],
                        "assignee_user_id": row[1],
                        "assigned_at": row[2],
                        "status": row[3],
                    } if row else None
        if (
            self.work_tracking_repository is not None
            and assignment
            and str(assignment.get("status") or "") == "assigned"
            and assignment.get("assignee_user_id")
        ):
            self.work_tracking_repository.ensure_for_assignment(
                email_message_id=email_message_id,
                routing_assignment_id=UUID(str(assignment["id"])),
                assignee_user_id=UUID(str(assignment["assignee_user_id"])),
                assigned_at=assignment.get("assigned_at"),
                reason="Mail Decision auto assignment.",
            )
        self.sync_assignment_index(email_message_id)

    def current_assignment(self, email_message_id: UUID) -> dict[str, Any] | None:
        import psycopg

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT ra.id, ra.email_message_id, ra.assignee_user_id, ra.status,
                           u.name AS assignee_name, u.email AS assignee_email
                    FROM routing_assignments ra
                    LEFT JOIN users u ON u.id = ra.assignee_user_id
                    WHERE ra.email_message_id = %(email_message_id)s
                    """,
                    {"email_message_id": email_message_id},
                )
                row = cursor.fetchone()
                return dict(row) if row else None

    def top_review_candidate_user_id(self, email_message_id: UUID) -> UUID | None:
        import psycopg

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT rc.candidate_user_id
                    FROM mail_decision_runs mdr
                    JOIN routing_candidates rc
                      ON rc.mail_decision_run_id = mdr.id
                    WHERE mdr.email_message_id = %(email_message_id)s
                      AND mdr.status = 'review_required'
                    ORDER BY mdr.created_at DESC, rc.rank ASC, rc.total_score DESC
                    LIMIT 1
                    """,
                    {"email_message_id": email_message_id},
                )
                row = cursor.fetchone()
        return UUID(str(row["candidate_user_id"])) if row else None

    def assign_review_required_mail(
        self,
        *,
        email_message_id: UUID,
        assignee_user_id: UUID,
        actor_label: str,
        reason: str = "",
    ) -> dict[str, Any]:
        import psycopg

        now = datetime.now(timezone.utc)
        result: dict[str, Any] | None = None
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT id, status, state_json
                        FROM mail_decision_runs
                        WHERE email_message_id = %(email_message_id)s
                        ORDER BY created_at DESC
                        LIMIT 1
                        FOR UPDATE
                        """,
                        {"email_message_id": email_message_id},
                    )
                    run = cursor.fetchone()
                    cursor.execute(
                        """
                        SELECT ra.id, ra.assignee_user_id, ra.status,
                               u.name AS assignee_name, u.email AS assignee_email
                        FROM routing_assignments ra
                        LEFT JOIN users u ON u.id = ra.assignee_user_id
                        WHERE ra.email_message_id = %(email_message_id)s
                        FOR UPDATE OF ra
                        """,
                        {"email_message_id": email_message_id},
                    )
                    current = cursor.fetchone()
                    current_status = str((current or {}).get("status") or "")
                    run_status = str((run or {}).get("status") or "")
                    if current_status != "review_required" and run_status != "review_required":
                        raise ValueError("review_required 상태의 메일만 수동 배정할 수 있습니다.")

                    cursor.execute(
                        """
                        SELECT id, name, email, notification_preferences
                        FROM users
                        WHERE id = %(assignee_user_id)s
                          AND status = 'active'
                          AND deleted_at IS NULL
                          AND email NOT LIKE '%%@coramail.invalid'
                        """,
                        {"assignee_user_id": assignee_user_id},
                    )
                    assignee = cursor.fetchone()
                    if not assignee:
                        raise ValueError("활성 운영 담당자만 배정할 수 있습니다.")

                    before_data = {
                        "routing_assignment_id": str((current or {}).get("id") or ""),
                        "assignee_user_id": str((current or {}).get("assignee_user_id") or ""),
                        "assignee_name": (current or {}).get("assignee_name") or "",
                        "assignee_email": (current or {}).get("assignee_email") or "",
                        "status": current_status,
                        "mail_decision_run_id": str((run or {}).get("id") or ""),
                        "mail_decision_status": run_status,
                    }
                    assignment_id = (current or {}).get("id") or uuid4()
                    cursor.execute(
                        """
                        INSERT INTO routing_assignments (
                            id, email_message_id, assignee_user_id, status, assignment_source,
                            assigned_at, fixed_at, created_at, updated_at
                        ) VALUES (
                            %(id)s, %(email_message_id)s, %(assignee_user_id)s, 'assigned',
                            'user', %(assigned_at)s, %(fixed_at)s, %(created_at)s, %(updated_at)s
                        )
                        ON CONFLICT (email_message_id) DO UPDATE SET
                            assignee_user_id = EXCLUDED.assignee_user_id,
                            status = EXCLUDED.status,
                            assignment_source = EXCLUDED.assignment_source,
                            assigned_at = EXCLUDED.assigned_at,
                            fixed_at = COALESCE(routing_assignments.fixed_at, EXCLUDED.fixed_at),
                            updated_at = EXCLUDED.updated_at
                        RETURNING id, email_message_id, assignee_user_id, status, assignment_source,
                                  assigned_at, fixed_at, created_at, updated_at
                        """,
                        {
                            "id": assignment_id,
                            "email_message_id": email_message_id,
                            "assignee_user_id": assignee_user_id,
                            "assigned_at": now,
                            "fixed_at": now,
                            "created_at": now,
                            "updated_at": now,
                        },
                    )
                    assignment = dict(cursor.fetchone())
                    event_type = "reassigned" if before_data["assignee_user_id"] else "assigned"
                    cursor.execute(
                        """
                        INSERT INTO routing_events (
                            id, routing_assignment_id, email_message_id, event_type,
                            from_user_id, to_user_id, performed_by_user_id, source, reason, created_at
                        ) VALUES (
                            %(id)s, %(routing_assignment_id)s, %(email_message_id)s, %(event_type)s,
                            %(from_user_id)s, %(to_user_id)s, NULL, 'user', %(reason)s, %(created_at)s
                        )
                        """,
                        {
                            "id": uuid4(),
                            "routing_assignment_id": assignment["id"],
                            "email_message_id": email_message_id,
                            "event_type": event_type,
                            "from_user_id": (current or {}).get("assignee_user_id"),
                            "to_user_id": assignee_user_id,
                            "reason": reason or f"Manual assignment from review_required by {actor_label}.",
                            "created_at": now,
                        },
                    )

                    if run and run_status == "review_required":
                        state_json = run.get("state_json") if isinstance(run.get("state_json"), dict) else {}
                        context = state_json.get("context") if isinstance(state_json.get("context"), dict) else {}
                        context["human_review"] = {
                            "status": "resolved",
                            "action": "manual_assignment",
                            "assignee_user_id": str(assignee_user_id),
                            "actor": actor_label,
                            "reason": reason,
                            "resolved_at": now.isoformat(),
                        }
                        state_json["context"] = context
                        cursor.execute(
                            """
                            UPDATE mail_decision_runs
                            SET status = 'completed',
                                review_required = FALSE,
                                state_json = %(state_json)s,
                                completed_at = COALESCE(completed_at, %(completed_at)s),
                                updated_at = %(updated_at)s
                            WHERE id = %(run_id)s
                            """,
                            {
                                "run_id": run["id"],
                                "state_json": Jsonb(state_json),
                                "completed_at": now,
                                "updated_at": now,
                            },
                        )

                    after_data = {
                        "routing_assignment_id": str(assignment["id"]),
                        "assignee_user_id": str(assignee_user_id),
                        "assignee_name": assignee.get("name") or "",
                        "assignee_email": assignee.get("email") or "",
                        "status": "assigned",
                        "mail_decision_run_id": before_data["mail_decision_run_id"],
                        "mail_decision_status": "completed" if run_status == "review_required" else run_status,
                    }
                    cursor.execute(
                        """
                        INSERT INTO audit_logs (
                            id, actor_type, actor_user_id, action, entity_type, entity_id,
                            before_data, after_data, request_id, created_at
                        ) VALUES (
                            %(id)s, 'user', NULL, 'routing.manual_assigned',
                            'routing_assignment', %(entity_id)s,
                            %(before_data)s, %(after_data)s, %(request_id)s, %(created_at)s
                        )
                        """,
                        {
                            "id": uuid4(),
                            "entity_id": assignment["id"],
                            "before_data": Jsonb(before_data),
                            "after_data": Jsonb(after_data),
                            "request_id": actor_label[:100],
                            "created_at": now,
                        },
                    )
                    assignment.update(
                        {
                            "assignee_name": assignee.get("name") or "",
                            "assignee_email": assignee.get("email") or "",
                            "review_resolved": run_status == "review_required",
                        }
                    )
                    result = assignment
        if self.work_tracking_repository is not None and result and result.get("assignee_user_id"):
            self.work_tracking_repository.ensure_for_assignment(
                email_message_id=email_message_id,
                routing_assignment_id=UUID(str(result["id"])),
                assignee_user_id=UUID(str(result["assignee_user_id"])),
                assigned_at=result.get("assigned_at"),
                reason=reason or f"Manual assignment from review_required by {actor_label}.",
            )
        self.sync_assignment_index(email_message_id)
        if result is None:
            raise RuntimeError("manual assignment did not produce a routing assignment")
        return result

    def latest_manual_forward_notification(self, email_message_id: UUID) -> dict[str, Any]:
        import psycopg

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, status, error_message, sent_at, created_at
                    FROM notifications
                    WHERE email_message_id = %(email_message_id)s
                      AND notification_type = 'manual_route_forward'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    {"email_message_id": email_message_id},
                )
                row = cursor.fetchone()
                return dict(row) if row else {}

    def create_manual_forward_notification(
        self,
        *,
        email_message_id: UUID,
        recipient_user_id: UUID,
        title: str,
        body: str,
        idempotency_key: str,
    ) -> UUID:
        import psycopg

        notification_id = uuid4()
        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO notifications (
                            id, email_message_id, recipient_user_id, channel, notification_type,
                            title, body, status, idempotency_key, created_at, updated_at
                        ) VALUES (
                            %(id)s, %(email_message_id)s, %(recipient_user_id)s, 'gmail',
                            'manual_route_forward', %(title)s, %(body)s, 'pending',
                            %(idempotency_key)s, %(created_at)s, %(updated_at)s
                        )
                        """,
                        {
                            "id": notification_id,
                            "email_message_id": email_message_id,
                            "recipient_user_id": recipient_user_id,
                            "title": title,
                            "body": body,
                            "idempotency_key": idempotency_key,
                            "created_at": now,
                            "updated_at": now,
                        },
                    )
        return notification_id

    def mark_manual_forward_sent(
        self,
        *,
        notification_id: UUID,
        email_message_id: UUID,
        assignee_user_id: UUID,
        provider_message_id: str = "",
    ) -> None:
        import psycopg

        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE notifications
                        SET status = 'sent',
                            provider_message_id = NULLIF(%(provider_message_id)s, ''),
                            sent_at = %(sent_at)s,
                            error_message = NULL,
                            updated_at = %(updated_at)s
                        WHERE id = %(notification_id)s
                        """,
                        {
                            "notification_id": notification_id,
                            "provider_message_id": provider_message_id,
                            "sent_at": now,
                            "updated_at": now,
                        },
                    )
                    cursor.execute(
                        """
                        UPDATE routing_assignments
                        SET status = 'forwarded',
                            forwarded_at = %(forwarded_at)s,
                            updated_at = %(updated_at)s
                        WHERE email_message_id = %(email_message_id)s
                        RETURNING id
                        """,
                        {
                            "email_message_id": email_message_id,
                            "forwarded_at": now,
                            "updated_at": now,
                        },
                    )
                    assignment = cursor.fetchone()
                    if assignment:
                        cursor.execute(
                            """
                            INSERT INTO routing_events (
                                id, routing_assignment_id, email_message_id, event_type,
                                to_user_id, source, reason, created_at
                            ) VALUES (
                                %(id)s, %(routing_assignment_id)s, %(email_message_id)s,
                                'forwarded', %(to_user_id)s, 'user',
                                'Manual dashboard routing forwarded through Gmail.', %(created_at)s
                            )
                            """,
                            {
                                "id": uuid4(),
                                "routing_assignment_id": assignment[0],
                                "email_message_id": email_message_id,
                                "to_user_id": assignee_user_id,
                                "created_at": now,
                            },
                        )
        self.sync_assignment_index(email_message_id)

    def mark_auto_forwarded(
        self,
        *,
        email_message_id: UUID,
        assignee_user_id: UUID,
        title: str = "",
        body: str = "",
        reason: str = "Mail Decision auto assignment forwarded automatically.",
    ) -> None:
        import psycopg

        now = datetime.now(timezone.utc)
        notification_id = uuid4()
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO notifications (
                            id, email_message_id, recipient_user_id, channel, notification_type,
                            title, body, status, idempotency_key, sent_at, created_at, updated_at
                        ) VALUES (
                            %(id)s, %(email_message_id)s, %(recipient_user_id)s, 'gmail',
                            'manual_route_forward', %(title)s, %(body)s, 'sent',
                            %(idempotency_key)s, %(sent_at)s, %(created_at)s, %(updated_at)s
                        )
                        """,
                        {
                            "id": notification_id,
                            "email_message_id": email_message_id,
                            "recipient_user_id": assignee_user_id,
                            "title": title[:500] or "자동 라우팅",
                            "body": body[:10000],
                            "idempotency_key": f"auto-route:{email_message_id}",
                            "sent_at": now,
                            "created_at": now,
                            "updated_at": now,
                        },
                    )
                    cursor.execute(
                        """
                        UPDATE routing_assignments
                        SET status = 'forwarded',
                            forwarded_at = COALESCE(forwarded_at, %(forwarded_at)s),
                            updated_at = %(updated_at)s
                        WHERE email_message_id = %(email_message_id)s
                        RETURNING id
                        """,
                        {
                            "email_message_id": email_message_id,
                            "forwarded_at": now,
                            "updated_at": now,
                        },
                    )
                    assignment = cursor.fetchone()
                    if assignment:
                        cursor.execute(
                            """
                            INSERT INTO routing_events (
                                id, routing_assignment_id, email_message_id, event_type,
                                to_user_id, source, reason, created_at
                            ) VALUES (
                                %(id)s, %(routing_assignment_id)s, %(email_message_id)s,
                                'forwarded', %(to_user_id)s, 'mail_decision_policy',
                                %(reason)s, %(created_at)s
                            )
                            """,
                            {
                                "id": uuid4(),
                                "routing_assignment_id": assignment[0],
                                "email_message_id": email_message_id,
                                "to_user_id": assignee_user_id,
                                "reason": reason,
                                "created_at": now,
                            },
                        )
        self.sync_assignment_index(email_message_id)

    def forward_auto_assigned_without_notification(self, *, limit: int = 100) -> int:
        import psycopg

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT m.id AS email_message_id, ra.assignee_user_id, m.subject, m.body_text, m.snippet
                    FROM routing_assignments ra
                    JOIN email_messages m ON m.id = ra.email_message_id
                    LEFT JOIN LATERAL (
                        SELECT status, state_json
                        FROM mail_decision_runs
                        WHERE email_message_id = m.id
                        ORDER BY created_at DESC
                        LIMIT 1
                    ) latest_run ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT status
                        FROM notifications
                        WHERE email_message_id = m.id
                          AND notification_type = 'manual_route_forward'
                        ORDER BY created_at DESC
                        LIMIT 1
                    ) latest_forward ON TRUE
                    WHERE ra.status = 'assigned'
                      AND ra.assignee_user_id IS NOT NULL
                      AND COALESCE(latest_forward.status, '') NOT IN ('pending', 'sent')
                      AND (
                        latest_run.status = 'auto_assigned'
                        OR latest_run.state_json #>> '{context,routing_decision,decision}' = 'auto_assign'
                      )
                    ORDER BY ra.updated_at DESC
                    LIMIT %(limit)s
                    """,
                    {"limit": max(1, limit)},
                )
                rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            self.mark_auto_forwarded(
                email_message_id=UUID(str(row["email_message_id"])),
                assignee_user_id=UUID(str(row["assignee_user_id"])),
                title=str(row.get("subject") or "자동 라우팅"),
                body=str(row.get("body_text") or row.get("snippet") or ""),
                reason="Mail Decision auto routing forwarded after assignment was already completed.",
            )
        return len(rows)

    def sync_assignment_index(self, email_message_id: UUID) -> None:
        if self.assignment_indexer is None:
            return
        try:
            self.assignment_indexer.index_email(email_message_id)
        except Exception:
            # Routing state is the source of truth. Qdrant sync can be retried
            # explicitly with the reindex command if the local vector stack is down.
            return

    def mark_manual_forward_failed(self, *, notification_id: UUID, error_message: str) -> None:
        import psycopg

        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE notifications
                    SET status = 'failed',
                        error_message = %(error_message)s,
                        updated_at = %(updated_at)s
                    WHERE id = %(notification_id)s
                    """,
                    {
                        "notification_id": notification_id,
                        "error_message": error_message[:4000],
                        "updated_at": now,
                    },
                )

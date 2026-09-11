-- Work execution state and shared Gmail reply tracking.

BEGIN;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS username VARCHAR(100),
    ADD COLUMN IF NOT EXISTS password_hash TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_unique
    ON users (lower(username))
    WHERE username IS NOT NULL AND deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS work_items (
    id UUID PRIMARY KEY,
    email_message_id UUID NOT NULL REFERENCES email_messages (id) ON DELETE CASCADE,
    routing_assignment_id UUID NOT NULL REFERENCES routing_assignments (id) ON DELETE CASCADE,
    assignee_user_id UUID NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    status VARCHAR(30) NOT NULL,
    assigned_at TIMESTAMPTZ NOT NULL,
    acknowledged_at TIMESTAMPTZ,
    reply_initiated_at TIMESTAMPTZ,
    first_responded_at TIMESTAMPTZ,
    responded_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    due_at TIMESTAMPTZ,
    last_activity_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT work_items_routing_assignment_unique UNIQUE (routing_assignment_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_work_items_current_email_unique
    ON work_items (email_message_id);
CREATE INDEX IF NOT EXISTS idx_work_items_assignee_status
    ON work_items (assignee_user_id, status, last_activity_at DESC);
CREATE INDEX IF NOT EXISTS idx_work_items_thread_lookup
    ON work_items (email_message_id, reply_initiated_at)
    WHERE reply_initiated_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS mail_read_states (
    email_message_id UUID NOT NULL REFERENCES email_messages (id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    read_at TIMESTAMPTZ,
    last_opened_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (email_message_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_mail_read_states_user_read
    ON mail_read_states (user_id, read_at DESC)
    WHERE read_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS work_events (
    id UUID PRIMARY KEY,
    work_item_id UUID NOT NULL REFERENCES work_items (id) ON DELETE CASCADE,
    email_message_id UUID NOT NULL REFERENCES email_messages (id) ON DELETE CASCADE,
    routing_assignment_id UUID REFERENCES routing_assignments (id) ON DELETE SET NULL,
    event_type VARCHAR(40) NOT NULL,
    actor_user_id UUID REFERENCES users (id) ON DELETE SET NULL,
    provider_message_id VARCHAR(255),
    provider_thread_id VARCHAR(255),
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_work_events_work_created
    ON work_events (work_item_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_work_events_email_type_created
    ON work_events (email_message_id, event_type, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_work_events_response_message_unique
    ON work_events (work_item_id, provider_message_id)
    WHERE event_type = 'response_detected' AND provider_message_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS gmail_outbound_messages (
    id UUID PRIMARY KEY,
    email_account_id UUID NOT NULL REFERENCES email_accounts (id) ON DELETE CASCADE,
    provider_message_id VARCHAR(255) NOT NULL,
    provider_thread_id VARCHAR(255) NOT NULL,
    rfc_message_id VARCHAR(998),
    sender_address VARCHAR(320),
    recipients JSONB,
    subject TEXT,
    sent_at TIMESTAMPTZ NOT NULL,
    linked_work_item_id UUID REFERENCES work_items (id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT gmail_outbound_messages_provider_unique UNIQUE (email_account_id, provider_message_id)
);

CREATE INDEX IF NOT EXISTS idx_gmail_outbound_thread_sent
    ON gmail_outbound_messages (provider_thread_id, sent_at);
CREATE INDEX IF NOT EXISTS idx_gmail_outbound_linked_work
    ON gmail_outbound_messages (linked_work_item_id);

INSERT INTO work_items (
    id, email_message_id, routing_assignment_id, assignee_user_id, status,
    assigned_at, due_at, last_activity_at, created_at, updated_at
)
SELECT
    gen_random_uuid(),
    ra.email_message_id,
    ra.id,
    ra.assignee_user_id,
    CASE WHEN ra.completed_at IS NOT NULL OR ra.status = 'completed' THEN 'completed' ELSE 'assigned' END,
    COALESCE(ra.assigned_at, ra.created_at, now()),
    COALESCE(ra.assigned_at, ra.created_at, now()) + INTERVAL '24 hours',
    COALESCE(ra.completed_at, ra.forwarded_at, ra.assigned_at, ra.updated_at, ra.created_at, now()),
    now(),
    now()
FROM routing_assignments ra
WHERE ra.assignee_user_id IS NOT NULL
  AND ra.status IN ('assigned', 'forwarded', 'completed')
ON CONFLICT (email_message_id) DO NOTHING;

INSERT INTO mail_read_states (
    email_message_id, user_id, read_at, last_opened_at, created_at, updated_at
)
SELECT
    wi.email_message_id,
    wi.assignee_user_id,
    wi.acknowledged_at,
    wi.acknowledged_at,
    now(),
    now()
FROM work_items wi
WHERE wi.acknowledged_at IS NOT NULL
ON CONFLICT (email_message_id, user_id) DO NOTHING;

COMMIT;

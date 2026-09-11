-- CoRA Mail Agent initial PostgreSQL schema.
-- This DDL follows docs/architecture/postgresql_schema.md and intentionally
-- excludes future correction/evaluation tables that still need a decision gate.

BEGIN;

CREATE TABLE IF NOT EXISTS organization_settings (
    id UUID PRIMARY KEY,
    organization_name VARCHAR(200) NOT NULL,
    timezone VARCHAR(50) NOT NULL DEFAULT 'Asia/Seoul',
    default_language VARCHAR(20),
    notification_settings JSONB,
    system_settings JSONB,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    name VARCHAR(100) NOT NULL,
    role VARCHAR(30) NOT NULL,
    status VARCHAR(30) NOT NULL,
    phone_number VARCHAR(30),
    notification_preferences JSONB,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    deleted_at TIMESTAMPTZ,
    CONSTRAINT users_email_unique UNIQUE (email)
);

CREATE INDEX IF NOT EXISTS idx_users_status ON users (status);

CREATE TABLE IF NOT EXISTS email_accounts (
    id UUID PRIMARY KEY,
    provider VARCHAR(30) NOT NULL,
    email_address VARCHAR(320) NOT NULL,
    display_name VARCHAR(100),
    status VARCHAR(30) NOT NULL,
    credentials_reference VARCHAR(500),
    sync_cursor VARCHAR(500),
    last_synced_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT email_accounts_provider_email_unique UNIQUE (provider, email_address)
);

CREATE INDEX IF NOT EXISTS idx_email_accounts_status ON email_accounts (status);
CREATE INDEX IF NOT EXISTS idx_email_accounts_last_synced_at ON email_accounts (last_synced_at);

CREATE TABLE IF NOT EXISTS document_categories (
    id UUID PRIMARY KEY,
    code VARCHAR(100) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT document_categories_code_unique UNIQUE (code)
);

CREATE INDEX IF NOT EXISTS idx_document_categories_is_active ON document_categories (is_active);

CREATE TABLE IF NOT EXISTS categories (
    id UUID PRIMARY KEY,
    code VARCHAR(100) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT categories_code_unique UNIQUE (code)
);

CREATE INDEX IF NOT EXISTS idx_categories_is_active_sort_order ON categories (is_active, sort_order);

CREATE TABLE IF NOT EXISTS email_messages (
    id UUID PRIMARY KEY,
    email_account_id UUID NOT NULL REFERENCES email_accounts (id) ON DELETE RESTRICT,
    provider_message_id VARCHAR(255) NOT NULL,
    provider_thread_id VARCHAR(255),
    rfc_message_id VARCHAR(998),
    in_reply_to VARCHAR(998),
    "references" TEXT[],
    sender_name VARCHAR(200),
    sender_address VARCHAR(320) NOT NULL,
    subject TEXT NOT NULL,
    subject_normalized TEXT,
    body_text TEXT NOT NULL,
    body_html TEXT,
    snippet TEXT,
    sent_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ,
    has_attachment BOOLEAN NOT NULL DEFAULT FALSE,
    attachment_count INTEGER NOT NULL DEFAULT 0,
    processing_status VARCHAR(30) NOT NULL,
    content_hash CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    deleted_at TIMESTAMPTZ,
    CONSTRAINT email_messages_account_provider_message_unique UNIQUE (email_account_id, provider_message_id),
    CONSTRAINT email_messages_attachment_count_nonnegative CHECK (attachment_count >= 0)
);

CREATE INDEX IF NOT EXISTS idx_email_messages_sent_at_desc ON email_messages (sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_messages_sender_address ON email_messages (sender_address);
CREATE INDEX IF NOT EXISTS idx_email_messages_account_thread ON email_messages (email_account_id, provider_thread_id);
CREATE INDEX IF NOT EXISTS idx_email_messages_processing_status ON email_messages (processing_status);

CREATE TABLE IF NOT EXISTS email_recipients (
    id UUID PRIMARY KEY,
    email_message_id UUID NOT NULL REFERENCES email_messages (id) ON DELETE CASCADE,
    recipient_type VARCHAR(10) NOT NULL,
    name VARCHAR(200),
    address VARCHAR(320) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT email_recipients_message_type_address_unique UNIQUE (email_message_id, recipient_type, address)
);

CREATE INDEX IF NOT EXISTS idx_email_recipients_address ON email_recipients (address);
CREATE INDEX IF NOT EXISTS idx_email_recipients_message_type ON email_recipients (email_message_id, recipient_type);

CREATE TABLE IF NOT EXISTS email_attachments (
    id UUID PRIMARY KEY,
    email_message_id UUID NOT NULL REFERENCES email_messages (id) ON DELETE CASCADE,
    provider_attachment_id TEXT,
    filename TEXT NOT NULL,
    storage_uri TEXT NOT NULL,
    content_type VARCHAR(255) NOT NULL,
    content_id TEXT,
    content_disposition VARCHAR(30),
    file_group VARCHAR(30) NOT NULL,
    file_size BIGINT,
    checksum CHAR(64),
    is_inline BOOLEAN NOT NULL DEFAULT FALSE,
    document_category_id UUID REFERENCES document_categories (id) ON DELETE SET NULL,
    processing_status VARCHAR(30) NOT NULL,
    parse_error TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    deleted_at TIMESTAMPTZ,
    CONSTRAINT email_attachments_file_size_nonnegative CHECK (file_size IS NULL OR file_size >= 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_email_attachments_message_provider_unique
    ON email_attachments (email_message_id, provider_attachment_id)
    WHERE provider_attachment_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_email_attachments_message ON email_attachments (email_message_id);
CREATE INDEX IF NOT EXISTS idx_email_attachments_processing_status ON email_attachments (processing_status);
CREATE INDEX IF NOT EXISTS idx_email_attachments_checksum ON email_attachments (checksum);
CREATE INDEX IF NOT EXISTS idx_email_attachments_document_category ON email_attachments (document_category_id);

CREATE TABLE IF NOT EXISTS email_category_assignments (
    id UUID PRIMARY KEY,
    email_message_id UUID NOT NULL REFERENCES email_messages (id) ON DELETE CASCADE,
    category_id UUID NOT NULL REFERENCES categories (id) ON DELETE RESTRICT,
    source VARCHAR(30) NOT NULL,
    confidence NUMERIC(5, 4),
    model_name VARCHAR(200),
    reason TEXT,
    assigned_by_user_id UUID REFERENCES users (id) ON DELETE SET NULL,
    is_current BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT email_category_assignments_confidence_range CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_email_category_assignments_one_current
    ON email_category_assignments (email_message_id)
    WHERE is_current IS TRUE;
CREATE INDEX IF NOT EXISTS idx_email_category_assignments_category_current
    ON email_category_assignments (category_id, is_current);
CREATE INDEX IF NOT EXISTS idx_email_category_assignments_message_created
    ON email_category_assignments (email_message_id, created_at DESC);

CREATE TABLE IF NOT EXISTS email_analysis_results (
    id UUID PRIMARY KEY,
    email_message_id UUID NOT NULL REFERENCES email_messages (id) ON DELETE CASCADE,
    analysis_type VARCHAR(50) NOT NULL,
    result_text TEXT,
    result_json JSONB,
    model_name VARCHAR(200) NOT NULL,
    prompt_version VARCHAR(100),
    status VARCHAR(30) NOT NULL,
    error_message TEXT,
    is_current BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_email_analysis_results_one_current
    ON email_analysis_results (email_message_id, analysis_type)
    WHERE is_current IS TRUE;
CREATE INDEX IF NOT EXISTS idx_email_analysis_results_message_type_current
    ON email_analysis_results (email_message_id, analysis_type, is_current);
CREATE INDEX IF NOT EXISTS idx_email_analysis_results_status ON email_analysis_results (status);

CREATE TABLE IF NOT EXISTS attachment_analysis_results (
    id UUID PRIMARY KEY,
    attachment_id UUID NOT NULL REFERENCES email_attachments (id) ON DELETE CASCADE,
    analysis_type VARCHAR(50) NOT NULL,
    result_text TEXT,
    result_json JSONB,
    model_name VARCHAR(200),
    model_version VARCHAR(100),
    status VARCHAR(30) NOT NULL,
    error_message TEXT,
    is_current BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_attachment_analysis_results_one_current
    ON attachment_analysis_results (attachment_id, analysis_type)
    WHERE is_current IS TRUE;
CREATE INDEX IF NOT EXISTS idx_attachment_analysis_results_attachment_type_current
    ON attachment_analysis_results (attachment_id, analysis_type, is_current);
CREATE INDEX IF NOT EXISTS idx_attachment_analysis_results_status ON attachment_analysis_results (status);

CREATE TABLE IF NOT EXISTS routing_rules (
    id UUID PRIMARY KEY,
    category_id UUID NOT NULL REFERENCES categories (id) ON DELETE RESTRICT,
    assignee_user_id UUID NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    priority INTEGER NOT NULL,
    is_active BOOLEAN NOT NULL,
    effective_from TIMESTAMPTZ,
    effective_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT routing_rules_category_assignee_unique UNIQUE (category_id, assignee_user_id),
    CONSTRAINT routing_rules_priority_nonnegative CHECK (priority >= 0)
);

CREATE INDEX IF NOT EXISTS idx_routing_rules_category_active_priority
    ON routing_rules (category_id, is_active, priority);

CREATE TABLE IF NOT EXISTS routing_assignments (
    id UUID PRIMARY KEY,
    email_message_id UUID NOT NULL REFERENCES email_messages (id) ON DELETE CASCADE,
    assignee_user_id UUID REFERENCES users (id) ON DELETE SET NULL,
    status VARCHAR(30) NOT NULL,
    assignment_source VARCHAR(30) NOT NULL,
    routing_rule_id UUID REFERENCES routing_rules (id) ON DELETE SET NULL,
    assigned_at TIMESTAMPTZ,
    forwarded_at TIMESTAMPTZ,
    fixed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT routing_assignments_email_message_unique UNIQUE (email_message_id)
);

CREATE INDEX IF NOT EXISTS idx_routing_assignments_assignee_status ON routing_assignments (assignee_user_id, status);
CREATE INDEX IF NOT EXISTS idx_routing_assignments_status_created ON routing_assignments (status, created_at DESC);

CREATE TABLE IF NOT EXISTS routing_events (
    id UUID PRIMARY KEY,
    routing_assignment_id UUID NOT NULL REFERENCES routing_assignments (id) ON DELETE CASCADE,
    email_message_id UUID NOT NULL REFERENCES email_messages (id) ON DELETE CASCADE,
    event_type VARCHAR(30) NOT NULL,
    from_user_id UUID REFERENCES users (id) ON DELETE SET NULL,
    to_user_id UUID REFERENCES users (id) ON DELETE SET NULL,
    performed_by_user_id UUID REFERENCES users (id) ON DELETE SET NULL,
    source VARCHAR(30) NOT NULL,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_routing_events_email_created ON routing_events (email_message_id, created_at);
CREATE INDEX IF NOT EXISTS idx_routing_events_assignment_created ON routing_events (routing_assignment_id, created_at);
CREATE INDEX IF NOT EXISTS idx_routing_events_type_created ON routing_events (event_type, created_at DESC);

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY,
    email_message_id UUID REFERENCES email_messages (id) ON DELETE CASCADE,
    recipient_user_id UUID REFERENCES users (id) ON DELETE SET NULL,
    channel VARCHAR(30) NOT NULL,
    notification_type VARCHAR(50) NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    status VARCHAR(30) NOT NULL,
    provider_message_id VARCHAR(255),
    idempotency_key VARCHAR(255),
    scheduled_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    read_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_notifications_idempotency_key_unique
    ON notifications (idempotency_key)
    WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_notifications_recipient_status_created
    ON notifications (recipient_user_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_status_scheduled ON notifications (status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_notifications_email_message ON notifications (email_message_id);

CREATE TABLE IF NOT EXISTS qdrant_index_records (
    id UUID PRIMARY KEY,
    source_type VARCHAR(30) NOT NULL,
    email_message_id UUID REFERENCES email_messages (id) ON DELETE CASCADE,
    attachment_id UUID REFERENCES email_attachments (id) ON DELETE CASCADE,
    chunk_id VARCHAR(255),
    chunk_index INTEGER,
    collection_name VARCHAR(255) NOT NULL,
    point_id VARCHAR(255) NOT NULL,
    schema_version INTEGER NOT NULL,
    embedding_model VARCHAR(200) NOT NULL,
    embedding_dimension INTEGER NOT NULL,
    content_hash CHAR(64) NOT NULL,
    status VARCHAR(30) NOT NULL,
    indexed_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT qdrant_index_records_collection_point_unique UNIQUE (collection_name, point_id),
    CONSTRAINT qdrant_index_records_email_source CHECK (
        source_type <> 'email' OR email_message_id IS NOT NULL
    ),
    CONSTRAINT qdrant_index_records_attachment_source CHECK (
        source_type <> 'attachment_chunk'
        OR (attachment_id IS NOT NULL AND chunk_id IS NOT NULL AND chunk_index IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_qdrant_index_records_source_status ON qdrant_index_records (source_type, status);
CREATE INDEX IF NOT EXISTS idx_qdrant_index_records_email_status ON qdrant_index_records (email_message_id, status);
CREATE INDEX IF NOT EXISTS idx_qdrant_index_records_attachment_status ON qdrant_index_records (attachment_id, status);
CREATE INDEX IF NOT EXISTS idx_qdrant_index_records_content_hash ON qdrant_index_records (content_hash);

CREATE TABLE IF NOT EXISTS processing_jobs (
    id UUID PRIMARY KEY,
    job_type VARCHAR(50) NOT NULL,
    source_type VARCHAR(30),
    source_id UUID,
    status VARCHAR(30) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL,
    scheduled_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT processing_jobs_attempt_count_nonnegative CHECK (attempt_count >= 0),
    CONSTRAINT processing_jobs_max_attempts_positive CHECK (max_attempts > 0)
);

CREATE INDEX IF NOT EXISTS idx_processing_jobs_status_scheduled ON processing_jobs (status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_type_status ON processing_jobs (job_type, status);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_source ON processing_jobs (source_type, source_id);

CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY,
    actor_type VARCHAR(30) NOT NULL,
    actor_user_id UUID REFERENCES users (id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    before_data JSONB,
    after_data JSONB,
    request_id VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_entity_created ON audit_logs (entity_type, entity_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_created ON audit_logs (actor_user_id, created_at DESC);

COMMIT;

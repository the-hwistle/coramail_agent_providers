-- Agentic RAG Mail Decision foundation schema.
BEGIN;

CREATE TABLE IF NOT EXISTS mail_decision_runs (
    id UUID PRIMARY KEY,
    email_message_id UUID NOT NULL REFERENCES email_messages (id) ON DELETE CASCADE,
    workflow_version VARCHAR(100) NOT NULL,
    status VARCHAR(40) NOT NULL,
    current_node VARCHAR(100),
    input_hash CHAR(64) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    review_required BOOLEAN NOT NULL DEFAULT FALSE,
    failure_code VARCHAR(100),
    failure_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT mail_decision_runs_attempt_nonnegative CHECK (attempt_count >= 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_mail_decision_runs_active_email
    ON mail_decision_runs (email_message_id)
    WHERE status IN ('queued', 'running', 'review_required');
CREATE INDEX IF NOT EXISTS idx_mail_decision_runs_status_created
    ON mail_decision_runs (status, created_at);

CREATE TABLE IF NOT EXISTS mail_decision_steps (
    id UUID PRIMARY KEY,
    mail_decision_run_id UUID NOT NULL REFERENCES mail_decision_runs (id) ON DELETE CASCADE,
    node_name VARCHAR(100) NOT NULL,
    attempt_number INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(40) NOT NULL,
    input_json JSONB,
    output_json JSONB,
    model_name VARCHAR(200),
    prompt_version VARCHAR(100),
    latency_ms INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT mail_decision_steps_attempt_positive CHECK (attempt_number > 0),
    CONSTRAINT mail_decision_steps_latency_nonnegative CHECK (latency_ms IS NULL OR latency_ms >= 0),
    CONSTRAINT mail_decision_steps_tokens_nonnegative CHECK (
        (input_tokens IS NULL OR input_tokens >= 0) AND
        (output_tokens IS NULL OR output_tokens >= 0)
    )
);

CREATE INDEX IF NOT EXISTS idx_mail_decision_steps_run_node
    ON mail_decision_steps (mail_decision_run_id, node_name, attempt_number DESC);

CREATE TABLE IF NOT EXISTS evidence_items (
    id UUID PRIMARY KEY,
    mail_decision_run_id UUID NOT NULL REFERENCES mail_decision_runs (id) ON DELETE CASCADE,
    source_type VARCHAR(40) NOT NULL,
    source_id UUID,
    attachment_id UUID REFERENCES email_attachments (id) ON DELETE CASCADE,
    page_number INTEGER,
    text_start INTEGER,
    text_end INTEGER,
    bbox JSONB,
    evidence_text TEXT NOT NULL,
    content_hash CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT evidence_items_page_positive CHECK (page_number IS NULL OR page_number > 0)
);

CREATE INDEX IF NOT EXISTS idx_evidence_items_run_source
    ON evidence_items (mail_decision_run_id, source_type, source_id);

CREATE TABLE IF NOT EXISTS mail_facts (
    id UUID PRIMARY KEY,
    email_message_id UUID NOT NULL REFERENCES email_messages (id) ON DELETE CASCADE,
    mail_decision_run_id UUID NOT NULL REFERENCES mail_decision_runs (id) ON DELETE CASCADE,
    facts_json JSONB NOT NULL,
    confidence NUMERIC(5, 4),
    is_current BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT mail_facts_confidence_range CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_mail_facts_one_current
    ON mail_facts (email_message_id)
    WHERE is_current IS TRUE;

CREATE TABLE IF NOT EXISTS retrieval_traces (
    id UUID PRIMARY KEY,
    mail_decision_run_id UUID NOT NULL REFERENCES mail_decision_runs (id) ON DELETE CASCADE,
    cycle_number INTEGER NOT NULL,
    purpose VARCHAR(100) NOT NULL,
    query_text TEXT NOT NULL,
    filters_json JSONB,
    retriever_type VARCHAR(50) NOT NULL,
    source_type VARCHAR(50),
    source_id UUID,
    retrieval_score NUMERIC(8, 6),
    rerank_score NUMERIC(8, 6),
    included_in_prompt BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT retrieval_traces_cycle_range CHECK (cycle_number BETWEEN 1 AND 3)
);

CREATE INDEX IF NOT EXISTS idx_retrieval_traces_run_cycle
    ON retrieval_traces (mail_decision_run_id, cycle_number, purpose);

CREATE TABLE IF NOT EXISTS assignee_capabilities (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    capability_type VARCHAR(50) NOT NULL,
    capability_value VARCHAR(300) NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    valid_from TIMESTAMPTZ,
    valid_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT assignee_capabilities_unique UNIQUE (user_id, capability_type, capability_value),
    CONSTRAINT assignee_capabilities_priority_nonnegative CHECK (priority >= 0)
);

CREATE INDEX IF NOT EXISTS idx_assignee_capabilities_lookup
    ON assignee_capabilities (capability_type, capability_value, priority);

CREATE TABLE IF NOT EXISTS routing_candidates (
    id UUID PRIMARY KEY,
    mail_decision_run_id UUID NOT NULL REFERENCES mail_decision_runs (id) ON DELETE CASCADE,
    email_message_id UUID NOT NULL REFERENCES email_messages (id) ON DELETE CASCADE,
    candidate_user_id UUID NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    customer_score NUMERIC(5, 4) NOT NULL DEFAULT 0,
    product_score NUMERIC(5, 4) NOT NULL DEFAULT 0,
    business_type_score NUMERIC(5, 4) NOT NULL DEFAULT 0,
    project_score NUMERIC(5, 4) NOT NULL DEFAULT 0,
    history_score NUMERIC(5, 4) NOT NULL DEFAULT 0,
    similarity_score NUMERIC(5, 4) NOT NULL DEFAULT 0,
    availability_score NUMERIC(5, 4) NOT NULL DEFAULT 0,
    total_score NUMERIC(5, 4) NOT NULL,
    rank INTEGER NOT NULL,
    reasons_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT routing_candidates_unique UNIQUE (mail_decision_run_id, candidate_user_id),
    CONSTRAINT routing_candidates_rank_positive CHECK (rank > 0),
    CONSTRAINT routing_candidates_total_range CHECK (total_score BETWEEN 0 AND 1)
);

CREATE INDEX IF NOT EXISTS idx_routing_candidates_run_rank
    ON routing_candidates (mail_decision_run_id, rank);

COMMIT;

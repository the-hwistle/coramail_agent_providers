-- Runtime state required to resume Mail Decision Runs safely.
BEGIN;

ALTER TABLE mail_decision_runs
    ADD COLUMN IF NOT EXISTS state_json JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_mail_decision_runs_email_created
    ON mail_decision_runs (email_message_id, created_at DESC);

COMMIT;

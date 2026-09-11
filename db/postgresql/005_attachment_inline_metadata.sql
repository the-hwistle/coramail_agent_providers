-- Preserve MIME inline attachment metadata needed to render HTML email bodies.
BEGIN;

ALTER TABLE email_attachments
    ADD COLUMN IF NOT EXISTS content_id TEXT;

ALTER TABLE email_attachments
    ADD COLUMN IF NOT EXISTS content_disposition VARCHAR(30);

COMMIT;

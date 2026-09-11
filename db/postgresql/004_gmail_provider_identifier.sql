-- Gmail attachment resource identifiers can exceed 255 characters.

BEGIN;

ALTER TABLE email_attachments
    ALTER COLUMN provider_attachment_id TYPE TEXT;

COMMIT;

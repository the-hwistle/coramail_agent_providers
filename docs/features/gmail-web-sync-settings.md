# Gmail Web Sync Settings

## Purpose

Let an administrator configure Gmail synchronization from the web UI instead of editing environment variables or running a local OAuth helper.

## Users

- 업무 관리자
- AI 운영·개발 담당자

## Input Data

- Google OAuth client JSON entered in the Gmail account modal only when `GOOGLE_CREDENTIALS_JSON` is not already available.
- Existing `GOOGLE_TOKEN_JSON` and optional `GOOGLE_SEND_TOKEN_JSON` loaded from environment or `.env`.
- Existing `GOOGLE_CREDENTIALS_JSON` loaded from environment or `.env` when a token should be issued by OAuth instead of pasted manually.
- Existing `GOOGLE_TOKEN_JSON` and optional `GOOGLE_SEND_TOKEN_JSON` pasted in the Gmail account modal as a fallback path only.
- Gmail OAuth callback code from Google.
- Manual sync action from the Gmail account modal or topbar.

## Output Data

- Connected Gmail account email address.
- OAuth scopes granted for Gmail synchronization and message state changes.
- Runtime token source: environment token, popup-saved token, or web OAuth token.
- Last sync status, timestamp, and error summary.
- PostgreSQL-backed Gmail inbox rows displayed in Gmail mode.
- Downloaded attachment originals stored in ignored local runtime storage.
- Initial classification and executive-summary results for new or content-changed messages.

## State

- `not_connected`: no token is available.
- `active`: token exists and the account is connected.
- `error`: token exists but the latest sync or OAuth action failed.
- `disabled`: token was removed by disconnect.

## Normal Flow

1. Admin switches to Gmail mode.
2. Admin clicks the Gmail account banner in the topbar.
3. If `GOOGLE_CREDENTIALS_JSON` is present in `.env`, the modal shows Google permission request as the primary action.
4. Admin clicks Google permission request and approves the account.
5. Google redirects to `/auth/gmail/callback`.
6. The server stores the granted token in the local runtime store, records the connected account, and updates `GOOGLE_TOKEN_JSON` in the active `.env` when that file exists.
7. Admin runs manual sync.
8. The server refreshes expired tokens automatically and writes refreshed `GOOGLE_TOKEN_JSON` back to `.env`.
9. The server follows Gmail `nextPageToken` pagination and reads the full matching INBOX by default. `CORAMAIL_GMAIL_MAX_RESULTS` may be set only when an operator intentionally wants a bounded development sync.
10. The server idempotently upserts messages, recipients, and attachment metadata into PostgreSQL.
11. Attachment originals are downloaded to `data/runtime/gmail_attachments/`.
12. New or changed messages run initial classification and executive-summary jobs.
13. Gmail mode displays persisted rows and uses their UUIDs for every analysis action.

Alternate new-permission flow:

1. Admin opens the advanced Google permission request section.
2. Admin saves Google OAuth client JSON.
3. Admin clicks Google permission request.
4. The server redirects to Google OAuth.
5. Google redirects to `/auth/gmail/callback`.
6. The server stores the granted token in the local runtime store and records the connected account.

`coramail_ai`-compatible local flow:

1. Admin sets `GOOGLE_CREDENTIALS_JSON` in the project `.env` or `CORAMAIL_ENV_FILE`.
2. The Gmail integration reads that JSON directly when an interactive OAuth token is needed.
3. When Google returns or refreshes credentials, the integration persists `GOOGLE_TOKEN_JSON` back to the active `.env` when that file exists, and also writes the runtime token file used by the web UI.
4. The administrator does not need to manually copy an access token from Google.

Fallback existing-token flow:

1. Admin opens the existing token manual registration section.
2. Admin pastes `GOOGLE_TOKEN_JSON` and optional `GOOGLE_SEND_TOKEN_JSON`.
3. The server validates and stores the token JSON in the local runtime store and active `.env`.

## Exception Flow

- Missing OAuth client JSON and token JSON: the Gmail account modal keeps the account disconnected and reports that OAuth client setup or token fallback is required.
- Invalid token JSON: the Gmail account modal reports a JSON validation error.
- Missing client JSON: the Gmail account modal opens OAuth client setup for the new-permission flow.
- Invalid client JSON: the Gmail account modal reports a JSON validation error.
- OAuth state mismatch: the callback rejects the request.
- Missing or invalid token: manual sync records an error and keeps the UI available.
- Gmail API failure: manual sync records the exception summary in sync status.

## API Contract

- `POST /ui/settings/gmail/client-config`
  - Form field: `client_config_json`
  - Response: Gmail settings partial HTML.
- `POST /ui/settings/gmail/tokens`
  - Form fields: `primary_token_json`, optional `send_token_json`
  - Response: Gmail settings partial HTML.
- `GET /ui/settings/gmail/connect`
  - Response: redirect to Google OAuth authorization URL.
- `GET /auth/gmail/callback`
  - Query: `code`, `state`, optional `error`
  - Response: redirect to `/`.
- `POST /ui/settings/gmail/sync`
  - Response: Gmail settings partial HTML with sync status.
- `POST /ui/settings/gmail/disconnect`
  - Response: Gmail settings partial HTML.
- `GET /api/auto-sync`
  - Response: current Gmail sync status JSON.

## Storage

Runtime credential and attachment storage:

- `data/runtime/gmail_oauth_client.json`
- `data/runtime/gmail_token.json`
- `data/runtime/gmail_send_token.json`
- `data/runtime/gmail_account.json`
- `data/runtime/gmail_attachments/`

`data/runtime/` is ignored by Git because these files can contain OAuth client secrets and tokens.

Persistent mailbox storage:

- Account metadata: `email_accounts`
- Fetched messages: `email_messages`
- Recipients: `email_recipients`
- Attachments: `email_attachments`
- Initial analysis jobs and results: `processing_jobs`, `email_analysis_results`, `email_category_assignments`

OAuth token material remains outside PostgreSQL and must move to a production secrets store before multi-host deployment.
Local `.env` may also contain `GOOGLE_CREDENTIALS_JSON`, `GOOGLE_TOKEN_JSON`, and `GOOGLE_SEND_TOKEN_JSON` for parity with `coramail_ai`; these values are secrets and must not be committed.

## Test Criteria

- Gmail account modal renders only in Gmail mode.
- Demo mode does not render the Gmail account modal or its opener.
- Existing `GOOGLE_TOKEN_JSON` is recognized as a connected Gmail account without requiring OAuth client JSON.
- Existing `GOOGLE_CREDENTIALS_JSON` is recognized as an OAuth client source so Gmail tokens can be issued without manually pasting `GOOGLE_TOKEN_JSON`.
- Pasting valid `GOOGLE_TOKEN_JSON` in the Gmail account modal marks Gmail as connected.
- Pasting valid `GOOGLE_TOKEN_JSON` updates the active `.env` when that file exists.
- Pasting optional valid `GOOGLE_SEND_TOKEN_JSON` records send-token availability in the modal.
- Pasting invalid token JSON returns a visible error.
- Saving valid client JSON enables the Gmail connect action.
- Saving invalid client JSON returns a visible error.
- OAuth callback stores account metadata, full-access scope, and token without exposing token content in HTML.
- Gmail token refresh or interactive OAuth persists updated `GOOGLE_TOKEN_JSON` to the active `.env` when that file exists.
- Manual sync uses the stored token path.
- Manual sync imports every Gmail INBOX page by default instead of stopping at the first 50-message page.
- `CORAMAIL_GMAIL_MAX_RESULTS` caps sync volume only when explicitly set for development or recovery runs.
- Manual sync idempotently upserts Gmail rows without duplicating provider messages.
- Gmail attachment IDs longer than 255 characters are stored without truncation.
- Gmail UI actions normally use canonical UUIDs. The Mail Decision API also resolves a Gmail provider message ID at its boundary,
  so a stale/read-only Gmail fallback cannot send the provider ID into UUID-only persistence and workflow code.
- New Gmail messages receive successful initial classification and summary results.
- Disconnect removes the token file and marks the account disabled.
- Demo mode still renders fixture-backed inbox data.

## LLMOps Notes

Gmail sync registers classification and summary jobs in PostgreSQL and starts a background queue drain so the
sync response does not wait for every local-model call. The worker executes the shared Mail Decision pipeline and
projects its schema-validated summary and classification. LLM/schema failures remain failed or review-required;
they are not replaced by a rule result marked as AI success. Gmail OAuth uses `https://mail.google.com/`, and the
trash action calls Gmail first and soft-deletes the local row only after the provider succeeds.

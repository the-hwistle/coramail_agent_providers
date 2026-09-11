# app/integrations/naver/AGENTS.md

These rules apply to Naver mail integration work in the Naver worktree.

- Do not modify `/home/ysh/workspace/coramail_agent`.
- Keep IMAP/SMTP calls inside this package.
- Do not use Gmail OAuth or `GOOGLE_*` environment variables.
- Do not ask for or store the normal Naver account password. Use `CORAMAIL_NAVER_APP_PASSWORD`.
- Keep `CORAMAIL_NAVER_MAIL_ADDRESS` and `CORAMAIL_NAVER_IMAP_USERNAME` separate.
- Use `CORAMAIL_NAVER_MAX_RESULTS=0`/`all`/`unlimited` for full mailbox syncs, and set a positive value only for bounded live probes.
- Do not commit real credentials, raw private mail, local DB files, or runtime artifacts.

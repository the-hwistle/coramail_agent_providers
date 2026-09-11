# app/integrations/hiworks/AGENTS.md

These rules apply to Hiworks mail integration work in the Hiworks worktree.

- Do not modify `/home/ysh/workspace/coramail_agent`.
- Keep POP3/SMTP calls inside this package.
- Do not use Gmail OAuth or `GOOGLE_*` environment variables.
- Do not ask for or store the normal Hiworks account password. Use `CORAMAIL_HIWORKS_APP_PASSWORD`.
- Keep `CORAMAIL_HIWORKS_MAIL_ADDRESS` and `CORAMAIL_HIWORKS_POP3_USERNAME` separate.
- Use `CORAMAIL_HIWORKS_MAX_RESULTS=0`/`all`/`unlimited` for full mailbox syncs, and set a positive value only for bounded live probes.
- Do not commit real credentials, raw private mail, local DB files, or runtime artifacts.

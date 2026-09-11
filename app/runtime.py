from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

# The UI server loads the project environment before creating its repositories.
# Runtime is a separate entrypoint, so it must do the same before importing the
# Mail Decision router (the repository is initialized at module import time).
PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = Path(os.getenv("CORAMAIL_ENV_FILE", PROJECT_DIR / ".env")).expanduser()
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)

from app.api.mail_decision import router as mail_decision_router  # noqa: E402
from app.config import database_url  # noqa: E402


app = FastAPI(
    title="CoRA Mail Decision Runtime",
    description="Agentic RAG Mail Decision execution API.",
    version="0.2.0",
)
app.include_router(mail_decision_router)


@app.get("/health")
def health() -> dict[str, str]:
    configured = bool(database_url())
    return {
        "status": "ok" if configured else "degraded",
        "runtime": "mail-decision",
        "database_configured": "true" if configured else "false",
    }

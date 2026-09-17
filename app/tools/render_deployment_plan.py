from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.tools.check_deployment_readiness import Severity, _read_env_file, deployment_readiness_issues


SENSITIVE_KEYS = (
    "CORAMAIL_AUTH_PASSWORD",
    "CORAMAIL_AUTH_SECRET",
    "CORAMAIL_POSTGRES_PASSWORD",
    "CORAMAIL_QDRANT_API_KEY",
    "GOOGLE_CREDENTIALS_JSON",
    "GOOGLE_TOKEN_JSON",
    "GOOGLE_SEND_TOKEN_JSON",
    "CORAMAIL_NAVER_APP_PASSWORD",
    "CORAMAIL_HIWORKS_APP_PASSWORD",
    "CORAMAIL_CLOUDFLARE_TUNNEL_TOKEN",
)

SUMMARY_KEYS = (
    "CORAMAIL_DEPLOYMENT_MODE",
    "CORAMAIL_LLM_RUNTIME",
    "CORAMAIL_EXTERNAL_LLM_APPROVED",
    "CORAMAIL_MAIL_PROVIDER",
    "CORAMAIL_WEB_IMAGE",
    "CORAMAIL_BETA_BASE_URL",
    "CORAMAIL_BETA_PUBLIC",
    "CORAMAIL_BETA_HOST",
    "CORAMAIL_WEB_BIND",
    "CORAMAIL_WEB_PORT",
    "CORAMAIL_EDGE_HTTP_PORT",
    "CORAMAIL_EDGE_HTTPS_PORT",
    "CORAMAIL_CLOUDFLARED_IMAGE",
    "CORAMAIL_POSTGRES_DB",
    "CORAMAIL_QDRANT_CASE_COLLECTION",
    "CORAMAIL_LLM_PROVIDER",
    "CORAMAIL_LLM_BASE_URL",
    "CORAMAIL_TEXT_MODEL",
    "CORAMAIL_CHAT_TEXT_MODEL",
    "CORAMAIL_VISION_MODEL",
    "CORAMAIL_EMBEDDING_MODEL",
)


def deployment_plan(env_file: Path) -> dict[str, object]:
    values = _read_env_file(env_file)
    issues = deployment_readiness_issues(values)
    return {
        "env_file": str(env_file),
        "summary": {key: values.get(key, "") for key in SUMMARY_KEYS},
        "secrets": {key: _secret_state(values.get(key, "")) for key in SENSITIVE_KEYS},
        "readiness": {
            "status": "blocked" if any(issue.severity is Severity.ERROR for issue in issues) else "ready",
            "issues": [
                {
                    "severity": issue.severity.value,
                    "code": issue.code,
                    "message": issue.message,
                }
                for issue in issues
            ],
        },
    }


def _secret_state(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return "missing"
    lowered = stripped.casefold()
    if "replace-with" in lowered or "your-" in lowered:
        return "placeholder"
    return "configured"


def render_markdown(plan: dict[str, object]) -> str:
    summary = plan["summary"]
    secrets = plan["secrets"]
    readiness = plan["readiness"]
    assert isinstance(summary, dict)
    assert isinstance(secrets, dict)
    assert isinstance(readiness, dict)
    lines = [
        "# CoRA Mail Beta Deployment Plan",
        "",
        f"- env_file: `{plan['env_file']}`",
        f"- readiness: `{readiness['status']}`",
        "",
        "## Deployment",
        "",
    ]
    for key in SUMMARY_KEYS:
        lines.append(f"- `{key}`: `{summary.get(key, '')}`")

    lines.extend(["", "## Secret Inputs", ""])
    for key in SENSITIVE_KEYS:
        lines.append(f"- `{key}`: `{secrets.get(key, 'missing')}`")

    issues = readiness.get("issues", [])
    lines.extend(["", "## Readiness Issues", ""])
    if not issues:
        lines.append("- none")
    else:
        for issue in issues:
            if isinstance(issue, dict):
                lines.append(f"- `{issue.get('severity')}` `{issue.get('code')}`: {issue.get('message')}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a redacted CoRA Mail beta deployment plan.")
    parser.add_argument("--env-file", type=Path, default=Path("config/production.env"))
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args()

    plan = deployment_plan(args.env_file)
    if args.format == "json":
        print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
    else:
        print(render_markdown(plan), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

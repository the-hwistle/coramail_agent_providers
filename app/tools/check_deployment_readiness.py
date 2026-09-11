from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from app.web.env_loader import strip_env_quotes


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class ReadinessIssue:
    severity: Severity
    code: str
    message: str


INSECURE_VALUES = {
    "",
    "admin",
    "coramail",
    "replace-with-random-secret",
    "your-client-id",
    "your-client-secret",
    "your-access-token",
    "your-refresh-token",
    "your-send-access-token",
    "your-send-refresh-token",
}
INSECURE_MARKERS = ("replace-with", "your-", "example.com")


def deployment_readiness_issues(env: dict[str, str] | None = None) -> list[ReadinessIssue]:
    values = dict(os.environ if env is None else env)
    issues: list[ReadinessIssue] = []

    _require_false(values, issues, "CORAMAIL_DEMO_MODE", default="false", code="demo-mode")
    _require_false(values, issues, "CORAMAIL_LOCAL_DEV_DEFAULTS", default="false", code="local-dev-defaults")
    _require_false(values, issues, "CORAMAIL_DEV_SEED_DEMO", default="false", code="demo-seed")
    _require_true(values, issues, "CORAMAIL_AUTH_ENABLED", default="true", code="auth-disabled")
    _require_true(values, issues, "CORAMAIL_AUTH_COOKIE_SECURE", default="false", code="insecure-cookie")

    _require_configured(values, issues, "CORAMAIL_DATABASE_URL", code="database-url")
    _require_configured(values, issues, "CORAMAIL_QDRANT_URL", code="qdrant-url")
    _require_configured(values, issues, "CORAMAIL_LLM_BASE_URL", code="llm-url")
    _require_configured(values, issues, "CORAMAIL_WEB_IMAGE", code="web-image")

    _reject_insecure(values, issues, "CORAMAIL_AUTH_USERNAME", code="default-auth-username")
    _reject_insecure(values, issues, "CORAMAIL_AUTH_PASSWORD", code="default-auth-password")
    _reject_insecure(values, issues, "CORAMAIL_AUTH_SECRET", code="weak-auth-secret", min_length=32)
    _reject_insecure(values, issues, "CORAMAIL_POSTGRES_PASSWORD", code="default-postgres-password")
    _reject_placeholder(values, issues, "CORAMAIL_WEB_IMAGE", code="placeholder-web-image")
    _reject_placeholder(values, issues, "CORAMAIL_TEXT_MODEL", code="placeholder-text-model")
    _reject_placeholder(values, issues, "CORAMAIL_CHAT_TEXT_MODEL", code="placeholder-chat-text-model", required=False)
    _reject_placeholder(values, issues, "CORAMAIL_VISION_MODEL", code="placeholder-vision-model")
    _reject_placeholder(values, issues, "CORAMAIL_EMBEDDING_MODEL", code="placeholder-embedding-model")

    llm_provider = values.get("CORAMAIL_LLM_PROVIDER", "ollama").strip().casefold()
    if llm_provider in {"gemini", "openai"}:
        issues.append(
            ReadinessIssue(
                Severity.ERROR,
                "external-llm-provider",
                "CORAMAIL_LLM_PROVIDER must be an approved on-premises provider for production.",
            )
        )

    for name in ("GOOGLE_CREDENTIALS_JSON", "GOOGLE_TOKEN_JSON", "GOOGLE_SEND_TOKEN_JSON"):
        value = values.get(name, "").strip()
        if value and any(marker in value for marker in INSECURE_VALUES - {""}):
            issues.append(
                ReadinessIssue(
                    Severity.ERROR,
                    f"placeholder-{name.lower()}",
                    f"{name} still contains placeholder credential material.",
                )
            )

    for name in ("CORAMAIL_WEB_IMAGE", "CORAMAIL_POSTGRES_IMAGE", "CORAMAIL_QDRANT_IMAGE", "CORAMAIL_OLLAMA_IMAGE"):
        image = values.get(name, "").strip()
        if image.endswith(":latest"):
            issues.append(
                ReadinessIssue(
                    Severity.WARNING,
                    f"unpinned-{name.lower()}",
                    f"{name} uses :latest; pin an image digest or tested version before production rollout.",
                )
            )

    return issues


def _enabled(value: str) -> bool:
    return value.strip().casefold() not in {"0", "false", "off", "no"}


def _require_true(
    values: dict[str, str],
    issues: list[ReadinessIssue],
    name: str,
    *,
    default: str,
    code: str,
) -> None:
    if not _enabled(values.get(name, default)):
        issues.append(ReadinessIssue(Severity.ERROR, code, f"{name} must be enabled for production."))


def _require_false(
    values: dict[str, str],
    issues: list[ReadinessIssue],
    name: str,
    *,
    default: str,
    code: str,
) -> None:
    if _enabled(values.get(name, default)):
        issues.append(ReadinessIssue(Severity.ERROR, code, f"{name} must be disabled for production."))


def _require_configured(
    values: dict[str, str],
    issues: list[ReadinessIssue],
    name: str,
    *,
    code: str,
) -> None:
    if not values.get(name, "").strip():
        issues.append(ReadinessIssue(Severity.ERROR, code, f"{name} is required for production."))


def _reject_insecure(
    values: dict[str, str],
    issues: list[ReadinessIssue],
    name: str,
    *,
    code: str,
    min_length: int = 1,
) -> None:
    value = values.get(name, "").strip()
    lowered = value.casefold()
    if lowered in INSECURE_VALUES or any(marker in lowered for marker in INSECURE_MARKERS) or len(value) < min_length:
        issues.append(ReadinessIssue(Severity.ERROR, code, f"{name} must be set to a non-default secure value."))


def _reject_placeholder(
    values: dict[str, str],
    issues: list[ReadinessIssue],
    name: str,
    *,
    code: str,
    required: bool = True,
) -> None:
    value = values.get(name, "").strip()
    if not value:
        if required:
            issues.append(ReadinessIssue(Severity.ERROR, code, f"{name} is required for production."))
        return
    lowered = value.casefold()
    if lowered in INSECURE_VALUES or any(marker in lowered for marker in INSECURE_MARKERS):
        issues.append(ReadinessIssue(Severity.ERROR, code, f"{name} must not contain placeholder values."))


def main() -> int:
    parser = argparse.ArgumentParser(description="Check CoRA Mail production deployment readiness settings.")
    parser.add_argument("--env-file", type=Path, help="Optional deployment environment file to check.")
    parser.add_argument("--warnings-as-errors", action="store_true")
    args = parser.parse_args()

    env = dict(os.environ)
    if args.env_file is not None:
        env.update(_read_env_file(args.env_file))

    issues = deployment_readiness_issues(env)
    for issue in issues:
        print(f"{issue.severity.value.upper()} {issue.code}: {issue.message}")

    has_errors = any(issue.severity is Severity.ERROR for issue in issues)
    has_warnings = any(issue.severity is Severity.WARNING for issue in issues)
    if has_errors or (args.warnings_as_errors and has_warnings):
        return 1
    print("deployment_readiness=ok")
    return 0


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise FileNotFoundError(f"environment file not found: {path}")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = strip_env_quotes(value.strip())
    return values


if __name__ == "__main__":
    raise SystemExit(main())

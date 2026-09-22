from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

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
    _require_configured(values, issues, "CORAMAIL_BETA_BASE_URL", code="beta-base-url")
    _require_deployment_mode(values, issues)
    _require_llm_runtime(values, issues)
    _require_mail_provider(values, issues)
    _require_public_beta_settings(values, issues)

    _reject_insecure(values, issues, "CORAMAIL_AUTH_USERNAME", code="default-auth-username")
    _reject_insecure(values, issues, "CORAMAIL_AUTH_PASSWORD", code="default-auth-password")
    _reject_insecure(values, issues, "CORAMAIL_AUTH_SECRET", code="weak-auth-secret", min_length=32)
    _reject_insecure(values, issues, "CORAMAIL_POSTGRES_PASSWORD", code="default-postgres-password")
    _reject_placeholder(values, issues, "CORAMAIL_WEB_IMAGE", code="placeholder-web-image")
    _reject_placeholder(values, issues, "CORAMAIL_BETA_BASE_URL", code="placeholder-beta-base-url")
    _reject_placeholder(values, issues, "CORAMAIL_TEXT_MODEL", code="placeholder-text-model")
    _reject_placeholder(values, issues, "CORAMAIL_CHAT_TEXT_MODEL", code="placeholder-chat-text-model", required=False)
    _reject_placeholder(values, issues, "CORAMAIL_VISION_MODEL", code="placeholder-vision-model")
    _reject_placeholder(values, issues, "CORAMAIL_EMBEDDING_MODEL", code="placeholder-embedding-model")

    llm_provider = values.get("CORAMAIL_LLM_PROVIDER", "ollama").strip().casefold()
    if llm_provider in {"gemini", "openai"}:
        _require_external_llm_approval(values, issues, llm_provider)

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


def deployment_exposure_issues(values: dict[str, str], exposure: str) -> list[ReadinessIssue]:
    issues: list[ReadinessIssue] = []
    if exposure == "internal":
        return issues

    if not _enabled(values.get("CORAMAIL_BETA_PUBLIC", "false")):
        issues.append(
            ReadinessIssue(
                Severity.ERROR,
                "public-exposure-disabled",
                f"The {exposure} exposure path requires CORAMAIL_BETA_PUBLIC=true.",
            )
        )

    if exposure == "tunnel" and not values.get("CORAMAIL_CLOUDFLARE_TUNNEL_TOKEN", "").strip():
        issues.append(
            ReadinessIssue(
                Severity.ERROR,
                "cloudflare-tunnel-token",
                "The tunnel exposure path requires CORAMAIL_CLOUDFLARE_TUNNEL_TOKEN.",
            )
        )
    return issues


def _require_deployment_mode(values: dict[str, str], issues: list[ReadinessIssue]) -> None:
    mode = values.get("CORAMAIL_DEPLOYMENT_MODE", "").strip().casefold()
    allowed = {"setup", "saas", "private", "hybrid"}
    if not mode:
        issues.append(
            ReadinessIssue(
                Severity.ERROR,
                "deployment-mode",
                "CORAMAIL_DEPLOYMENT_MODE must be set explicitly for production.",
            )
        )
        return
    if mode not in allowed:
        issues.append(
            ReadinessIssue(
                Severity.ERROR,
                "unsupported-deployment-mode",
                "CORAMAIL_DEPLOYMENT_MODE must be one of: setup, saas, private, hybrid.",
            )
        )


def _require_llm_runtime(values: dict[str, str], issues: list[ReadinessIssue]) -> None:
    deployment_mode = values.get("CORAMAIL_DEPLOYMENT_MODE", "").strip().casefold()
    runtime = values.get("CORAMAIL_LLM_RUNTIME", "").strip().casefold()
    allowed = {"setup", "local", "managed", "external"}
    if not runtime:
        issues.append(
            ReadinessIssue(
                Severity.ERROR,
                "llm-runtime",
                "CORAMAIL_LLM_RUNTIME must be set explicitly for production.",
            )
        )
        return
    if runtime not in allowed:
        issues.append(
            ReadinessIssue(
                Severity.ERROR,
                "unsupported-llm-runtime",
                "CORAMAIL_LLM_RUNTIME must be one of: setup, local, managed, external.",
            )
        )
        return
    if deployment_mode == "private" and runtime == "external":
        issues.append(
            ReadinessIssue(
                Severity.ERROR,
                "private-external-llm",
                "Private deployment must not use an external LLM runtime.",
            )
        )


def _require_external_llm_approval(
    values: dict[str, str],
    issues: list[ReadinessIssue],
    provider: str,
) -> None:
    runtime = values.get("CORAMAIL_LLM_RUNTIME", "").strip().casefold()
    approved = _enabled(values.get("CORAMAIL_EXTERNAL_LLM_APPROVED", "false"))
    if runtime != "external" or not approved:
        issues.append(
            ReadinessIssue(
                Severity.ERROR,
                "external-llm-provider",
                (
                    f"CORAMAIL_LLM_PROVIDER={provider} requires CORAMAIL_LLM_RUNTIME=external "
                    "and CORAMAIL_EXTERNAL_LLM_APPROVED=true."
                ),
            )
        )


def _require_mail_provider(values: dict[str, str], issues: list[ReadinessIssue]) -> None:
    provider = values.get("CORAMAIL_MAIL_PROVIDER", "").strip().casefold()
    if not provider:
        issues.append(
            ReadinessIssue(
                Severity.ERROR,
                "mail-provider",
                "CORAMAIL_MAIL_PROVIDER must be set explicitly for production.",
            )
        )
        return

    if provider not in {"setup", "gmail", "naver", "hiworks"}:
        issues.append(
            ReadinessIssue(
                Severity.ERROR,
                "unsupported-mail-provider",
                "CORAMAIL_MAIL_PROVIDER must be one of: setup, gmail, naver, hiworks.",
            )
        )
        return

    if provider == "naver":
        _require_configured(values, issues, "CORAMAIL_NAVER_MAIL_ADDRESS", code="naver-mail-address")
        _require_configured(values, issues, "CORAMAIL_NAVER_APP_PASSWORD", code="naver-app-password")
    elif provider == "hiworks":
        _require_configured(values, issues, "CORAMAIL_HIWORKS_MAIL_ADDRESS", code="hiworks-mail-address")
        _require_configured(values, issues, "CORAMAIL_HIWORKS_APP_PASSWORD", code="hiworks-app-password")


def _require_public_beta_settings(values: dict[str, str], issues: list[ReadinessIssue]) -> None:
    if not _enabled(values.get("CORAMAIL_BETA_PUBLIC", "false")):
        return

    beta_url = values.get("CORAMAIL_BETA_BASE_URL", "").strip()
    beta_host = values.get("CORAMAIL_BETA_HOST", "").strip()
    parsed = urlparse(beta_url)

    if parsed.scheme != "https":
        issues.append(
            ReadinessIssue(
                Severity.ERROR,
                "public-beta-https",
                "CORAMAIL_BETA_PUBLIC=true requires CORAMAIL_BETA_BASE_URL to use https://.",
            )
        )

    if not parsed.hostname or parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        issues.append(
            ReadinessIssue(
                Severity.ERROR,
                "public-beta-host",
                "CORAMAIL_BETA_PUBLIC=true requires a non-localhost CORAMAIL_BETA_BASE_URL hostname.",
            )
        )
    elif parsed.hostname.casefold().endswith(".trycloudflare.com"):
        issues.append(
            ReadinessIssue(
                Severity.ERROR,
                "public-beta-quick-tunnel",
                (
                    "CORAMAIL_BETA_PUBLIC=true must not use an ad-hoc trycloudflare.com Quick Tunnel URL. "
                    "Use a Cloudflare Named Tunnel public hostname on a registered domain, or mark the beta "
                    "as non-public until the fixed hostname is configured."
                ),
            )
        )

    if not beta_host:
        issues.append(
            ReadinessIssue(
                Severity.ERROR,
                "beta-host",
                "CORAMAIL_BETA_HOST is required when CORAMAIL_BETA_PUBLIC=true.",
            )
        )
    else:
        lowered_host = beta_host.casefold()
        if any(marker in lowered_host for marker in INSECURE_MARKERS) or lowered_host in INSECURE_VALUES:
            issues.append(
                ReadinessIssue(
                    Severity.ERROR,
                    "placeholder-beta-host",
                    "CORAMAIL_BETA_HOST must not contain placeholder values.",
                )
            )
        if parsed.hostname and parsed.hostname.casefold() != lowered_host:
            issues.append(
                ReadinessIssue(
                    Severity.ERROR,
                    "public-beta-host-mismatch",
                    "CORAMAIL_BETA_HOST must match the hostname in CORAMAIL_BETA_BASE_URL.",
                )
            )


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
    parser.add_argument(
        "--exposure",
        choices=("internal", "edge", "tunnel"),
        help="Require settings for the selected mutually exclusive exposure path.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format.")
    args = parser.parse_args()

    env = dict(os.environ)
    if args.env_file is not None:
        env.update(_read_env_file(args.env_file))

    issues = deployment_readiness_issues(env)
    if args.exposure is not None:
        issues.extend(deployment_exposure_issues(env, args.exposure))
    if args.format == "json":
        print(
            json.dumps(
                {
                    "deployment_readiness": "issues" if issues else "ok",
                    "issues": [
                        {
                            "severity": issue.severity.value,
                            "code": issue.code,
                            "message": issue.message,
                        }
                        for issue in issues
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    else:
        for issue in issues:
            print(f"{issue.severity.value.upper()} {issue.code}: {issue.message}")

    has_errors = any(issue.severity is Severity.ERROR for issue in issues)
    has_warnings = any(issue.severity is Severity.WARNING for issue in issues)
    if has_errors or (args.warnings_as_errors and has_warnings):
        return 1
    if args.format == "text":
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

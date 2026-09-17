from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class GmailAccountRepository:
    """Local runtime store for Gmail web OAuth settings.

    This is a temporary repository until the documented PostgreSQL `email_accounts`
    path is implemented. Runtime files live under `data/runtime/`, which is ignored
    by Git because it contains OAuth client configuration and tokens.
    """

    def __init__(self, project_dir: Path):
        runtime_dir = os.getenv("CORAMAIL_RUNTIME_DIR", "data/runtime").strip() or "data/runtime"
        path = Path(runtime_dir).expanduser()
        self.env_path = self._path_from_env(project_dir, "CORAMAIL_ENV_FILE") or (project_dir / ".env")
        self.runtime_dir = path if path.is_absolute() else (project_dir / path).resolve()
        self.saved_client_config_path = self.runtime_dir / "gmail_oauth_client.json"
        self.env_client_config_path = self._path_from_env(project_dir, "CORAMAIL_GMAIL_CREDENTIALS_PATH")
        self.env_client_config_json = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
        self.env_primary_token_json = os.getenv("GOOGLE_TOKEN_JSON", "").strip()
        self.env_send_token_json = os.getenv("GOOGLE_SEND_TOKEN_JSON", "").strip()
        self.token_path = self.runtime_dir / "gmail_token.json"
        self.send_token_path = self.runtime_dir / "gmail_send_token.json"
        self.account_path = self.runtime_dir / "gmail_account.json"

    @property
    def client_config_path(self) -> Path:
        if self.env_client_config_path and self.env_client_config_path.exists():
            return self.env_client_config_path
        return self.saved_client_config_path

    def has_client_config(self) -> bool:
        return bool(self.client_config_info()) or self.client_config_path.exists()

    def client_config_info(self) -> dict[str, Any]:
        if not self.env_client_config_json:
            return {}
        try:
            parsed = json.loads(self.env_client_config_json)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def save_client_config(self, raw_json: str) -> None:
        parsed = json.loads(raw_json)
        if not isinstance(parsed, dict) or not any(key in parsed for key in ("web", "installed")):
            raise ValueError("Google OAuth client JSON must contain a `web` or `installed` object.")
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.saved_client_config_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_connected_account(self, *, email_address: str, token_json: str, scopes: list[str]) -> None:
        token_info = self._parse_token_json(token_json, "GOOGLE_TOKEN_JSON")
        compact_token_json = json.dumps(token_info, ensure_ascii=False, separators=(",", ":"))
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(token_json, encoding="utf-8")
        self._persist_json_env("GOOGLE_TOKEN_JSON", token_info)
        self.env_primary_token_json = compact_token_json
        self._write_account(
            {
                "provider": "gmail",
                "email_address": email_address,
                "status": "active",
                "scopes": scopes,
                "connected_at": self._now(),
                "last_synced_at": "",
                "last_sync_status": "",
                "last_sync_error": "",
                "credentials_reference": str(self.token_path),
            }
        )

    def save_existing_tokens(self, *, primary_token_json: str, send_token_json: str = "") -> None:
        primary_token = self._parse_token_json(primary_token_json, "GOOGLE_TOKEN_JSON")
        send_token = self._parse_token_json(send_token_json, "GOOGLE_SEND_TOKEN_JSON") if send_token_json.strip() else {}
        self._persist_json_env("GOOGLE_TOKEN_JSON", primary_token)
        self.env_primary_token_json = json.dumps(primary_token, ensure_ascii=False, separators=(",", ":"))
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(json.dumps(primary_token, ensure_ascii=False, indent=2), encoding="utf-8")
        if send_token:
            self._persist_json_env("GOOGLE_SEND_TOKEN_JSON", send_token)
            self.env_send_token_json = json.dumps(send_token, ensure_ascii=False, separators=(",", ":"))
            self.send_token_path.write_text(json.dumps(send_token, ensure_ascii=False, indent=2), encoding="utf-8")
        elif self.send_token_path.exists():
            self.send_token_path.unlink()
        self._write_account(
            {
                "provider": "gmail",
                "email_address": self._token_email(primary_token),
                "status": "active",
                "scopes": self._token_scopes(primary_token),
                "connected_at": self._now(),
                "last_synced_at": "",
                "last_sync_status": "",
                "last_sync_error": "",
                "credentials_reference": str(self.token_path),
                "send_credentials_reference": str(self.send_token_path) if send_token else "",
            }
        )

    def save_account_identity(self, *, email_address: str) -> None:
        normalized_email = email_address.strip()
        if not normalized_email:
            return
        account = self.account()
        primary_token = self.primary_token_info()
        account.update(
            {
                "provider": "gmail",
                "email_address": normalized_email,
                "status": "active",
                "scopes": self._token_scopes(primary_token) or account.get("scopes", []),
                "connected_at": account.get("connected_at") or self._now(),
                "last_synced_at": account.get("last_synced_at", ""),
                "last_sync_status": account.get("last_sync_status", ""),
                "last_sync_error": account.get("last_sync_error", ""),
                "credentials_reference": (
                    "GOOGLE_TOKEN_JSON"
                    if self.env_primary_token_json
                    else str(self.token_path) if self.token_path.exists() else account.get("credentials_reference", "")
                ),
                "send_credentials_reference": account.get("send_credentials_reference", ""),
            }
        )
        self._write_account(account)

    def disconnect(self) -> None:
        if self.token_path.exists():
            self.token_path.unlink()
        if self.send_token_path.exists():
            self.send_token_path.unlink()
        account = self.account()
        if account:
            account.update(
                {
                    "status": "disabled",
                    "last_sync_status": "",
                    "last_sync_error": "",
                    "updated_at": self._now(),
                }
            )
            self._write_account(account)

    def record_oauth_error(self, error: str) -> None:
        account = self.account()
        account.update(
            {
                "provider": "gmail",
                "status": "error",
                "last_sync_status": "oauth_error",
                "last_sync_error": error,
                "credentials_reference": str(self.token_path) if self.token_path.exists() else "",
            }
        )
        self._write_account(account)

    def account(self) -> dict[str, Any]:
        if not self.account_path.exists():
            return {}
        try:
            parsed = json.loads(self.account_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def connected_account(self) -> dict[str, Any]:
        account = self.account()
        primary_token = self.primary_token_info()
        if primary_token:
            return {
                "provider": "gmail",
                "email_address": self._token_email(primary_token),
                "status": "active",
                "scopes": self._token_scopes(primary_token),
                "credentials_reference": "GOOGLE_TOKEN_JSON" if self.env_primary_token_json else str(self.token_path),
            }
        if account.get("status") not in {"active", "error"} or not self.token_path.exists():
            return {}
        return account

    def update_sync_result(self, *, ok: bool, error: str = "") -> None:
        account = self.account()
        if not account:
            account = {"provider": "gmail", "email_address": "", "connected_at": ""}
        account.update(
            {
                "status": "active" if ok else "error",
                "last_synced_at": self._now() if ok else account.get("last_synced_at", ""),
                "last_sync_status": "ok" if ok else "error",
                "last_sync_error": "" if ok else error,
                "updated_at": self._now(),
                "credentials_reference": str(self.token_path) if self.token_path.exists() else "",
            }
        )
        self._write_account(account)

    def public_status(self) -> dict[str, Any]:
        self._reload_runtime_state()
        account = self.account()
        primary_token = self.primary_token_info()
        send_token = self.send_token_info()
        connected = bool(primary_token) or (account.get("status") in {"active", "error"} and self.token_path.exists())
        scopes = self._token_scopes(primary_token) or account.get("scopes", [])
        email_address = self._token_email(primary_token) or (account.get("email_address", "") if connected else "")
        return {
            "connected": connected,
            "has_client_config": self.has_client_config(),
            "email_address": email_address,
            "status": "active" if primary_token else account.get("status", "not_connected") if connected else "not_connected",
            "scopes": scopes,
            "connected_at": account.get("connected_at", ""),
            "last_synced_at": account.get("last_synced_at", ""),
            "last_sync_status": account.get("last_sync_status", ""),
            "last_sync_error": account.get("last_sync_error", "") if connected else "",
            "client_config_source": self._client_config_source(),
            "token_source": "env" if self.env_primary_token_json and primary_token else "runtime" if primary_token else "",
            "has_send_token": bool(send_token),
            "can_disconnect": connected and not (self.env_primary_token_json and primary_token),
        }

    def primary_token_info(self) -> dict[str, Any]:
        self._reload_runtime_state()
        return self._json_env_info(self.env_primary_token_json) or self._json_file_info(self.token_path)

    def send_token_info(self) -> dict[str, Any]:
        self._reload_runtime_state()
        return self._json_env_info(self.env_send_token_json) or self._json_file_info(self.send_token_path)

    def _reload_runtime_state(self) -> None:
        self.env_client_config_json = self._current_env_value("GOOGLE_CREDENTIALS_JSON")
        self.env_primary_token_json = self._current_env_value("GOOGLE_TOKEN_JSON")
        self.env_send_token_json = self._current_env_value("GOOGLE_SEND_TOKEN_JSON")

    def _write_account(self, payload: dict[str, Any]) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        next_payload = {**payload, "updated_at": self._now()}
        self.account_path.write_text(json.dumps(next_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _path_from_env(project_dir: Path, name: str) -> Path | None:
        value = os.getenv(name, "").strip()
        if not value:
            return None
        path = Path(value).expanduser()
        return path if path.is_absolute() else (project_dir / path).resolve()

    def _persist_json_env(self, name: str, payload: dict[str, Any]) -> None:
        if not self.env_path.exists():
            return
        compact_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        next_line = f"{name}='{compact_json}'"
        existing_lines = self.env_path.read_text(encoding="utf-8").splitlines()
        replaced = False
        updated_lines: list[str] = []
        for line in existing_lines:
            if line.strip().startswith(f"{name}="):
                updated_lines.append(next_line)
                replaced = True
            else:
                updated_lines.append(line)
        if not replaced:
            if updated_lines and updated_lines[-1].strip():
                updated_lines.append("")
            updated_lines.append(next_line)
        self.env_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
        os.environ[name] = compact_json

    def _current_env_value(self, name: str) -> str:
        file_value = self._read_dotenv_value(name)
        if file_value:
            os.environ[name] = file_value
            return file_value
        return os.getenv(name, "").strip()

    def _read_dotenv_value(self, name: str) -> str:
        if not self.env_path.exists():
            return ""
        prefix = f"{name}="
        for line in self.env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or not stripped.startswith(prefix):
                continue
            return self._strip_env_quotes(stripped.split("=", 1)[1].strip())
        return ""

    @staticmethod
    def _strip_env_quotes(value: str) -> str:
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            return value[1:-1]
        return value

    def _client_config_source(self) -> str:
        if self.client_config_info():
            return "env-json"
        if self.env_client_config_path and self.env_client_config_path.exists():
            return "env-path"
        if self.saved_client_config_path.exists():
            return "runtime"
        return ""

    @staticmethod
    def _json_env_info(raw_value: str) -> dict[str, Any]:
        if not raw_value:
            return {}
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _json_file_info(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _parse_token_json(raw_value: str, label: str) -> dict[str, Any]:
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label} 형식이 올바른 JSON이 아닙니다.") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"{label}은 JSON object여야 합니다.")
        if not str(parsed.get("refresh_token") or "").strip() and not str(parsed.get("token") or "").strip():
            raise ValueError(f"{label}에 token 또는 refresh_token이 없습니다.")
        return parsed

    @staticmethod
    def _token_scopes(token_info: dict[str, Any]) -> list[str]:
        scopes = token_info.get("scopes") if isinstance(token_info.get("scopes"), list) else []
        return [str(scope) for scope in scopes if str(scope).strip()]

    @staticmethod
    def _token_email(token_info: dict[str, Any]) -> str:
        return str(
            token_info.get("account")
            or token_info.get("email")
            or token_info.get("email_address")
            or ""
        ).strip()

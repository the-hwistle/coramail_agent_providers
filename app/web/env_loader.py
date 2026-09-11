from __future__ import annotations

import os
from pathlib import Path


def strip_env_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_dotenv_file(
    *,
    default_path: Path,
    env_path: str | Path | None = None,
    environ: dict[str, str] | os._Environ[str] | None = None,
) -> Path:
    target_environ = environ if environ is not None else os.environ
    configured_path = target_environ.get("CORAMAIL_ENV_FILE")
    path = Path(env_path or configured_path or default_path).expanduser().resolve()
    if not path.exists():
        return path

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        target_environ.setdefault(key.strip(), strip_env_quotes(value.strip()))
    return path

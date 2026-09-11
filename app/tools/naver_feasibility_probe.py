from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.integrations.naver.sync_client import NaverImapConfig, NaverSyncError, probe_inbox
from app.web.env_loader import load_dotenv_file


PROJECT_DIR = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Naver IMAP feasibility without persisting mail.")
    parser.add_argument("--env-file", default=os.getenv("CORAMAIL_ENV_FILE", "config/naver-feasibility.env"))
    parser.add_argument("--max-results", type=int, default=None)
    parser.add_argument("--summary-only", action="store_true", help="Do not print message preview metadata.")
    args = parser.parse_args()

    env_path = Path(args.env_file).expanduser()
    if not env_path.is_absolute():
        env_path = PROJECT_DIR / env_path
    load_dotenv_file(default_path=PROJECT_DIR / ".env", env_path=env_path)
    if args.max_results is not None:
        os.environ["CORAMAIL_NAVER_MAX_RESULTS"] = str(args.max_results)

    try:
        result = probe_inbox(NaverImapConfig.from_env())
    except NaverSyncError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(_public_result(result, summary_only=args.summary_only), ensure_ascii=False, indent=2))
    return 0


def _public_result(result: dict[str, Any], *, summary_only: bool = False) -> dict[str, Any]:
    public = {key: value for key, value in result.items() if key != "previews"}
    if not summary_only:
        public["previews"] = [asdict(item) for item in result.get("previews", [])]
    return public


if __name__ == "__main__":
    raise SystemExit(main())

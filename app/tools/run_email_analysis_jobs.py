from __future__ import annotations

import argparse
import json
import os

from app.services.postgres_email_analysis_worker import PostgresEmailAnalysisWorker


def main() -> int:
    parser = argparse.ArgumentParser(description="Run pending CoRA Mail email analysis jobs.")
    parser.add_argument("--database-url", default=os.getenv("CORAMAIL_DATABASE_URL", ""))
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("database URL is required via --database-url or CORAMAIL_DATABASE_URL")

    result = PostgresEmailAnalysisWorker(args.database_url).run_pending(limit=args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

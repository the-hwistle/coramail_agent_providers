from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.repositories.demo_mail_repository import DemoMailRepository
from app.repositories.postgres_seed_writer import PostgresSeedWriter, ordered_table_counts
from app.services.demo_seed_service import DemoSeedService


PROJECT_DIR = Path(__file__).resolve().parents[2]
DEMO_DIR = PROJECT_DIR / "data" / "demo"


def main() -> int:
    parser = argparse.ArgumentParser(description="Load fixture-backed demo seed rows into PostgreSQL.")
    parser.add_argument("--demo-dir", type=Path, default=DEMO_DIR)
    parser.add_argument(
        "--database-url",
        default=os.getenv("CORAMAIL_DATABASE_URL", ""),
        help="PostgreSQL connection URL. Defaults to CORAMAIL_DATABASE_URL.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Build and validate the seed bundle without writing.")
    args = parser.parse_args()

    service = DemoSeedService(DemoMailRepository(args.demo_dir))
    bundle = service.build_seed_bundle()
    counts = service.validate_seed_bundle(bundle)

    if args.dry_run:
        print(json.dumps({"status": "ok", "dry_run": True, "counts": counts}, ensure_ascii=False, indent=2))
        return 0

    database_url = str(args.database_url or "").strip()
    if not database_url:
        parser.error("--database-url or CORAMAIL_DATABASE_URL is required unless --dry-run is used.")

    result = PostgresSeedWriter(database_url).write_bundle(bundle)
    print(
        json.dumps(
            {
                "status": "ok",
                "dry_run": False,
                "validated_counts": counts,
                "written_counts": result.table_counts,
                "total_rows": result.total_rows,
                "target_tables": ordered_table_counts(bundle),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

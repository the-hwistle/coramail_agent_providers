from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.repositories.demo_mail_repository import DemoMailRepository
from app.services.demo_seed_service import DemoSeedService


PROJECT_DIR = Path(__file__).resolve().parents[2]
DEMO_DIR = PROJECT_DIR / "data" / "demo"


def main() -> int:
    parser = argparse.ArgumentParser(description="Export fixture-backed demo rows for PostgreSQL seeding.")
    parser.add_argument("--demo-dir", type=Path, default=DEMO_DIR)
    parser.add_argument("--output", type=Path, default=None, help="Write the seed bundle JSON to this path.")
    parser.add_argument("--check", action="store_true", help="Validate the generated seed bundle and print row counts.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    service = DemoSeedService(DemoMailRepository(args.demo_dir))
    bundle = service.build_seed_bundle()
    if args.check:
        print(json.dumps(service.validate_seed_bundle(bundle), ensure_ascii=False, indent=2))
        return 0

    payload = json.dumps(bundle, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

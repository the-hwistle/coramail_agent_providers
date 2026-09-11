from __future__ import annotations

import argparse
import os
from pathlib import Path

from app.repositories.postgres_seed_writer import PostgresSeedWriterError


PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA_DIR = PROJECT_DIR / "db" / "postgresql"


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply ordered CoRA Mail PostgreSQL schema migrations.")
    parser.add_argument(
        "--schema",
        type=Path,
        action="append",
        default=None,
        help="Specific SQL file to apply. Repeat for multiple files. Defaults to all db/postgresql/*.sql files.",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("CORAMAIL_DATABASE_URL", ""),
        help="PostgreSQL connection URL. Defaults to CORAMAIL_DATABASE_URL.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report ordered files and statement counts only.")
    args = parser.parse_args()

    schema_paths = _schema_paths(args.schema)
    schemas = [(path, path.read_text(encoding="utf-8")) for path in schema_paths]

    if args.dry_run:
        for path, schema_sql in schemas:
            print(f"schema={path} statements={_statement_count(schema_sql)}")
        print(f"files={len(schemas)} total_statements={sum(_statement_count(sql) for _, sql in schemas)}")
        return 0

    database_url = str(args.database_url or "").strip()
    if not database_url:
        parser.error("--database-url or CORAMAIL_DATABASE_URL is required unless --dry-run is used.")

    psycopg = _load_psycopg()
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cursor:
            for path, schema_sql in schemas:
                cursor.execute(schema_sql)
                print(f"applied schema={path} statements={_statement_count(schema_sql)}")

    print(f"applied_files={len(schemas)}")
    return 0


def _schema_paths(explicit_paths: list[Path] | None) -> list[Path]:
    if explicit_paths:
        paths = [path.expanduser().resolve() for path in explicit_paths]
    else:
        paths = sorted(DEFAULT_SCHEMA_DIR.glob("*.sql"))
    if not paths:
        raise FileNotFoundError(f"no PostgreSQL schema files found under {DEFAULT_SCHEMA_DIR}")
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"schema files not found: {missing}")
    return paths


def _load_psycopg():
    try:
        import psycopg
    except ImportError as exc:
        raise PostgresSeedWriterError(
            "Applying the PostgreSQL schema requires psycopg. Install psycopg in the runtime environment first."
        ) from exc
    return psycopg


def _statement_count(schema_sql: str) -> int:
    return sum(1 for part in schema_sql.split(";") if part.strip())


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.repositories.demo_mail_repository import DemoMailRepository
from app.repositories.postgres_seed_writer import PostgresSeedWriter
from app.services.demo_seed_service import DemoSeedService
from app.tools.apply_postgres_schema import DEFAULT_SCHEMA_DIR, _statement_count


PROJECT_DIR = Path(__file__).resolve().parents[2]
DEMO_DIR = PROJECT_DIR / "data" / "demo"


def main() -> int:
    database_url = _required_env("CORAMAIL_DATABASE_URL")
    qdrant_url = os.getenv("CORAMAIL_QDRANT_URL", "http://qdrant:6333").rstrip("/")
    collection = os.getenv("CORAMAIL_QDRANT_CASE_COLLECTION", "coramail_cases_clean_v2").strip()
    vector_size = int(os.getenv("CORAMAIL_QDRANT_VECTOR_SIZE", "768"))
    seed_demo = os.getenv("CORAMAIL_DEV_SEED_DEMO", "true").strip().casefold() not in {"0", "false", "off", "no"}

    _wait_for_postgres(database_url)
    _wait_for_qdrant(qdrant_url)
    _ensure_qdrant_collection(qdrant_url, collection, vector_size)
    _apply_postgres_schema(database_url)
    if seed_demo:
        _load_demo_seed(database_url)
    return 0


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _wait_for_postgres(database_url: str) -> None:
    import psycopg

    deadline = time.monotonic() + float(os.getenv("CORAMAIL_DEV_WAIT_SECONDS", "90"))
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(database_url, connect_timeout=3) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
            print("postgres=ready")
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"PostgreSQL did not become ready: {last_error}") from last_error


def _wait_for_qdrant(qdrant_url: str) -> None:
    deadline = time.monotonic() + float(os.getenv("CORAMAIL_DEV_WAIT_SECONDS", "90"))
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            _request("GET", qdrant_url, "/collections")
            print("qdrant=ready")
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"Qdrant did not become ready: {last_error}") from last_error


def _ensure_qdrant_collection(qdrant_url: str, collection: str, vector_size: int) -> None:
    path = f"/collections/{collection}"
    try:
        _request("GET", qdrant_url, path)
        print(f"qdrant_collection={collection} status=exists")
        return
    except HTTPError as exc:
        if exc.code != 404:
            raise
    payload = {"vectors": {"size": vector_size, "distance": "Cosine"}}
    _request("PUT", qdrant_url, path, payload)
    print(f"qdrant_collection={collection} status=created vector_size={vector_size}")


def _apply_postgres_schema(database_url: str) -> None:
    import psycopg

    schema_paths = sorted(DEFAULT_SCHEMA_DIR.glob("*.sql"))
    if not schema_paths:
        raise FileNotFoundError(f"no PostgreSQL schema files found under {DEFAULT_SCHEMA_DIR}")
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cursor:
            for path in schema_paths:
                schema_sql = path.read_text(encoding="utf-8")
                cursor.execute(schema_sql)
                print(f"applied schema={path} statements={_statement_count(schema_sql)}")
    print(f"applied_files={len(schema_paths)}")


def _load_demo_seed(database_url: str) -> None:
    service = DemoSeedService(DemoMailRepository(DEMO_DIR))
    bundle = service.build_seed_bundle()
    counts = service.validate_seed_bundle(bundle)
    result = PostgresSeedWriter(database_url).write_bundle(bundle)
    print(
        json.dumps(
            {
                "demo_seed": "ok",
                "validated_counts": counts,
                "written_counts": result.table_counts,
                "total_rows": result.total_rows,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def _request(method: str, base_url: str, path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}/{path.lstrip('/')}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=10) as response:
        body = response.read().decode("utf-8")
        return json.loads(body) if body else {}


if __name__ == "__main__":
    raise SystemExit(main())

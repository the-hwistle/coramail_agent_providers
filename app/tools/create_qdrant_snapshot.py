from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.config import qdrant_case_collection, qdrant_url


class QdrantSnapshotError(RuntimeError):
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Create and download a Qdrant collection snapshot.")
    parser.add_argument("--qdrant-url", default=qdrant_url())
    parser.add_argument("--collection", default=qdrant_case_collection())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--api-key", default=os.getenv("CORAMAIL_QDRANT_API_KEY", ""))
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_name = create_collection_snapshot(
        base_url=args.qdrant_url,
        collection=args.collection,
        api_key=args.api_key,
        timeout_seconds=args.timeout_seconds,
    )
    output_path = args.output_dir / snapshot_name
    download_collection_snapshot(
        base_url=args.qdrant_url,
        collection=args.collection,
        snapshot_name=snapshot_name,
        output_path=output_path,
        api_key=args.api_key,
        timeout_seconds=args.timeout_seconds,
    )
    print(f"qdrant_snapshot={output_path} collection={args.collection}")
    return 0


def create_collection_snapshot(
    *,
    base_url: str,
    collection: str,
    api_key: str = "",
    timeout_seconds: float = 120.0,
) -> str:
    payload = _request_json(
        "POST",
        base_url,
        f"/collections/{quote(collection, safe='')}/snapshots?wait=true",
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )
    result = payload.get("result") if isinstance(payload, dict) else None
    snapshot_name = result.get("name") if isinstance(result, dict) else None
    if not isinstance(snapshot_name, str) or not snapshot_name:
        raise QdrantSnapshotError("Qdrant snapshot response did not include result.name")
    return snapshot_name


def download_collection_snapshot(
    *,
    base_url: str,
    collection: str,
    snapshot_name: str,
    output_path: Path,
    api_key: str = "",
    timeout_seconds: float = 120.0,
) -> None:
    request = _request(
        "GET",
        base_url,
        f"/collections/{quote(collection, safe='')}/snapshots/{quote(snapshot_name, safe='')}",
        api_key=api_key,
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            output_path.write_bytes(response.read())
    except HTTPError:
        raise
    except (OSError, URLError, TimeoutError) as exc:
        raise QdrantSnapshotError(f"Qdrant snapshot download failed: {exc}") from exc


def _request_json(
    method: str,
    base_url: str,
    path: str,
    *,
    api_key: str,
    timeout_seconds: float,
) -> dict[str, object]:
    request = _request(method, base_url, path, api_key=api_key)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except HTTPError:
        raise
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise QdrantSnapshotError(f"Qdrant snapshot request failed: {method} {path}: {exc}") from exc


def _request(method: str, base_url: str, path: str, *, api_key: str) -> Request:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["api-key"] = api_key
    return Request(f"{base_url.rstrip('/')}/{path.lstrip('/')}", method=method, headers=headers)


if __name__ == "__main__":
    raise SystemExit(main())

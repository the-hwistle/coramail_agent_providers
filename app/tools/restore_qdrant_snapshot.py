from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4

from app.config import qdrant_case_collection, qdrant_url


class QdrantRestoreError(RuntimeError):
    pass


def restore_collection_snapshot(
    *,
    base_url: str,
    collection: str,
    snapshot_path: Path,
    api_key: str = "",
    timeout_seconds: float = 120.0,
) -> dict[str, object]:
    if not snapshot_path.is_file() or snapshot_path.stat().st_size <= 0:
        raise QdrantRestoreError(f"snapshot is missing or empty: {snapshot_path}")

    boundary = f"coramail-{uuid4().hex}"
    filename = snapshot_path.name.replace('"', "")
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="snapshot"; filename="{filename}"\r\n'.encode(),
            b"Content-Type: application/octet-stream\r\n\r\n",
            snapshot_path.read_bytes(),
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if api_key:
        headers["api-key"] = api_key
    request = Request(
        f"{base_url.rstrip('/')}/collections/{quote(collection, safe='')}/snapshots/upload?priority=snapshot",
        data=body,
        method="POST",
        headers=headers,
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError:
        raise
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise QdrantRestoreError(f"Qdrant snapshot restore failed: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise QdrantRestoreError("Qdrant snapshot restore did not return status=ok")
    return payload


def collection_info(
    *,
    base_url: str,
    collection: str,
    api_key: str = "",
    timeout_seconds: float = 30.0,
) -> dict[str, object]:
    headers = {"api-key": api_key} if api_key else {}
    request = Request(
        f"{base_url.rstrip('/')}/collections/{quote(collection, safe='')}",
        method="GET",
        headers=headers,
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError:
        raise
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise QdrantRestoreError(f"Qdrant collection verification failed: {exc}") from exc
    result = payload.get("result") if isinstance(payload, dict) else None
    if payload.get("status") != "ok" or not isinstance(result, dict):
        raise QdrantRestoreError("Qdrant collection verification did not return a result")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore and verify a Qdrant collection snapshot.")
    parser.add_argument("snapshot_path", type=Path)
    parser.add_argument("--qdrant-url", default=qdrant_url())
    parser.add_argument("--collection", default=qdrant_case_collection())
    parser.add_argument("--api-key", default=os.getenv("CORAMAIL_QDRANT_API_KEY", ""))
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    args = parser.parse_args()

    restore_collection_snapshot(
        base_url=args.qdrant_url,
        collection=args.collection,
        snapshot_path=args.snapshot_path,
        api_key=args.api_key,
        timeout_seconds=args.timeout_seconds,
    )
    result = collection_info(
        base_url=args.qdrant_url,
        collection=args.collection,
        api_key=args.api_key,
        timeout_seconds=args.timeout_seconds,
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "collection": args.collection,
                "points_count": result.get("points_count"),
                "collection_status": result.get("status"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

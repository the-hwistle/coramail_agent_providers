from __future__ import annotations

import argparse
import json
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any


class BackupVerificationError(RuntimeError):
    pass


def _read_manifest(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _artifact(backup_dir: Path, name: str, *, label: str) -> Path:
    relative = PurePosixPath(name)
    if not name or relative.is_absolute() or ".." in relative.parts:
        raise BackupVerificationError(f"{label} has an unsafe path")
    path = backup_dir.joinpath(*relative.parts)
    if not path.is_file() or path.stat().st_size <= 0:
        raise BackupVerificationError(f"{label} is missing or empty: {name}")
    return path


def _verify_runtime_archive(path: Path) -> tuple[int, int]:
    file_count = 0
    total_bytes = 0
    try:
        with tarfile.open(path, mode="r:gz") as archive:
            for member in archive.getmembers():
                member_path = PurePosixPath(member.name)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise BackupVerificationError(f"runtime archive contains an unsafe path: {member.name}")
                if member.issym() or member.islnk():
                    raise BackupVerificationError(f"runtime archive contains a link: {member.name}")
                if member.isfile():
                    if not member_path.parts or member_path.parts[0] != "runtime":
                        raise BackupVerificationError(
                            f"runtime archive contains a file outside runtime/: {member.name}"
                        )
                    file_count += 1
                    total_bytes += member.size
    except (tarfile.TarError, OSError) as exc:
        raise BackupVerificationError(f"runtime archive is unreadable: {exc}") from exc
    if file_count == 0:
        raise BackupVerificationError("runtime archive contains no files")
    return file_count, total_bytes


def verify_production_backup(backup_dir: Path) -> dict[str, Any]:
    root = backup_dir.resolve()
    if not root.is_dir():
        raise BackupVerificationError(f"backup directory does not exist: {backup_dir}")

    manifest_path = root / "manifest.txt"
    if not manifest_path.is_file():
        raise BackupVerificationError("manifest.txt is missing")
    manifest = _read_manifest(manifest_path)
    for key in ("created_at", "postgres_dump", "runtime_archive", "qdrant_collection"):
        if not manifest.get(key, "").strip():
            raise BackupVerificationError(f"manifest field is missing: {key}")

    postgres_dump = _artifact(root, manifest["postgres_dump"], label="PostgreSQL dump")
    with postgres_dump.open("rb") as stream:
        signature = stream.read(5)
    if signature != b"PGDMP":
        raise BackupVerificationError("PostgreSQL dump does not use the custom pg_dump format")

    runtime_archive = _artifact(root, manifest["runtime_archive"], label="runtime archive")
    runtime_file_count, runtime_uncompressed_bytes = _verify_runtime_archive(runtime_archive)

    snapshots = sorted(path for path in root.glob("*.snapshot") if path.is_file() and path.stat().st_size > 0)
    if len(snapshots) != 1:
        raise BackupVerificationError(f"expected exactly one non-empty Qdrant snapshot, found {len(snapshots)}")

    return {
        "status": "ok",
        "backup_dir": str(root),
        "created_at": manifest["created_at"],
        "postgres_dump_bytes": postgres_dump.stat().st_size,
        "runtime_archive_bytes": runtime_archive.stat().st_size,
        "runtime_file_count": runtime_file_count,
        "runtime_uncompressed_bytes": runtime_uncompressed_bytes,
        "qdrant_collection": manifest["qdrant_collection"],
        "qdrant_snapshot": snapshots[0].name,
        "qdrant_snapshot_bytes": snapshots[0].stat().st_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a CoRA Mail production backup artifact set.")
    parser.add_argument("backup_dir", type=Path)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()
    try:
        report = verify_production_backup(args.backup_dir)
    except BackupVerificationError as exc:
        if args.format == "json":
            print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        else:
            print(f"production_backup_verification=error reason={exc}")
        return 1
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(
            "production_backup_verification=ok "
            f"runtime_files={report['runtime_file_count']} "
            f"postgres_bytes={report['postgres_dump_bytes']} "
            f"qdrant_bytes={report['qdrant_snapshot_bytes']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

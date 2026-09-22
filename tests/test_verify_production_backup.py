from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from app.tools.verify_production_backup import BackupVerificationError, verify_production_backup


def _write_valid_backup(root: Path) -> None:
    (root / "postgres.dump").write_bytes(b"PGDMP" + b"database")
    (root / "cases.snapshot").write_bytes(b"qdrant")
    with tarfile.open(root / "runtime.tar.gz", mode="w:gz") as archive:
        content = b"attachment"
        info = tarfile.TarInfo("runtime/gmail_attachments/message/file.pdf")
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    (root / "manifest.txt").write_text(
        "\n".join(
            [
                "created_at=20260922T020000Z",
                "postgres_dump=postgres.dump",
                "runtime_archive=runtime.tar.gz",
                "qdrant_collection=cases",
            ]
        ),
        encoding="utf-8",
    )


def test_verify_production_backup_accepts_complete_artifacts(tmp_path: Path) -> None:
    _write_valid_backup(tmp_path)

    report = verify_production_backup(tmp_path)

    assert report["status"] == "ok"
    assert report["runtime_file_count"] == 1
    assert report["qdrant_snapshot"] == "cases.snapshot"


def test_verify_production_backup_rejects_unsafe_runtime_member(tmp_path: Path) -> None:
    _write_valid_backup(tmp_path)
    with tarfile.open(tmp_path / "runtime.tar.gz", mode="w:gz") as archive:
        content = b"secret"
        info = tarfile.TarInfo("../secret")
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))

    with pytest.raises(BackupVerificationError, match="unsafe path"):
        verify_production_backup(tmp_path)


def test_verify_production_backup_rejects_plain_sql_dump(tmp_path: Path) -> None:
    _write_valid_backup(tmp_path)
    (tmp_path / "postgres.dump").write_text("CREATE TABLE mail", encoding="utf-8")

    with pytest.raises(BackupVerificationError, match="custom pg_dump format"):
        verify_production_backup(tmp_path)

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools import restore_qdrant_snapshot


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return self.body


def test_restore_collection_snapshot_uploads_multipart(monkeypatch, tmp_path: Path) -> None:
    snapshot = tmp_path / "cases.snapshot"
    snapshot.write_bytes(b"snapshot bytes")
    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse(b'{"status":"ok","result":true}')

    monkeypatch.setattr(restore_qdrant_snapshot, "urlopen", fake_urlopen)

    payload = restore_qdrant_snapshot.restore_collection_snapshot(
        base_url="http://qdrant:6333/",
        collection="mail cases",
        snapshot_path=snapshot,
        api_key="secret",
        timeout_seconds=15,
    )

    request, timeout = requests[0]
    assert payload["status"] == "ok"
    assert request.full_url == "http://qdrant:6333/collections/mail%20cases/snapshots/upload?priority=snapshot"
    assert request.get_method() == "POST"
    assert request.get_header("Api-key") == "secret"
    assert request.get_header("Content-type").startswith("multipart/form-data; boundary=coramail-")
    assert b"snapshot bytes" in request.data
    assert timeout == 15


def test_collection_info_returns_qdrant_result(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        assert request.full_url == "http://qdrant:6333/collections/cases"
        assert timeout == 12
        return FakeResponse(b'{"status":"ok","result":{"status":"green","points_count":3}}')

    monkeypatch.setattr(restore_qdrant_snapshot, "urlopen", fake_urlopen)

    result = restore_qdrant_snapshot.collection_info(
        base_url="http://qdrant:6333",
        collection="cases",
        timeout_seconds=12,
    )

    assert result == {"status": "green", "points_count": 3}


def test_restore_collection_snapshot_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(restore_qdrant_snapshot.QdrantRestoreError, match="missing or empty"):
        restore_qdrant_snapshot.restore_collection_snapshot(
            base_url="http://qdrant:6333",
            collection="cases",
            snapshot_path=tmp_path / "missing.snapshot",
        )

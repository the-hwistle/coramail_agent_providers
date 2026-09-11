from __future__ import annotations

from pathlib import Path

from app.tools import create_qdrant_snapshot


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return self.body


def test_create_collection_snapshot_posts_to_qdrant(monkeypatch) -> None:
    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request.full_url, request.get_method(), dict(request.header_items()), timeout))
        return FakeResponse(b'{"status":"ok","result":{"name":"snapshot-1.snapshot"}}')

    monkeypatch.setattr(create_qdrant_snapshot, "urlopen", fake_urlopen)

    snapshot_name = create_qdrant_snapshot.create_collection_snapshot(
        base_url="http://qdrant:6333",
        collection="coramail cases",
        api_key="secret",
        timeout_seconds=15,
    )

    assert snapshot_name == "snapshot-1.snapshot"
    assert requests == [
        (
            "http://qdrant:6333/collections/coramail%20cases/snapshots?wait=true",
            "POST",
            {"Content-type": "application/json", "Api-key": "secret"},
            15,
        )
    ]


def test_download_collection_snapshot_writes_file(monkeypatch, tmp_path: Path) -> None:
    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request.full_url, request.get_method(), timeout))
        return FakeResponse(b"snapshot bytes")

    monkeypatch.setattr(create_qdrant_snapshot, "urlopen", fake_urlopen)
    output_path = tmp_path / "snapshot-1.snapshot"

    create_qdrant_snapshot.download_collection_snapshot(
        base_url="http://qdrant:6333/",
        collection="cases",
        snapshot_name="snapshot-1.snapshot",
        output_path=output_path,
        timeout_seconds=20,
    )

    assert output_path.read_bytes() == b"snapshot bytes"
    assert requests == [
        ("http://qdrant:6333/collections/cases/snapshots/snapshot-1.snapshot", "GET", 20),
    ]


def test_main_creates_snapshot_and_downloads_it(monkeypatch, tmp_path: Path, capsys) -> None:
    bodies = [
        b'{"status":"ok","result":{"name":"snapshot-1.snapshot"}}',
        b"snapshot bytes",
    ]

    def fake_urlopen(request, timeout):
        return FakeResponse(bodies.pop(0))

    monkeypatch.setattr(create_qdrant_snapshot, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        "sys.argv",
        [
            "create_qdrant_snapshot",
            "--qdrant-url",
            "http://qdrant:6333",
            "--collection",
            "cases",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert create_qdrant_snapshot.main() == 0

    assert (tmp_path / "snapshot-1.snapshot").read_bytes() == b"snapshot bytes"
    assert f"qdrant_snapshot={tmp_path / 'snapshot-1.snapshot'} collection=cases" in capsys.readouterr().out

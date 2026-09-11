from __future__ import annotations

import sys

import pytest

from app.tools import prepare_qdrant_collection


def test_prepare_qdrant_collection_ensures_collection(monkeypatch, capsys) -> None:
    calls = []

    class FakeQdrantCaseIndexClient:
        def __init__(self, *, base_url: str, collection: str):
            calls.append(("init", base_url, collection))

        def ensure_collection(self, vector_size: int) -> None:
            calls.append(("ensure", vector_size))

    monkeypatch.setattr(prepare_qdrant_collection, "QdrantCaseIndexClient", FakeQdrantCaseIndexClient)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prepare_qdrant_collection",
            "--qdrant-url",
            "http://qdrant.internal:6333",
            "--collection",
            "coramail_cases_production",
            "--vector-size",
            "768",
        ],
    )

    assert prepare_qdrant_collection.main() == 0

    assert calls == [
        ("init", "http://qdrant.internal:6333", "coramail_cases_production"),
        ("ensure", 768),
    ]
    assert "qdrant_collection=coramail_cases_production status=ready vector_size=768" in capsys.readouterr().out


def test_prepare_qdrant_collection_rejects_invalid_vector_size(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["prepare_qdrant_collection", "--vector-size", "0"])

    with pytest.raises(SystemExit) as exc_info:
        prepare_qdrant_collection.main()

    assert exc_info.value.code == 2

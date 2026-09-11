from __future__ import annotations

import pytest

from app.evaluation.attachment_loader import file_group_for_fixture


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("purchase-order.pdf", "pdf"),
        ("price-list.xlsx", "spreadsheet"),
        ("specification.docx", "document"),
        ("drawing.png", "image"),
        ("notes.txt", "text"),
        ("DRAWING.PNG", "image"),
    ],
)
def test_file_group_for_fixture_maps_supported_extensions(filename: str, expected: str) -> None:
    assert file_group_for_fixture(filename) == expected


@pytest.mark.parametrize("filename", ["archive.zip", "no-extension"])
def test_file_group_for_fixture_rejects_unsupported_extensions(filename: str) -> None:
    with pytest.raises(ValueError, match="unsupported attachment fixture extension"):
        file_group_for_fixture(filename)

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def default_to_non_demo_display_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep ordinary tests on the production-style UI/runtime path.

    Tests that verify the hosted demo path must opt in explicitly with
    ``monkeypatch.setenv("CORAMAIL_DEMO_MODE", "true")``.  This prevents the
    application's hosting fallback default from silently changing view-model,
    routing, or runtime-client expectations in unrelated tests.
    """

    monkeypatch.setenv("CORAMAIL_DEMO_MODE", "false")

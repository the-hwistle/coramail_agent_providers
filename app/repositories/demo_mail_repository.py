from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.schemas.demo_mail import DemoAttachment, DemoFixture, DemoMessage


class DemoMailRepository:
    """Loads demo mail fixtures directly from data/demo.

    This repository is intentionally read-only. PostgreSQL and Qdrant are seed outputs,
    while fixture JSON files are the canonical demo source during D1/D2.
    """

    def __init__(self, demo_dir: Path):
        self.demo_dir = demo_dir

    @lru_cache(maxsize=1)
    def fixtures(self) -> tuple[DemoFixture, ...]:
        fixture_paths = sorted(self.demo_dir.glob("*.fixture.json"))
        fixtures: list[DemoFixture] = []
        for fixture_path in fixture_paths:
            payload = json.loads(fixture_path.read_text(encoding="utf-8"))
            fixtures.append(DemoFixture.model_validate(payload))
        return tuple(fixtures)

    def messages(self) -> list[DemoMessage]:
        items: list[DemoMessage] = []
        for fixture in self.fixtures():
            items.extend(fixture.messages)
        return sorted(items, key=lambda item: item.sent_at, reverse=True)

    def message_by_index(self, index: int) -> DemoMessage | None:
        messages = self.messages()
        if index < 0 or index >= len(messages):
            return None
        return messages[index]

    def message_by_uid(self, email_uid: str) -> tuple[int, DemoMessage] | None:
        for index, message in enumerate(self.messages()):
            if message.id == email_uid:
                return index, message
        return None

    def attachment_path(self, attachment: DemoAttachment) -> Path:
        return (self.demo_dir.parent.parent / attachment.storage_uri).resolve()

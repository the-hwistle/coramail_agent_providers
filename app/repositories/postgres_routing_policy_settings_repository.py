from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.routing.policy import RoutingPolicyConfig


SETTINGS_ID = UUID("00000000-0000-0000-0000-000000000001")
ROUTING_POLICY_KEY = "routing_policy"


@dataclass(frozen=True)
class RoutingPolicySettings:
    auto_assign_threshold: float
    minimum_margin: float
    minimum_classification_confidence: float

    def as_config(self) -> RoutingPolicyConfig:
        return RoutingPolicyConfig(
            auto_assign_threshold=self.auto_assign_threshold,
            minimum_margin=self.minimum_margin,
            minimum_classification_confidence=self.minimum_classification_confidence,
        )

    def model(self) -> dict[str, float]:
        return {
            "auto_assign_threshold": self.auto_assign_threshold,
            "minimum_margin": self.minimum_margin,
            "minimum_classification_confidence": self.minimum_classification_confidence,
        }


class PostgresRoutingPolicySettingsRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url.strip()

    @property
    def enabled(self) -> bool:
        return bool(self.database_url)

    def get(self) -> RoutingPolicySettings:
        defaults = self.defaults()
        if not self.enabled:
            return defaults

        import psycopg

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COALESCE(system_settings->%(key)s, '{}'::jsonb) AS settings
                    FROM organization_settings
                    ORDER BY created_at, id
                    LIMIT 1
                    """,
                    {"key": ROUTING_POLICY_KEY},
                )
                row = cursor.fetchone()
        values = row["settings"] if row else {}
        return RoutingPolicySettings(
            auto_assign_threshold=self._setting_float(
                values,
                "auto_assign_threshold",
                defaults.auto_assign_threshold,
            ),
            minimum_margin=self._setting_float(values, "minimum_margin", defaults.minimum_margin),
            minimum_classification_confidence=self._setting_float(
                values,
                "minimum_classification_confidence",
                defaults.minimum_classification_confidence,
            ),
        )

    def save(
        self,
        *,
        auto_assign_threshold: float,
        minimum_margin: float,
        minimum_classification_confidence: float,
    ) -> RoutingPolicySettings:
        settings = RoutingPolicySettings(
            auto_assign_threshold=self._validate_ratio(
                auto_assign_threshold,
                "auto_assign_threshold",
            ),
            minimum_margin=self._validate_ratio(minimum_margin, "minimum_margin"),
            minimum_classification_confidence=self._validate_ratio(
                minimum_classification_confidence,
                "minimum_classification_confidence",
            ),
        )
        if not self.enabled:
            return settings

        import psycopg

        now = datetime.now(timezone.utc)
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO organization_settings (
                            id, organization_name, timezone, default_language,
                            notification_settings, system_settings, created_at, updated_at
                        )
                        VALUES (
                            %(id)s, 'CoRA Mail', 'Asia/Seoul', 'ko',
                            '{}'::jsonb, '{}'::jsonb, %(now)s, %(now)s
                        )
                        ON CONFLICT (id) DO NOTHING
                        """,
                        {"id": SETTINGS_ID, "now": now},
                    )
                    cursor.execute(
                        """
                        UPDATE organization_settings
                        SET system_settings = jsonb_set(
                                COALESCE(system_settings, '{}'::jsonb),
                                %(path)s,
                                %(settings)s,
                                true
                            ),
                            updated_at = %(now)s
                        WHERE id = (
                            SELECT id
                            FROM organization_settings
                            ORDER BY created_at, id
                            LIMIT 1
                        )
                        """,
                        {
                            "path": [ROUTING_POLICY_KEY],
                            "settings": Jsonb(settings.model()),
                            "now": now,
                        },
                    )
        return settings

    @staticmethod
    def defaults() -> RoutingPolicySettings:
        return RoutingPolicySettings(
            auto_assign_threshold=PostgresRoutingPolicySettingsRepository._env_float(
                "CORAMAIL_AUTO_ASSIGN_THRESHOLD",
                0.82,
            ),
            minimum_margin=PostgresRoutingPolicySettingsRepository._env_float(
                "CORAMAIL_ROUTING_MIN_MARGIN",
                0.15,
            ),
            minimum_classification_confidence=PostgresRoutingPolicySettingsRepository._env_float(
                "CORAMAIL_CLASSIFICATION_MIN_CONFIDENCE",
                0.78,
            ),
        )

    @staticmethod
    def _env_float(name: str, default: float) -> float:
        try:
            return PostgresRoutingPolicySettingsRepository._validate_ratio(float(os.getenv(name, default)), name)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _setting_float(values: Any, key: str, default: float) -> float:
        if not isinstance(values, dict) or key not in values:
            return default
        try:
            return PostgresRoutingPolicySettingsRepository._validate_ratio(float(values[key]), key)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _validate_ratio(value: float, field_name: str) -> float:
        if not 0 <= value <= 1:
            raise ValueError(f"{field_name} must be between 0 and 1")
        return round(float(value), 4)

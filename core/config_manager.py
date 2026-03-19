import json
from typing import Any, Dict, Optional

from database.models import SessionLocal, SystemSettings


class ConfigManager:
    """Single source of truth for dynamic system configuration."""

    DEFAULT_SETTINGS: Dict[str, Dict[str, Any]] = {
        "is_trading_active": {
            "value": False,
            "description": "Global switch to enable or disable live/paper trade execution.",
            "type": bool,
        },
        "max_risk_per_trade": {
            "value": 0.02,
            "description": "Maximum account risk allocated to any single trade.",
            "type": float,
        },
        "allowed_crypto": {
            "value": ["BTC/USD", "ETH/USD"],
            "description": "List of crypto symbols approved for strategy execution.",
            "type": list,
        },
    }

    KEY_TYPE_MAP: Dict[str, type] = {
        key: entry["type"] for key, entry in DEFAULT_SETTINGS.items()
    }

    @staticmethod
    def _serialize_value(value: Any) -> str:
        if isinstance(value, (list, dict)):
            return json.dumps(value)
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    @staticmethod
    def _parse_bool(raw_value: str) -> bool:
        return raw_value.strip().lower() in {"true", "1", "yes", "y", "on"}

    def _deserialize_value(self, key: str, raw_value: str) -> Any:
        expected_type = self.KEY_TYPE_MAP.get(key)

        if expected_type is bool:
            return self._parse_bool(raw_value)
        if expected_type is int:
            return int(raw_value)
        if expected_type is float:
            return float(raw_value)
        if expected_type is list:
            parsed = json.loads(raw_value)
            if not isinstance(parsed, list):
                raise ValueError(f"Expected list for key '{key}', got {type(parsed).__name__}.")
            return parsed

        try:
            return json.loads(raw_value)
        except (json.JSONDecodeError, TypeError):
            return raw_value

    def get_setting(self, key: str, default: Optional[Any] = None) -> Any:
        with SessionLocal() as session:
            setting = session.query(SystemSettings).filter(SystemSettings.key == key).first()
            if setting is None:
                return default
            return self._deserialize_value(key, setting.value)

    def set_setting(self, key: str, value: Any, description: Optional[str] = None) -> Any:
        serialized_value = self._serialize_value(value)

        with SessionLocal() as session:
            setting = session.query(SystemSettings).filter(SystemSettings.key == key).first()

            if setting is None:
                setting = SystemSettings(
                    key=key,
                    value=serialized_value,
                    description=description,
                )
                session.add(setting)
            else:
                setting.value = serialized_value
                if description is not None:
                    setting.description = description

            session.commit()
            session.refresh(setting)
            return self._deserialize_value(setting.key, setting.value)

    def initialize_default_settings(self) -> None:
        with SessionLocal() as session:
            has_any_settings = session.query(SystemSettings.id).first() is not None
            if has_any_settings:
                return

            for key, entry in self.DEFAULT_SETTINGS.items():
                session.add(
                    SystemSettings(
                        key=key,
                        value=self._serialize_value(entry["value"]),
                        description=entry["description"],
                    )
                )

            session.commit()

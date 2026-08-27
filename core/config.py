"""Конфигурация диагностики (~/.config/ireplicator-gamepad-tester/config.json)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


CONFIG_DIR = Path.home() / ".config" / "ireplicator-gamepad-tester"
CONFIG_PATH = CONFIG_DIR / "config.json"


@dataclass
class DiagnosticConfig:
    stick_drift_warn: float = 0.03
    stick_drift_fail: float = 0.07
    stick_noise: float = 0.02
    stick_drift_hold_ms: int = 500
    stick_drift_sample_ratio: float = 0.25
    trigger_min: float = 0.03
    trigger_max: float = 0.97
    trigger_spike: float = 0.03
    trigger_rest_jitter: float = 0.02
    button_bounce_ms: int = 30
    rest_test_seconds: float = 5.0
    stress_test_seconds: float = 300.0
    graph_max_points: int = 10000
    locale: str = "ru"
    left_stick_deadzone: float = 0.05
    right_stick_deadzone: float = 0.05
    center_compensation: bool = True
    smoothing: float = 0.0
    button_hold_seconds: int = 3
    test_stickiness: bool = True
    test_hold: bool = True
    test_sensitivity: bool = True

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls) -> DiagnosticConfig:
        if not CONFIG_PATH.exists():
            cfg = cls()
            cfg.save()
            return cfg
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except (OSError, json.JSONDecodeError, TypeError):
            cfg = cls()
            cfg.save()
            return cfg

    def hold_seconds(self) -> int:
        try:
            value = int(self.button_hold_seconds)
        except (TypeError, ValueError):
            value = 3
        return max(1, min(15, value))


def save_config(config: DiagnosticConfig) -> None:
    config.save()

"""JSON serialization for API responses."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from backend.protocol import PadState
from core.config import DiagnosticConfig
from core.report import DiagnosticReport
from core.status import TestStatus
from pad_common import AxisProfile, diagram_kind, normalize_trigger


def _to_json(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.value
    if is_dataclass(obj):
        return {k: _to_json(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): _to_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_json(v) for v in obj]
    return obj


def config_dict(config: DiagnosticConfig) -> dict[str, Any]:
    return _to_json(config)


def report_dict(report: DiagnosticReport) -> dict[str, Any]:
    return _to_json(report)


def pad_state_dict(state: PadState, profile: AxisProfile) -> dict[str, Any]:
    axes_raw = {int(k): float(v) for k, v in state.axes.items()}
    parsed = profile.read(axes_raw)
    return {
        "connected": state.connected,
        "name": state.name,
        "axis_profile": state.axis_profile,
        "hint": state.hint,
        "transport": state.transport,
        "diagram_kind": diagram_kind(profile.name, state.name),
        "buttons": {str(k): bool(v) for k, v in state.buttons.items()},
        "axes": {
            "left_x": parsed["left_x"],
            "left_y": parsed["left_y"],
            "right_x": parsed["right_x"],
            "right_y": parsed["right_y"],
            "lt": normalize_trigger(parsed["lt"]),
            "rt": normalize_trigger(parsed["rt"]),
        },
    }

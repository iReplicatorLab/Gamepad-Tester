"""Структуры сэмплов и сырых событий ввода."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GamepadSample:
    timestamp_ns: int
    axes: dict[str, float] = field(default_factory=dict)
    buttons: dict[int, bool] = field(default_factory=dict)
    hat: tuple[int, int] = (0, 0)


@dataclass
class RawInputEvent:
    timestamp_ns: int
    event_type: str
    code: str
    value: int | float
    test_id: str = ""


@dataclass
class DeviceInfo:
    name: str = ""
    path: str = ""
    vendor_id: int | None = None
    product_id: int | None = None
    axis_profile: str = ""
    connected: bool = False

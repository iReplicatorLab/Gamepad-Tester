"""Общие константы и профили осей для Linux/Windows сборок."""

from __future__ import annotations

from dataclasses import dataclass

BUTTONS = [
    (0, "A"),
    (1, "B"),
    (2, "X"),
    (3, "Y"),
    (4, "LB"),
    (5, "RB"),
    (6, "View"),
    (7, "Menu"),
    (8, "Xbox"),
    (9, "L3"),
    (10, "R3"),
    (15, "Share"),
]

DPAD_BUTTONS = [
    (11, "↑"),
    (12, "↓"),
    (13, "←"),
    (14, "→"),
]

ALL_BUTTON_INDICES = [idx for idx, _ in BUTTONS + DPAD_BUTTONS]

APP_NAME = "iReplicator Gamepad Tester"
APP_ID = "com.ireplicator.gamepad-tester"
VERSION = "0.2.1"
REPORT_SCHEMA = "diagnostic_report_v1"


@dataclass(frozen=True)
class AxisProfile:
    name: str
    label: str
    left_x: int
    left_y: int
    right_x: int
    right_y: int
    lt: int
    rt: int

    def read(self, axes: dict[int, float]) -> dict[str, float]:
        return {
            "left_x": axes.get(self.left_x, 0.0),
            "left_y": axes.get(self.left_y, 0.0),
            "right_x": axes.get(self.right_x, 0.0),
            "right_y": axes.get(self.right_y, 0.0),
            "lt": axes.get(self.lt, -1.0),
            "rt": axes.get(self.rt, -1.0),
        }


XBOX360_PROFILE = AxisProfile(
    name="xbox360",
    label="Xbox 360",
    left_x=0,
    left_y=1,
    lt=2,
    right_x=3,
    right_y=4,
    rt=5,
)

XINPUT_PROFILE = AxisProfile(
    name="xinput",
    label="Xbox One / Series",
    left_x=0,
    left_y=1,
    right_x=2,
    right_y=3,
    lt=4,
    rt=5,
)


def diagram_kind(profile_name: str, device_name: str) -> str:
    """Какую схему показать: Xbox 360 или Series."""
    text = f"{profile_name} {device_name}".lower()
    if profile_name == "xbox360" or "360" in text:
        return "360"
    return "series"


def detect_axis_profile_from_name(name: str, num_axes: int | None = None) -> AxisProfile:
    lowered = name.lower()
    if any(token in lowered for token in ("360", "x-box 360", "xbox wireless receiver", "wireless receiver (xbox)")):
        return XBOX360_PROFILE
    if num_axes == 6 and any(token in lowered for token in ("xbox", "x-box", "microsoft")):
        if "series" not in lowered and "one" not in lowered:
            return XBOX360_PROFILE
    return XINPUT_PROFILE


def normalize_trigger(value: float) -> float:
    if value < 0.0:
        return (value + 1.0) / 2.0
    return max(0.0, min(1.0, value))


def input_step_detected(
    baseline_axes: dict[str, float],
    current_axes: dict[str, float],
    baseline_buttons: dict[int, bool],
    current_buttons: dict[int, bool],
    expect: str = "any",
) -> bool:
    """True, когда пользователь начал запрошенное действие."""
    def moved(name: str, threshold: float) -> bool:
        return abs(current_axes.get(name, 0.0) - baseline_axes.get(name, 0.0)) > threshold

    if expect.startswith("button:"):
        try:
            idx = int(expect.split(":", 1)[1])
        except ValueError:
            return False
        return bool(current_buttons.get(idx, False))
    if expect in ("any", "left", "stick") and (moved("left_x", 0.25) or moved("left_y", 0.25)):
        return True
    if expect in ("any", "right", "stick") and (moved("right_x", 0.25) or moved("right_y", 0.25)):
        return True
    if expect in ("any", "lt"):
        if abs(normalize_trigger(current_axes.get("lt", -1.0)) - normalize_trigger(baseline_axes.get("lt", -1.0))) > 0.12:
            return True
    if expect in ("any", "rt"):
        if abs(normalize_trigger(current_axes.get("rt", -1.0)) - normalize_trigger(baseline_axes.get("rt", -1.0))) > 0.12:
            return True
    if expect in ("any", "buttons"):
        for idx, pressed in current_buttons.items():
            if pressed and not baseline_buttons.get(idx, False):
                return True
    return False

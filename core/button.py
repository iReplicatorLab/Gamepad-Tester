"""Диагностика цифровых кнопок: нажатие и удержание."""

from __future__ import annotations

import time

from core.i18n import t
from core.report import ButtonCheck, ButtonsTestResult
from core.status import TestStatus
from pad_common import BUTTONS, DPAD_BUTTONS, diagram_kind

HOLD_SECONDS = 3.0
HOLD_RATIO = 0.8
PRESS_TIMEOUT = 12.0
STICKY_LIMIT = 1.0


def buttons_for_device(profile_name: str, device_name: str) -> list[tuple[int, str]]:
    items = list(BUTTONS) + list(DPAD_BUTTONS)
    if diagram_kind(profile_name, device_name) == "360":
        items = [(idx, name) for idx, name in items if idx != 15]
    return items


def check_button(
    index: int,
    name: str,
    pressed: bool,
    held: bool,
    *,
    skipped: bool = False,
    sticky: bool = False,
    sensitive: bool = True,
    tap_count: int = 0,
    seconds: int | None = None,
) -> ButtonCheck:
    hold = int(seconds if seconds is not None else HOLD_SECONDS)
    issues: list[str] = []
    if skipped:
        issues.append(t("button.skipped", name=name))
    elif not pressed:
        issues.append(t("button.missed", name=name))
    if pressed and not skipped and not sensitive:
        issues.append(t("button.insensitive", name=name))
    if pressed and not skipped and sticky:
        issues.append(t("button.sticky", name=name))
    if pressed and not skipped and not held:
        issues.append(t("button.not_held", name=name, seconds=hold))
    return ButtonCheck(
        index=index,
        name=name,
        pressed=pressed,
        held=held,
        skipped=skipped,
        sticky=sticky,
        sensitive=sensitive,
        tap_count=tap_count,
        issues=issues,
    )


def summarize(checks: list[ButtonCheck]) -> ButtonsTestResult:
    issues = [issue for check in checks for issue in check.issues]
    missed = sum(1 for check in checks if not check.pressed or check.skipped)
    not_held = sum(1 for check in checks if check.pressed and not check.held and not check.skipped)
    sticky_n = sum(1 for check in checks if check.sticky)
    dull_n = sum(1 for check in checks if not check.sensitive)
    if missed >= 2 or sticky_n >= 2 or dull_n >= 2:
        status = TestStatus.FAIL
    elif missed or not_held or sticky_n or dull_n:
        status = TestStatus.WARN
    elif checks:
        status = TestStatus.PASS
    else:
        status = TestStatus.NOT_TESTED
    return ButtonsTestResult(
        status=status,
        buttons=checks,
        pressed_count=sum(1 for check in checks if check.pressed),
        held_count=sum(1 for check in checks if check.held),
        issues=issues,
    )


def wait_hold(source, index: int, seconds: float, stop_check) -> bool:
    end = time.monotonic() + seconds
    pressed_for = 0.0
    last = time.monotonic()
    while time.monotonic() < end:
        if stop_check():
            return False
        state = source.get_state()
        now = time.monotonic()
        if state.buttons.get(index, False):
            pressed_for += now - last
        last = now
        time.sleep(0.02)
    return pressed_for >= seconds * HOLD_RATIO

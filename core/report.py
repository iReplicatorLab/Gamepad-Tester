"""Результаты диагностики."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from core.status import TestStatus, overall_from_tests
from core.stats import looks_like_square_gate
from pad_common import APP_NAME, REPORT_SCHEMA, VERSION


@dataclass
class StickTestResult:
    status: TestStatus = TestStatus.NOT_TESTED
    drift_pct: float = 0.0
    mean_x: float = 0.0
    mean_y: float = 0.0
    max_radius: float = 0.0
    deadzone_pct: float = 0.0
    physical_drift_pct: float = 0.0
    circularity_pct: float = 0.0
    range_ok: bool = True
    issues: list[str] = field(default_factory=list)
    rest_points: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class TriggerTestResult:
    status: TestStatus = TestStatus.NOT_TESTED
    min_value: float = 0.0
    max_value: float = 0.0
    spike_count: int = 0
    returns_to_zero: bool = True
    issues: list[str] = field(default_factory=list)
    timeline: list[tuple[int, float]] = field(default_factory=list)


@dataclass
class ButtonCheck:
    index: int
    name: str
    pressed: bool = False
    held: bool = False
    skipped: bool = False
    sticky: bool = False
    sensitive: bool = True
    tap_count: int = 0
    issues: list[str] = field(default_factory=list)


@dataclass
class ButtonsTestResult:
    status: TestStatus = TestStatus.NOT_TESTED
    buttons: list[ButtonCheck] = field(default_factory=list)
    pressed_count: int = 0
    held_count: int = 0
    issues: list[str] = field(default_factory=list)


@dataclass
class EventRateResult:
    mean_interval_ms: float = 0.0
    median_interval_ms: float = 0.0
    max_interval_ms: float = 0.0
    estimated_hz: float = 0.0
    note: str = ""


def compute_score(report: "DiagnosticReport") -> int:
    score = 10.0
    for stick in (report.left_stick, report.right_stick):
        if stick.status == TestStatus.FAIL:
            score -= 3.0
        elif stick.status == TestStatus.WARN:
            score -= 1.5
    for trig in (report.lt, report.rt):
        if trig.status == TestStatus.FAIL:
            score -= 2.0
        elif trig.status == TestStatus.WARN:
            score -= 0.75
    buttons = report.buttons
    if buttons.status not in (TestStatus.NOT_TESTED, TestStatus.NOT_SUPPORTED):
        missed = sum(1 for item in buttons.buttons if not item.pressed or item.skipped)
        not_held = sum(1 for item in buttons.buttons if item.pressed and not item.held and not item.skipped)
        sticky = sum(1 for item in buttons.buttons if item.sticky)
        dull = sum(1 for item in buttons.buttons if not item.sensitive)
        score -= min(6.0, missed * 1.5)
        score -= min(2.0, not_held * 0.5)
        score -= min(3.0, sticky * 1.0)
        score -= min(3.0, dull * 1.0)
    return max(1, min(10, int(round(score))))


def score_tone(score: int) -> str:
    if score >= 8:
        return "good"
    if score >= 5:
        return "ok"
    return "bad"


@dataclass
class DiagnosticReport:
    schema_version: str = REPORT_SCHEMA
    app_name: str = APP_NAME
    app_version: str = VERSION
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    locale: str = "ru"
    device_name: str = ""
    device_path: str = ""
    vendor_id: int | None = None
    product_id: int | None = None
    axis_profile: str = ""
    duration_seconds: float = 0.0
    overall: TestStatus = TestStatus.NOT_TESTED
    tests: dict[str, TestStatus] = field(default_factory=dict)
    left_stick: StickTestResult = field(default_factory=StickTestResult)
    right_stick: StickTestResult = field(default_factory=StickTestResult)
    lt: TriggerTestResult = field(default_factory=TriggerTestResult)
    rt: TriggerTestResult = field(default_factory=TriggerTestResult)
    buttons: ButtonsTestResult = field(default_factory=ButtonsTestResult)
    event_rate: EventRateResult = field(default_factory=EventRateResult)
    issues: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    score: int = 0
    disclaimer: str = ""
    thresholds: dict[str, float] = field(default_factory=dict)

    def finalize(self) -> None:
        self.overall = overall_from_tests(self.tests)
        self.issues = []
        self.notes = []
        for res in (self.left_stick, self.right_stick):
            self.issues.extend(res.issues)
            if res.status not in (TestStatus.NOT_TESTED, TestStatus.NOT_SUPPORTED) and looks_like_square_gate(
                res.circularity_pct
            ):
                self.notes.append("circularity.square_ok")
        self.issues.extend(self.lt.issues)
        self.issues.extend(self.rt.issues)
        self.issues.extend(self.buttons.issues)
        seen: set[str] = set()
        unique_notes: list[str] = []
        for note in self.notes:
            if note not in seen:
                seen.add(note)
                unique_notes.append(note)
        self.notes = unique_notes
        tested = any(
            status not in (TestStatus.NOT_TESTED, TestStatus.NOT_SUPPORTED)
            for status in self.tests.values()
        ) or self.overall != TestStatus.NOT_TESTED
        self.score = compute_score(self) if tested else 0

    def status_label_key(self) -> str:
        mapping = {
            TestStatus.PASS: "status.pass",
            TestStatus.WARN: "status.warn",
            TestStatus.FAIL: "status.fail",
            TestStatus.NOT_TESTED: "status.not_tested",
        }
        return mapping.get(self.overall, "status.not_tested")

    def score_css_class(self) -> str:
        return {
            "good": "score-good",
            "ok": "score-ok",
            "bad": "score-bad",
        }.get(score_tone(self.score), "score-ok")


def button_check_status(item: ButtonCheck) -> TestStatus:
    if item.skipped or not item.pressed:
        return TestStatus.FAIL
    if item.sticky or not item.sensitive or not item.held:
        return TestStatus.WARN
    return TestStatus.PASS


def _bare_issue(issue: str, name: str) -> str:
    if issue.startswith(f"{name}: "):
        return issue[len(name) + 2 :]
    if issue.startswith(f"{name} "):
        return issue[len(name) + 1 :]
    return issue


def _control_lines(name: str, status: TestStatus, issues: list[str], extra: str = "") -> list[str]:
    title = f"{name} — {status.value}"
    if extra:
        title = f"{title} ({extra})"
    lines = [title]
    lines.extend(f"• {_bare_issue(issue, name)}" for issue in issues)
    return lines


def _stick_extra(stick: StickTestResult) -> str:
    from core.i18n import t

    parts = [t("report.drift", pct=f"{stick.drift_pct:.1f}")]
    if stick.circularity_pct > 0:
        parts.append(t("report.gate_shape", pct=f"{stick.circularity_pct:.1f}"))
    return " · ".join(parts)


def _extend_section(lines: list[str], heading: str, blocks: list[list[str]]) -> None:
    if not blocks:
        return
    if lines and lines[-1] != "":
        lines.append("")
    lines.append(heading)
    for index, block in enumerate(blocks):
        if index and (len(blocks[index - 1]) > 1 or len(block) > 1):
            lines.append("")
        lines.extend(block)


def result_lines(report: DiagnosticReport) -> list[str]:
    from core.i18n import t

    lines = [
        t("diag.score", score=report.score),
        f"{t('diag.status')}: {t(report.status_label_key())}",
    ]

    stick_blocks: list[list[str]] = []
    for stick, label in (
        (report.left_stick, t("stick.left")),
        (report.right_stick, t("stick.right")),
    ):
        if stick.status == TestStatus.NOT_TESTED:
            continue
        stick_blocks.append(_control_lines(label, stick.status, stick.issues, _stick_extra(stick)))
    _extend_section(lines, t("diag.sticks"), stick_blocks)

    trigger_blocks: list[list[str]] = []
    for trig, label in ((report.lt, "LT"), (report.rt, "RT")):
        if trig.status == TestStatus.NOT_TESTED:
            continue
        extra = f"{trig.max_value * 100:.0f}%"
        trigger_blocks.append(_control_lines(label, trig.status, trig.issues, extra))
    _extend_section(lines, t("diag.triggers"), trigger_blocks)

    button_blocks: list[list[str]] = []
    if report.buttons.status != TestStatus.NOT_TESTED:
        for item in report.buttons.buttons:
            button_blocks.append(
                _control_lines(item.name, button_check_status(item), item.issues)
            )
    _extend_section(lines, t("diag.buttons"), button_blocks)

    for note in report.notes:
        lines.append("")
        lines.append(t(note))
    return lines


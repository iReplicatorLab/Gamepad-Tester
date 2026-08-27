"""Диагностика аналоговых стиков."""

from __future__ import annotations

import time

from core.config import DiagnosticConfig
from core.i18n import t
from core.report import StickTestResult
from core.sample import GamepadSample
from core.stats import (
    analyze_circularity,
    analyze_drift,
    classify_circularity,
    classify_drift,
    detect_spikes,
    drift_detected,
    radial_distance,
)
from core.status import TestStatus


class StickDiagnostic:
    def __init__(self, config: DiagnosticConfig) -> None:
        self._config = config

    def analyze_rest(
        self,
        samples: list[GamepadSample],
        axis_x: str,
        axis_y: str,
        deadzone: float,
    ) -> StickTestResult:
        points = [(s.axes.get(axis_x, 0.0), s.axes.get(axis_y, 0.0)) for s in samples]
        if len(points) < 10:
            return StickTestResult(
                status=TestStatus.NOT_TESTED,
                issues=["Недостаточно данных для теста покоя"],
            )

        metrics = analyze_drift(
            points,
            threshold=self._config.stick_drift_warn,
            sample_interval_ms=8.0,
            hold_ms=self._config.stick_drift_hold_ms,
            sample_ratio=self._config.stick_drift_sample_ratio,
        )
        detected = drift_detected(
            metrics,
            self._config.stick_drift_warn,
            self._config.stick_drift_hold_ms,
            self._config.stick_drift_sample_ratio,
        )
        level = classify_drift(
            metrics.max_radius,
            self._config.stick_drift_warn,
            self._config.stick_drift_fail,
        )
        status = TestStatus[level] if detected else TestStatus.PASS

        result = StickTestResult(
            status=status,
            drift_pct=metrics.max_radius * 100,
            mean_x=metrics.mean_x,
            mean_y=metrics.mean_y,
            max_radius=metrics.max_radius,
            physical_drift_pct=metrics.max_radius * 100,
            deadzone_pct=deadzone * 100,
            rest_points=points[-2000:],
        )
        if detected:
            result.issues.append(
                f"Дрифт: {metrics.max_radius * 100:.1f}% (среднее {metrics.mean_radius * 100:.1f}%)"
            )
        if metrics.stddev_radius > self._config.stick_noise:
            if status == TestStatus.PASS:
                result.status = TestStatus.WARN
            result.issues.append(f"Шум стика: σ={metrics.stddev_radius * 100:.1f}%")
        return result

    def analyze_range_step(
        self,
        samples: list[GamepadSample],
        axis_x: str,
        axis_y: str,
        direction: str,
    ) -> tuple[bool, list[str]]:
        if not samples:
            return False, ["Нет данных диапазона"]
        issues: list[str] = []
        xs = [s.axes.get(axis_x, 0.0) for s in samples]
        ys = [s.axes.get(axis_y, 0.0) for s in samples]
        spikes_x = detect_spikes(xs)
        spikes_y = detect_spikes(ys)
        if spikes_x + spikes_y > 2:
            issues.append(f"Скачки при движении ({direction})")

        ok = True
        if direction == "up" and min(ys) > -0.85:
            ok = False
            issues.append(f"Не достигнут верхний диапазон ({min(ys)*100:.0f}%)")
        elif direction == "down" and max(ys) < 0.85:
            ok = False
            issues.append(f"Не достигнут нижний диапазон ({max(ys)*100:.0f}%)")
        elif direction == "left" and min(xs) > -0.85:
            ok = False
            issues.append(f"Не достигнут левый диапазон ({min(xs)*100:.0f}%)")
        elif direction == "right" and max(xs) < 0.85:
            ok = False
            issues.append(f"Не достигнут правый диапазон ({max(xs)*100:.0f}%)")
        return ok, issues

    def analyze_circularity(
        self,
        samples: list[GamepadSample],
        axis_x: str,
        axis_y: str,
    ) -> tuple[float, TestStatus, list[str]]:
        points: list[tuple[float, float, float]] = []
        for s in samples:
            x = s.axes.get(axis_x, 0.0)
            y = s.axes.get(axis_y, 0.0)
            points.append((x, y, radial_distance(x, y)))

        if len(points) < 20:
            return 0.0, TestStatus.NOT_TESTED, [t("circularity.too_few")]

        metrics = analyze_circularity(points)
        if metrics.max_radius <= 0:
            return 0.0, TestStatus.WARN, [t("circularity.too_few_rim")]

        level = classify_circularity(metrics.circularity_error_pct)
        issues: list[str] = []
        if level != "PASS":
            issues.append(t("circularity.error", pct=f"{metrics.circularity_error_pct:.1f}"))
        return metrics.circularity_error_pct, TestStatus[level], issues

    @staticmethod
    def wait_seconds(seconds: float, stop_check) -> bool:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if stop_check():
                return False
            time.sleep(0.05)
        return True

    @staticmethod
    def collect_samples(
        sample_source,
        duration: float,
        stop_check,
        test_id: str = "",
    ) -> list[GamepadSample]:
        sample_source.start_logging(test_id)
        end = time.monotonic() + duration
        while time.monotonic() < end:
            if stop_check():
                break
            time.sleep(0.01)
        samples = sample_source.get_logged_samples()
        sample_source.stop_logging()
        return samples

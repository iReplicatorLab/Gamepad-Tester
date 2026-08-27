"""Диагностика триггеров LT/RT."""

from __future__ import annotations

import time

from core.config import DiagnosticConfig
from core.report import TriggerTestResult
from core.sample import GamepadSample
from core.stats import analyze_trigger, classify_trigger
from core.status import TestStatus


class TriggerDiagnostic:
    def __init__(self, config: DiagnosticConfig) -> None:
        self._config = config

    def analyze(self, samples: list[GamepadSample], axis_name: str) -> TriggerTestResult:
        values = [max(0.0, min(1.0, s.axes.get(axis_name, 0.0))) for s in samples]
        if len(values) < 10:
            return TriggerTestResult(
                status=TestStatus.NOT_TESTED,
                issues=["Недостаточно данных для теста триггера"],
            )

        metrics = analyze_trigger(
            values,
            min_ok=self._config.trigger_min,
            max_ok=self._config.trigger_max,
            rest_jitter=self._config.trigger_rest_jitter,
        )
        level = classify_trigger(
            metrics,
            self._config.trigger_min,
            self._config.trigger_max,
            self._config.trigger_rest_jitter,
        )
        result = TriggerTestResult(
            status=TestStatus[level],
            min_value=metrics.min_value,
            max_value=metrics.max_value,
            spike_count=metrics.spike_count,
            returns_to_zero=metrics.returns_to_zero,
            timeline=[(s.timestamp_ns, v) for s, v in zip(samples, values)],
        )
        if metrics.max_value < self._config.trigger_max:
            result.issues.append(f"Не достигает 100% (max {metrics.max_value * 100:.0f}%)")
        if not metrics.returns_to_zero:
            result.issues.append("Не возвращается к нулю")
        if metrics.spike_count > 3:
            result.issues.append(f"Скачки значения: {metrics.spike_count}")
        if metrics.rest_jitter > self._config.trigger_rest_jitter:
            result.issues.append(f"Нестабильность в покое: {metrics.rest_jitter * 100:.1f}%")
        return result

    @staticmethod
    def collect_trigger_samples(sample_source, duration: float, stop_check, test_id: str) -> list[GamepadSample]:
        sample_source.start_logging(test_id)
        end = time.monotonic() + duration
        while time.monotonic() < end:
            if stop_check():
                break
            time.sleep(0.01)
        samples = sample_source.get_logged_samples()
        sample_source.stop_logging()
        return samples

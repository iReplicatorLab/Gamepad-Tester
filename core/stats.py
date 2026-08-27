"""Статистические функции для диагностики."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass


@dataclass
class DriftMetrics:
    mean_x: float
    mean_y: float
    max_radius: float
    mean_radius: float
    stddev_radius: float
    above_threshold_ratio: float
    sustained_ms: float


@dataclass
class CircularityMetrics:
    min_radius: float
    max_radius: float
    mean_radius: float
    circularity_error_pct: float
    quadrant_asymmetry: dict[str, float]


@dataclass
class TriggerMetrics:
    min_value: float
    max_value: float
    rest_jitter: float
    spike_count: int
    returns_to_zero: bool
    dead_band: float


@dataclass
class EventRateMetrics:
    sample_count: int
    event_count: int
    mean_interval_ms: float
    median_interval_ms: float
    max_interval_ms: float
    estimated_hz: float
    stddev_interval_ms: float


def radial_distance(x: float, y: float) -> float:
    return math.sqrt(x * x + y * y)


def analyze_drift(
    points: list[tuple[float, float]],
    *,
    threshold: float,
    sample_interval_ms: float = 8.0,
    hold_ms: int = 500,
    sample_ratio: float = 0.25,
) -> DriftMetrics:
    if not points:
        return DriftMetrics(0, 0, 0, 0, 0, 0, 0)

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    radii = [radial_distance(x, y) for x, y in points]
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    max_r = max(radii)
    mean_r = statistics.fmean(radii)
    std_r = statistics.pstdev(radii) if len(radii) > 1 else 0.0
    above = sum(1 for r in radii if r > threshold)
    above_ratio = above / len(radii)

    sustained = 0.0
    streak = 0
    for r in radii:
        if r > threshold:
            streak += 1
            sustained = max(sustained, streak * sample_interval_ms)
        else:
            streak = 0

    return DriftMetrics(
        mean_x=mean_x,
        mean_y=mean_y,
        max_radius=max_r,
        mean_radius=mean_r,
        stddev_radius=std_r,
        above_threshold_ratio=above_ratio,
        sustained_ms=sustained,
    )


def drift_detected(metrics: DriftMetrics, threshold: float, hold_ms: int, sample_ratio: float) -> bool:
    if metrics.max_radius <= threshold:
        return False
    if metrics.sustained_ms >= hold_ms:
        return True
    return metrics.above_threshold_ratio >= sample_ratio


def classify_drift(max_radius: float, warn: float, fail: float) -> str:
    if max_radius > fail:
        return "FAIL"
    if max_radius > warn:
        return "WARN"
    return "PASS"


def detect_spikes(values: list[float], threshold: float = 0.03) -> int:
    spikes = 0
    for i in range(1, len(values)):
        if abs(values[i] - values[i - 1]) > threshold:
            spikes += 1
    return spikes


# Envelope of the gate: max radius per angle. Inner travel must not affect the score.
CIRCULARITY_OUTER_MIN = 0.55
CIRCULARITY_BINS = 36
CIRCULARITY_MIN_BINS = 16
# Independent X/Y axes (Xbox square gate): cardinal r≈1, diagonal r≈√2 → ~29%.
CIRCULARITY_WARN_PCT = 38.0
CIRCULARITY_FAIL_PCT = 52.0
CIRCULARITY_SQUARE_MIN_PCT = 18.0
CIRCULARITY_SQUARE_MAX_PCT = 38.0


def analyze_circularity(
    points: list[tuple[float, float, float]],
    *,
    outer_min: float = CIRCULARITY_OUTER_MIN,
) -> CircularityMetrics:
    if not points:
        return CircularityMetrics(0, 0, 0, 0, {})

    outer = [p for p in points if p[2] >= outer_min]
    if len(outer) < 12:
        return CircularityMetrics(0, 0, 0, 0, {})

    n = CIRCULARITY_BINS
    bins = [0.0] * n
    filled = [False] * n
    for x, y, r in outer:
        idx = int((math.atan2(y, x) + math.pi) / math.tau * n) % n
        if r > bins[idx]:
            bins[idx] = r
            filled[idx] = True

    envelope = [bins[i] for i in range(n) if filled[i]]
    quads = [False, False, False, False]
    for i, ok in enumerate(filled):
        if ok:
            quads[i * 4 // n] = True
    if len(envelope) < CIRCULARITY_MIN_BINS or not all(quads):
        return CircularityMetrics(0, 0, 0, 0, {})

    r_min = min(envelope)
    r_max = max(envelope)
    r_mean = statistics.fmean(envelope)
    error = ((r_max - r_min) / r_max * 100.0) if r_max > 0 else 0.0

    quadrants: dict[str, list[float]] = {"NE": [], "NW": [], "SE": [], "SW": []}
    for x, y, r in outer:
        if x >= 0 and y >= 0:
            quadrants["NE"].append(r)
        elif x < 0 and y >= 0:
            quadrants["NW"].append(r)
        elif x >= 0 and y < 0:
            quadrants["SE"].append(r)
        else:
            quadrants["SW"].append(r)

    asymmetry = {name: statistics.fmean(rs) if rs else 0.0 for name, rs in quadrants.items()}
    return CircularityMetrics(
        min_radius=r_min,
        max_radius=r_max,
        mean_radius=r_mean,
        circularity_error_pct=error,
        quadrant_asymmetry=asymmetry,
    )


def classify_circularity(error_pct: float) -> str:
    if error_pct > CIRCULARITY_FAIL_PCT:
        return "FAIL"
    if error_pct > CIRCULARITY_WARN_PCT:
        return "WARN"
    return "PASS"


def looks_like_square_gate(error_pct: float) -> bool:
    return CIRCULARITY_SQUARE_MIN_PCT <= error_pct <= CIRCULARITY_SQUARE_MAX_PCT


def analyze_trigger(values: list[float], *, min_ok: float, max_ok: float, rest_jitter: float) -> TriggerMetrics:
    if not values:
        return TriggerMetrics(0, 0, 0, 0, False, 0)

    v_min = min(values)
    v_max = max(values)
    rest = values[: max(1, len(values) // 10)]
    jitter = max(rest) - min(rest) if rest else 0
    spikes = detect_spikes(values)
    returns = v_min <= min_ok + 0.02
    dead = 0.0
    for v in values:
        if v > min_ok:
            break
        dead = v

    return TriggerMetrics(
        min_value=v_min,
        max_value=v_max,
        rest_jitter=jitter,
        spike_count=spikes,
        returns_to_zero=returns,
        dead_band=dead,
    )


def classify_trigger(m: TriggerMetrics, min_ok: float, max_ok: float, jitter_ok: float) -> str:
    if m.max_value < max_ok or m.min_value > min_ok + 0.05 or not m.returns_to_zero:
        return "FAIL"
    if m.max_value < max_ok + 0.02 or m.rest_jitter > jitter_ok or m.spike_count > 3:
        return "WARN"
    return "PASS"


def analyze_event_rate(timestamps_ns: list[int]) -> EventRateMetrics:
    if len(timestamps_ns) < 2:
        return EventRateMetrics(len(timestamps_ns), len(timestamps_ns), 0, 0, 0, 0, 0)

    intervals = [(timestamps_ns[i] - timestamps_ns[i - 1]) / 1_000_000 for i in range(1, len(timestamps_ns))]
    mean_i = statistics.fmean(intervals)
    median_i = statistics.median(intervals)
    max_i = max(intervals)
    std_i = statistics.pstdev(intervals) if len(intervals) > 1 else 0.0
    hz = 1000.0 / mean_i if mean_i > 0 else 0.0

    return EventRateMetrics(
        sample_count=len(timestamps_ns),
        event_count=len(timestamps_ns),
        mean_interval_ms=mean_i,
        median_interval_ms=median_i,
        max_interval_ms=max_i,
        estimated_hz=hz,
        stddev_interval_ms=std_i,
    )

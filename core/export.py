"""Экспорт отчётов JSON/CSV."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from core.report import DiagnosticReport
from core.status import TestStatus


def _serialize(obj: object) -> object:
    if isinstance(obj, TestStatus):
        return obj.value
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    if isinstance(obj, tuple):
        return list(obj)
    return obj


def export_json(report: DiagnosticReport, path: Path) -> None:
    data = _serialize(asdict(report))
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def export_csv(report: DiagnosticReport, path: Path) -> None:
    rows: list[list[str]] = [
        ["section", "key", "value"],
        ["device", "name", report.device_name],
        ["device", "path", report.device_path],
        ["device", "profile", report.axis_profile],
        ["summary", "overall", report.overall.value],
        ["summary", "score", str(report.score)],
        ["summary", "duration_s", str(report.duration_seconds)],
    ]
    for test_id, status in report.tests.items():
        rows.append(["test", test_id, status.value])

    for prefix, stick in (("left_stick", report.left_stick), ("right_stick", report.right_stick)):
        rows.append([prefix, "status", stick.status.value])
        rows.append([prefix, "drift_pct", f"{stick.drift_pct:.4f}"])
        rows.append([prefix, "circularity_pct", f"{stick.circularity_pct:.2f}"])
        for issue in stick.issues:
            rows.append([prefix, "issue", issue])

    for prefix, trig in (("lt", report.lt), ("rt", report.rt)):
        rows.append([prefix, "status", trig.status.value])
        rows.append([prefix, "min", f"{trig.min_value:.4f}"])
        rows.append([prefix, "max", f"{trig.max_value:.4f}"])
        for issue in trig.issues:
            rows.append([prefix, "issue", issue])

    rows.append(["buttons", "status", report.buttons.status.value])
    rows.append(["buttons", "pressed", str(report.buttons.pressed_count)])
    rows.append(["buttons", "held", str(report.buttons.held_count)])
    for item in report.buttons.buttons:
        rows.append(["button", item.name, f"pressed={item.pressed}, held={item.held}"])
        for issue in item.issues:
            rows.append(["button", item.name, issue])

    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerows(rows)

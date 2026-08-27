"""Статусы результатов диагностики."""

from __future__ import annotations

from enum import Enum


class TestStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    NOT_TESTED = "NOT_TESTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"


def worst_status(*statuses: TestStatus) -> TestStatus:
    order = {
        TestStatus.FAIL: 4,
        TestStatus.WARN: 3,
        TestStatus.NOT_SUPPORTED: 2,
        TestStatus.NOT_TESTED: 1,
        TestStatus.PASS: 0,
    }
    if not statuses:
        return TestStatus.NOT_TESTED
    return max(statuses, key=lambda s: order[s])


def overall_from_tests(tests: dict[str, TestStatus]) -> TestStatus:
    values = list(tests.values())
    if any(s == TestStatus.FAIL for s in values):
        return TestStatus.FAIL
    if any(s == TestStatus.WARN for s in values):
        return TestStatus.WARN
    tested = [s for s in values if s not in (TestStatus.NOT_TESTED, TestStatus.NOT_SUPPORTED)]
    if not tested:
        return TestStatus.NOT_TESTED
    if all(s == TestStatus.PASS for s in tested):
        return TestStatus.PASS
    return TestStatus.WARN

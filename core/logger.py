"""Журнал сэмплов и событий."""

from __future__ import annotations

import threading
from collections import deque

from core.sample import GamepadSample, RawInputEvent

MAX_SAMPLES = 50_000
MAX_EVENTS = 100_000
RING_SIZE = 500


class EventLogger:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._samples: deque[GamepadSample] = deque(maxlen=MAX_SAMPLES)
        self._events: deque[RawInputEvent] = deque(maxlen=MAX_EVENTS)
        self._ring_samples: deque[GamepadSample] = deque(maxlen=RING_SIZE)
        self._ring_events: deque[RawInputEvent] = deque(maxlen=RING_SIZE)
        self._active = False
        self._test_id = ""

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def start(self, test_id: str = "") -> None:
        with self._lock:
            self._active = True
            self._test_id = test_id
            self._samples.clear()
            self._events.clear()

    def stop(self) -> None:
        with self._lock:
            self._active = False
            self._test_id = ""

    def add_sample(self, sample: GamepadSample) -> None:
        with self._lock:
            self._ring_samples.append(sample)
            if self._active:
                self._samples.append(sample)

    def add_event(self, event: RawInputEvent) -> None:
        with self._lock:
            self._ring_events.append(event)
            if self._active:
                if event.test_id == "" and self._test_id:
                    event.test_id = self._test_id
                self._events.append(event)

    def get_samples(self, since_ns: int = 0) -> list[GamepadSample]:
        with self._lock:
            if since_ns <= 0:
                return list(self._samples)
            return [s for s in self._samples if s.timestamp_ns >= since_ns]

    def get_events(self, since_ns: int = 0) -> list[RawInputEvent]:
        with self._lock:
            if since_ns <= 0:
                return list(self._events)
            return [e for e in self._events if e.timestamp_ns >= since_ns]

    def recent_samples(self, limit: int = RING_SIZE) -> list[GamepadSample]:
        with self._lock:
            items = list(self._ring_samples)
            return items[-limit:]

    def recent_events(self, limit: int = RING_SIZE) -> list[RawInputEvent]:
        with self._lock:
            items = list(self._ring_events)
            return items[-limit:]

    def clear_session(self) -> None:
        with self._lock:
            self._samples.clear()
            self._events.clear()

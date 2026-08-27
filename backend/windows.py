"""Windows backend: pygame input."""

from __future__ import annotations

import threading
import time

from backend.sdl_env import configure_sdl_env

configure_sdl_env()

import pygame

from backend.protocol import PadState
from core.logger import EventLogger
from core.sample import DeviceInfo, GamepadSample, RawInputEvent
from pad_common import XINPUT_PROFILE, detect_axis_profile_from_name, input_step_detected, normalize_trigger


class WindowsGamepadBackend:
    def __init__(self) -> None:
        self.logger = EventLogger()
        self._lock = threading.Lock()
        self._joy: pygame.joystick.Joystick | None = None
        self._profile = XINPUT_PROFILE
        self._state = PadState()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._event_timestamps: list[int] = []

    def start(self) -> None:
        if not pygame.get_init():
            pygame.init()
        if not pygame.joystick.get_init():
            pygame.joystick.init()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        if self._joy:
            try:
                self._joy.stop_rumble()
                self._joy.quit()
            except pygame.error:
                pass
        pygame.joystick.quit()
        pygame.quit()

    def get_state(self) -> PadState:
        with self._lock:
            return PadState(
                connected=self._state.connected,
                name=self._state.name,
                axis_profile=self._profile.label,
                hint=self._state.hint,
                buttons=dict(self._state.buttons),
                axes=dict(self._state.axes),
                hat=self._state.hat,
            )

    def get_axis_profile(self):
        return self._profile

    def get_device_info(self) -> DeviceInfo:
        with self._lock:
            return DeviceInfo(
                name=self._state.name,
                path="pygame",
                axis_profile=self._profile.label,
                connected=self._state.connected,
            )

    def start_logging(self, test_id: str) -> None:
        self.logger.start(test_id)

    def stop_logging(self) -> None:
        self.logger.stop()

    def get_logged_samples(self) -> list:
        return self.logger.get_samples()

    def get_event_timestamps(self) -> list[int]:
        with self._lock:
            return list(self._event_timestamps)

    def wait_for_user_step(self, message: str, timeout: float, stop_check, expect: str = "any") -> bool:
        del message
        end = time.monotonic() + timeout
        baseline = self.get_state()
        mapped0 = self._profile.read(baseline.axes)
        while time.monotonic() < end:
            if stop_check():
                return False
            state = self.get_state()
            mapped = self._profile.read(state.axes)
            if input_step_detected(mapped0, mapped, baseline.buttons, state.buttons, expect):
                return True
            time.sleep(0.05)
        return False

    def rumble(self, left: float, right: float, duration_ms: int) -> bool:
        if self._joy is None:
            return False
        try:
            return bool(self._joy.rumble(left, right, duration_ms))
        except pygame.error:
            return False

    def stop_rumble(self) -> None:
        if self._joy is None:
            return
        try:
            self._joy.stop_rumble()
        except pygame.error:
            pass

    def is_connected(self) -> bool:
        return self.get_state().connected

    def get_device_name(self) -> str:
        return self.get_state().name

    def get_device_path(self) -> str:
        return "pygame"

    def get_vendor_product(self) -> tuple[int | None, int | None]:
        return None, None

    def get_axis_profile_name(self) -> str:
        return self._profile.label

    def _attach(self, index: int) -> None:
        joy = pygame.joystick.Joystick(index)
        joy.init()
        self._joy = joy
        self._profile = detect_axis_profile_from_name(joy.get_name(), joy.get_numaxes())
        with self._lock:
            self._state.connected = True
            self._state.name = joy.get_name()
            self._state.buttons.clear()
            self._state.axes.clear()
            self._state.hat = (0, 0)

    def _detach(self) -> None:
        if self._joy:
            try:
                self._joy.quit()
            except pygame.error:
                pass
        self._joy = None
        self._profile = XINPUT_PROFILE
        with self._lock:
            self._state = PadState(hint="Подключите геймпад Xbox")

    def _pick_joystick(self) -> None:
        count = pygame.joystick.get_count()
        if count == 0:
            if self._joy:
                self._detach()
            return
        if self._joy is not None:
            return
        best = 0
        best_score = -1
        for i in range(count):
            j = pygame.joystick.Joystick(i)
            j.init()
            name = j.get_name().lower()
            score = 100 if "xbox" in name or "microsoft" in name else 0
            if score > best_score:
                best_score = score
                best = i
            j.quit()
        self._attach(best)

    def _emit_sample(self, ts: int) -> None:
        with self._lock:
            mapped = self._profile.read(self._state.axes)
            for k in ("lt", "rt"):
                mapped[k] = normalize_trigger(mapped[k])
            sample = GamepadSample(
                timestamp_ns=ts,
                axes=mapped,
                buttons=dict(self._state.buttons),
                hat=self._state.hat,
            )
        self.logger.add_sample(sample)

    def _loop(self) -> None:
        self._pick_joystick()
        while not self._stop.is_set():
            for event in pygame.event.get():
                ts = time.monotonic_ns()
                with self._lock:
                    self._event_timestamps.append(ts)
                    if len(self._event_timestamps) > 10000:
                        self._event_timestamps = self._event_timestamps[-5000:]

                if event.type == pygame.JOYDEVICEADDED:
                    if self._joy is None:
                        self._pick_joystick()
                elif event.type == pygame.JOYDEVICEREMOVED:
                    if self._joy and event.instance_id == self._joy.get_instance_id():
                        self._detach()
                elif event.type in (pygame.JOYBUTTONDOWN, pygame.JOYBUTTONUP):
                    with self._lock:
                        self._state.buttons[event.button] = event.type == pygame.JOYBUTTONDOWN
                    self.logger.add_event(
                        RawInputEvent(ts, "BUTTON", str(event.button), int(event.type == pygame.JOYBUTTONDOWN))
                    )
                    self._emit_sample(ts)
                elif event.type in (
                    getattr(pygame, "CONTROLLERBUTTONDOWN", -1),
                    getattr(pygame, "CONTROLLERBUTTONUP", -2),
                ):
                    misc = getattr(pygame, "CONTROLLER_BUTTON_MISC1", 15)
                    if event.button == misc:
                        pressed = event.type == getattr(pygame, "CONTROLLERBUTTONDOWN", -1)
                        with self._lock:
                            self._state.buttons[15] = pressed
                        self.logger.add_event(RawInputEvent(ts, "BUTTON", "Share", int(pressed)))
                        self._emit_sample(ts)
                elif event.type == pygame.JOYAXISMOTION:
                    with self._lock:
                        self._state.axes[event.axis] = event.value
                    self.logger.add_event(
                        RawInputEvent(ts, "AXIS", str(event.axis), float(event.value))
                    )
                    self._emit_sample(ts)
                elif event.type == pygame.JOYHATMOTION:
                    with self._lock:
                        self._state.hat = event.value
                        hx, hy = event.value
                        self._state.buttons[11] = hy < 0
                        self._state.buttons[12] = hy > 0
                        self._state.buttons[13] = hx < 0
                        self._state.buttons[14] = hx > 0
                    self.logger.add_event(
                        RawInputEvent(ts, "HAT", "0", str(event.value))
                    )
                    self._emit_sample(ts)
            if self._joy is None:
                self._pick_joystick()
            pygame.time.wait(5)

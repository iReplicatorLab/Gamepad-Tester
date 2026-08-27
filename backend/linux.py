"""Linux backend: evdev input, pygame rumble fallback, Xbox 360 D-pad workarounds."""

from __future__ import annotations

import os
import select
import struct
import threading
import time
from pathlib import Path

from evdev import InputDevice, ecodes, ff, list_devices

try:
    import pygame
except ImportError:
    pygame = None  # type: ignore[assignment]

from backend.protocol import PadState
from core.i18n import t
from core.logger import EventLogger
from core.sample import DeviceInfo, GamepadSample, RawInputEvent
from pad_common import (
    XBOX360_PROFILE,
    XINPUT_PROFILE,
    AxisProfile,
    detect_axis_profile_from_name,
    input_step_detected,
    normalize_trigger,
)

MS_VENDOR_ID = 0x045E


def _transport_label(dev: InputDevice) -> str:
    try:
        bustype = int(dev.info.bustype)
    except (AttributeError, OSError, TypeError, ValueError):
        return ""
    if bustype == getattr(ecodes, "BUS_USB", 0x03):
        return "USB"
    if bustype == getattr(ecodes, "BUS_BLUETOOTH", 0x05):
        return "Bluetooth"
    if bustype == getattr(ecodes, "BUS_WIRELESS", 0x0B):
        return "Wireless"
    return ""

# Linux 6.17+ меняет D-pad у Xbox 360 Wireless; фикс из SDL/Fedora workaround.
# https://github.com/libsdl-org/SDL/issues/14324
X360_SDL_GAMECONTROLLERCONFIG = (
    "0300a81c5e040000a102000000010000,X360 Wireless Controller,"
    "a:b0,b:b1,x:b2,y:b3,back:b6,guide:b8,start:b7,"
    "leftshoulder:b4,rightshoulder:b5,leftstick:b9,rightstick:b10,"
    "lefttrigger:a2,righttrigger:a5,leftx:a0,lefty:a1,rightx:a3,righty:a4,"
    "dpup:b11,dpdown:b12,dpleft:b13,dpright:b14,platform:Linux,"
)
X360_SDL_MAPPING_FIELDS = (
    "a:b0,b:b1,x:b2,y:b3,back:b6,guide:b8,start:b7,"
    "leftshoulder:b4,rightshoulder:b5,leftstick:b9,rightstick:b10,"
    "lefttrigger:a2,righttrigger:a5,leftx:a0,lefty:a1,rightx:a3,righty:a4,"
    "dpup:b11,dpdown:b12,dpleft:b13,dpright:b14"
)

JS_EVENT_FORMAT = "IhBB"
JS_EVENT_SIZE = struct.calcsize(JS_EVENT_FORMAT)
JS_EVENT_BUTTON = 0x01
JS_EVENT_AXIS = 0x02
JS_EVENT_INIT = 0x80
JS_HAT_X_AXIS = 6
JS_HAT_Y_AXIS = 7
JS_HAT_THRESHOLD = 16384
DPAD_INDICES = (11, 12, 13, 14)
SDL_CONTROLLER_DPAD = (11, 12, 13, 14)

EVDEV_BUTTONS = {
    ecodes.BTN_SOUTH: 0,  # A
    ecodes.BTN_EAST: 1,  # B
    # xpad шлёт BTN_X/BTN_Y. В ядре BTN_X=NORTH, BTN_Y=WEST — это не Xbox-ромб.
    ecodes.BTN_X: 2,
    ecodes.BTN_Y: 3,
    ecodes.BTN_TL: 4,
    ecodes.BTN_TR: 5,
    ecodes.BTN_SELECT: 6,
    ecodes.BTN_START: 7,
    ecodes.BTN_MODE: 8,
    ecodes.BTN_THUMBL: 9,
    ecodes.BTN_THUMBR: 10,
    ecodes.BTN_DPAD_UP: 11,
    ecodes.BTN_DPAD_DOWN: 12,
    ecodes.BTN_DPAD_LEFT: 13,
    ecodes.BTN_DPAD_RIGHT: 14,
    getattr(ecodes, "KEY_RECORD", 167): 15,  # Share (Series / One)
}


def abs_codes_from_caps(caps) -> list[int]:
    data = caps.get(ecodes.EV_ABS, [])
    if isinstance(data, dict):
        return list(data.keys())
    if not data:
        return []
    if isinstance(data[0], tuple):
        return [code for code, _ in data]
    return list(data)


def can_access_gamepads() -> bool:
    if os.geteuid() == 0:
        return True
    try:
        import grp

        input_gid = grp.getgrnam("input").gr_gid
        if input_gid in os.getgroups():
            return True
    except KeyError:
        pass
    return find_best_gamepad() is not None


def normalize_axis(value: int, info) -> float:
    if info.max <= info.min:
        return 0.0
    mid = (info.max + info.min) / 2.0
    half = (info.max - info.min) / 2.0
    if half == 0:
        return 0.0
    return max(-1.0, min(1.0, (value - mid) / half))


def normalize_trigger_axis(value: int, info) -> float:
    if info.max <= info.min:
        return 0.0
    if info.min < 0:
        return normalize_axis(value, info)
    return max(0.0, min(1.0, (value - info.min) / (info.max - info.min)))


def score_gamepad_device(dev: InputDevice) -> int:
    try:
        caps = dev.capabilities(absinfo=False)
    except OSError:
        return -1

    keys = caps.get(ecodes.EV_KEY, [])
    abses = abs_codes_from_caps(caps)
    if ecodes.BTN_SOUTH not in keys:
        return -1

    score = len(abses) + len(keys)
    name = dev.name.lower()
    if "xbox" in name or "x-box" in name or "microsoft" in name:
        score += 200
    if "series" in name:
        score += 50
    if dev.info.vendor == MS_VENDOR_ID:
        score += 100
    if ecodes.ABS_X in abses and ecodes.ABS_RX in abses:
        score += 40
    if "mouse" in name or "keyboard" in name or "consumer control" in name:
        score -= 500
    if "headset" in name or "audio" in name:
        score -= 300
    return score


def find_best_gamepad() -> InputDevice | None:
    best_score = -1
    best_dev: InputDevice | None = None
    candidates: list[str] = list(list_devices())

    by_id = Path("/dev/input/by-id")
    if by_id.is_dir():
        for link in sorted(by_id.glob("*event-joystick")):
            path = str(link.resolve())
            if path not in candidates:
                candidates.append(path)

    for path in candidates:
        try:
            dev = InputDevice(path)
        except (OSError, PermissionError):
            continue
        score = score_gamepad_device(dev)
        if score > best_score:
            if best_dev is not None:
                try:
                    best_dev.close()
                except OSError:
                    pass
            best_score = score
            best_dev = dev
        else:
            try:
                dev.close()
            except OSError:
                pass

    return best_dev if best_score >= 0 else None


def find_js_device_path(event_path: str) -> str | None:
    """Путь к /dev/input/js* для того же геймпада, что и event-устройство."""
    event_name = Path(event_path).name
    by_id = Path("/dev/input/by-id")
    if by_id.is_dir():
        for link in sorted(by_id.glob("*event-joystick")):
            try:
                if link.resolve().name != event_name:
                    continue
                js_link = by_id / link.name.replace("event-joystick", "joystick")
                if js_link.exists():
                    return str(js_link.resolve())
            except OSError:
                continue
    try:
        text = Path("/proc/bus/input/devices").read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    for block in text.split("\n\n"):
        if event_name not in block:
            continue
        for line in block.splitlines():
            if not line.startswith("H: Handlers="):
                continue
            for token in line.split("=", 1)[1].split():
                if token.startswith("js"):
                    path = f"/dev/input/{token}"
                    if Path(path).exists():
                        return path
    js0 = Path("/dev/input/js0")
    return str(js0) if js0.exists() else None


def _hat_from_js_axis(value: int) -> int:
    if value <= -JS_HAT_THRESHOLD:
        return -1
    if value >= JS_HAT_THRESHOLD:
        return 1
    return 0


def build_abs_code_map(profile: AxisProfile, abses: list[int]) -> dict[str, int]:
    lt = ecodes.ABS_GAS if ecodes.ABS_GAS in abses else ecodes.ABS_Z
    rt = ecodes.ABS_BRAKE if ecodes.ABS_BRAKE in abses else ecodes.ABS_RZ
    if profile is XBOX360_PROFILE:
        return {
            "left_x": ecodes.ABS_X,
            "left_y": ecodes.ABS_Y,
            "lt": lt,
            "right_x": ecodes.ABS_RX,
            "right_y": ecodes.ABS_RY,
            "rt": rt,
        }
    return {
        "left_x": ecodes.ABS_X,
        "left_y": ecodes.ABS_Y,
        "right_x": ecodes.ABS_RX,
        "right_y": ecodes.ABS_RY,
        "lt": lt,
        "rt": rt,
    }


def _evdev_code_name(event_type: int, code: int) -> str:
    table = ecodes.bytype.get(event_type)
    if table is not None:
        try:
            return table[code]
        except KeyError:
            pass
    return str(code)


class LinuxGamepadBackend:
    """Читает геймпад через evdev (Linux). Pygame — только резерв для вибрации."""

    def __init__(self) -> None:
        self.logger = EventLogger()
        self._lock = threading.Lock()
        self._state = PadState()
        self._profile = XINPUT_PROFILE
        self._device: InputDevice | None = None
        self._device_path: str | None = None
        self._abs_map: dict[str, int] = {}
        self._dpad_via_keys = False
        self._x360_dpad_keys: dict[int, bool] = {11: False, 12: False, 13: False, 14: False}
        self._pygame_dpad_buttons: dict[int, bool] = {11: False, 12: False, 13: False, 14: False}
        self._pygame_hat: tuple[int, int] = (0, 0)
        self._js_fd: int | None = None
        self._js_path: str | None = None
        self._js_dpad_buttons: dict[int, bool] = {11: False, 12: False, 13: False, 14: False}
        self._js_hat: tuple[int, int] = (0, 0)
        self._rumble_device: InputDevice | None = None
        self._rumble_effect_id: int | None = None
        self._rumble_stop_timer: threading.Timer | None = None
        self._pygame_joy = None
        self._pygame_controller = None
        self._sdl_controller_mod = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _set_dpad_from_hat_locked(self, hx: int, hy: int) -> None:
        """D-pad из hat. Linux/evdev: Y=-1 вверх, X=-1 влево."""
        self._state.buttons[11] = hy < 0
        self._state.buttons[12] = hy > 0
        self._state.buttons[13] = hx < 0
        self._state.buttons[14] = hx > 0

    def _sync_dpad_from_hat_locked(self, hx: int, hy: int) -> None:
        """Series / Xbox One: D-pad через evdev hat."""
        if hx != 0 or hy != 0:
            self._set_dpad_from_hat_locked(hx, hy)
        elif not self._dpad_via_keys:
            for idx in DPAD_INDICES:
                self._state.buttons[idx] = False

    def _apply_x360_dpad_locked(self, dev: InputDevice | None) -> None:
        """Xbox 360: OR по evdev-кнопкам/hat, js0 и pygame (kernel 6.17+ wireless)."""
        up = down = left = right = False
        hx, hy = 0, 0

        if dev is not None:
            try:
                keys = set(dev.active_keys())
                up |= ecodes.BTN_DPAD_UP in keys
                down |= ecodes.BTN_DPAD_DOWN in keys
                left |= ecodes.BTN_DPAD_LEFT in keys
                right |= ecodes.BTN_DPAD_RIGHT in keys
                happy1 = getattr(ecodes, "BTN_TRIGGER_HAPPY1", None)
                if happy1 is not None and any(code in keys for code in range(happy1, happy1 + 4)):
                    # Старый xpad wireless: HAPPY1–4 = left/right/up/down.
                    up |= (happy1 + 2) in keys
                    down |= (happy1 + 3) in keys
                    left |= happy1 in keys
                    right |= (happy1 + 1) in keys
            except OSError:
                pass
            try:
                hat_x = dev.absinfo(ecodes.ABS_HAT0X)
                hat_y = dev.absinfo(ecodes.ABS_HAT0Y)
                if hat_x is not None and hat_y is not None:
                    hx, hy = hat_x.value, hat_y.value
            except (OSError, TypeError):
                pass

        up |= self._x360_dpad_keys.get(11, False)
        down |= self._x360_dpad_keys.get(12, False)
        left |= self._x360_dpad_keys.get(13, False)
        right |= self._x360_dpad_keys.get(14, False)

        up |= self._js_dpad_buttons.get(11, False)
        down |= self._js_dpad_buttons.get(12, False)
        left |= self._js_dpad_buttons.get(13, False)
        right |= self._js_dpad_buttons.get(14, False)
        jhx, jhy = self._js_hat
        if jhx or jhy:
            hx, hy = jhx, jhy

        phx, phy = self._pygame_hat
        if phx or phy:
            hx, hy = phx, phy
        up |= self._pygame_dpad_buttons.get(11, False)
        down |= self._pygame_dpad_buttons.get(12, False)
        left |= self._pygame_dpad_buttons.get(13, False)
        right |= self._pygame_dpad_buttons.get(14, False)

        if hx or hy:
            up |= hy < 0
            down |= hy > 0
            left |= hx < 0
            right |= hx > 0

        self._state.hat = (hx, hy)
        self._state.buttons[11] = up
        self._state.buttons[12] = down
        self._state.buttons[13] = left
        self._state.buttons[14] = right

    def _poll_pygame_supplement(self) -> None:
        """Xbox 360 Wireless: D-pad и триггеры часто надёжнее через SDL."""
        if self._profile is not XBOX360_PROFILE:
            return
        if pygame is None:
            return
        try:
            pygame.event.pump()
            ctrl_btns = {11: False, 12: False, 13: False, 14: False}
            if self._sdl_controller_mod is not None and self._pygame_controller is not None:
                try:
                    self._sdl_controller_mod.update()
                    for idx in SDL_CONTROLLER_DPAD:
                        ctrl_btns[idx] = bool(self._pygame_controller.get_button(idx))
                except Exception:
                    pass
            joy_btns = {11: False, 12: False, 13: False, 14: False}
            phx, phy = 0, 0
            joy = self._pygame_joy
            if joy is not None:
                if joy.get_numhats() > 0:
                    raw_x, raw_y = joy.get_hat(0)
                    # SDL hat: Y=+1 вверх → evdev Y=-1 вверх.
                    phx, phy = raw_x, -raw_y
                for idx in DPAD_INDICES:
                    if idx < joy.get_numbuttons():
                        joy_btns[idx] = bool(joy.get_button(idx))
            with self._lock:
                self._pygame_hat = (phx, phy)
                for idx in DPAD_INDICES:
                    self._pygame_dpad_buttons[idx] = ctrl_btns[idx] or joy_btns[idx]
                self._apply_x360_dpad_locked(self._device)
        except pygame.error:
            pass

    def _poll_share_locked(self, dev: InputDevice | None) -> None:
        """Share на Series / One: KEY_RECORD (xpad) или SDL MISC1."""
        if self._profile is XBOX360_PROFILE:
            self._state.buttons[15] = False
            return
        pressed = False
        rec = getattr(ecodes, "KEY_RECORD", None)
        if rec is not None and dev is not None:
            try:
                pressed = rec in set(dev.active_keys())
            except OSError:
                pressed = bool(self._state.buttons.get(15, False))
        if pygame is not None:
            try:
                pygame.event.pump()
                if self._sdl_controller_mod is not None and self._pygame_controller is not None:
                    try:
                        self._sdl_controller_mod.update()
                        pressed = pressed or bool(self._pygame_controller.get_button(15))
                    except Exception:
                        pass
                joy = self._pygame_joy
                if joy is not None and joy.get_numbuttons() > 15:
                    pressed = pressed or bool(joy.get_button(15))
            except pygame.error:
                pass
        self._state.buttons[15] = pressed

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        self._close_device()
        self._stop_rumble_effect()
        self._close_pygame()

    def _refresh_live_state(self) -> None:
        dev = self._device
        if dev is None:
            return
        try:
            hat_x = dev.absinfo(ecodes.ABS_HAT0X)
            hat_y = dev.absinfo(ecodes.ABS_HAT0Y)
        except (OSError, TypeError):
            hat_x = hat_y = None

        abs_updates: list[tuple[str, float]] = []
        for logical, code in self._abs_map.items():
            info = dev.absinfo(code)
            if info is None:
                continue
            if logical in ("lt", "rt"):
                value = normalize_trigger_axis(info.value, info)
            else:
                value = normalize_axis(info.value, info)
            abs_updates.append((logical, value))

        with self._lock:
            if self._profile is XBOX360_PROFILE:
                self._apply_x360_dpad_locked(dev)
            elif not self._dpad_via_keys and hat_x is not None and hat_y is not None:
                self._state.hat = (hat_x.value, hat_y.value)
                self._sync_dpad_from_hat_locked(hat_x.value, hat_y.value)

            use_pygame_triggers = (
                self._profile is XBOX360_PROFILE
                and pygame is not None
                and (self._pygame_controller is not None or self._pygame_joy is not None)
            )
            pygame_lt = pygame_rt = 0.0
            if use_pygame_triggers:
                try:
                    pygame.event.pump()
                    if self._pygame_controller is not None:
                        pygame_lt = max(0.0, min(1.0, float(self._pygame_controller.get_axis(4)) / 32767.0))
                        pygame_rt = max(0.0, min(1.0, float(self._pygame_controller.get_axis(5)) / 32767.0))
                    elif self._pygame_joy is not None and self._pygame_joy.get_numaxes() > 5:
                        pygame_lt = normalize_trigger(self._pygame_joy.get_axis(2))
                        pygame_rt = normalize_trigger(self._pygame_joy.get_axis(5))
                    else:
                        use_pygame_triggers = False
                except pygame.error:
                    use_pygame_triggers = False

            for logical, value in abs_updates:
                idx = getattr(self._profile, logical)
                self._state.axes[idx] = value
            if use_pygame_triggers:
                self._state.axes[self._profile.lt] = max(
                    self._state.axes.get(self._profile.lt, 0.0), pygame_lt
                )
                self._state.axes[self._profile.rt] = max(
                    self._state.axes.get(self._profile.rt, 0.0), pygame_rt
                )

            self._poll_share_locked(dev)

    def get_state(self) -> PadState:
        self._refresh_live_state()
        with self._lock:
            return PadState(
                connected=self._state.connected,
                name=self._state.name,
                axis_profile=self._profile.label,
                hint=self._state.hint,
                buttons=dict(self._state.buttons),
                axes=dict(self._state.axes),
                hat=self._state.hat,
                transport=self._state.transport,
            )

    def get_axis_profile(self) -> AxisProfile:
        return self._profile

    def get_device_info(self) -> DeviceInfo:
        with self._lock:
            connected = self._state.connected
            name = self._state.name
            axis_profile = self._profile.label if connected else ""

        vendor_id: int | None = None
        product_id: int | None = None
        path = self._device_path or ""
        dev = self._device
        if dev is not None:
            try:
                vendor_id = dev.info.vendor
                product_id = dev.info.product
            except (OSError, AttributeError):
                pass

        return DeviceInfo(
            name=name,
            path=path,
            vendor_id=vendor_id,
            product_id=product_id,
            axis_profile=axis_profile,
            connected=connected,
        )

    def is_connected(self) -> bool:
        return self.get_state().connected

    def get_device_name(self) -> str:
        return self.get_state().name

    def get_device_path(self) -> str:
        return self._device_path or ""

    def get_vendor_product(self) -> tuple[int | None, int | None]:
        info = self.get_device_info()
        return info.vendor_id, info.product_id

    def get_axis_profile_name(self) -> str:
        return self._profile.label if self._state.connected else ""

    def start_logging(self, test_id: str) -> None:
        self.logger.start(test_id)

    def stop_logging(self) -> None:
        self.logger.stop()

    def get_logged_samples(self) -> list[GamepadSample]:
        return self.logger.get_samples()

    def get_event_timestamps(self) -> list[int]:
        return [event.timestamp_ns for event in self.logger.get_events()]

    def wait_for_user_step(self, message: str, timeout: float, stop_check, expect: str = "any") -> bool:
        del message
        end = time.monotonic() + timeout
        baseline = self.get_state()
        profile = self.get_axis_profile()
        baseline_axes = profile.read(baseline.axes)

        while time.monotonic() < end:
            if stop_check():
                return False
            state = self.get_state()
            axes = profile.read(state.axes)
            if input_step_detected(baseline_axes, axes, baseline.buttons, state.buttons, expect):
                return True
            time.sleep(0.05)
        return False

    def rumble(self, left: float, right: float, duration_ms: int) -> bool:
        if self._rumble_device and self._upload_rumble(left, right, duration_ms):
            return True
        if self._pygame_joy is not None and pygame is not None:
            try:
                return bool(self._pygame_joy.rumble(left, right, duration_ms))
            except pygame.error:
                return False
        return False

    def stop_rumble(self) -> None:
        self._stop_rumble_effect()
        if self._pygame_joy is not None and pygame is not None:
            try:
                self._pygame_joy.stop_rumble()
            except pygame.error:
                pass

    def _close_pygame(self) -> None:
        if pygame is None:
            return
        try:
            if self._pygame_controller is not None:
                try:
                    self._pygame_controller.quit()
                except Exception:
                    pass
            if self._sdl_controller_mod is not None:
                try:
                    self._sdl_controller_mod.quit()
                except Exception:
                    pass
            if self._pygame_joy is not None:
                self._pygame_joy.quit()
            pygame.joystick.quit()
            pygame.quit()
        except Exception:
            pass
        self._pygame_joy = None
        self._pygame_controller = None
        self._sdl_controller_mod = None

    def _init_pygame(self) -> None:
        if pygame is None:
            return
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
        os.environ["SDL_GAMECONTROLLERCONFIG"] = X360_SDL_GAMECONTROLLERCONFIG
        try:
            if not pygame.get_init():
                pygame.init()
            if not pygame.joystick.get_init():
                pygame.joystick.init()
            self._pygame_joy = None
            for index in range(pygame.joystick.get_count()):
                joy = pygame.joystick.Joystick(index)
                joy.init()
                name = joy.get_name().lower()
                if "xbox" in name or "microsoft" in name or "x-box" in name or "360" in name:
                    self._pygame_joy = joy
                    break
            if self._pygame_joy is None and pygame.joystick.get_count() > 0:
                joy = pygame.joystick.Joystick(0)
                joy.init()
                self._pygame_joy = joy
        except pygame.error:
            self._pygame_joy = None

        self._pygame_controller = None
        self._sdl_controller_mod = None
        try:
            from pygame._sdl2 import controller as sdl_controller

            if not sdl_controller.get_init():
                sdl_controller.init()
            self._sdl_controller_mod = sdl_controller
            for index in range(sdl_controller.get_count()):
                if not sdl_controller.is_controller(index):
                    continue
                ctrl = sdl_controller.Controller(index)
                name = (getattr(ctrl, "name", None) or "") or ""
                try:
                    name = name or (sdl_controller.name_forindex(index) or "")
                except Exception:
                    pass
                lowered = name.lower()
                if not any(token in lowered for token in ("xbox", "microsoft", "x-box", "360")):
                    if self._pygame_controller is None:
                        self._pygame_controller = ctrl
                    continue
                try:
                    ctrl.set_mapping(X360_SDL_MAPPING_FIELDS)
                except Exception:
                    pass
                self._pygame_controller = ctrl
                break
        except Exception:
            self._pygame_controller = None
            self._sdl_controller_mod = None

    def _close_js_device(self) -> None:
        if self._js_fd is not None:
            try:
                os.close(self._js_fd)
            except OSError:
                pass
        self._js_fd = None
        self._js_path = None

    def _open_js_device(self, event_path: str | None) -> None:
        self._close_js_device()
        if self._profile is not XBOX360_PROFILE or not event_path:
            return
        path = find_js_device_path(event_path)
        if path is None:
            return
        try:
            self._js_fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            self._js_path = path
        except OSError:
            self._js_fd = None
            self._js_path = None

    def _close_device(self) -> None:
        self._close_js_device()
        if self._device is not None:
            try:
                self._device.close()
            except OSError:
                pass
        self._device = None
        self._device_path = None
        self._rumble_device = None

    def _attach(self, dev: InputDevice) -> None:
        self._close_device()

        caps = dev.capabilities(absinfo=True)
        abses = abs_codes_from_caps(caps)
        profile = detect_axis_profile_from_name(dev.name, len(abses))
        self._device = dev
        self._device_path = dev.path
        self._profile = profile
        self._abs_map = build_abs_code_map(profile, abses)
        key_caps = caps.get(ecodes.EV_KEY, [])
        if isinstance(key_caps, dict):
            key_codes = list(key_caps.keys())
        else:
            key_codes = list(key_caps)
        self._dpad_via_keys = ecodes.BTN_DPAD_UP in key_codes
        self._rumble_device = dev if ecodes.EV_FF in caps else None

        initial_axes: dict[int, float] = {}
        for logical, code in self._abs_map.items():
            info = dev.absinfo(code)
            if info is None:
                continue
            if logical in ("lt", "rt"):
                value = normalize_trigger_axis(info.value, info)
            else:
                value = normalize_axis(info.value, info)
            initial_axes[getattr(profile, logical)] = value

        self._js_dpad_buttons = {11: False, 12: False, 13: False, 14: False}
        self._js_hat = (0, 0)
        self._init_pygame()
        self._open_js_device(dev.path)

        with self._lock:
            self._state = PadState(
                connected=True,
                name=dev.name,
                axis_profile=profile.label,
                axes=initial_axes,
                transport=_transport_label(dev),
            )
            if self._profile is XBOX360_PROFILE:
                self._apply_x360_dpad_locked(dev)
            elif not self._dpad_via_keys:
                hat_x = dev.absinfo(ecodes.ABS_HAT0X)
                hat_y = dev.absinfo(ecodes.ABS_HAT0Y)
                if hat_x is not None and hat_y is not None:
                    self._state.hat = (hat_x.value, hat_y.value)
                    self._sync_dpad_from_hat_locked(hat_x.value, hat_y.value)
        if self._js_fd is not None:
            self._read_js_events()

    def _detach(self, hint: str = "") -> None:
        self._close_device()
        self._profile = XINPUT_PROFILE
        self._dpad_via_keys = False
        self._x360_dpad_keys = {11: False, 12: False, 13: False, 14: False}
        self._pygame_dpad_buttons = {11: False, 12: False, 13: False, 14: False}
        self._pygame_hat = (0, 0)
        self._js_dpad_buttons = {11: False, 12: False, 13: False, 14: False}
        self._js_hat = (0, 0)
        with self._lock:
            self._state = PadState(hint=hint)

    def _scan_and_attach(self) -> None:
        if self._device_path and Path(self._device_path).exists():
            return
        if self._device is not None and self._device_path is None:
            return
        if self._device_path and not Path(self._device_path).exists():
            self._detach(t("hint.disconnected"))

        dev = find_best_gamepad()
        if dev is None:
            with self._lock:
                if not self._state.connected:
                    if can_access_gamepads():
                        self._state.hint = t("hint.connect")
                    else:
                        self._state.hint = t("hint.no_access")
            return
        if dev.path != self._device_path:
            try:
                self._attach(dev)
            except OSError as exc:
                self._detach(t("hint.open_failed", error=exc))

    def _emit_event(self, event) -> None:
        if event.type == ecodes.EV_KEY:
            event_type = "KEY"
        elif event.type == ecodes.EV_ABS:
            event_type = "ABS"
        else:
            return

        self.logger.add_event(
            RawInputEvent(
                timestamp_ns=time.monotonic_ns(),
                event_type=event_type,
                code=_evdev_code_name(event.type, event.code),
                value=event.value,
            )
        )

    def _emit_sample(self) -> None:
        with self._lock:
            axes = self._profile.read(self._state.axes)
            buttons = dict(self._state.buttons)
            hat = self._state.hat

        self.logger.add_sample(
            GamepadSample(
                timestamp_ns=time.monotonic_ns(),
                axes=axes,
                buttons=buttons,
                hat=hat,
            )
        )

    def _emit_sample_if_needed(self) -> None:
        self._emit_sample()

    def _handle_event(self, event) -> None:
        if event.type == ecodes.EV_KEY:
            btn_idx = EVDEV_BUTTONS.get(event.code)
            if btn_idx is not None:
                with self._lock:
                    if self._profile is XBOX360_PROFILE and btn_idx in (11, 12, 13, 14):
                        self._x360_dpad_keys[btn_idx] = bool(event.value)
                        self._apply_x360_dpad_locked(self._device)
                    else:
                        self._state.buttons[btn_idx] = bool(event.value)
            self._emit_event(event)
            self._emit_sample_if_needed()
            return

        if event.type == ecodes.EV_ABS:
            if self._device is not None:
                with self._lock:
                    if event.code == ecodes.ABS_HAT0X:
                        hx, hy = self._state.hat
                        self._state.hat = (event.value, hy)
                        if self._profile is XBOX360_PROFILE:
                            self._apply_x360_dpad_locked(self._device)
                        else:
                            self._sync_dpad_from_hat_locked(event.value, hy)
                    elif event.code == ecodes.ABS_HAT0Y:
                        hx, hy = self._state.hat
                        self._state.hat = (hx, event.value)
                        if self._profile is XBOX360_PROFILE:
                            self._apply_x360_dpad_locked(self._device)
                        else:
                            self._sync_dpad_from_hat_locked(hx, event.value)
                    else:
                        info = self._device.absinfo(event.code)
                        if info is not None:
                            for logical, code in self._abs_map.items():
                                if event.code != code:
                                    continue
                                if logical in ("lt", "rt"):
                                    value = normalize_trigger_axis(event.value, info)
                                else:
                                    value = normalize_axis(event.value, info)
                                self._state.axes[getattr(self._profile, logical)] = value
                                break
            self._emit_event(event)
            self._emit_sample_if_needed()

    def _loop(self) -> None:
        last_scan = 0.0
        while not self._stop.is_set():
            now = time.monotonic()
            if now - last_scan > 1.0:
                self._scan_and_attach()
                last_scan = now

            dev = self._device
            if dev is None:
                time.sleep(0.2)
                continue

            self._poll_pygame_supplement()
            logging = self.logger.is_active
            if logging:
                self._refresh_live_state()
                self._emit_sample()

            try:
                fds = [dev.fd]
                if self._js_fd is not None:
                    fds.append(self._js_fd)
                ready, _, _ = select.select(fds, [], [], 0.02 if logging else 0.05)
                if not ready:
                    continue
                for fd in ready:
                    if fd == dev.fd:
                        for event in dev.read():
                            if self._stop.is_set():
                                break
                            self._handle_event(event)
                    elif fd == self._js_fd:
                        self._read_js_events()
            except OSError:
                self._detach(t("hint.disconnected"))
                time.sleep(0.3)

    def _read_js_events(self) -> None:
        fd = self._js_fd
        if fd is None:
            return
        while True:
            try:
                data = os.read(fd, JS_EVENT_SIZE)
            except BlockingIOError:
                return
            except OSError:
                self._close_js_device()
                return
            if len(data) < JS_EVENT_SIZE:
                return
            _time, value, ev_type, number = struct.unpack(JS_EVENT_FORMAT, data)
            ev_type &= ~JS_EVENT_INIT
            with self._lock:
                if ev_type == JS_EVENT_BUTTON and number in DPAD_INDICES:
                    self._js_dpad_buttons[number] = bool(value)
                    self._apply_x360_dpad_locked(self._device)
                elif ev_type == JS_EVENT_AXIS and number == JS_HAT_X_AXIS:
                    hx = _hat_from_js_axis(value)
                    _, hy = self._js_hat
                    self._js_hat = (hx, hy)
                    self._apply_x360_dpad_locked(self._device)
                elif ev_type == JS_EVENT_AXIS and number == JS_HAT_Y_AXIS:
                    hy = _hat_from_js_axis(value)
                    hx, _ = self._js_hat
                    self._js_hat = (hx, hy)
                    self._apply_x360_dpad_locked(self._device)

    def _upload_rumble(self, left: float, right: float, duration_ms: int) -> bool:
        dev = self._rumble_device
        if dev is None:
            return False
        try:
            self._stop_rumble_effect()
            strong = int(max(0.0, min(1.0, left)) * 0xFFFF)
            weak = int(max(0.0, min(1.0, right)) * 0xFFFF)
            effect = ff.Effect()
            effect.type = ecodes.FF_RUMBLE
            effect.id = -1
            effect.direction = 0
            effect.ff_trigger = ff.Trigger(0, 0)
            effect.ff_replay = ff.Replay(max(100, duration_ms), 0)
            effect.u.ff_rumble_effect = ff.Rumble(
                strong_magnitude=strong,
                weak_magnitude=weak,
            )
            self._rumble_effect_id = dev.upload_effect(effect)
            dev.write(ecodes.EV_FF, self._rumble_effect_id, 1)
            if self._rumble_stop_timer is not None:
                self._rumble_stop_timer.cancel()
            self._rumble_stop_timer = threading.Timer(
                duration_ms / 1000.0,
                self.stop_rumble,
            )
            self._rumble_stop_timer.daemon = True
            self._rumble_stop_timer.start()
            return True
        except (OSError, PermissionError, ValueError, TypeError):
            return False

    def _stop_rumble_effect(self) -> None:
        if self._rumble_stop_timer is not None:
            self._rumble_stop_timer.cancel()
            self._rumble_stop_timer = None
        dev = self._rumble_device
        effect_id = self._rumble_effect_id
        if dev is None or effect_id is None:
            self._rumble_effect_id = None
            return
        try:
            dev.write(ecodes.EV_FF, effect_id, 0)
            dev.erase_effect(effect_id)
        except OSError:
            pass
        self._rumble_effect_id = None

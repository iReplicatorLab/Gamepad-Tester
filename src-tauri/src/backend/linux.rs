use std::collections::HashMap;
use std::fs;
use std::os::fd::{AsRawFd, BorrowedFd, FromRawFd, OwnedFd};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, Sender};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use evdev::{
    AbsoluteAxisType, Device, FFEffect, FFEffectData, FFEffectKind, FFReplay, FFTrigger,
    InputEventKind, Key,
};
use nix::poll::{poll, PollFd, PollFlags, PollTimeout};

use crate::i18n::{t, t_vars};
use crate::logger::EventLogger;
use crate::pad::{
    detect_axis_profile_from_name, AxisProfile, PadState, XBOX360_PROFILE, XINPUT_PROFILE,
};
use crate::sample::{GamepadSample, RawInputEvent};
use crate::session::SampleSource;

const MS_VENDOR_ID: u16 = 0x045E;
const JS_EVENT_SIZE: usize = 8;
const JS_EVENT_BUTTON: u8 = 0x01;
const JS_EVENT_AXIS: u8 = 0x02;
const JS_EVENT_INIT: u8 = 0x80;
const JS_HAT_X_AXIS: u8 = 6;
const JS_HAT_Y_AXIS: u8 = 7;
const JS_HAT_THRESHOLD: i16 = 16384;

enum Cmd {
    Rumble {
        left: f64,
        right: f64,
        duration_ms: u32,
        reply: Sender<bool>,
    },
    #[allow(dead_code)]
    StopRumble,
    Shutdown,
}

#[derive(Clone)]
pub struct LinuxGamepadBackend {
    shared: Arc<Mutex<Shared>>,
    logger: EventLogger,
    cmd: Sender<Cmd>,
    stop: Arc<AtomicBool>,
}

struct Shared {
    state: PadState,
    profile: AxisProfile,
    device_path: String,
    vendor_id: Option<u16>,
    product_id: Option<u16>,
}

impl LinuxGamepadBackend {
    pub fn new() -> Self {
        let (tx, rx) = mpsc::channel();
        let shared = Arc::new(Mutex::new(Shared {
            state: PadState::default(),
            profile: XINPUT_PROFILE,
            device_path: String::new(),
            vendor_id: None,
            product_id: None,
        }));
        let logger = EventLogger::new();
        let stop = Arc::new(AtomicBool::new(false));
        let backend = Self {
            shared: Arc::clone(&shared),
            logger: logger.clone(),
            cmd: tx,
            stop: Arc::clone(&stop),
        };
        thread::spawn(move || run_loop(shared, logger, rx, stop));
        backend
    }
}

impl SampleSource for LinuxGamepadBackend {
    fn is_connected(&self) -> bool {
        self.shared.lock().unwrap().state.connected
    }

    fn device_name(&self) -> String {
        self.shared.lock().unwrap().state.name.clone()
    }

    fn device_path(&self) -> String {
        self.shared.lock().unwrap().device_path.clone()
    }

    fn vendor_product(&self) -> (Option<u16>, Option<u16>) {
        let s = self.shared.lock().unwrap();
        (s.vendor_id, s.product_id)
    }

    fn axis_profile_name(&self) -> String {
        let s = self.shared.lock().unwrap();
        if s.state.connected {
            s.profile.label.to_string()
        } else {
            String::new()
        }
    }

    fn axis_profile(&self) -> AxisProfile {
        self.shared.lock().unwrap().profile
    }

    fn state(&self) -> PadState {
        self.shared.lock().unwrap().state.clone()
    }

    fn start_logging(&self, test_id: &str) {
        self.logger.start(test_id);
    }

    fn stop_logging(&self) {
        self.logger.stop();
    }

    fn logged_samples(&self) -> Vec<GamepadSample> {
        self.logger.get_samples()
    }

    fn event_timestamps(&self) -> Vec<u64> {
        self.logger
            .get_events()
            .into_iter()
            .map(|e| e.timestamp_ns)
            .collect()
    }

    fn start(&self) {}

    fn shutdown(&self) {
        self.stop.store(true, Ordering::SeqCst);
        let _ = self.cmd.send(Cmd::Shutdown);
    }

    fn rumble(&self, left: f64, right: f64, duration_ms: u32) -> bool {
        let (tx, rx) = mpsc::channel();
        if self
            .cmd
            .send(Cmd::Rumble {
                left,
                right,
                duration_ms,
                reply: tx,
            })
            .is_err()
        {
            return false;
        }
        rx.recv_timeout(Duration::from_secs(1)).unwrap_or(false)
    }

    fn stop_rumble(&self) {
        let _ = self.cmd.send(Cmd::StopRumble);
    }

    fn recent_events(&self, limit: usize) -> Vec<RawInputEvent> {
        self.logger.recent_events(limit)
    }
}

struct LoopState {
    device: Option<Device>,
    path: Option<PathBuf>,
    abs_map: HashMap<String, AbsoluteAxisType>,
    abs_range: HashMap<u16, (i32, i32)>,
    dpad_via_keys: bool,
    x360_dpad_keys: HashMap<u8, bool>,
    js_fd: Option<OwnedFd>,
    js_dpad: HashMap<u8, bool>,
    js_hat: (i32, i32),
    rumble_effect: Option<FFEffect>,
    rumble_until: Option<Instant>,
    supports_ff: bool,
}

fn run_loop(
    shared: Arc<Mutex<Shared>>,
    logger: EventLogger,
    rx: mpsc::Receiver<Cmd>,
    stop: Arc<AtomicBool>,
) {
    let mut st = LoopState {
        device: None,
        path: None,
        abs_map: HashMap::new(),
        abs_range: HashMap::new(),
        dpad_via_keys: false,
        x360_dpad_keys: HashMap::from([(11, false), (12, false), (13, false), (14, false)]),
        js_fd: None,
        js_dpad: HashMap::from([(11, false), (12, false), (13, false), (14, false)]),
        js_hat: (0, 0),
        rumble_effect: None,
        rumble_until: None,
        supports_ff: false,
    };
    let mut last_scan = Instant::now() - Duration::from_secs(2);
    while !stop.load(Ordering::SeqCst) {
        while let Ok(cmd) = rx.try_recv() {
            match cmd {
                Cmd::Shutdown => return,
                Cmd::StopRumble => stop_rumble_effect(&mut st),
                Cmd::Rumble {
                    left,
                    right,
                    duration_ms,
                    reply,
                } => {
                    let ok = upload_rumble(&mut st, left, right, duration_ms);
                    let _ = reply.send(ok);
                }
            }
        }
        if let Some(until) = st.rumble_until {
            if Instant::now() >= until {
                stop_rumble_effect(&mut st);
            }
        }
        if last_scan.elapsed() > Duration::from_secs(1) {
            scan_and_attach(&mut st, &shared);
            last_scan = Instant::now();
        }
        if st.device.is_none() {
            thread::sleep(Duration::from_millis(200));
            continue;
        }
        let logging = logger.is_active();
        refresh_live_state(&mut st, &shared);
        if logging {
            emit_sample(&shared, &logger);
        }
        let timeout = if logging { 20 } else { 50 };
        let Some(dev_raw) = st.device.as_ref().map(|d| d.as_raw_fd()) else {
            continue;
        };
        let js_raw = st.js_fd.as_ref().map(|fd| fd.as_raw_fd());
        let mut poll_fds = Vec::new();
        poll_fds.push(PollFd::new(
            unsafe { BorrowedFd::borrow_raw(dev_raw) },
            PollFlags::POLLIN,
        ));
        if let Some(js) = js_raw {
            poll_fds.push(PollFd::new(
                unsafe { BorrowedFd::borrow_raw(js) },
                PollFlags::POLLIN,
            ));
        }
        let poll_timeout = PollTimeout::try_from(timeout).unwrap_or(PollTimeout::NONE);
        match poll(&mut poll_fds, poll_timeout) {
            Ok(n) if n > 0 => {
                let dev_ready = poll_fds[0]
                    .revents()
                    .map(|r| r.contains(PollFlags::POLLIN))
                    .unwrap_or(false);
                let js_ready = poll_fds
                    .get(1)
                    .and_then(|p| p.revents())
                    .map(|r| r.contains(PollFlags::POLLIN))
                    .unwrap_or(false);
                if dev_ready {
                    if let Err(_) = read_evdev_events(&mut st, &shared, &logger) {
                        detach(&mut st, &shared, t("hint.disconnected"));
                        thread::sleep(Duration::from_millis(300));
                        continue;
                    }
                }
                if js_ready {
                    read_js_events(&mut st, &shared);
                }
            }
            Ok(_) => {}
            Err(_) => thread::sleep(Duration::from_millis(20)),
        }
    }
}

fn read_evdev_events(
    st: &mut LoopState,
    shared: &Arc<Mutex<Shared>>,
    logger: &EventLogger,
) -> std::io::Result<()> {
    let events: Vec<_> = {
        let Some(dev) = st.device.as_mut() else {
            return Ok(());
        };
        dev.fetch_events()?.collect::<Vec<_>>()
    };
    for event in events {
        match event.kind() {
            InputEventKind::Key(key) => {
                if let Some(idx) = evdev_button(key) {
                    let mut g = shared.lock().unwrap();
                    if g.profile == XBOX360_PROFILE && (11..=14).contains(&idx) {
                        st.x360_dpad_keys.insert(idx, event.value() != 0);
                        apply_x360_dpad(st, &mut g);
                    } else {
                        g.state.buttons.insert(idx, event.value() != 0);
                    }
                }
                logger.add_event(RawInputEvent {
                    timestamp_ns: monotonic_ns(),
                    event_type: "KEY".into(),
                    code: format!("{key:?}"),
                    value: event.value().to_string(),
                    test_id: String::new(),
                });
                emit_sample(shared, logger);
            }
            InputEventKind::AbsAxis(axis) => {
                {
                    let mut g = shared.lock().unwrap();
                    if axis == AbsoluteAxisType::ABS_HAT0X {
                        let hy = g.state.hat.1;
                        g.state.hat = (event.value(), hy);
                        if g.profile == XBOX360_PROFILE {
                            apply_x360_dpad(st, &mut g);
                        } else {
                            sync_dpad_from_hat(&mut g, event.value(), hy, st.dpad_via_keys);
                        }
                    } else if axis == AbsoluteAxisType::ABS_HAT0Y {
                        let hx = g.state.hat.0;
                        g.state.hat = (hx, event.value());
                        if g.profile == XBOX360_PROFILE {
                            apply_x360_dpad(st, &mut g);
                        } else {
                            sync_dpad_from_hat(&mut g, hx, event.value(), st.dpad_via_keys);
                        }
                    } else {
                        for (logical, code) in &st.abs_map {
                            if *code != axis {
                                continue;
                            }
                            let (mn, mx) =
                                axis_limits(&st.abs_range, axis, logical, event.value());
                            let value = if logical == "lt" || logical == "rt" {
                                normalize_trigger_axis(event.value(), mn, mx)
                            } else {
                                normalize_axis(event.value(), mn, mx)
                            };
                            if let Some(idx) = g.profile.axis_index(logical) {
                                g.state.axes.insert(idx, value);
                            }
                        }
                    }
                }
                logger.add_event(RawInputEvent {
                    timestamp_ns: monotonic_ns(),
                    event_type: "ABS".into(),
                    code: format!("{axis:?}"),
                    value: event.value().to_string(),
                    test_id: String::new(),
                });
                emit_sample(shared, logger);
            }
            _ => {}
        }
    }
    Ok(())
}

fn refresh_live_state(st: &mut LoopState, shared: &Arc<Mutex<Shared>>) {
    let (abs_vals, axis_codes) = {
        let Some(dev) = st.device.as_ref() else {
            return;
        };
        let Ok(abs_vals) = dev.get_abs_state() else {
            return;
        };
        let axis_codes: Vec<AbsoluteAxisType> = dev
            .supported_absolute_axes()
            .map(|set| set.iter().collect())
            .unwrap_or_default();
        (abs_vals, axis_codes)
    };
    for axis in &axis_codes {
        let info = &abs_vals[axis.0 as usize];
        if info.maximum > info.minimum {
            st.abs_range.insert(axis.0, (info.minimum, info.maximum));
        }
    }
    let mut updates = Vec::new();
    for (logical, code) in &st.abs_map {
        let info = &abs_vals[code.0 as usize];
        let (mn, mx) = axis_limits(&st.abs_range, *code, logical, info.value);
        let value = if logical == "lt" || logical == "rt" {
            normalize_trigger_axis(info.value, mn, mx)
        } else {
            normalize_axis(info.value, mn, mx)
        };
        updates.push((logical.clone(), value));
    }
    let hat_x = abs_vals
        .get(AbsoluteAxisType::ABS_HAT0X.0 as usize)
        .map(|i| i.value);
    let hat_y = abs_vals
        .get(AbsoluteAxisType::ABS_HAT0Y.0 as usize)
        .map(|i| i.value);
    let mut g = shared.lock().unwrap();
    if g.profile == XBOX360_PROFILE {
        apply_x360_dpad(st, &mut g);
    } else if !st.dpad_via_keys {
        if let (Some(hx), Some(hy)) = (hat_x, hat_y) {
            g.state.hat = (hx, hy);
            sync_dpad_from_hat(&mut g, hx, hy, st.dpad_via_keys);
        }
    }
    for (logical, value) in updates {
        if let Some(idx) = g.profile.axis_index(&logical) {
            g.state.axes.insert(idx, value);
        }
    }
    poll_share(st, &mut g);
}

fn poll_share(st: &LoopState, g: &mut Shared) {
    if g.profile == XBOX360_PROFILE {
        g.state.buttons.insert(15, false);
        return;
    }
    let mut pressed = false;
    if let Some(dev) = st.device.as_ref() {
        if let Some(keys) = dev.cached_state().key_vals() {
            pressed = keys.contains(Key::KEY_RECORD);
        }
    }
    g.state.buttons.insert(15, pressed);
}

fn apply_x360_dpad(st: &LoopState, g: &mut Shared) {
    let mut up = false;
    let mut down = false;
    let mut left = false;
    let mut right = false;
    let mut hx = 0;
    let mut hy = 0;
    if let Some(dev) = st.device.as_ref() {
        if let Some(keys) = dev.cached_state().key_vals() {
            up |= keys.contains(Key::BTN_DPAD_UP);
            down |= keys.contains(Key::BTN_DPAD_DOWN);
            left |= keys.contains(Key::BTN_DPAD_LEFT);
            right |= keys.contains(Key::BTN_DPAD_RIGHT);
            let happy1 = Key::BTN_TRIGGER_HAPPY1;
            if (0..4).any(|i| keys.contains(Key(happy1.0 + i))) {
                left |= keys.contains(happy1);
                right |= keys.contains(Key(happy1.0 + 1));
                up |= keys.contains(Key(happy1.0 + 2));
                down |= keys.contains(Key(happy1.0 + 3));
            }
        }
        if let Some(abs) = dev.cached_state().abs_vals() {
            if let Some(info) = abs.get(AbsoluteAxisType::ABS_HAT0X.0 as usize) {
                hx = info.value;
            }
            if let Some(info) = abs.get(AbsoluteAxisType::ABS_HAT0Y.0 as usize) {
                hy = info.value;
            }
        }
    }
    up |= *st.x360_dpad_keys.get(&11).unwrap_or(&false);
    down |= *st.x360_dpad_keys.get(&12).unwrap_or(&false);
    left |= *st.x360_dpad_keys.get(&13).unwrap_or(&false);
    right |= *st.x360_dpad_keys.get(&14).unwrap_or(&false);
    up |= *st.js_dpad.get(&11).unwrap_or(&false);
    down |= *st.js_dpad.get(&12).unwrap_or(&false);
    left |= *st.js_dpad.get(&13).unwrap_or(&false);
    right |= *st.js_dpad.get(&14).unwrap_or(&false);
    if st.js_hat.0 != 0 || st.js_hat.1 != 0 {
        hx = st.js_hat.0;
        hy = st.js_hat.1;
    }
    if hx != 0 || hy != 0 {
        up |= hy < 0;
        down |= hy > 0;
        left |= hx < 0;
        right |= hx > 0;
    }
    g.state.hat = (hx, hy);
    g.state.buttons.insert(11, up);
    g.state.buttons.insert(12, down);
    g.state.buttons.insert(13, left);
    g.state.buttons.insert(14, right);
}

fn sync_dpad_from_hat(g: &mut Shared, hx: i32, hy: i32, dpad_via_keys: bool) {
    if hx != 0 || hy != 0 {
        g.state.buttons.insert(11, hy < 0);
        g.state.buttons.insert(12, hy > 0);
        g.state.buttons.insert(13, hx < 0);
        g.state.buttons.insert(14, hx > 0);
    } else if !dpad_via_keys {
        for idx in 11..=14 {
            g.state.buttons.insert(idx, false);
        }
    }
}

fn emit_sample(shared: &Arc<Mutex<Shared>>, logger: &EventLogger) {
    let g = shared.lock().unwrap();
    logger.add_sample(GamepadSample {
        timestamp_ns: monotonic_ns(),
        axes: g.profile.read_map(&g.state.axes),
        buttons: g.state.buttons.clone(),
        hat: g.state.hat,
    });
}

fn scan_and_attach(st: &mut LoopState, shared: &Arc<Mutex<Shared>>) {
    if let Some(path) = &st.path {
        if path.exists() {
            return;
        }
        detach(st, shared, t("hint.disconnected"));
    }
    match find_best_gamepad() {
        None => {
            let mut g = shared.lock().unwrap();
            if !g.state.connected {
                g.state.hint = if can_access_gamepads() {
                    t("hint.connect")
                } else {
                    t("hint.no_access")
                };
            }
        }
        Some((path, dev)) => {
            if st.path.as_ref() == Some(&path) {
                return;
            }
            if let Err(exc) = attach(st, shared, path, dev) {
                detach(st, shared, t_vars("hint.open_failed", &[("error", exc)]));
            }
        }
    }
}

fn attach(
    st: &mut LoopState,
    shared: &Arc<Mutex<Shared>>,
    path: PathBuf,
    dev: Device,
) -> Result<(), String> {
    let name = dev.name().unwrap_or("Gamepad").to_string();
    let abses: Vec<AbsoluteAxisType> = dev
        .supported_absolute_axes()
        .map(|set| set.iter().collect())
        .unwrap_or_default();
    let profile = detect_axis_profile_from_name(&name, Some(abses.len()));
    let abs_range = load_abs_ranges(&dev);
    let abs_map = build_abs_code_map(&abses, &abs_range);
    let dpad_via_keys = dev
        .supported_keys()
        .map(|keys| keys.contains(Key::BTN_DPAD_UP))
        .unwrap_or(false);
    let supports_ff = dev.supported_ff().is_some();
    let input_id = dev.input_id();
    let abs_vals = dev.get_abs_state().ok();
    let mut initial_axes = HashMap::new();
    if let Some(ref abs_vals) = abs_vals {
        for (logical, code) in &abs_map {
            let info = &abs_vals[code.0 as usize];
            let (mn, mx) = axis_limits(&abs_range, *code, logical, info.value);
            let value = if logical == "lt" || logical == "rt" {
                normalize_trigger_axis(info.value, mn, mx)
            } else {
                normalize_axis(info.value, mn, mx)
            };
            if let Some(idx) = profile.axis_index(logical) {
                initial_axes.insert(idx, value);
            }
        }
    }
    let transport = match input_id.bus_type() {
        evdev::BusType::BUS_USB => "USB",
        evdev::BusType::BUS_BLUETOOTH => "Bluetooth",
        _ => {
            if format!("{:?}", input_id.bus_type()).contains("WIRELESS") {
                "Wireless"
            } else {
                ""
            }
        }
    }
    .to_string();
    close_js(st);
    if profile == XBOX360_PROFILE {
        st.js_fd = open_js_device(&path);
    }
    st.device = Some(dev);
    st.path = Some(path.clone());
    st.abs_map = abs_map;
    st.abs_range = abs_range;
    st.dpad_via_keys = dpad_via_keys;
    st.supports_ff = supports_ff;
    st.x360_dpad_keys = HashMap::from([(11, false), (12, false), (13, false), (14, false)]);
    st.js_dpad = HashMap::from([(11, false), (12, false), (13, false), (14, false)]);
    st.js_hat = (0, 0);
    {
        let mut g = shared.lock().unwrap();
        g.profile = profile;
        g.device_path = path.to_string_lossy().into_owned();
        g.vendor_id = Some(input_id.vendor());
        g.product_id = Some(input_id.product());
        g.state = PadState {
            connected: true,
            name,
            transport,
            axes: initial_axes,
            ..PadState::default()
        };
        if profile == XBOX360_PROFILE {
            apply_x360_dpad(st, &mut g);
        } else if !dpad_via_keys {
            if let Some(abs) = abs_vals.as_ref() {
                let hx = abs
                    .get(AbsoluteAxisType::ABS_HAT0X.0 as usize)
                    .map(|i| i.value)
                    .unwrap_or(0);
                let hy = abs
                    .get(AbsoluteAxisType::ABS_HAT0Y.0 as usize)
                    .map(|i| i.value)
                    .unwrap_or(0);
                g.state.hat = (hx, hy);
                sync_dpad_from_hat(&mut g, hx, hy, dpad_via_keys);
            }
        }
    }
    if st.js_fd.is_some() {
        read_js_events(st, shared);
    }
    Ok(())
}

fn detach(st: &mut LoopState, shared: &Arc<Mutex<Shared>>, hint: String) {
    stop_rumble_effect(st);
    close_js(st);
    st.device = None;
    st.path = None;
    st.abs_map.clear();
    st.abs_range.clear();
    st.supports_ff = false;
    st.dpad_via_keys = false;
    st.x360_dpad_keys = HashMap::from([(11, false), (12, false), (13, false), (14, false)]);
    st.js_dpad = HashMap::from([(11, false), (12, false), (13, false), (14, false)]);
    st.js_hat = (0, 0);
    let mut g = shared.lock().unwrap();
    g.profile = XINPUT_PROFILE;
    g.device_path.clear();
    g.vendor_id = None;
    g.product_id = None;
    g.state = PadState {
        hint,
        ..PadState::default()
    };
}

fn close_js(st: &mut LoopState) {
    st.js_fd = None;
}

fn open_js_device(event_path: &Path) -> Option<OwnedFd> {
    let path = find_js_device_path(event_path)?;
    let fd = nix::fcntl::open(
        path.as_path(),
        nix::fcntl::OFlag::O_RDONLY | nix::fcntl::OFlag::O_NONBLOCK,
        nix::sys::stat::Mode::empty(),
    )
    .ok()?;
    Some(unsafe { OwnedFd::from_raw_fd(fd) })
}

fn find_js_device_path(event_path: &Path) -> Option<PathBuf> {
    let event_name = event_path.file_name()?.to_string_lossy().into_owned();
    let by_id = Path::new("/dev/input/by-id");
    if by_id.is_dir() {
        if let Ok(entries) = fs::read_dir(by_id) {
            for entry in entries.flatten() {
                let name = entry.file_name().to_string_lossy().into_owned();
                if !name.ends_with("event-joystick") {
                    continue;
                }
                if entry.path().canonicalize().ok()?.file_name()?.to_string_lossy() != event_name {
                    continue;
                }
                let js_name = name.replace("event-joystick", "joystick");
                let js_link = by_id.join(js_name);
                if js_link.exists() {
                    return js_link.canonicalize().ok();
                }
            }
        }
    }
    if let Ok(text) = fs::read_to_string("/proc/bus/input/devices") {
        for block in text.split("\n\n") {
            if !block.contains(&event_name) {
                continue;
            }
            for line in block.lines() {
                if let Some(rest) = line.strip_prefix("H: Handlers=") {
                    for token in rest.split_whitespace() {
                        if token.starts_with("js") {
                            let path = PathBuf::from(format!("/dev/input/{token}"));
                            if path.exists() {
                                return Some(path);
                            }
                        }
                    }
                }
            }
        }
    }
    let js0 = PathBuf::from("/dev/input/js0");
    if js0.exists() {
        Some(js0)
    } else {
        None
    }
}

fn read_js_events(st: &mut LoopState, shared: &Arc<Mutex<Shared>>) {
    let Some(fd) = st.js_fd.as_ref() else {
        return;
    };
    loop {
        let mut buf = [0u8; JS_EVENT_SIZE];
        match nix::unistd::read(fd.as_raw_fd(), &mut buf) {
            Ok(n) if n >= JS_EVENT_SIZE => {
                let value = i16::from_le_bytes([buf[4], buf[5]]);
                let ev_type = buf[6] & !JS_EVENT_INIT;
                let number = buf[7];
                let mut g = shared.lock().unwrap();
                if ev_type == JS_EVENT_BUTTON && (11..=14).contains(&number) {
                    st.js_dpad.insert(number, value != 0);
                    apply_x360_dpad(st, &mut g);
                } else if ev_type == JS_EVENT_AXIS && number == JS_HAT_X_AXIS {
                    st.js_hat.0 = hat_from_js_axis(value);
                    apply_x360_dpad(st, &mut g);
                } else if ev_type == JS_EVENT_AXIS && number == JS_HAT_Y_AXIS {
                    st.js_hat.1 = hat_from_js_axis(value);
                    apply_x360_dpad(st, &mut g);
                }
            }
            Ok(_) => return,
            Err(nix::errno::Errno::EAGAIN) => return,
            Err(_) => {
                st.js_fd = None;
                return;
            }
        }
    }
}

fn hat_from_js_axis(value: i16) -> i32 {
    if value <= -JS_HAT_THRESHOLD {
        -1
    } else if value >= JS_HAT_THRESHOLD {
        1
    } else {
        0
    }
}

fn upload_rumble(st: &mut LoopState, left: f64, right: f64, duration_ms: u32) -> bool {
    stop_rumble_effect(st);
    if !st.supports_ff {
        return false;
    }
    let strong = (left.clamp(0.0, 1.0) * 65535.0) as u16;
    let weak = (right.clamp(0.0, 1.0) * 65535.0) as u16;
    let data = FFEffectData {
        direction: 0,
        trigger: FFTrigger {
            button: 0,
            interval: 0,
        },
        replay: FFReplay {
            length: duration_ms.max(100) as u16,
            delay: 0,
        },
        kind: FFEffectKind::Rumble {
            strong_magnitude: strong,
            weak_magnitude: weak,
        },
    };
    let uploaded = st
        .device
        .as_mut()
        .map(|dev| dev.upload_ff_effect(data));
    match uploaded {
        Some(Ok(mut effect)) => {
            if effect.play(1).is_err() {
                return false;
            }
            st.rumble_effect = Some(effect);
            st.rumble_until = Some(Instant::now() + Duration::from_millis(u64::from(duration_ms)));
            true
        }
        _ => false,
    }
}

fn stop_rumble_effect(st: &mut LoopState) {
    st.rumble_until = None;
    if let Some(mut effect) = st.rumble_effect.take() {
        let _ = effect.stop();
    }
}

fn find_best_gamepad() -> Option<(PathBuf, Device)> {
    let mut best_score = -1;
    let mut best: Option<(PathBuf, Device)> = None;
    let mut candidates: Vec<PathBuf> = evdev::enumerate().map(|(p, _)| p).collect();
    let by_id = Path::new("/dev/input/by-id");
    if by_id.is_dir() {
        if let Ok(entries) = fs::read_dir(by_id) {
            for entry in entries.flatten() {
                let name = entry.file_name().to_string_lossy().into_owned();
                if name.ends_with("event-joystick") {
                    if let Ok(path) = entry.path().canonicalize() {
                        if !candidates.contains(&path) {
                            candidates.push(path);
                        }
                    }
                }
            }
        }
    }
    for path in candidates {
        let Ok(dev) = Device::open(&path) else {
            continue;
        };
        let score = score_gamepad(&dev);
        if score > best_score {
            best_score = score;
            best = Some((path, dev));
        }
    }
    if best_score >= 0 {
        best
    } else {
        None
    }
}

fn score_gamepad(dev: &Device) -> i32 {
    let Some(keys) = dev.supported_keys() else {
        return -1;
    };
    if !keys.contains(Key::BTN_SOUTH) {
        return -1;
    }
    let abs_len = dev
        .supported_absolute_axes()
        .map(|s| s.iter().count())
        .unwrap_or(0) as i32;
    let key_len = keys.iter().count() as i32;
    let mut score = abs_len + key_len;
    let name = dev.name().unwrap_or("").to_lowercase();
    if name.contains("xbox") || name.contains("x-box") || name.contains("microsoft") {
        score += 200;
    }
    if name.contains("series") {
        score += 50;
    }
    if dev.input_id().vendor() == MS_VENDOR_ID {
        score += 100;
    }
    if let Some(abs) = dev.supported_absolute_axes() {
        if abs.contains(AbsoluteAxisType::ABS_X) && abs.contains(AbsoluteAxisType::ABS_RX) {
            score += 40;
        }
    }
    if name.contains("mouse") || name.contains("keyboard") || name.contains("consumer control") {
        score -= 500;
    }
    if name.contains("headset") || name.contains("audio") {
        score -= 300;
    }
    score
}

fn can_access_gamepads() -> bool {
    if nix::unistd::geteuid().is_root() {
        return true;
    }
    if let Ok(Some(group)) = nix::unistd::Group::from_name("input") {
        if let Ok(groups) = nix::unistd::getgroups() {
            if groups.contains(&group.gid) {
                return true;
            }
        }
    }
    find_best_gamepad().is_some()
}

fn load_abs_ranges(dev: &Device) -> HashMap<u16, (i32, i32)> {
    let mut map = HashMap::new();
    let Ok(vals) = dev.get_abs_state() else {
        return map;
    };
    let Some(supported) = dev.supported_absolute_axes() else {
        return map;
    };
    for axis in supported.iter() {
        let info = &vals[axis.0 as usize];
        if info.maximum > info.minimum {
            map.insert(axis.0, (info.minimum, info.maximum));
        }
    }
    map
}

fn axis_usable(ranges: &HashMap<u16, (i32, i32)>, code: AbsoluteAxisType) -> bool {
    ranges
        .get(&code.0)
        .map(|(mn, mx)| mx > mn)
        .unwrap_or(false)
}

fn pick_axis(
    abses: &[AbsoluteAxisType],
    ranges: &HashMap<u16, (i32, i32)>,
    candidates: &[AbsoluteAxisType],
    skip: Option<AbsoluteAxisType>,
) -> AbsoluteAxisType {
    for code in candidates {
        if skip == Some(*code) {
            continue;
        }
        if abses.contains(code) && axis_usable(ranges, *code) {
            return *code;
        }
    }
    candidates
        .iter()
        .copied()
        .find(|code| skip != Some(*code) && abses.contains(code))
        .unwrap_or(candidates[0])
}

fn build_abs_code_map(
    abses: &[AbsoluteAxisType],
    ranges: &HashMap<u16, (i32, i32)>,
) -> HashMap<String, AbsoluteAxisType> {
    let (lt, rt) = if axis_usable(ranges, AbsoluteAxisType::ABS_Z)
        && axis_usable(ranges, AbsoluteAxisType::ABS_RZ)
    {
        (AbsoluteAxisType::ABS_Z, AbsoluteAxisType::ABS_RZ)
    } else if axis_usable(ranges, AbsoluteAxisType::ABS_GAS)
        && axis_usable(ranges, AbsoluteAxisType::ABS_BRAKE)
    {
        (AbsoluteAxisType::ABS_GAS, AbsoluteAxisType::ABS_BRAKE)
    } else {
        let lt = pick_axis(
            abses,
            ranges,
            &[
                AbsoluteAxisType::ABS_Z,
                AbsoluteAxisType::ABS_BRAKE,
                AbsoluteAxisType::ABS_GAS,
            ],
            None,
        );
        let rt = pick_axis(
            abses,
            ranges,
            &[
                AbsoluteAxisType::ABS_RZ,
                AbsoluteAxisType::ABS_GAS,
                AbsoluteAxisType::ABS_BRAKE,
            ],
            Some(lt),
        );
        (lt, rt)
    };
    HashMap::from([
        ("left_x".into(), AbsoluteAxisType::ABS_X),
        ("left_y".into(), AbsoluteAxisType::ABS_Y),
        ("right_x".into(), AbsoluteAxisType::ABS_RX),
        ("right_y".into(), AbsoluteAxisType::ABS_RY),
        ("lt".into(), lt),
        ("rt".into(), rt),
    ])
}

fn axis_limits(
    ranges: &HashMap<u16, (i32, i32)>,
    axis: AbsoluteAxisType,
    logical: &str,
    value: i32,
) -> (i32, i32) {
    if let Some(&(min, max)) = ranges.get(&axis.0) {
        if max > min {
            return (min, max);
        }
    }
    fallback_limits(logical, value)
}

fn fallback_limits(logical: &str, value: i32) -> (i32, i32) {
    if logical == "lt" || logical == "rt" {
        if value < 0 {
            (-32768, 32767)
        } else {
            let max = if value > 255 { value.max(1023) } else { 255 };
            (0, max)
        }
    } else {
        (-32768, 32767)
    }
}

fn evdev_button(key: Key) -> Option<u8> {
    match key {
        Key::BTN_SOUTH => Some(0),
        Key::BTN_EAST => Some(1),
        Key::BTN_NORTH => Some(2),
        Key::BTN_WEST => Some(3),
        Key::BTN_TL => Some(4),
        Key::BTN_TR => Some(5),
        Key::BTN_SELECT => Some(6),
        Key::BTN_START => Some(7),
        Key::BTN_MODE => Some(8),
        Key::BTN_THUMBL => Some(9),
        Key::BTN_THUMBR => Some(10),
        Key::BTN_DPAD_UP => Some(11),
        Key::BTN_DPAD_DOWN => Some(12),
        Key::BTN_DPAD_LEFT => Some(13),
        Key::BTN_DPAD_RIGHT => Some(14),
        Key::KEY_RECORD => Some(15),
        _ => None,
    }
}

fn normalize_axis(value: i32, min: i32, max: i32) -> f64 {
    if max <= min {
        return 0.0;
    }
    let mid = (f64::from(max) + f64::from(min)) / 2.0;
    let half = (f64::from(max) - f64::from(min)) / 2.0;
    if half == 0.0 {
        0.0
    } else {
        ((f64::from(value) - mid) / half).clamp(-1.0, 1.0)
    }
}

fn normalize_trigger_axis(value: i32, min: i32, max: i32) -> f64 {
    if max <= min {
        return 0.0;
    }
    if min < 0 {
        normalize_axis(value, min, max)
    } else {
        ((f64::from(value) - f64::from(min)) / (f64::from(max) - f64::from(min))).clamp(0.0, 1.0)
    }
}

fn monotonic_ns() -> u64 {
    let ts = nix::time::clock_gettime(nix::time::ClockId::CLOCK_MONOTONIC).ok();
    ts.map(|t| t.tv_sec() as u64 * 1_000_000_000 + t.tv_nsec() as u64)
        .unwrap_or(0)
}

use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, Sender};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use gilrs::{Axis, Button, Event, EventType, GamepadId, Gilrs};

use crate::i18n::t;
use crate::logger::EventLogger;
use crate::pad::{detect_axis_profile_from_name, AxisProfile, PadState, XINPUT_PROFILE};
use crate::sample::{GamepadSample, RawInputEvent};
use crate::session::SampleSource;

enum Cmd {
    Rumble {
        left: f64,
        right: f64,
        duration_ms: u32,
        reply: Sender<bool>,
    },
    StopRumble,
    Shutdown,
}

#[derive(Clone)]
pub struct GilrsGamepadBackend {
    shared: Arc<Mutex<Shared>>,
    logger: EventLogger,
    cmd: Sender<Cmd>,
    stop: Arc<AtomicBool>,
}

struct Shared {
    state: PadState,
    profile: AxisProfile,
    vendor_id: Option<u16>,
    product_id: Option<u16>,
}

impl GilrsGamepadBackend {
    pub fn new() -> Self {
        let (tx, rx) = mpsc::channel();
        let shared = Arc::new(Mutex::new(Shared {
            state: PadState {
                hint: t("hint.connect"),
                ..PadState::default()
            },
            profile: XINPUT_PROFILE,
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

impl SampleSource for GilrsGamepadBackend {
    fn is_connected(&self) -> bool {
        self.shared.lock().unwrap().state.connected
    }
    fn device_name(&self) -> String {
        self.shared.lock().unwrap().state.name.clone()
    }
    fn device_path(&self) -> String {
        "gilrs".into()
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

fn run_loop(
    shared: Arc<Mutex<Shared>>,
    logger: EventLogger,
    rx: mpsc::Receiver<Cmd>,
    stop: Arc<AtomicBool>,
) {
    let Ok(mut gilrs) = Gilrs::new() else {
        return;
    };
    let mut active: Option<GamepadId> = None;
    let mut rumble_until: Option<Instant> = None;
    let mut ff_effect: Option<gilrs::ff::Effect> = None;
    pick_gamepad(&mut gilrs, &mut active, &shared);
    while !stop.load(Ordering::SeqCst) {
        while let Ok(cmd) = rx.try_recv() {
            match cmd {
                Cmd::Shutdown => return,
                Cmd::StopRumble => {
                    rumble_until = None;
                    if let Some(effect) = ff_effect.take() {
                        let _ = effect.stop();
                    }
                }
                Cmd::Rumble {
                    left,
                    right,
                    duration_ms,
                    reply,
                } => {
                    let ok = start_rumble(
                        &mut gilrs,
                        active,
                        left,
                        right,
                        duration_ms,
                        &mut ff_effect,
                        &mut rumble_until,
                    );
                    let _ = reply.send(ok);
                }
            }
        }
        if let Some(until) = rumble_until {
            if Instant::now() >= until {
                rumble_until = None;
                if let Some(effect) = ff_effect.take() {
                    let _ = effect.stop();
                }
            }
        }
        while let Some(Event { id, event, .. }) = gilrs.next_event() {
            match event {
                EventType::Connected => {
                    if active.is_none() {
                        pick_gamepad(&mut gilrs, &mut active, &shared);
                    }
                }
                EventType::Disconnected => {
                    if active == Some(id) {
                        detach(&shared);
                        active = None;
                        pick_gamepad(&mut gilrs, &mut active, &shared);
                    }
                }
                EventType::ButtonPressed(btn, _) | EventType::ButtonReleased(btn, _) => {
                    if active != Some(id) {
                        continue;
                    }
                    let pressed = matches!(event, EventType::ButtonPressed(_, _));
                    if let Some(idx) = map_button(btn) {
                        {
                            let mut g = shared.lock().unwrap();
                            g.state.buttons.insert(idx, pressed);
                        }
                        logger.add_event(RawInputEvent {
                            timestamp_ns: monotonic_ns(),
                            event_type: "BUTTON".into(),
                            code: idx.to_string(),
                            value: i32::from(pressed).to_string(),
                            test_id: String::new(),
                        });
                        emit_sample(&shared, &logger);
                    }
                }
                EventType::AxisChanged(axis, value, _) => {
                    if active != Some(id) {
                        continue;
                    }
                    apply_axis(&shared, axis, value as f64);
                    logger.add_event(RawInputEvent {
                        timestamp_ns: monotonic_ns(),
                        event_type: "AXIS".into(),
                        code: format!("{axis:?}"),
                        value: value.to_string(),
                        test_id: String::new(),
                    });
                    emit_sample(&shared, &logger);
                }
                _ => {}
            }
        }
        if let Some(id) = active {
            if gilrs.gamepad(id).is_connected() {
                sync_axes(&gilrs, id, &shared);
                if logger.is_active() {
                    emit_sample(&shared, &logger);
                }
            } else {
                detach(&shared);
                active = None;
            }
        } else {
            pick_gamepad(&mut gilrs, &mut active, &shared);
        }
        thread::sleep(Duration::from_millis(8));
    }
}

fn pick_gamepad(gilrs: &mut Gilrs, active: &mut Option<GamepadId>, shared: &Arc<Mutex<Shared>>) {
    if active.is_some() {
        return;
    }
    let mut best: Option<(i32, GamepadId)> = None;
    for (id, gp) in gilrs.gamepads() {
        if !gp.is_connected() {
            continue;
        }
        let name = gp.name().to_lowercase();
        let mut score = 0;
        if name.contains("xbox") || name.contains("microsoft") || name.contains("x-box") {
            score += 100;
        }
        if best.map(|(s, _)| s).unwrap_or(-1) < score {
            best = Some((score, id));
        }
    }
    let Some((_, id)) = best else {
        return;
    };
    let gp = gilrs.gamepad(id);
    let name = gp.name().to_string();
    let profile = detect_axis_profile_from_name(&name, None);
    let mut g = shared.lock().unwrap();
    g.profile = profile;
    g.vendor_id = None;
    g.product_id = None;
    g.state = PadState {
        connected: true,
        name,
        ..PadState::default()
    };
    *active = Some(id);
}

fn detach(shared: &Arc<Mutex<Shared>>) {
    let mut g = shared.lock().unwrap();
    g.profile = XINPUT_PROFILE;
    g.vendor_id = None;
    g.product_id = None;
    g.state = PadState {
        hint: t("hint.disconnected"),
        ..PadState::default()
    };
}

fn map_button(btn: Button) -> Option<u8> {
    Some(match btn {
        Button::South => 0,
        Button::East => 1,
        Button::West => 2,
        Button::North => 3,
        Button::LeftTrigger => 4,
        Button::RightTrigger => 5,
        Button::Select => 6,
        Button::Start => 7,
        Button::Mode => 8,
        Button::LeftThumb => 9,
        Button::RightThumb => 10,
        Button::DPadUp => 11,
        Button::DPadDown => 12,
        Button::DPadLeft => 13,
        Button::DPadRight => 14,
        Button::C => 15,
        _ => return None,
    })
}

fn apply_axis(shared: &Arc<Mutex<Shared>>, axis: Axis, value: f64) {
    let mut g = shared.lock().unwrap();
    let logical = match axis {
        Axis::LeftStickX => "left_x",
        Axis::LeftStickY => "left_y",
        Axis::RightStickX => "right_x",
        Axis::RightStickY => "right_y",
        Axis::LeftZ => "lt",
        Axis::RightZ => "rt",
        Axis::DPadX => {
            g.state.buttons.insert(13, value < -0.5);
            g.state.buttons.insert(14, value > 0.5);
            return;
        }
        Axis::DPadY => {
            g.state.buttons.insert(11, value < -0.5);
            g.state.buttons.insert(12, value > 0.5);
            return;
        }
        _ => return,
    };
    if let Some(idx) = g.profile.axis_index(logical) {
        g.state.axes.insert(idx, value as f64);
    }
}

fn sync_axes(gilrs: &Gilrs, id: GamepadId, shared: &Arc<Mutex<Shared>>) {
    let gp = gilrs.gamepad(id);
    let mut g = shared.lock().unwrap();
    let pairs = [
        (Axis::LeftStickX, "left_x"),
        (Axis::LeftStickY, "left_y"),
        (Axis::RightStickX, "right_x"),
        (Axis::RightStickY, "right_y"),
        (Axis::LeftZ, "lt"),
        (Axis::RightZ, "rt"),
    ];
    for (axis, logical) in pairs {
        if let Some(idx) = g.profile.axis_index(logical) {
            g.state.axes.insert(idx, f64::from(gp.value(axis)));
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

fn start_rumble(
    gilrs: &mut Gilrs,
    active: Option<GamepadId>,
    left: f64,
    right: f64,
    duration_ms: u32,
    ff_effect: &mut Option<gilrs::ff::Effect>,
    rumble_until: &mut Option<Instant>,
) -> bool {
    let Some(id) = active else {
        return false;
    };
    use gilrs::ff::{BaseEffect, BaseEffectType, EffectBuilder, Repeat, Ticks};
    if let Some(effect) = ff_effect.take() {
        let _ = effect.stop();
    }
    let duration = Ticks::from_ms(duration_ms.max(1));
    let built = EffectBuilder::new()
        .add_effect(BaseEffect {
            kind: BaseEffectType::Strong {
                magnitude: (left.clamp(0.0, 1.0) * f64::from(u16::MAX)) as u16,
            },
            ..Default::default()
        })
        .add_effect(BaseEffect {
            kind: BaseEffectType::Weak {
                magnitude: (right.clamp(0.0, 1.0) * f64::from(u16::MAX)) as u16,
            },
            ..Default::default()
        })
        .repeat(Repeat::For(duration))
        .gamepads(&[id])
        .finish(gilrs);
    match built {
        Ok(effect) => {
            let _ = effect.play();
            *ff_effect = Some(effect);
            *rumble_until = Some(Instant::now() + Duration::from_millis(u64::from(duration_ms)));
            true
        }
        Err(_) => false,
    }
}

fn monotonic_ns() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos() as u64)
        .unwrap_or(0)
}

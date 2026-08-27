use std::collections::HashSet;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use serde::Serialize;

use crate::button::{buttons_for_device, check_button, summarize, PRESS_TIMEOUT, STICKY_LIMIT};
use crate::config::DiagnosticConfig;
use crate::i18n::{t, t_vars};
use crate::pad::{normalize_trigger, AxisProfile, PadState};
use crate::report::{DiagnosticReport, EventRateResult, StickTestResult};
use crate::sample::GamepadSample;
use crate::stats::analyze_event_rate;
use crate::status::TestStatus;
use crate::stick::StickDiagnostic;
use crate::trigger::TriggerDiagnostic;

pub const ANALOG_ACTIVE: f64 = 0.38;
pub const ANALOG_REST: f64 = 0.22;
pub const ANALOG_HOLD: f64 = 0.85;
pub const TRIGGER_ACTIVE: f64 = 0.12;
pub const TRIGGER_REST: f64 = 0.06;
pub const TRIGGER_HOLD: f64 = 0.85;
pub const CIRCLE_RIM: f64 = 0.55;

pub trait SampleSource: Send + Sync {
    fn is_connected(&self) -> bool;
    fn device_name(&self) -> String;
    fn device_path(&self) -> String;
    fn vendor_product(&self) -> (Option<u16>, Option<u16>);
    fn axis_profile_name(&self) -> String;
    fn axis_profile(&self) -> AxisProfile;
    fn state(&self) -> PadState;
    fn start_logging(&self, test_id: &str);
    fn stop_logging(&self);
    fn logged_samples(&self) -> Vec<GamepadSample>;
    fn event_timestamps(&self) -> Vec<u64>;
    fn start(&self);
    fn shutdown(&self);
    fn rumble(&self, left: f64, right: f64, duration_ms: u32) -> bool;
    #[allow(dead_code)]
    fn stop_rumble(&self);
    fn recent_events(&self, limit: usize) -> Vec<crate::sample::RawInputEvent>;
}

#[derive(Clone, Copy)]
struct ActionCheck {
    pressed: bool,
    held: bool,
    skipped: bool,
    sticky: bool,
    sensitive: bool,
    stopped: bool,
    taps: u32,
}

#[derive(Clone, Debug, Serialize)]
pub struct HoldTimer {
    pub remaining: f64,
    pub total: f64,
}

#[derive(Clone, Debug, Serialize)]
pub struct StickCue {
    pub side: String,
    pub motion: String,
    pub repeats: i32,
}

#[derive(Clone, Debug, Serialize)]
pub struct DiagnosticsStatus {
    pub running: bool,
    pub progress: f64,
    pub step: String,
    pub focus: String,
    pub phase: String,
    pub step_index: i32,
    pub step_total: i32,
    pub can_skip: bool,
    pub selected: Vec<String>,
    pub failed_buttons: Vec<u8>,
    pub passed_buttons: Vec<u8>,
    pub hold: Option<HoldTimer>,
    pub cue: StickCue,
    pub hold_seconds: i32,
    pub tests: std::collections::HashMap<String, TestStatus>,
    pub overall: TestStatus,
    pub score: i32,
    pub category_done: i32,
    pub category_total: i32,
}

struct Live {
    progress: f64,
    step: String,
    focus: String,
    hold_total: f64,
    hold_ends_at: Option<Instant>,
    hold_paused: bool,
    hold_frozen: f64,
    can_skip: bool,
    failed_buttons: HashSet<u8>,
    phase: String,
    step_index: i32,
    step_total: i32,
    selected: Vec<String>,
    cue_side: String,
    cue_motion: String,
    cue_repeats: i32,
    report: DiagnosticReport,
}

impl Live {
    fn new(config: &DiagnosticConfig) -> Self {
        Self {
            progress: 0.0,
            step: String::new(),
            focus: String::new(),
            hold_total: 0.0,
            hold_ends_at: None,
            hold_paused: false,
            hold_frozen: 0.0,
            can_skip: false,
            failed_buttons: HashSet::new(),
            phase: String::new(),
            step_index: 0,
            step_total: 1,
            selected: Vec::new(),
            cue_side: String::new(),
            cue_motion: String::new(),
            cue_repeats: 0,
            report: DiagnosticReport::new(&config.locale, t("report.disclaimer"), Default::default()),
        }
    }
}

pub struct DiagnosticSession {
    config: DiagnosticConfig,
    source: Arc<dyn SampleSource>,
    stop: Arc<AtomicBool>,
    skip: Arc<AtomicBool>,
    running: Arc<AtomicBool>,
    live: Arc<Mutex<Live>>,
}

impl DiagnosticSession {
    pub fn new(config: DiagnosticConfig, source: Arc<dyn SampleSource>) -> Self {
        Self {
            live: Arc::new(Mutex::new(Live::new(&config))),
            config,
            source,
            stop: Arc::new(AtomicBool::new(false)),
            skip: Arc::new(AtomicBool::new(false)),
            running: Arc::new(AtomicBool::new(false)),
        }
    }

    pub fn start(&self, tests: Option<Vec<String>>) {
        if self.running.load(Ordering::SeqCst) {
            return;
        }
        let selected = tests.unwrap_or_else(|| vec!["sticks".into(), "triggers".into(), "buttons".into()]);
        self.stop.store(false, Ordering::SeqCst);
        self.skip.store(false, Ordering::SeqCst);
        self.running.store(true, Ordering::SeqCst);
        {
            let mut live = self.live.lock().unwrap();
            live.focus.clear();
            live.progress = 0.0;
            live.step.clear();
            live.hold_total = 0.0;
            live.hold_ends_at = None;
            live.hold_paused = false;
            live.hold_frozen = 0.0;
            live.can_skip = false;
            live.failed_buttons.clear();
            live.phase.clear();
            live.step_index = 0;
            live.step_total = 1;
            live.selected = selected.clone();
            live.cue_side.clear();
            live.cue_motion.clear();
            live.cue_repeats = 0;
            live.report = DiagnosticReport::new(
                &self.config.locale,
                t("report.disclaimer"),
                std::collections::HashMap::from([
                    ("stick_drift_warn".into(), self.config.stick_drift_warn),
                    ("stick_drift_fail".into(), self.config.stick_drift_fail),
                    ("trigger_min".into(), self.config.trigger_min),
                    ("trigger_max".into(), self.config.trigger_max),
                ]),
            );
        }
        let runner = SessionRunner {
            config: self.config.clone(),
            source: Arc::clone(&self.source),
            stick: StickDiagnostic::new(self.config.clone()),
            trigger: TriggerDiagnostic::new(self.config.clone()),
            stop: Arc::clone(&self.stop),
            skip: Arc::clone(&self.skip),
            running: Arc::clone(&self.running),
            live: Arc::clone(&self.live),
        };
        thread::spawn(move || runner.run(selected));
    }

    pub fn stop(&self) {
        self.stop.store(true, Ordering::SeqCst);
        self.skip.store(true, Ordering::SeqCst);
    }

    pub fn skip(&self) {
        if self.can_skip() {
            self.skip.store(true, Ordering::SeqCst);
        }
    }

    pub fn can_skip(&self) -> bool {
        self.live.lock().unwrap().can_skip && self.running.load(Ordering::SeqCst)
    }

    #[allow(dead_code)]
    pub fn is_running(&self) -> bool {
        self.running.load(Ordering::SeqCst)
    }

    pub fn get_results(&self) -> DiagnosticReport {
        self.live.lock().unwrap().report.clone()
    }

    pub fn status(&self) -> DiagnosticsStatus {
        let live = self.live.lock().unwrap();
        let hold = if live.hold_paused {
            Some(HoldTimer {
                remaining: live.hold_frozen.max(0.0),
                total: live.hold_total,
            })
        } else if let Some(ends) = live.hold_ends_at {
            Some(HoldTimer {
                remaining: ends.saturating_duration_since(Instant::now()).as_secs_f64(),
                total: live.hold_total,
            })
        } else {
            None
        };
        let (done, total) = category_progress(&live);
        let passed: Vec<u8> = live
            .report
            .buttons
            .buttons
            .iter()
            .filter(|item| item.pressed && !item.skipped && item.sensitive && !item.sticky)
            .map(|item| item.index)
            .collect();
        let mut failed: Vec<u8> = live.failed_buttons.iter().copied().collect();
        failed.sort_unstable();
        DiagnosticsStatus {
            running: self.running.load(Ordering::SeqCst),
            progress: live.progress,
            step: live.step.clone(),
            focus: live.focus.clone(),
            phase: live.phase.clone(),
            step_index: live.step_index,
            step_total: live.step_total.max(1),
            can_skip: live.can_skip && self.running.load(Ordering::SeqCst),
            selected: live.selected.clone(),
            failed_buttons: failed,
            passed_buttons: passed,
            hold,
            cue: StickCue {
                side: live.cue_side.clone(),
                motion: live.cue_motion.clone(),
                repeats: live.cue_repeats,
            },
            hold_seconds: self.config.hold_seconds(),
            tests: live.report.tests.clone(),
            overall: live.report.overall,
            score: live.report.score,
            category_done: done,
            category_total: total,
        }
    }
}

fn category_progress(live: &Live) -> (i32, i32) {
    let runnable = ["sticks", "triggers", "buttons"];
    let mut selected: Vec<String> = live
        .selected
        .iter()
        .filter(|name| runnable.contains(&name.as_str()))
        .cloned()
        .collect();
    if selected.is_empty() {
        selected = runnable.iter().map(|s| (*s).to_string()).collect();
    }
    let done = selected
        .iter()
        .filter(|name| {
            !matches!(
                live.report.tests.get(*name).copied().unwrap_or(TestStatus::NotTested),
                TestStatus::NotTested | TestStatus::NotSupported
            )
        })
        .count() as i32;
    (done, selected.len() as i32)
}

struct SessionRunner {
    config: DiagnosticConfig,
    source: Arc<dyn SampleSource>,
    stick: StickDiagnostic,
    trigger: TriggerDiagnostic,
    stop: Arc<AtomicBool>,
    skip: Arc<AtomicBool>,
    running: Arc<AtomicBool>,
    live: Arc<Mutex<Live>>,
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum WaitKind {
    Ok,
    Sticky,
    Miss,
    Skip,
    Stop,
}

impl SessionRunner {
    fn aborting(&self) -> bool {
        self.stop.load(Ordering::SeqCst) || self.skip.load(Ordering::SeqCst)
    }

    fn consume_skip(&self) -> bool {
        if self.skip.load(Ordering::SeqCst) && !self.stop.load(Ordering::SeqCst) {
            self.skip.store(false, Ordering::SeqCst);
            true
        } else {
            false
        }
    }

    fn hold_seconds(&self) -> i32 {
        self.config.hold_seconds()
    }

    fn enabled_checks(&self) -> (bool, bool, bool) {
        let sticky = self.config.test_stickiness;
        let hold = self.config.test_hold;
        let sens = self.config.test_sensitivity;
        if !(sticky || hold || sens) {
            (true, true, true)
        } else {
            (sticky, hold, sens)
        }
    }

    fn set_can_skip(&self, enabled: bool) {
        self.live.lock().unwrap().can_skip = enabled;
    }

    fn mark_failed(&self, index: u8) {
        self.live.lock().unwrap().failed_buttons.insert(index);
    }

    fn set_stick_cue(&self, side: &str, motion: &str, repeats: i32) {
        let mut live = self.live.lock().unwrap();
        live.cue_side = side.to_string();
        live.cue_motion = motion.to_string();
        live.cue_repeats = repeats;
    }

    fn set_phase(&self, phase: &str) {
        self.live.lock().unwrap().phase = phase.to_string();
    }

    fn begin_hold(&self, seconds: f64) {
        let mut live = self.live.lock().unwrap();
        live.hold_paused = false;
        live.hold_frozen = 0.0;
        live.hold_total = seconds.max(0.0);
        live.hold_ends_at = if seconds > 0.0 {
            Some(Instant::now() + Duration::from_secs_f64(live.hold_total))
        } else {
            None
        };
    }

    fn clear_hold(&self) {
        let mut live = self.live.lock().unwrap();
        live.hold_total = 0.0;
        live.hold_ends_at = None;
        live.hold_paused = false;
        live.hold_frozen = 0.0;
    }

    fn set_progress(&self, value: f64, step: &str, focus: Option<&str>) {
        let mut live = self.live.lock().unwrap();
        if !step.is_empty() && step != live.step {
            live.step_index = (live.step_index + 1).min(live.step_total);
        }
        live.progress = value;
        live.step = step.to_string();
        if let Some(focus) = focus {
            live.focus = focus.to_string();
        }
    }

    fn logical_axes(&self) -> std::collections::HashMap<String, f64> {
        self.source.axis_profile().read_map(&self.source.state().axes)
    }

    fn dir_value(&self, axis_x: &str, axis_y: &str, direction: &str) -> f64 {
        let axes = self.logical_axes();
        let x = *axes.get(axis_x).unwrap_or(&0.0);
        let y = *axes.get(axis_y).unwrap_or(&0.0);
        match direction {
            "up" => -y,
            "down" => y,
            "left" => -x,
            _ => x,
        }
    }

    fn stick_radius(&self, axis_x: &str, axis_y: &str) -> f64 {
        let axes = self.logical_axes();
        let x = *axes.get(axis_x).unwrap_or(&0.0);
        let y = *axes.get(axis_y).unwrap_or(&0.0);
        (x * x + y * y).sqrt()
    }

    fn trigger_value(&self, axis: &str) -> f64 {
        normalize_trigger(*self.logical_axes().get(axis).unwrap_or(&-1.0))
    }

    fn wait_held(&self, is_down: impl Fn() -> bool, seconds: f64) -> bool {
        let mut accumulated = 0.0;
        let mut last = Instant::now();
        let deadline = Instant::now() + Duration::from_secs_f64(40.0_f64.max(seconds * 8.0));
        let mut counting = false;
        loop {
            if accumulated >= seconds {
                self.clear_hold();
                return true;
            }
            if self.aborting() {
                self.clear_hold();
                return false;
            }
            let now = Instant::now();
            if now > deadline {
                self.clear_hold();
                return false;
            }
            let down = is_down();
            let dt = (now - last).as_secs_f64().min(0.1);
            last = now;
            if down {
                if !counting {
                    counting = true;
                    accumulated = 0.0;
                    self.begin_hold(seconds);
                } else {
                    accumulated += dt;
                }
            } else if counting {
                counting = false;
                accumulated = 0.0;
                self.clear_hold();
            }
            thread::sleep(Duration::from_millis(30));
        }
    }

    fn wait_seconds(&self, seconds: f64, timed: bool) -> bool {
        if seconds <= 0.0 {
            return !self.stop.load(Ordering::SeqCst);
        }
        if timed {
            self.begin_hold(seconds);
        }
        let end = Instant::now() + Duration::from_secs_f64(seconds);
        while Instant::now() < end {
            if self.stop.load(Ordering::SeqCst) {
                if timed {
                    self.clear_hold();
                }
                return false;
            }
            thread::sleep(Duration::from_millis(30));
        }
        if timed {
            self.clear_hold();
        }
        true
    }

    fn wait_until_released(&self, index: u8) -> bool {
        while *self.source.state().buttons.get(&index).unwrap_or(&false) {
            if self.aborting() {
                return false;
            }
            thread::sleep(Duration::from_millis(20));
        }
        thread::sleep(Duration::from_millis(80));
        !self.aborting()
    }

    fn wait_until_pred(&self, pred: impl Fn() -> bool, timeout: Option<f64>) -> WaitKind {
        let end = timeout.map(|t| Instant::now() + Duration::from_secs_f64(t));
        loop {
            if self.aborting() {
                return if self.skip.load(Ordering::SeqCst) && !self.stop.load(Ordering::SeqCst) {
                    WaitKind::Skip
                } else {
                    WaitKind::Stop
                };
            }
            if pred() {
                return WaitKind::Ok;
            }
            if let Some(end) = end {
                if Instant::now() >= end {
                    return WaitKind::Miss;
                }
            }
            thread::sleep(Duration::from_millis(10));
        }
    }

    fn wait_press_release(&self, index: u8, timeout: f64) -> (WaitKind, f64) {
        if !self.wait_until_released(index) {
            let kind = if self.skip.load(Ordering::SeqCst) && !self.stop.load(Ordering::SeqCst) {
                WaitKind::Skip
            } else {
                WaitKind::Stop
            };
            return (kind, 0.0);
        }
        let end = Instant::now() + Duration::from_secs_f64(timeout);
        loop {
            if Instant::now() >= end {
                return (WaitKind::Miss, 0.0);
            }
            if self.aborting() {
                let kind = if self.skip.load(Ordering::SeqCst) && !self.stop.load(Ordering::SeqCst) {
                    WaitKind::Skip
                } else {
                    WaitKind::Stop
                };
                return (kind, 0.0);
            }
            if *self.source.state().buttons.get(&index).unwrap_or(&false) {
                break;
            }
            thread::sleep(Duration::from_millis(10));
        }
        let t0 = Instant::now();
        loop {
            if self.aborting() {
                let kind = if self.skip.load(Ordering::SeqCst) && !self.stop.load(Ordering::SeqCst) {
                    WaitKind::Skip
                } else {
                    WaitKind::Stop
                };
                return (kind, t0.elapsed().as_secs_f64());
            }
            let down = *self.source.state().buttons.get(&index).unwrap_or(&false);
            let dur = t0.elapsed().as_secs_f64();
            if !down {
                return (
                    if dur > STICKY_LIMIT {
                        WaitKind::Sticky
                    } else {
                        WaitKind::Ok
                    },
                    dur,
                );
            }
            if dur > STICKY_LIMIT {
                if !self.wait_until_released(index) {
                    let kind = if self.skip.load(Ordering::SeqCst) && !self.stop.load(Ordering::SeqCst) {
                        WaitKind::Skip
                    } else {
                        WaitKind::Stop
                    };
                    return (kind, t0.elapsed().as_secs_f64());
                }
                return (WaitKind::Sticky, t0.elapsed().as_secs_f64());
            }
            thread::sleep(Duration::from_millis(10));
        }
    }

    fn wait_analog_pulse(
        &self,
        is_active: impl Fn() -> bool,
        is_rest: impl Fn() -> bool,
        timeout: f64,
    ) -> (WaitKind, f64) {
        let kind = self.wait_until_pred(&is_rest, None);
        if kind != WaitKind::Ok {
            return (kind, 0.0);
        }
        let kind = self.wait_until_pred(&is_active, Some(timeout));
        if kind != WaitKind::Ok {
            return (kind, 0.0);
        }
        let t0 = Instant::now();
        loop {
            if self.aborting() {
                let kind = if self.skip.load(Ordering::SeqCst) && !self.stop.load(Ordering::SeqCst) {
                    WaitKind::Skip
                } else {
                    WaitKind::Stop
                };
                return (kind, t0.elapsed().as_secs_f64());
            }
            let dur = t0.elapsed().as_secs_f64();
            if is_rest() {
                return (
                    if dur > STICKY_LIMIT {
                        WaitKind::Sticky
                    } else {
                        WaitKind::Ok
                    },
                    dur,
                );
            }
            if dur > STICKY_LIMIT {
                let rest = self.wait_until_pred(&is_rest, None);
                if rest != WaitKind::Ok {
                    return (rest, t0.elapsed().as_secs_f64());
                }
                return (WaitKind::Sticky, t0.elapsed().as_secs_f64());
            }
            thread::sleep(Duration::from_millis(10));
        }
    }

    fn action_issues(
        &self,
        name: &str,
        pressed: bool,
        held: bool,
        skipped: bool,
        sticky: bool,
        sensitive: bool,
        want_sticky: bool,
        want_hold: bool,
        want_sens: bool,
    ) -> Vec<String> {
        let hold = self.hold_seconds();
        let mut issues = Vec::new();
        if skipped {
            issues.push(t_vars("button.skipped", &[("name", name.to_string())]));
        } else if !pressed {
            issues.push(t_vars("button.missed", &[("name", name.to_string())]));
        }
        if pressed && !skipped && want_sens && !sensitive {
            issues.push(t_vars("button.insensitive", &[("name", name.to_string())]));
        }
        if pressed && !skipped && want_sticky && sticky {
            issues.push(t_vars("button.sticky", &[("name", name.to_string())]));
        }
        if pressed && !skipped && want_hold && !held {
            issues.push(t_vars(
                "button.not_held",
                &[("name", name.to_string()), ("seconds", hold.to_string())],
            ));
        }
        issues
    }

    fn perform_action_checks(
        &self,
        name: &str,
        focus: &str,
        progress: f64,
        tap_text: impl Fn(i32) -> String,
        hold_text: &str,
        is_active: impl Fn() -> bool,
        is_rest: impl Fn() -> bool,
        is_held: impl Fn() -> bool,
        log_id: &str,
        stick_cue: Option<(&str, &str)>,
    ) -> (ActionCheck, Vec<GamepadSample>) {
        let (want_sticky, want_hold, want_sens) = self.enabled_checks();
        let hold = self.hold_seconds();
        let mut result = ActionCheck {
            pressed: false,
            held: !want_hold,
            skipped: false,
            sticky: false,
            sensitive: true,
            stopped: false,
            taps: 0,
        };
        let _ = name;
        self.skip.store(false, Ordering::SeqCst);
        self.source.start_logging(log_id);
        if want_sticky || want_sens {
            for tap_n in [1, 2] {
                if let Some((side, motion)) = stick_cue {
                    self.set_stick_cue(side, motion, 2);
                }
                self.set_progress(progress, &tap_text(tap_n), Some(focus));
                let (kind, _) = self.wait_analog_pulse(&is_active, &is_rest, PRESS_TIMEOUT);
                if kind == WaitKind::Stop || self.stop.load(Ordering::SeqCst) {
                    result.stopped = true;
                    result.skipped = true;
                    break;
                }
                if kind == WaitKind::Skip {
                    self.consume_skip();
                    result.skipped = true;
                    break;
                }
                if kind == WaitKind::Miss {
                    result.sensitive = false;
                    break;
                }
                result.pressed = true;
                result.taps += 1;
                if kind == WaitKind::Sticky {
                    result.sticky = true;
                }
            }
            if result.stopped || result.skipped || !result.pressed {
                let samples = self.source.logged_samples();
                self.source.stop_logging();
                return (result, samples);
            }
            if want_sens && result.taps < 2 {
                result.sensitive = false;
            }
        }
        if want_hold && !self.stop.load(Ordering::SeqCst) && !result.skipped {
            if let Some((side, motion)) = stick_cue {
                self.set_stick_cue(side, motion, 0);
            }
            self.set_progress(progress, hold_text, Some(focus));
            let rest = self.wait_until_pred(&is_rest, None);
            if rest == WaitKind::Stop || self.stop.load(Ordering::SeqCst) {
                result.stopped = true;
                let samples = self.source.logged_samples();
                self.source.stop_logging();
                return (result, samples);
            }
            if rest == WaitKind::Skip {
                self.consume_skip();
                result.skipped = true;
                result.held = false;
                result.pressed = true;
                let samples = self.source.logged_samples();
                self.source.stop_logging();
                return (result, samples);
            }
            let held = self.wait_held(&is_held, f64::from(hold));
            if self.stop.load(Ordering::SeqCst) {
                result.stopped = true;
                let samples = self.source.logged_samples();
                self.source.stop_logging();
                return (result, samples);
            }
            if self.consume_skip() {
                result.skipped = true;
                result.held = false;
                result.pressed = true;
            } else if held {
                result.held = true;
                result.pressed = true;
            } else {
                result.held = false;
                result.pressed = true;
            }
        }
        let samples = self.source.logged_samples();
        self.source.stop_logging();
        (result, samples)
    }

    fn estimate_steps(&self, tests: &[String]) -> i32 {
        let (sticky, hold, sens) = self.enabled_checks();
        let mut per = (if sticky || sens { 2 } else { 0 }) + (if hold { 1 } else { 0 });
        per = per.max(1);
        let mut n = 0;
        if tests.iter().any(|t| t == "sticks") {
            n += 2 * (1 + 4 * per + 1);
        }
        if tests.iter().any(|t| t == "triggers") {
            n += 2 * per;
        }
        if tests.iter().any(|t| t == "buttons") {
            let items = buttons_for_device(&self.source.axis_profile_name(), &self.source.device_name());
            n += items.len().max(1) as i32 * per;
        }
        n.max(1)
    }

    fn run(self, tests: Vec<String>) {
        let t0 = Instant::now();
        {
            let mut live = self.live.lock().unwrap();
            live.report.device_name = self.source.device_name();
            live.report.device_path = self.source.device_path();
            let (vid, pid) = self.source.vendor_product();
            live.report.vendor_id = vid;
            live.report.product_id = pid;
            live.report.axis_profile = self.source.axis_profile_name();
            live.step_total = self.estimate_steps(&tests);
            live.step_index = 0;
            live.report.tests.insert("rumble".into(), TestStatus::NotTested);
            live.report.tests.insert("stress".into(), TestStatus::NotTested);
            if !tests.iter().any(|t| t == "buttons") {
                live.report.tests.insert("buttons".into(), TestStatus::NotTested);
            }
        }

        let steps: Vec<(&str, fn(&SessionRunner))> = {
            let mut s = Vec::new();
            if tests.iter().any(|t| t == "sticks") {
                s.push(("sticks", SessionRunner::run_sticks as fn(&SessionRunner)));
            }
            if tests.iter().any(|t| t == "triggers") {
                s.push(("triggers", SessionRunner::run_triggers as fn(&SessionRunner)));
            }
            if tests.iter().any(|t| t == "buttons") {
                s.push(("buttons", SessionRunner::run_buttons as fn(&SessionRunner)));
            }
            s
        };

        for (name, fn_) in steps {
            if self.stop.load(Ordering::SeqCst) || !self.source.is_connected() {
                break;
            }
            fn_(&self);
            let status = self.group_status(name);
            self.live.lock().unwrap().report.tests.insert(name.into(), status);
        }

        let timestamps = self.source.event_timestamps();
        let tail = if timestamps.len() > 5000 {
            &timestamps[timestamps.len() - 5000..]
        } else {
            &timestamps
        };
        let rate = analyze_event_rate(tail);
        {
            let mut live = self.live.lock().unwrap();
            live.report.event_rate = EventRateResult {
                mean_interval_ms: rate.mean_interval_ms,
                median_interval_ms: rate.median_interval_ms,
                max_interval_ms: rate.max_interval_ms,
                estimated_hz: rate.estimated_hz,
                note: t("report.event_rate_note"),
            };
        }

        self.clear_hold();
        {
            let mut live = self.live.lock().unwrap();
            live.report.duration_seconds = t0.elapsed().as_secs_f64();
            live.report.finalize();
        }
        self.set_progress(1.0, &t("diag.done_hint"), Some(""));
        self.running.store(false, Ordering::SeqCst);
    }

    fn group_status(&self, name: &str) -> TestStatus {
        let live = self.live.lock().unwrap();
        match name {
            "sticks" => worst(&[live.report.left_stick.status, live.report.right_stick.status]),
            "triggers" => worst(&[live.report.lt.status, live.report.rt.status]),
            "buttons" => live.report.buttons.status,
            _ => TestStatus::NotTested,
        }
    }

    fn run_sticks(&self) {
        let hold = self.hold_seconds();
        let (want_sticky, want_hold, want_sens) = self.enabled_checks();
        self.set_phase("sticks");
        let sides = [
            ("left", "left_x", "left_y", true, self.config.left_stick_deadzone),
            ("right", "right_x", "right_y", false, self.config.right_stick_deadzone),
        ];
        for (side, axis_x, axis_y, is_left, dz) in sides {
            if self.stop.load(Ordering::SeqCst) {
                return;
            }
            let stick_name = if side == "left" {
                t("stick.left")
            } else {
                t("stick.right")
            };
            self.set_stick_cue(side, "rest", 0);
            self.set_progress(
                if is_left { 0.08 } else { 0.28 },
                &t_vars(
                    "stick.rest_instruction",
                    &[("stick", stick_name.clone()), ("seconds", "3".into())],
                ),
                Some(&format!("{side}_rest")),
            );
            if !self.wait_seconds(3.0, true) {
                return;
            }
            self.source.start_logging(&format!("rest_{side}"));
            if !self.wait_seconds(self.config.rest_test_seconds, true) {
                self.source.stop_logging();
                return;
            }
            let rest_samples = self.source.logged_samples();
            self.source.stop_logging();
            let rest_result = self.stick.analyze_rest(&rest_samples, axis_x, axis_y, dz);
            {
                let mut live = self.live.lock().unwrap();
                if is_left {
                    live.report.left_stick = rest_result;
                } else {
                    live.report.right_stick = rest_result;
                }
            }
            self.set_can_skip(true);
            let mut defects = 0;
            for (direction, dir_key) in [
                ("up", "stick.dir_up"),
                ("down", "stick.dir_down"),
                ("left", "stick.dir_left"),
                ("right", "stick.dir_right"),
            ] {
                if self.stop.load(Ordering::SeqCst) {
                    self.set_can_skip(false);
                    return;
                }
                let dir_label = t(dir_key);
                let name = t_vars(
                    "stick.action",
                    &[("stick", stick_name.clone()), ("direction", dir_label)],
                );
                let progress = if is_left { 0.15 } else { 0.35 };
                let (check, step_samples) = self.perform_action_checks(
                    &name,
                    &format!("{side}_{direction}"),
                    progress,
                    |n| t_vars("stick.tap", &[("name", name.clone()), ("n", n.to_string())]),
                    &t_vars(
                        "stick.holding",
                        &[("name", name.clone()), ("seconds", hold.to_string())],
                    ),
                    || self.dir_value(axis_x, axis_y, direction) >= ANALOG_ACTIVE,
                    || self.dir_value(axis_x, axis_y, direction) <= ANALOG_REST,
                    || self.dir_value(axis_x, axis_y, direction) >= ANALOG_HOLD,
                    &format!("range_{side}_{direction}"),
                    Some((side, direction)),
                );
                if check.stopped || self.stop.load(Ordering::SeqCst) {
                    self.set_can_skip(false);
                    return;
                }
                let (ok, range_issues) =
                    self.stick.analyze_range_step(&step_samples, axis_x, axis_y, direction);
                let action_issues = self.action_issues(
                    &name,
                    check.pressed,
                    check.held,
                    check.skipped,
                    check.sticky,
                    check.sensitive,
                    want_sticky,
                    want_hold,
                    want_sens,
                );
                let failed = check.skipped
                    || !check.pressed
                    || (want_hold && !check.held)
                    || (want_sticky && check.sticky)
                    || (want_sens && !check.sensitive)
                    || !ok;
                {
                    let mut live = self.live.lock().unwrap();
                    let cur: &mut StickTestResult = if is_left {
                        &mut live.report.left_stick
                    } else {
                        &mut live.report.right_stick
                    };
                    if !ok {
                        cur.range_ok = false;
                    }
                    cur.issues.extend(action_issues);
                    cur.issues.extend(range_issues);
                    if failed {
                        defects += 1;
                        if cur.status == TestStatus::Pass {
                            cur.status = TestStatus::Warn;
                        }
                    }
                }
            }
            if self.stop.load(Ordering::SeqCst) {
                self.set_can_skip(false);
                return;
            }
            let circle_name = t_vars("stick.circle_name", &[("stick", stick_name.clone())]);
            let msg = t_vars("stick.range_circle", &[("stick", stick_name.clone())]);
            let progress = if is_left { 0.22 } else { 0.42 };
            self.skip.store(false, Ordering::SeqCst);
            self.set_stick_cue(side, "circle", 0);
            self.set_progress(progress, &msg, Some(&format!("{side}_circle")));
            self.source.start_logging(&format!("circ_{side}"));
            let start = self.wait_until_pred(|| self.stick_radius(axis_x, axis_y) >= ANALOG_ACTIVE, Some(PRESS_TIMEOUT));
            let mut circ_skipped = false;
            let mut circ_missed = false;
            let mut circ_held = true;
            if start == WaitKind::Stop || self.stop.load(Ordering::SeqCst) {
                self.source.stop_logging();
                self.set_can_skip(false);
                return;
            }
            if start == WaitKind::Skip {
                self.consume_skip();
                circ_skipped = true;
            } else if start == WaitKind::Miss {
                circ_missed = true;
            } else if want_hold {
                self.set_progress(
                    progress,
                    &t_vars(
                        "stick.circle_hold",
                        &[("stick", stick_name.clone()), ("seconds", hold.to_string())],
                    ),
                    Some(&format!("{side}_circle")),
                );
                circ_held = self.wait_held(|| self.stick_radius(axis_x, axis_y) >= CIRCLE_RIM, f64::from(hold));
                if self.stop.load(Ordering::SeqCst) {
                    self.source.stop_logging();
                    self.set_can_skip(false);
                    return;
                }
                if self.consume_skip() {
                    circ_skipped = true;
                    circ_held = false;
                }
            } else if !self.wait_seconds(f64::from(hold), true) {
                self.source.stop_logging();
                self.set_can_skip(false);
                return;
            }
            let circ_samples = self.source.logged_samples();
            self.source.stop_logging();
            let (err, circ_status, circ_issues) =
                self.stick.analyze_circularity(&circ_samples, axis_x, axis_y);
            {
                let mut live = self.live.lock().unwrap();
                let cur: &mut StickTestResult = if is_left {
                    &mut live.report.left_stick
                } else {
                    &mut live.report.right_stick
                };
                cur.circularity_pct = err;
                if circ_skipped {
                    cur.issues
                        .push(t_vars("button.skipped", &[("name", circle_name.clone())]));
                    defects += 1;
                } else if circ_missed {
                    cur.issues
                        .push(t_vars("button.missed", &[("name", circle_name.clone())]));
                    defects += 1;
                } else if want_hold && !circ_held {
                    cur.issues.push(t_vars(
                        "button.not_held",
                        &[("name", circle_name.clone()), ("seconds", hold.to_string())],
                    ));
                    defects += 1;
                }
                cur.issues.extend(circ_issues);
                if circ_status == TestStatus::Fail
                    || (circ_status == TestStatus::Warn && cur.status == TestStatus::Pass)
                {
                    cur.status = circ_status;
                }
                if defects >= 2 && cur.status != TestStatus::Fail {
                    cur.status = TestStatus::Fail;
                } else if defects > 0 && cur.status == TestStatus::Pass {
                    cur.status = TestStatus::Warn;
                }
            }
            self.set_can_skip(false);
            self.skip.store(false, Ordering::SeqCst);
        }
    }

    fn run_triggers(&self) {
        let hold = self.hold_seconds();
        let (want_sticky, want_hold, want_sens) = self.enabled_checks();
        self.set_phase("triggers");
        self.set_stick_cue("", "", 0);
        self.set_can_skip(true);
        for (axis, is_lt, label, progress) in [("lt", true, "LT", 0.52), ("rt", false, "RT", 0.62)] {
            if self.stop.load(Ordering::SeqCst) {
                self.set_can_skip(false);
                return;
            }
            let (check, samples) = self.perform_action_checks(
                label,
                axis,
                progress,
                |n| t_vars("trigger.tap", &[("name", label.to_string()), ("n", n.to_string())]),
                &t_vars(
                    "trigger.holding",
                    &[("name", label.to_string()), ("seconds", hold.to_string())],
                ),
                || self.trigger_value(axis) >= TRIGGER_ACTIVE,
                || self.trigger_value(axis) <= TRIGGER_REST,
                || self.trigger_value(axis) >= TRIGGER_HOLD,
                &format!("trigger_{axis}"),
                None,
            );
            if check.stopped || self.stop.load(Ordering::SeqCst) {
                self.set_can_skip(false);
                return;
            }
            let mut result = self.trigger.analyze(&samples, axis);
            let action_issues = self.action_issues(
                label,
                check.pressed,
                check.held,
                check.skipped,
                check.sticky,
                check.sensitive,
                want_sticky,
                want_hold,
                want_sens,
            );
            result.issues = [action_issues, result.issues].concat();
            let failed = check.skipped
                || !check.pressed
                || (want_hold && !check.held)
                || (want_sticky && check.sticky)
                || (want_sens && !check.sensitive);
            if failed && matches!(result.status, TestStatus::Pass | TestStatus::NotTested) {
                result.status = TestStatus::Warn;
            }
            if check.skipped || !check.pressed {
                if result.status != TestStatus::Fail {
                    result.status = TestStatus::Warn;
                }
            }
            let mut live = self.live.lock().unwrap();
            if is_lt {
                live.report.lt = result;
            } else {
                live.report.rt = result;
            }
        }
        self.set_can_skip(false);
        self.skip.store(false, Ordering::SeqCst);
    }

    fn run_buttons(&self) {
        let items = buttons_for_device(&self.source.axis_profile_name(), &self.source.device_name());
        self.set_phase("buttons");
        self.set_stick_cue("", "", 0);
        let hold = self.hold_seconds();
        let (want_sticky, want_hold, want_sens) = self.enabled_checks();
        let mut checks = Vec::new();
        let n = items.len().max(1) as f64;
        self.set_can_skip(true);
        for (i, (idx, name)) in items.iter().enumerate() {
            if self.stop.load(Ordering::SeqCst) {
                break;
            }
            self.skip.store(false, Ordering::SeqCst);
            let progress = 0.70 + 0.25 * i as f64 / n;
            let mut pressed = false;
            let mut held = !want_hold;
            let mut skipped = false;
            let mut sticky = false;
            let mut sensitive = true;
            let mut taps = 0u32;
            if want_sticky || want_sens {
                for tap_n in [1, 2] {
                    let msg = t_vars("button.tap", &[("name", name.clone()), ("n", tap_n.to_string())]);
                    self.set_progress(progress, &msg, Some(&format!("btn:{idx}")));
                    let (kind, _) = self.wait_press_release(*idx, PRESS_TIMEOUT);
                    if kind == WaitKind::Stop || self.stop.load(Ordering::SeqCst) {
                        skipped = true;
                        break;
                    }
                    if kind == WaitKind::Skip {
                        self.consume_skip();
                        skipped = true;
                        break;
                    }
                    if kind == WaitKind::Miss {
                        sensitive = false;
                        if tap_n == 1 {
                            pressed = false;
                        }
                        break;
                    }
                    pressed = true;
                    taps += 1;
                    if kind == WaitKind::Sticky {
                        sticky = true;
                    }
                }
                if self.stop.load(Ordering::SeqCst) {
                    break;
                }
                if skipped {
                    self.mark_failed(*idx);
                    checks.push(check_button(
                        *idx, name, false, false, true, false, true, 0, hold,
                    ));
                    continue;
                }
                if !pressed {
                    self.mark_failed(*idx);
                    checks.push(check_button(
                        *idx, name, false, false, false, false, false, 0, hold,
                    ));
                    continue;
                }
                if want_sens && taps < 2 {
                    sensitive = false;
                }
            }
            if want_hold && !self.stop.load(Ordering::SeqCst) {
                self.set_progress(
                    progress,
                    &t_vars(
                        "button.holding",
                        &[("name", name.clone()), ("seconds", hold.to_string())],
                    ),
                    Some(&format!("btn:{idx}")),
                );
                if !self.wait_until_released(*idx) {
                    if self.stop.load(Ordering::SeqCst) {
                        break;
                    }
                    self.consume_skip();
                    self.mark_failed(*idx);
                    checks.push(check_button(
                        *idx, name, true, false, true, sticky, sensitive, taps, hold,
                    ));
                    continue;
                }
                held = self.wait_held(
                    || *self.source.state().buttons.get(idx).unwrap_or(&false),
                    f64::from(hold),
                );
                if self.stop.load(Ordering::SeqCst) {
                    break;
                }
                if self.consume_skip() {
                    skipped = true;
                    held = false;
                } else if held {
                    pressed = true;
                }
            }
            let failed = skipped
                || !pressed
                || (want_hold && !held)
                || (want_sticky && sticky)
                || (want_sens && !sensitive);
            if failed {
                self.mark_failed(*idx);
            }
            checks.push(check_button(
                *idx,
                name,
                pressed,
                if want_hold { held } else { true },
                skipped,
                if want_sticky { sticky } else { false },
                if want_sens { sensitive } else { true },
                taps,
                hold,
            ));
            thread::sleep(Duration::from_millis(80));
        }
        self.set_can_skip(false);
        self.skip.store(false, Ordering::SeqCst);
        self.live.lock().unwrap().report.buttons = summarize(checks);
    }
}

fn worst(statuses: &[TestStatus]) -> TestStatus {
    if statuses.contains(&TestStatus::Fail) {
        TestStatus::Fail
    } else if statuses.contains(&TestStatus::Warn) {
        TestStatus::Warn
    } else if statuses.iter().all(|s| *s == TestStatus::Pass) {
        TestStatus::Pass
    } else {
        TestStatus::NotTested
    }
}

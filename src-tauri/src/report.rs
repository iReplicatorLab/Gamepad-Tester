use std::collections::{HashMap, HashSet};

use serde::Serialize;

use crate::i18n::{t, t_vars};
use crate::pad::{APP_NAME, REPORT_SCHEMA, VERSION};
use crate::stats::looks_like_square_gate;
use crate::status::{overall_from_tests, TestStatus};

#[derive(Clone, Debug, Serialize)]
pub struct StickTestResult {
    pub status: TestStatus,
    pub drift_pct: f64,
    pub mean_x: f64,
    pub mean_y: f64,
    pub max_radius: f64,
    pub deadzone_pct: f64,
    pub physical_drift_pct: f64,
    pub circularity_pct: f64,
    pub range_ok: bool,
    pub issues: Vec<String>,
    pub rest_points: Vec<(f64, f64)>,
}

impl Default for StickTestResult {
    fn default() -> Self {
        Self {
            status: TestStatus::NotTested,
            drift_pct: 0.0,
            mean_x: 0.0,
            mean_y: 0.0,
            max_radius: 0.0,
            deadzone_pct: 0.0,
            physical_drift_pct: 0.0,
            circularity_pct: 0.0,
            range_ok: true,
            issues: Vec::new(),
            rest_points: Vec::new(),
        }
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct TriggerTestResult {
    pub status: TestStatus,
    pub min_value: f64,
    pub max_value: f64,
    pub spike_count: i32,
    pub returns_to_zero: bool,
    pub issues: Vec<String>,
    pub timeline: Vec<(u64, f64)>,
}

impl Default for TriggerTestResult {
    fn default() -> Self {
        Self {
            status: TestStatus::NotTested,
            min_value: 0.0,
            max_value: 0.0,
            spike_count: 0,
            returns_to_zero: true,
            issues: Vec::new(),
            timeline: Vec::new(),
        }
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct ButtonCheck {
    pub index: u8,
    pub name: String,
    pub pressed: bool,
    pub held: bool,
    pub skipped: bool,
    pub sticky: bool,
    pub sensitive: bool,
    pub tap_count: u32,
    pub issues: Vec<String>,
}

#[derive(Clone, Debug, Default, Serialize)]
pub struct ButtonsTestResult {
    pub status: TestStatus,
    pub buttons: Vec<ButtonCheck>,
    pub pressed_count: i32,
    pub held_count: i32,
    pub issues: Vec<String>,
}

#[derive(Clone, Debug, Default, Serialize)]
pub struct EventRateResult {
    pub mean_interval_ms: f64,
    pub median_interval_ms: f64,
    pub max_interval_ms: f64,
    pub estimated_hz: f64,
    pub note: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct DiagnosticReport {
    pub schema_version: String,
    pub app_name: String,
    pub app_version: String,
    pub created_at: String,
    pub locale: String,
    pub device_name: String,
    pub device_path: String,
    pub vendor_id: Option<u16>,
    pub product_id: Option<u16>,
    pub axis_profile: String,
    pub duration_seconds: f64,
    pub overall: TestStatus,
    pub tests: HashMap<String, TestStatus>,
    pub left_stick: StickTestResult,
    pub right_stick: StickTestResult,
    pub lt: TriggerTestResult,
    pub rt: TriggerTestResult,
    pub buttons: ButtonsTestResult,
    pub event_rate: EventRateResult,
    pub issues: Vec<String>,
    pub notes: Vec<String>,
    pub score: i32,
    pub disclaimer: String,
    pub thresholds: HashMap<String, f64>,
}

impl DiagnosticReport {
    pub fn new(locale: &str, disclaimer: String, thresholds: HashMap<String, f64>) -> Self {
        Self {
            schema_version: REPORT_SCHEMA.into(),
            app_name: APP_NAME.into(),
            app_version: VERSION.into(),
            created_at: chrono::Utc::now().to_rfc3339(),
            locale: locale.to_string(),
            device_name: String::new(),
            device_path: String::new(),
            vendor_id: None,
            product_id: None,
            axis_profile: String::new(),
            duration_seconds: 0.0,
            overall: TestStatus::NotTested,
            tests: HashMap::new(),
            left_stick: StickTestResult::default(),
            right_stick: StickTestResult::default(),
            lt: TriggerTestResult::default(),
            rt: TriggerTestResult::default(),
            buttons: ButtonsTestResult::default(),
            event_rate: EventRateResult::default(),
            issues: Vec::new(),
            notes: Vec::new(),
            score: 0,
            disclaimer,
            thresholds,
        }
    }

    pub fn finalize(&mut self) {
        self.overall = overall_from_tests(&self.tests);
        self.issues.clear();
        self.notes.clear();
        for res in [&self.left_stick, &self.right_stick] {
            self.issues.extend(res.issues.clone());
            if !matches!(res.status, TestStatus::NotTested | TestStatus::NotSupported)
                && looks_like_square_gate(res.circularity_pct)
            {
                self.notes.push("circularity.square_ok".into());
            }
        }
        self.issues.extend(self.lt.issues.clone());
        self.issues.extend(self.rt.issues.clone());
        self.issues.extend(self.buttons.issues.clone());
        let mut seen = HashSet::new();
        self.notes.retain(|note| seen.insert(note.clone()));
        let tested = self.tests.values().any(|s| {
            !matches!(s, TestStatus::NotTested | TestStatus::NotSupported)
        }) || self.overall != TestStatus::NotTested;
        self.score = if tested { compute_score(self) } else { 0 };
    }

    pub fn status_label_key(&self) -> &'static str {
        match self.overall {
            TestStatus::Pass => "status.pass",
            TestStatus::Warn => "status.warn",
            TestStatus::Fail => "status.fail",
            _ => "status.not_tested",
        }
    }
}

pub fn compute_score(report: &DiagnosticReport) -> i32 {
    let mut score = 10.0;
    for stick in [&report.left_stick, &report.right_stick] {
        match stick.status {
            TestStatus::Fail => score -= 3.0,
            TestStatus::Warn => score -= 1.5,
            _ => {}
        }
    }
    for trig in [&report.lt, &report.rt] {
        match trig.status {
            TestStatus::Fail => score -= 2.0,
            TestStatus::Warn => score -= 0.75,
            _ => {}
        }
    }
    let buttons = &report.buttons;
    if !matches!(buttons.status, TestStatus::NotTested | TestStatus::NotSupported) {
        let missed = buttons
            .buttons
            .iter()
            .filter(|item| !item.pressed || item.skipped)
            .count() as f64;
        let not_held = buttons
            .buttons
            .iter()
            .filter(|item| item.pressed && !item.held && !item.skipped)
            .count() as f64;
        let sticky = buttons.buttons.iter().filter(|item| item.sticky).count() as f64;
        let dull = buttons.buttons.iter().filter(|item| !item.sensitive).count() as f64;
        score -= (missed * 1.5).min(6.0);
        score -= (not_held * 0.5).min(2.0);
        score -= (sticky * 1.0).min(3.0);
        score -= (dull * 1.0).min(3.0);
    }
    score.round().clamp(1.0, 10.0) as i32
}

fn button_check_status(item: &ButtonCheck) -> TestStatus {
    if item.skipped || !item.pressed {
        TestStatus::Fail
    } else if item.sticky || !item.sensitive || !item.held {
        TestStatus::Warn
    } else {
        TestStatus::Pass
    }
}

fn bare_issue(issue: &str, name: &str) -> String {
    let prefix_colon = format!("{name}: ");
    let prefix_space = format!("{name} ");
    if let Some(rest) = issue.strip_prefix(&prefix_colon) {
        rest.to_string()
    } else if let Some(rest) = issue.strip_prefix(&prefix_space) {
        rest.to_string()
    } else {
        issue.to_string()
    }
}

fn control_lines(name: &str, status: TestStatus, issues: &[String], extra: &str) -> Vec<String> {
    let mut title = format!("{} — {}", name, status.as_str());
    if !extra.is_empty() {
        title = format!("{title} ({extra})");
    }
    let mut lines = vec![title];
    lines.extend(issues.iter().map(|issue| format!("• {}", bare_issue(issue, name))));
    lines
}

fn stick_extra(stick: &StickTestResult) -> String {
    let mut parts = vec![t_vars("report.drift", &[("pct", format!("{:.1}", stick.drift_pct))])];
    if stick.circularity_pct > 0.0 {
        parts.push(t_vars(
            "report.gate_shape",
            &[("pct", format!("{:.1}", stick.circularity_pct))],
        ));
    }
    parts.join(" · ")
}

fn extend_section(lines: &mut Vec<String>, heading: String, blocks: &[Vec<String>]) {
    if blocks.is_empty() {
        return;
    }
    if let Some(last) = lines.last() {
        if !last.is_empty() {
            lines.push(String::new());
        }
    }
    lines.push(heading);
    for (index, block) in blocks.iter().enumerate() {
        if index > 0 && (blocks[index - 1].len() > 1 || block.len() > 1) {
            lines.push(String::new());
        }
        lines.extend(block.clone());
    }
}

pub fn result_lines(report: &DiagnosticReport) -> Vec<String> {
    let mut lines = vec![
        t_vars("diag.score", &[("score", report.score.to_string())]),
        format!("{}: {}", t("diag.status"), t(report.status_label_key())),
    ];

    let mut stick_blocks = Vec::new();
    for (stick, label) in [
        (&report.left_stick, t("stick.left")),
        (&report.right_stick, t("stick.right")),
    ] {
        if stick.status == TestStatus::NotTested {
            continue;
        }
        stick_blocks.push(control_lines(
            &label,
            stick.status,
            &stick.issues,
            &stick_extra(stick),
        ));
    }
    extend_section(&mut lines, t("diag.sticks"), &stick_blocks);

    let mut trigger_blocks = Vec::new();
    for (trig, label) in [(&report.lt, "LT"), (&report.rt, "RT")] {
        if trig.status == TestStatus::NotTested {
            continue;
        }
        let extra = format!("{:.0}%", trig.max_value * 100.0);
        trigger_blocks.push(control_lines(label, trig.status, &trig.issues, &extra));
    }
    extend_section(&mut lines, t("diag.triggers"), &trigger_blocks);

    let mut button_blocks = Vec::new();
    if report.buttons.status != TestStatus::NotTested {
        for item in &report.buttons.buttons {
            button_blocks.push(control_lines(
                &item.name,
                button_check_status(item),
                &item.issues,
                "",
            ));
        }
    }
    extend_section(&mut lines, t("diag.buttons"), &button_blocks);

    for note in &report.notes {
        lines.push(String::new());
        lines.push(t(note));
    }
    lines
}

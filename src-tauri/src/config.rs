use std::fs;
use std::path::PathBuf;

use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DiagnosticConfig {
    pub stick_drift_warn: f64,
    pub stick_drift_fail: f64,
    pub stick_noise: f64,
    pub stick_drift_hold_ms: i32,
    pub stick_drift_sample_ratio: f64,
    pub trigger_min: f64,
    pub trigger_max: f64,
    pub trigger_spike: f64,
    pub trigger_rest_jitter: f64,
    pub button_bounce_ms: i32,
    pub rest_test_seconds: f64,
    pub stress_test_seconds: f64,
    pub graph_max_points: i32,
    pub locale: String,
    pub left_stick_deadzone: f64,
    pub right_stick_deadzone: f64,
    pub center_compensation: bool,
    pub smoothing: f64,
    pub button_hold_seconds: i32,
    pub test_stickiness: bool,
    pub test_hold: bool,
    pub test_sensitivity: bool,
}

impl Default for DiagnosticConfig {
    fn default() -> Self {
        Self {
            stick_drift_warn: 0.03,
            stick_drift_fail: 0.07,
            stick_noise: 0.02,
            stick_drift_hold_ms: 500,
            stick_drift_sample_ratio: 0.25,
            trigger_min: 0.03,
            trigger_max: 0.97,
            trigger_spike: 0.03,
            trigger_rest_jitter: 0.02,
            button_bounce_ms: 30,
            rest_test_seconds: 5.0,
            stress_test_seconds: 300.0,
            graph_max_points: 10000,
            locale: "ru".into(),
            left_stick_deadzone: 0.05,
            right_stick_deadzone: 0.05,
            center_compensation: true,
            smoothing: 0.0,
            button_hold_seconds: 3,
            test_stickiness: true,
            test_hold: true,
            test_sensitivity: true,
        }
    }
}

impl DiagnosticConfig {
    pub fn config_dir() -> PathBuf {
        home_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join(".config")
            .join("ireplicator-gamepad-tester")
    }

    pub fn config_path() -> PathBuf {
        Self::config_dir().join("config.json")
    }

    pub fn load() -> Self {
        let path = Self::config_path();
        if !path.exists() {
            let cfg = Self::default();
            let _ = cfg.save();
            return cfg;
        }
        match fs::read_to_string(&path) {
            Ok(text) => match serde_json::from_value::<PartialConfig>(
                serde_json::from_str(&text).unwrap_or(serde_json::Value::Null),
            ) {
                Ok(partial) => {
                    let mut cfg = Self::default();
                    partial.apply(&mut cfg);
                    cfg
                }
                Err(_) => {
                    let cfg = Self::default();
                    let _ = cfg.save();
                    cfg
                }
            },
            Err(_) => {
                let cfg = Self::default();
                let _ = cfg.save();
                cfg
            }
        }
    }

    pub fn save(&self) -> Result<(), String> {
        fs::create_dir_all(Self::config_dir()).map_err(|e| e.to_string())?;
        let text = serde_json::to_string_pretty(self).map_err(|e| e.to_string())?;
        fs::write(Self::config_path(), text).map_err(|e| e.to_string())
    }

    pub fn hold_seconds(&self) -> i32 {
        self.button_hold_seconds.clamp(1, 15)
    }

    pub fn update_from_json(&mut self, data: &serde_json::Value) {
        let Ok(partial) = serde_json::from_value::<PartialConfig>(data.clone()) else {
            return;
        };
        partial.apply(self);
    }
}

#[derive(Default, Deserialize)]
struct PartialConfig {
    stick_drift_warn: Option<f64>,
    stick_drift_fail: Option<f64>,
    stick_noise: Option<f64>,
    stick_drift_hold_ms: Option<i32>,
    stick_drift_sample_ratio: Option<f64>,
    trigger_min: Option<f64>,
    trigger_max: Option<f64>,
    trigger_spike: Option<f64>,
    trigger_rest_jitter: Option<f64>,
    button_bounce_ms: Option<i32>,
    rest_test_seconds: Option<f64>,
    stress_test_seconds: Option<f64>,
    graph_max_points: Option<i32>,
    locale: Option<String>,
    left_stick_deadzone: Option<f64>,
    right_stick_deadzone: Option<f64>,
    center_compensation: Option<bool>,
    smoothing: Option<f64>,
    button_hold_seconds: Option<serde_json::Value>,
    test_stickiness: Option<bool>,
    test_hold: Option<bool>,
    test_sensitivity: Option<bool>,
}

impl PartialConfig {
    fn apply(self, cfg: &mut DiagnosticConfig) {
        if let Some(v) = self.stick_drift_warn {
            cfg.stick_drift_warn = v;
        }
        if let Some(v) = self.stick_drift_fail {
            cfg.stick_drift_fail = v;
        }
        if let Some(v) = self.stick_noise {
            cfg.stick_noise = v;
        }
        if let Some(v) = self.stick_drift_hold_ms {
            cfg.stick_drift_hold_ms = v;
        }
        if let Some(v) = self.stick_drift_sample_ratio {
            cfg.stick_drift_sample_ratio = v;
        }
        if let Some(v) = self.trigger_min {
            cfg.trigger_min = v;
        }
        if let Some(v) = self.trigger_max {
            cfg.trigger_max = v;
        }
        if let Some(v) = self.trigger_spike {
            cfg.trigger_spike = v;
        }
        if let Some(v) = self.trigger_rest_jitter {
            cfg.trigger_rest_jitter = v;
        }
        if let Some(v) = self.button_bounce_ms {
            cfg.button_bounce_ms = v;
        }
        if let Some(v) = self.rest_test_seconds {
            cfg.rest_test_seconds = v;
        }
        if let Some(v) = self.stress_test_seconds {
            cfg.stress_test_seconds = v;
        }
        if let Some(v) = self.graph_max_points {
            cfg.graph_max_points = v;
        }
        if let Some(v) = self.locale {
            cfg.locale = if v == "en" { "en".into() } else { "ru".into() };
        }
        if let Some(v) = self.left_stick_deadzone {
            cfg.left_stick_deadzone = v;
        }
        if let Some(v) = self.right_stick_deadzone {
            cfg.right_stick_deadzone = v;
        }
        if let Some(v) = self.center_compensation {
            cfg.center_compensation = v;
        }
        if let Some(v) = self.smoothing {
            cfg.smoothing = v;
        }
        if let Some(v) = self.button_hold_seconds {
            if let Some(n) = v.as_i64() {
                cfg.button_hold_seconds = n as i32;
            } else if let Some(n) = v.as_f64() {
                cfg.button_hold_seconds = n as i32;
            } else if let Some(s) = v.as_str() {
                if let Ok(n) = s.parse::<i32>() {
                    cfg.button_hold_seconds = n;
                }
            }
        }
        if let Some(v) = self.test_stickiness {
            cfg.test_stickiness = v;
        }
        if let Some(v) = self.test_hold {
            cfg.test_hold = v;
        }
        if let Some(v) = self.test_sensitivity {
            cfg.test_sensitivity = v;
        }
    }
}

pub fn home_dir() -> Option<PathBuf> {
    std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from)
}

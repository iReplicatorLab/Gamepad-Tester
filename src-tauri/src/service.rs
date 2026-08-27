use std::sync::{Arc, Mutex};

use serde::Serialize;

use crate::backend::create_backend;
use crate::config::DiagnosticConfig;
use crate::i18n::init_from_config;
use crate::pad::{pad_state_payload, PadStatePayload};
use crate::report::{result_lines, DiagnosticReport};
use crate::session::{DiagnosticSession, DiagnosticsStatus, SampleSource};

pub struct GamepadService {
    backend: Arc<dyn SampleSource>,
    config: Mutex<DiagnosticConfig>,
    session: Mutex<DiagnosticSession>,
    log_lines: Mutex<Vec<String>>,
}

impl GamepadService {
    pub fn new() -> Self {
        let config = DiagnosticConfig::load();
        init_from_config(&config.locale);
        let backend = create_backend();
        backend.start();
        let session = DiagnosticSession::new(config.clone(), Arc::clone(&backend));
        Self {
            backend,
            session: Mutex::new(session),
            config: Mutex::new(config),
            log_lines: Mutex::new(Vec::new()),
        }
    }

    pub fn shutdown(&self) {
        self.session.lock().unwrap().stop();
        self.backend.shutdown();
    }

    fn append_log(&self, line: String) {
        let mut lines = self.log_lines.lock().unwrap();
        lines.push(line);
        if lines.len() > 2000 {
            let n = lines.len();
            let keep = lines.split_off(n - 1500);
            *lines = keep;
        }
    }

    pub fn refresh_log(&self) {
        let events = self.backend.recent_events(80);
        for event in events.iter().rev().take(5).rev() {
            self.append_log(format!("{} {}={}", event.event_type, event.code, event.value));
        }
    }

    pub fn get_log(&self, since: usize) -> LogPayload {
        let lines = self.log_lines.lock().unwrap();
        let slice = if since >= lines.len() {
            Vec::new()
        } else {
            lines[since..].to_vec()
        };
        LogPayload {
            next: lines.len(),
            lines: slice,
        }
    }

    pub fn get_state_payload(&self) -> PadStatePayload {
        self.refresh_log();
        pad_state_payload(&self.backend.state(), self.backend.axis_profile())
    }

    pub fn get_diagnostics_payload(&self) -> DiagnosticsStatus {
        self.session.lock().unwrap().status()
    }

    pub fn get_report_payload(&self) -> ReportPayload {
        let report = self.session.lock().unwrap().get_results();
        ReportPayload {
            lines: result_lines(&report),
            report,
        }
    }

    pub fn config_json(&self) -> DiagnosticConfig {
        self.config.lock().unwrap().clone()
    }

    pub fn update_config(&self, data: serde_json::Value) -> DiagnosticConfig {
        let mut config = self.config.lock().unwrap();
        config.update_from_json(&data);
        let _ = config.save();
        init_from_config(&config.locale);
        *self.session.lock().unwrap() = DiagnosticSession::new(config.clone(), Arc::clone(&self.backend));
        config.clone()
    }

    pub fn start_diagnostics(&self, tests: Option<Vec<String>>) {
        self.append_log("Diagnostics started".into());
        self.session.lock().unwrap().start(tests);
    }

    pub fn stop_diagnostics(&self) {
        self.session.lock().unwrap().stop();
        self.append_log("Diagnostics stopped".into());
    }

    pub fn skip_step(&self) {
        self.session.lock().unwrap().skip();
    }

    pub fn rumble(&self, left: f64, right: f64, duration_ms: u32) -> bool {
        self.backend.rumble(left, right, duration_ms)
    }

    pub fn export_json(&self) -> Result<String, String> {
        crate::export::export_json(&self.session.lock().unwrap().get_results())
    }

    pub fn export_csv(&self) -> String {
        crate::export::export_csv(&self.session.lock().unwrap().get_results())
    }
}

#[derive(Serialize)]
pub struct LogPayload {
    pub lines: Vec<String>,
    pub next: usize,
}

#[derive(Serialize)]
pub struct ReportPayload {
    pub report: DiagnosticReport,
    pub lines: Vec<String>,
}

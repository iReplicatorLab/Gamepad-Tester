use crate::config::DiagnosticConfig;
use crate::report::TriggerTestResult;
use crate::sample::GamepadSample;
use crate::stats::{analyze_trigger, classify_trigger};
use crate::status::TestStatus;

pub struct TriggerDiagnostic {
    config: DiagnosticConfig,
}

impl TriggerDiagnostic {
    pub fn new(config: DiagnosticConfig) -> Self {
        Self { config }
    }

    pub fn analyze(&self, samples: &[GamepadSample], axis_name: &str) -> TriggerTestResult {
        let values: Vec<f64> = samples
            .iter()
            .map(|s| s.axes.get(axis_name).copied().unwrap_or(0.0).clamp(0.0, 1.0))
            .collect();
        if values.len() < 10 {
            return TriggerTestResult {
                status: TestStatus::NotTested,
                issues: vec!["Недостаточно данных для теста триггера".into()],
                ..Default::default()
            };
        }
        let metrics = analyze_trigger(
            &values,
            self.config.trigger_min,
            self.config.trigger_max,
            self.config.trigger_rest_jitter,
        );
        let level = classify_trigger(
            &metrics,
            self.config.trigger_min,
            self.config.trigger_max,
            self.config.trigger_rest_jitter,
        );
        let mut issues = Vec::new();
        if metrics.max_value < self.config.trigger_max {
            issues.push(format!(
                "Не достигает 100% (max {:.0}%)",
                metrics.max_value * 100.0
            ));
        }
        if !metrics.returns_to_zero {
            issues.push("Не возвращается к нулю".into());
        }
        if metrics.spike_count > 3 {
            issues.push(format!("Скачки значения: {}", metrics.spike_count));
        }
        if metrics.rest_jitter > self.config.trigger_rest_jitter {
            issues.push(format!(
                "Нестабильность в покое: {:.1}%",
                metrics.rest_jitter * 100.0
            ));
        }
        TriggerTestResult {
            status: TestStatus::from_level(level),
            min_value: metrics.min_value,
            max_value: metrics.max_value,
            spike_count: metrics.spike_count,
            returns_to_zero: metrics.returns_to_zero,
            issues,
            timeline: samples
                .iter()
                .zip(values.iter())
                .map(|(s, v)| (s.timestamp_ns, *v))
                .collect(),
        }
    }
}

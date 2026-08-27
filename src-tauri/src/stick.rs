use crate::config::DiagnosticConfig;
use crate::i18n::t;
use crate::report::StickTestResult;
use crate::sample::GamepadSample;
use crate::stats::{
    analyze_circularity, analyze_drift, classify_circularity, classify_drift, detect_spikes,
    drift_detected, radial_distance, CIRCULARITY_OUTER_MIN,
};
use crate::status::TestStatus;

pub struct StickDiagnostic {
    config: DiagnosticConfig,
}

impl StickDiagnostic {
    pub fn new(config: DiagnosticConfig) -> Self {
        Self { config }
    }

    pub fn analyze_rest(
        &self,
        samples: &[GamepadSample],
        axis_x: &str,
        axis_y: &str,
        deadzone: f64,
    ) -> StickTestResult {
        let points: Vec<(f64, f64)> = samples
            .iter()
            .map(|s| {
                (
                    *s.axes.get(axis_x).unwrap_or(&0.0),
                    *s.axes.get(axis_y).unwrap_or(&0.0),
                )
            })
            .collect();
        if points.len() < 10 {
            return StickTestResult {
                status: TestStatus::NotTested,
                issues: vec!["Недостаточно данных для теста покоя".into()],
                ..Default::default()
            };
        }
        let metrics = analyze_drift(
            &points,
            self.config.stick_drift_warn,
            8.0,
            self.config.stick_drift_hold_ms,
            self.config.stick_drift_sample_ratio,
        );
        let detected = drift_detected(
            &metrics,
            self.config.stick_drift_warn,
            self.config.stick_drift_hold_ms,
            self.config.stick_drift_sample_ratio,
        );
        let level = classify_drift(
            metrics.max_radius,
            self.config.stick_drift_warn,
            self.config.stick_drift_fail,
        );
        let mut status = if detected {
            TestStatus::from_level(level)
        } else {
            TestStatus::Pass
        };
        let mut issues = Vec::new();
        if detected {
            issues.push(format!(
                "Дрифт: {:.1}% (среднее {:.1}%)",
                metrics.max_radius * 100.0,
                metrics.mean_radius * 100.0
            ));
        }
        if metrics.stddev_radius > self.config.stick_noise {
            if status == TestStatus::Pass {
                status = TestStatus::Warn;
            }
            issues.push(format!("Шум стика: σ={:.1}%", metrics.stddev_radius * 100.0));
        }
        let rest_points = if points.len() > 2000 {
            points[points.len() - 2000..].to_vec()
        } else {
            points
        };
        StickTestResult {
            status,
            drift_pct: metrics.max_radius * 100.0,
            mean_x: metrics.mean_x,
            mean_y: metrics.mean_y,
            max_radius: metrics.max_radius,
            physical_drift_pct: metrics.max_radius * 100.0,
            deadzone_pct: deadzone * 100.0,
            rest_points,
            issues,
            ..Default::default()
        }
    }

    pub fn analyze_range_step(
        &self,
        samples: &[GamepadSample],
        axis_x: &str,
        axis_y: &str,
        direction: &str,
    ) -> (bool, Vec<String>) {
        if samples.is_empty() {
            return (false, vec!["Нет данных диапазона".into()]);
        }
        let mut issues = Vec::new();
        let xs: Vec<f64> = samples
            .iter()
            .map(|s| *s.axes.get(axis_x).unwrap_or(&0.0))
            .collect();
        let ys: Vec<f64> = samples
            .iter()
            .map(|s| *s.axes.get(axis_y).unwrap_or(&0.0))
            .collect();
        if detect_spikes(&xs, 0.03) + detect_spikes(&ys, 0.03) > 2 {
            issues.push(format!("Скачки при движении ({direction})"));
        }
        let mut ok = true;
        match direction {
            "up" => {
                let min_y = ys.iter().copied().fold(f64::INFINITY, f64::min);
                if min_y > -0.85 {
                    ok = false;
                    issues.push(format!("Не достигнут верхний диапазон ({:.0}%)", min_y * 100.0));
                }
            }
            "down" => {
                let max_y = ys.iter().copied().fold(f64::NEG_INFINITY, f64::max);
                if max_y < 0.85 {
                    ok = false;
                    issues.push(format!("Не достигнут нижний диапазон ({:.0}%)", max_y * 100.0));
                }
            }
            "left" => {
                let min_x = xs.iter().copied().fold(f64::INFINITY, f64::min);
                if min_x > -0.85 {
                    ok = false;
                    issues.push(format!("Не достигнут левый диапазон ({:.0}%)", min_x * 100.0));
                }
            }
            "right" => {
                let max_x = xs.iter().copied().fold(f64::NEG_INFINITY, f64::max);
                if max_x < 0.85 {
                    ok = false;
                    issues.push(format!("Не достигнут правый диапазон ({:.0}%)", max_x * 100.0));
                }
            }
            _ => {}
        }
        (ok, issues)
    }

    pub fn analyze_circularity(
        &self,
        samples: &[GamepadSample],
        axis_x: &str,
        axis_y: &str,
    ) -> (f64, TestStatus, Vec<String>) {
        let points: Vec<(f64, f64, f64)> = samples
            .iter()
            .map(|s| {
                let x = *s.axes.get(axis_x).unwrap_or(&0.0);
                let y = *s.axes.get(axis_y).unwrap_or(&0.0);
                (x, y, radial_distance(x, y))
            })
            .collect();
        if points.len() < 20 {
            return (0.0, TestStatus::NotTested, vec![t("circularity.too_few")]);
        }
        let metrics = analyze_circularity(&points, CIRCULARITY_OUTER_MIN);
        if metrics.max_radius <= 0.0 {
            return (0.0, TestStatus::Warn, vec![t("circularity.too_few_rim")]);
        }
        let level = classify_circularity(metrics.circularity_error_pct);
        let mut issues = Vec::new();
        if level != "PASS" {
            issues.push(crate::i18n::t_vars(
                "circularity.error",
                &[("pct", format!("{:.1}", metrics.circularity_error_pct))],
            ));
        }
        (
            metrics.circularity_error_pct,
            TestStatus::from_level(level),
            issues,
        )
    }
}

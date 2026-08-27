#[derive(Clone, Debug, Default)]
pub struct DriftMetrics {
    pub mean_x: f64,
    pub mean_y: f64,
    pub max_radius: f64,
    pub mean_radius: f64,
    pub stddev_radius: f64,
    pub above_threshold_ratio: f64,
    pub sustained_ms: f64,
}

#[derive(Clone, Debug, Default)]
pub struct CircularityMetrics {
    pub max_radius: f64,
    pub circularity_error_pct: f64,
}

#[derive(Clone, Debug, Default)]
pub struct TriggerMetrics {
    pub min_value: f64,
    pub max_value: f64,
    pub rest_jitter: f64,
    pub spike_count: i32,
    pub returns_to_zero: bool,
}

#[derive(Clone, Debug, Default)]
pub struct EventRateMetrics {
    pub mean_interval_ms: f64,
    pub median_interval_ms: f64,
    pub max_interval_ms: f64,
    pub estimated_hz: f64,
}

pub const CIRCULARITY_OUTER_MIN: f64 = 0.55;
pub const CIRCULARITY_BINS: usize = 36;
pub const CIRCULARITY_MIN_BINS: usize = 16;
pub const CIRCULARITY_WARN_PCT: f64 = 38.0;
pub const CIRCULARITY_FAIL_PCT: f64 = 52.0;
pub const CIRCULARITY_SQUARE_MIN_PCT: f64 = 18.0;
pub const CIRCULARITY_SQUARE_MAX_PCT: f64 = 38.0;

pub fn radial_distance(x: f64, y: f64) -> f64 {
    (x * x + y * y).sqrt()
}

fn mean(values: &[f64]) -> f64 {
    if values.is_empty() {
        0.0
    } else {
        values.iter().sum::<f64>() / values.len() as f64
    }
}

fn pstdev(values: &[f64]) -> f64 {
    if values.len() < 2 {
        return 0.0;
    }
    let m = mean(values);
    let var = values.iter().map(|v| (v - m) * (v - m)).sum::<f64>() / values.len() as f64;
    var.sqrt()
}

fn median(values: &mut [f64]) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    values.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let n = values.len();
    if n % 2 == 1 {
        values[n / 2]
    } else {
        (values[n / 2 - 1] + values[n / 2]) / 2.0
    }
}

pub fn analyze_drift(
    points: &[(f64, f64)],
    threshold: f64,
    sample_interval_ms: f64,
    _hold_ms: i32,
    _sample_ratio: f64,
) -> DriftMetrics {
    if points.is_empty() {
        return DriftMetrics::default();
    }
    let xs: Vec<f64> = points.iter().map(|p| p.0).collect();
    let ys: Vec<f64> = points.iter().map(|p| p.1).collect();
    let radii: Vec<f64> = points.iter().map(|p| radial_distance(p.0, p.1)).collect();
    let max_r = radii.iter().copied().fold(0.0, f64::max);
    let above = radii.iter().filter(|r| **r > threshold).count();
    let mut sustained: f64 = 0.0;
    let mut streak = 0;
    for r in &radii {
        if *r > threshold {
            streak += 1;
            sustained = sustained.max(streak as f64 * sample_interval_ms);
        } else {
            streak = 0;
        }
    }
    DriftMetrics {
        mean_x: mean(&xs),
        mean_y: mean(&ys),
        max_radius: max_r,
        mean_radius: mean(&radii),
        stddev_radius: pstdev(&radii),
        above_threshold_ratio: above as f64 / radii.len() as f64,
        sustained_ms: sustained,
    }
}

pub fn drift_detected(metrics: &DriftMetrics, threshold: f64, hold_ms: i32, sample_ratio: f64) -> bool {
    if metrics.max_radius <= threshold {
        return false;
    }
    if metrics.sustained_ms >= f64::from(hold_ms) {
        return true;
    }
    metrics.above_threshold_ratio >= sample_ratio
}

pub fn classify_drift(max_radius: f64, warn: f64, fail: f64) -> &'static str {
    if max_radius > fail {
        "FAIL"
    } else if max_radius > warn {
        "WARN"
    } else {
        "PASS"
    }
}

pub fn detect_spikes(values: &[f64], threshold: f64) -> i32 {
    let mut spikes = 0;
    for i in 1..values.len() {
        if (values[i] - values[i - 1]).abs() > threshold {
            spikes += 1;
        }
    }
    spikes
}

pub fn analyze_circularity(points: &[(f64, f64, f64)], outer_min: f64) -> CircularityMetrics {
    if points.is_empty() {
        return CircularityMetrics::default();
    }
    let outer: Vec<&(f64, f64, f64)> = points.iter().filter(|p| p.2 >= outer_min).collect();
    if outer.len() < 12 {
        return CircularityMetrics::default();
    }
    let n = CIRCULARITY_BINS;
    let mut bins = vec![0.0; n];
    let mut filled = vec![false; n];
    for (x, y, r) in &outer {
        let idx = ((((y.atan2(*x) + std::f64::consts::PI) / std::f64::consts::TAU) * n as f64) as i32)
            .rem_euclid(n as i32) as usize;
        if *r > bins[idx] {
            bins[idx] = *r;
            filled[idx] = true;
        }
    }
    let envelope: Vec<f64> = bins
        .iter()
        .zip(filled.iter())
        .filter(|(_, ok)| **ok)
        .map(|(v, _)| *v)
        .collect();
    let mut quads = [false; 4];
    for (i, ok) in filled.iter().enumerate() {
        if *ok {
            quads[i * 4 / n] = true;
        }
    }
    if envelope.len() < CIRCULARITY_MIN_BINS || !quads.iter().all(|q| *q) {
        return CircularityMetrics::default();
    }
    let r_min = envelope.iter().copied().fold(f64::INFINITY, f64::min);
    let r_max = envelope.iter().copied().fold(0.0, f64::max);
    let error = if r_max > 0.0 {
        (r_max - r_min) / r_max * 100.0
    } else {
        0.0
    };
    CircularityMetrics {
        max_radius: r_max,
        circularity_error_pct: error,
    }
}

pub fn classify_circularity(error_pct: f64) -> &'static str {
    if error_pct > CIRCULARITY_FAIL_PCT {
        "FAIL"
    } else if error_pct > CIRCULARITY_WARN_PCT {
        "WARN"
    } else {
        "PASS"
    }
}

pub fn looks_like_square_gate(error_pct: f64) -> bool {
    (CIRCULARITY_SQUARE_MIN_PCT..=CIRCULARITY_SQUARE_MAX_PCT).contains(&error_pct)
}

pub fn analyze_trigger(values: &[f64], min_ok: f64, _max_ok: f64, _rest_jitter: f64) -> TriggerMetrics {
    if values.is_empty() {
        return TriggerMetrics::default();
    }
    let v_min = values.iter().copied().fold(f64::INFINITY, f64::min);
    let v_max = values.iter().copied().fold(0.0, f64::max);
    let rest_len = (values.len() / 10).max(1);
    let rest = &values[..rest_len.min(values.len())];
    let jitter = rest.iter().copied().fold(0.0, f64::max) - rest.iter().copied().fold(f64::INFINITY, f64::min);
    let spikes = detect_spikes(values, 0.03);
    let returns = v_min <= min_ok + 0.02;
    TriggerMetrics {
        min_value: v_min,
        max_value: v_max,
        rest_jitter: jitter,
        spike_count: spikes,
        returns_to_zero: returns,
    }
}

pub fn classify_trigger(m: &TriggerMetrics, min_ok: f64, max_ok: f64, jitter_ok: f64) -> &'static str {
    if m.max_value < max_ok || m.min_value > min_ok + 0.05 || !m.returns_to_zero {
        "FAIL"
    } else if m.max_value < max_ok + 0.02 || m.rest_jitter > jitter_ok || m.spike_count > 3 {
        "WARN"
    } else {
        "PASS"
    }
}

pub fn analyze_event_rate(timestamps_ns: &[u64]) -> EventRateMetrics {
    if timestamps_ns.len() < 2 {
        return EventRateMetrics::default();
    }
    let mut intervals: Vec<f64> = timestamps_ns
        .windows(2)
        .map(|w| (w[1] as f64 - w[0] as f64) / 1_000_000.0)
        .collect();
    let mean_i = mean(&intervals);
    let max_i = intervals.iter().copied().fold(0.0, f64::max);
    let median_i = median(&mut intervals);
    EventRateMetrics {
        mean_interval_ms: mean_i,
        median_interval_ms: median_i,
        max_interval_ms: max_i,
        estimated_hz: if mean_i > 0.0 { 1000.0 / mean_i } else { 0.0 },
    }
}

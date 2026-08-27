use crate::report::DiagnosticReport;

pub fn export_json(report: &DiagnosticReport) -> Result<String, String> {
    serde_json::to_string_pretty(report).map_err(|e| e.to_string())
}

pub fn export_csv(report: &DiagnosticReport) -> String {
    let mut rows: Vec<Vec<String>> = vec![
        vec!["section".into(), "key".into(), "value".into()],
        vec!["device".into(), "name".into(), report.device_name.clone()],
        vec!["device".into(), "path".into(), report.device_path.clone()],
        vec!["device".into(), "profile".into(), report.axis_profile.clone()],
        vec!["summary".into(), "overall".into(), report.overall.as_str().into()],
        vec!["summary".into(), "score".into(), report.score.to_string()],
        vec![
            "summary".into(),
            "duration_s".into(),
            report.duration_seconds.to_string(),
        ],
    ];
    for (test_id, status) in &report.tests {
        rows.push(vec!["test".into(), test_id.clone(), status.as_str().into()]);
    }
    for (prefix, stick) in [("left_stick", &report.left_stick), ("right_stick", &report.right_stick)] {
        rows.push(vec![prefix.into(), "status".into(), stick.status.as_str().into()]);
        rows.push(vec![prefix.into(), "drift_pct".into(), format!("{:.4}", stick.drift_pct)]);
        rows.push(vec![
            prefix.into(),
            "circularity_pct".into(),
            format!("{:.2}", stick.circularity_pct),
        ]);
        for issue in &stick.issues {
            rows.push(vec![prefix.into(), "issue".into(), issue.clone()]);
        }
    }
    for (prefix, trig) in [("lt", &report.lt), ("rt", &report.rt)] {
        rows.push(vec![prefix.into(), "status".into(), trig.status.as_str().into()]);
        rows.push(vec![prefix.into(), "min".into(), format!("{:.4}", trig.min_value)]);
        rows.push(vec![prefix.into(), "max".into(), format!("{:.4}", trig.max_value)]);
        for issue in &trig.issues {
            rows.push(vec![prefix.into(), "issue".into(), issue.clone()]);
        }
    }
    rows.push(vec![
        "buttons".into(),
        "status".into(),
        report.buttons.status.as_str().into(),
    ]);
    rows.push(vec![
        "buttons".into(),
        "pressed".into(),
        report.buttons.pressed_count.to_string(),
    ]);
    rows.push(vec![
        "buttons".into(),
        "held".into(),
        report.buttons.held_count.to_string(),
    ]);
    for item in &report.buttons.buttons {
        rows.push(vec![
            "button".into(),
            item.name.clone(),
            format!("pressed={}, held={}", item.pressed, item.held),
        ]);
        for issue in &item.issues {
            rows.push(vec!["button".into(), item.name.clone(), issue.clone()]);
        }
    }

    rows.into_iter()
        .map(|cols| {
            cols.into_iter()
                .map(|c| csv_escape(&c))
                .collect::<Vec<_>>()
                .join(",")
        })
        .collect::<Vec<_>>()
        .join("\n")
        + "\n"
}

fn csv_escape(value: &str) -> String {
    if value.contains([',', '"', '\n']) {
        format!("\"{}\"", value.replace('"', "\"\""))
    } else {
        value.to_string()
    }
}

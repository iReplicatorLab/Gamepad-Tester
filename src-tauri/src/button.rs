use crate::i18n::t_vars;
use crate::pad::{diagram_kind, BUTTONS, DPAD_BUTTONS};
use crate::report::{ButtonCheck, ButtonsTestResult};
use crate::status::TestStatus;

pub const PRESS_TIMEOUT: f64 = 12.0;
pub const STICKY_LIMIT: f64 = 1.0;

pub fn buttons_for_device(profile_name: &str, device_name: &str) -> Vec<(u8, String)> {
    let mut items: Vec<(u8, String)> = BUTTONS
        .iter()
        .chain(DPAD_BUTTONS.iter())
        .map(|(idx, name)| (*idx, (*name).to_string()))
        .collect();
    if diagram_kind(profile_name, device_name) == "360" {
        items.retain(|(idx, _)| *idx != 15);
    }
    items
}

pub fn check_button(
    index: u8,
    name: &str,
    pressed: bool,
    held: bool,
    skipped: bool,
    sticky: bool,
    sensitive: bool,
    tap_count: u32,
    seconds: i32,
) -> ButtonCheck {
    let mut issues = Vec::new();
    if skipped {
        issues.push(t_vars("button.skipped", &[("name", name.to_string())]));
    } else if !pressed {
        issues.push(t_vars("button.missed", &[("name", name.to_string())]));
    }
    if pressed && !skipped && !sensitive {
        issues.push(t_vars("button.insensitive", &[("name", name.to_string())]));
    }
    if pressed && !skipped && sticky {
        issues.push(t_vars("button.sticky", &[("name", name.to_string())]));
    }
    if pressed && !skipped && !held {
        issues.push(t_vars(
            "button.not_held",
            &[("name", name.to_string()), ("seconds", seconds.to_string())],
        ));
    }
    ButtonCheck {
        index,
        name: name.to_string(),
        pressed,
        held,
        skipped,
        sticky,
        sensitive,
        tap_count,
        issues,
    }
}

pub fn summarize(checks: Vec<ButtonCheck>) -> ButtonsTestResult {
    let issues: Vec<String> = checks.iter().flat_map(|c| c.issues.clone()).collect();
    let missed = checks.iter().filter(|c| !c.pressed || c.skipped).count();
    let not_held = checks
        .iter()
        .filter(|c| c.pressed && !c.held && !c.skipped)
        .count();
    let sticky_n = checks.iter().filter(|c| c.sticky).count();
    let dull_n = checks.iter().filter(|c| !c.sensitive).count();
    let status = if missed >= 2 || sticky_n >= 2 || dull_n >= 2 {
        TestStatus::Fail
    } else if missed > 0 || not_held > 0 || sticky_n > 0 || dull_n > 0 {
        TestStatus::Warn
    } else if !checks.is_empty() {
        TestStatus::Pass
    } else {
        TestStatus::NotTested
    };
    ButtonsTestResult {
        status,
        pressed_count: checks.iter().filter(|c| c.pressed).count() as i32,
        held_count: checks.iter().filter(|c| c.held).count() as i32,
        buttons: checks,
        issues,
    }
}

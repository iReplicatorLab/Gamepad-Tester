use std::collections::HashMap;

use serde::Serialize;

pub const APP_NAME: &str = "iReplicator Gamepad Tester";
pub const VERSION: &str = "0.1.0";
pub const REPORT_SCHEMA: &str = "diagnostic_report_v1";

pub const BUTTONS: &[(u8, &str)] = &[
    (0, "A"),
    (1, "B"),
    (2, "X"),
    (3, "Y"),
    (4, "LB"),
    (5, "RB"),
    (6, "View"),
    (7, "Menu"),
    (8, "Xbox"),
    (9, "L3"),
    (10, "R3"),
    (15, "Share"),
];

pub const DPAD_BUTTONS: &[(u8, &str)] = &[(11, "↑"), (12, "↓"), (13, "←"), (14, "→")];

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct AxisProfile {
    pub name: &'static str,
    pub label: &'static str,
    pub left_x: u8,
    pub left_y: u8,
    pub right_x: u8,
    pub right_y: u8,
    pub lt: u8,
    pub rt: u8,
}

pub const XBOX360_PROFILE: AxisProfile = AxisProfile {
    name: "xbox360",
    label: "Xbox 360",
    left_x: 0,
    left_y: 1,
    lt: 2,
    right_x: 3,
    right_y: 4,
    rt: 5,
};

pub const XINPUT_PROFILE: AxisProfile = AxisProfile {
    name: "xinput",
    label: "Xbox One / Series",
    left_x: 0,
    left_y: 1,
    right_x: 2,
    right_y: 3,
    lt: 4,
    rt: 5,
};

#[derive(Clone, Copy, Debug, Default, Serialize)]
pub struct LogicalAxes {
    pub left_x: f64,
    pub left_y: f64,
    pub right_x: f64,
    pub right_y: f64,
    pub lt: f64,
    pub rt: f64,
}

impl AxisProfile {
    pub fn axis_index(&self, logical: &str) -> Option<u8> {
        match logical {
            "left_x" => Some(self.left_x),
            "left_y" => Some(self.left_y),
            "right_x" => Some(self.right_x),
            "right_y" => Some(self.right_y),
            "lt" => Some(self.lt),
            "rt" => Some(self.rt),
            _ => None,
        }
    }

    pub fn read(&self, axes: &HashMap<u8, f64>) -> LogicalAxes {
        LogicalAxes {
            left_x: *axes.get(&self.left_x).unwrap_or(&0.0),
            left_y: *axes.get(&self.left_y).unwrap_or(&0.0),
            right_x: *axes.get(&self.right_x).unwrap_or(&0.0),
            right_y: *axes.get(&self.right_y).unwrap_or(&0.0),
            lt: *axes.get(&self.lt).unwrap_or(&-1.0),
            rt: *axes.get(&self.rt).unwrap_or(&-1.0),
        }
    }

    pub fn read_map(&self, axes: &HashMap<u8, f64>) -> HashMap<String, f64> {
        let parsed = self.read(axes);
        HashMap::from([
            ("left_x".into(), parsed.left_x),
            ("left_y".into(), parsed.left_y),
            ("right_x".into(), parsed.right_x),
            ("right_y".into(), parsed.right_y),
            ("lt".into(), parsed.lt),
            ("rt".into(), parsed.rt),
        ])
    }
}

#[derive(Clone, Debug)]
pub struct PadState {
    pub connected: bool,
    pub name: String,
    pub hint: String,
    pub transport: String,
    pub buttons: HashMap<u8, bool>,
    pub axes: HashMap<u8, f64>,
    pub hat: (i32, i32),
}

impl Default for PadState {
    fn default() -> Self {
        Self {
            connected: false,
            name: String::new(),
            hint: String::new(),
            transport: String::new(),
            buttons: HashMap::new(),
            axes: HashMap::new(),
            hat: (0, 0),
        }
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct PadStatePayload {
    pub connected: bool,
    pub name: String,
    pub axis_profile: String,
    pub hint: String,
    pub transport: String,
    pub diagram_kind: String,
    pub buttons: HashMap<String, bool>,
    pub axes: LogicalAxes,
}

pub fn diagram_kind(profile_name: &str, device_name: &str) -> &'static str {
    let text = format!("{profile_name} {device_name}").to_lowercase();
    if profile_name == "xbox360" || text.contains("360") {
        "360"
    } else {
        "series"
    }
}

pub fn detect_axis_profile_from_name(name: &str, num_axes: Option<usize>) -> AxisProfile {
    let lowered = name.to_lowercase();
    if ["360", "x-box 360", "xbox wireless receiver", "wireless receiver (xbox)"]
        .iter()
        .any(|token| lowered.contains(token))
    {
        return XBOX360_PROFILE;
    }
    if num_axes == Some(6)
        && ["xbox", "x-box", "microsoft"]
            .iter()
            .any(|token| lowered.contains(token))
        && !lowered.contains("series")
        && !lowered.contains("one")
    {
        return XBOX360_PROFILE;
    }
    XINPUT_PROFILE
}

pub fn normalize_trigger(value: f64) -> f64 {
    if value < 0.0 {
        (value + 1.0) / 2.0
    } else {
        value.clamp(0.0, 1.0)
    }
}

pub fn pad_state_payload(state: &PadState, profile: AxisProfile) -> PadStatePayload {
    let parsed = profile.read(&state.axes);
    PadStatePayload {
        connected: state.connected,
        name: state.name.clone(),
        axis_profile: if state.connected {
            profile.label.to_string()
        } else {
            String::new()
        },
        hint: state.hint.clone(),
        transport: state.transport.clone(),
        diagram_kind: diagram_kind(profile.name, &state.name).to_string(),
        buttons: state
            .buttons
            .iter()
            .map(|(k, v)| (k.to_string(), *v))
            .collect(),
        axes: LogicalAxes {
            left_x: parsed.left_x,
            left_y: parsed.left_y,
            right_x: parsed.right_x,
            right_y: parsed.right_y,
            lt: normalize_trigger(parsed.lt),
            rt: normalize_trigger(parsed.rt),
        },
    }
}

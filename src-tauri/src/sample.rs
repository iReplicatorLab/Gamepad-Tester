use std::collections::HashMap;

#[derive(Clone, Debug)]
pub struct GamepadSample {
    pub timestamp_ns: u64,
    pub axes: HashMap<String, f64>,
    #[allow(dead_code)]
    pub buttons: HashMap<u8, bool>,
    #[allow(dead_code)]
    pub hat: (i32, i32),
}

#[derive(Clone, Debug)]
pub struct RawInputEvent {
    pub timestamp_ns: u64,
    pub event_type: String,
    pub code: String,
    pub value: String,
    pub test_id: String,
}

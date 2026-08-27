use std::collections::VecDeque;
use std::sync::{Arc, Mutex};

use crate::sample::{GamepadSample, RawInputEvent};

const MAX_SAMPLES: usize = 50_000;
const MAX_EVENTS: usize = 100_000;
const RING_SIZE: usize = 500;

#[derive(Clone, Default)]
pub struct EventLogger {
    inner: Arc<Mutex<Inner>>,
}

struct Inner {
    samples: VecDeque<GamepadSample>,
    events: VecDeque<RawInputEvent>,
    ring_samples: VecDeque<GamepadSample>,
    ring_events: VecDeque<RawInputEvent>,
    active: bool,
    test_id: String,
}

impl Default for Inner {
    fn default() -> Self {
        Self {
            samples: VecDeque::with_capacity(1024),
            events: VecDeque::with_capacity(1024),
            ring_samples: VecDeque::with_capacity(RING_SIZE),
            ring_events: VecDeque::with_capacity(RING_SIZE),
            active: false,
            test_id: String::new(),
        }
    }
}

impl EventLogger {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn is_active(&self) -> bool {
        self.inner.lock().unwrap().active
    }

    pub fn start(&self, test_id: &str) {
        let mut inner = self.inner.lock().unwrap();
        inner.active = true;
        inner.test_id = test_id.to_string();
        inner.samples.clear();
        inner.events.clear();
    }

    pub fn stop(&self) {
        let mut inner = self.inner.lock().unwrap();
        inner.active = false;
        inner.test_id.clear();
    }

    pub fn add_sample(&self, sample: GamepadSample) {
        let mut inner = self.inner.lock().unwrap();
        if inner.ring_samples.len() == RING_SIZE {
            inner.ring_samples.pop_front();
        }
        inner.ring_samples.push_back(sample.clone());
        if inner.active {
            if inner.samples.len() == MAX_SAMPLES {
                inner.samples.pop_front();
            }
            inner.samples.push_back(sample);
        }
    }

    pub fn add_event(&self, mut event: RawInputEvent) {
        let mut inner = self.inner.lock().unwrap();
        if inner.ring_events.len() == RING_SIZE {
            inner.ring_events.pop_front();
        }
        inner.ring_events.push_back(event.clone());
        if inner.active {
            if event.test_id.is_empty() && !inner.test_id.is_empty() {
                event.test_id = inner.test_id.clone();
            }
            if inner.events.len() == MAX_EVENTS {
                inner.events.pop_front();
            }
            inner.events.push_back(event);
        }
    }

    pub fn get_samples(&self) -> Vec<GamepadSample> {
        self.inner.lock().unwrap().samples.iter().cloned().collect()
    }

    pub fn get_events(&self) -> Vec<RawInputEvent> {
        self.inner.lock().unwrap().events.iter().cloned().collect()
    }

    pub fn recent_events(&self, limit: usize) -> Vec<RawInputEvent> {
        let inner = self.inner.lock().unwrap();
        inner
            .ring_events
            .iter()
            .rev()
            .take(limit)
            .cloned()
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
            .collect()
    }
}

use std::collections::HashMap;

use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub enum TestStatus {
    #[serde(rename = "PASS")]
    Pass,
    #[serde(rename = "WARN")]
    Warn,
    #[serde(rename = "FAIL")]
    Fail,
    #[serde(rename = "NOT_TESTED")]
    #[default]
    NotTested,
    #[serde(rename = "NOT_SUPPORTED")]
    NotSupported,
}

impl TestStatus {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Pass => "PASS",
            Self::Warn => "WARN",
            Self::Fail => "FAIL",
            Self::NotTested => "NOT_TESTED",
            Self::NotSupported => "NOT_SUPPORTED",
        }
    }

    pub fn from_level(level: &str) -> Self {
        match level {
            "FAIL" => Self::Fail,
            "WARN" => Self::Warn,
            "PASS" => Self::Pass,
            "NOT_SUPPORTED" => Self::NotSupported,
            _ => Self::NotTested,
        }
    }
}

pub fn overall_from_tests(tests: &HashMap<String, TestStatus>) -> TestStatus {
    let values: Vec<TestStatus> = tests.values().copied().collect();
    if values.iter().any(|s| *s == TestStatus::Fail) {
        return TestStatus::Fail;
    }
    if values.iter().any(|s| *s == TestStatus::Warn) {
        return TestStatus::Warn;
    }
    let tested: Vec<TestStatus> = values
        .into_iter()
        .filter(|s| !matches!(s, TestStatus::NotTested | TestStatus::NotSupported))
        .collect();
    if tested.is_empty() {
        TestStatus::NotTested
    } else if tested.iter().all(|s| *s == TestStatus::Pass) {
        TestStatus::Pass
    } else {
        TestStatus::Warn
    }
}

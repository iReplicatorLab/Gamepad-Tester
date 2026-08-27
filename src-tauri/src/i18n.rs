use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};

static STRINGS: OnceLock<Mutex<(String, HashMap<String, String>)>> = OnceLock::new();

fn store() -> &'static Mutex<(String, HashMap<String, String>)> {
    STRINGS.get_or_init(|| Mutex::new(("ru".into(), load_locale_map("ru"))))
}

fn load_locale_map(code: &str) -> HashMap<String, String> {
    let raw = if code == "en" {
        include_str!("../../locale/en.json")
    } else {
        include_str!("../../locale/ru.json")
    };
    serde_json::from_str(raw).unwrap_or_default()
}

pub fn set_locale(code: &str) {
    let locale = if code == "en" { "en" } else { "ru" };
    let map = load_locale_map(locale);
    *store().lock().unwrap() = (locale.to_string(), map);
}

pub fn locale_map(code: &str) -> HashMap<String, String> {
    load_locale_map(if code == "en" { "en" } else { "ru" })
}

pub fn t(key: &str) -> String {
    t_vars(key, &[])
}

pub fn t_vars(key: &str, vars: &[(&str, String)]) -> String {
    let guard = store().lock().unwrap();
    let mut text = guard.1.get(key).cloned().unwrap_or_else(|| key.to_string());
    drop(guard);
    for (name, value) in vars {
        text = text.replace(&format!("{{{name}}}"), value);
    }
    text
}

pub fn init_from_config(locale: &str) {
    set_locale(locale);
}

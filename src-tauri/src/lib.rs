mod backend;
mod button;
mod config;
mod export;
mod i18n;
mod logger;
mod pad;
mod report;
mod sample;
mod service;
mod session;
mod stats;
mod status;
mod stick;
mod trigger;

use std::process::Command;
use std::sync::Mutex;

use tauri::{Manager, State};
use tauri_plugin_dialog::DialogExt;

use crate::config::DiagnosticConfig;
use crate::i18n::locale_map;
use crate::pad::PadStatePayload;
use crate::service::{GamepadService, LogPayload, ReportPayload};
use crate::session::DiagnosticsStatus;

struct AppState {
    service: Mutex<GamepadService>,
}

#[tauri::command]
fn health() -> serde_json::Value {
    serde_json::json!({ "ok": true })
}

#[tauri::command]
fn get_pad_state(state: State<'_, AppState>) -> PadStatePayload {
    state.service.lock().unwrap().get_state_payload()
}

#[tauri::command]
fn get_config(state: State<'_, AppState>) -> DiagnosticConfig {
    state.service.lock().unwrap().config_json()
}

#[tauri::command]
fn put_config(state: State<'_, AppState>, config: serde_json::Value) -> DiagnosticConfig {
    state.service.lock().unwrap().update_config(config)
}

#[tauri::command]
fn get_locale_strings(code: String) -> std::collections::HashMap<String, String> {
    locale_map(&code)
}

#[tauri::command]
fn get_diagnostics_status(state: State<'_, AppState>) -> DiagnosticsStatus {
    state.service.lock().unwrap().get_diagnostics_payload()
}

#[tauri::command]
fn start_diagnostics(state: State<'_, AppState>, tests: Option<Vec<String>>) -> serde_json::Value {
    state.service.lock().unwrap().start_diagnostics(tests);
    serde_json::json!({ "ok": true })
}

#[tauri::command]
fn stop_diagnostics(state: State<'_, AppState>) -> serde_json::Value {
    state.service.lock().unwrap().stop_diagnostics();
    serde_json::json!({ "ok": true })
}

#[tauri::command]
fn skip_step(state: State<'_, AppState>) -> serde_json::Value {
    state.service.lock().unwrap().skip_step();
    serde_json::json!({ "ok": true })
}

#[tauri::command]
fn get_report(state: State<'_, AppState>) -> ReportPayload {
    state.service.lock().unwrap().get_report_payload()
}

#[tauri::command]
fn get_log(state: State<'_, AppState>, since: Option<u64>) -> LogPayload {
    state.service.lock().unwrap().get_log(since.unwrap_or(0) as usize)
}

#[tauri::command]
fn rumble(
    state: State<'_, AppState>,
    left: f64,
    right: f64,
    duration_ms: Option<u32>,
) -> serde_json::Value {
    let ok = state
        .service
        .lock()
        .unwrap()
        .rumble(left, right, duration_ms.unwrap_or(500));
    serde_json::json!({ "ok": ok })
}

#[tauri::command]
fn export_report(app: tauri::AppHandle, state: State<'_, AppState>, format: String) -> Result<(), String> {
    let content = if format == "csv" {
        state.service.lock().unwrap().export_csv()
    } else {
        state.service.lock().unwrap().export_json()?
    };
    let ext = if format == "csv" { "csv" } else { "json" };
    let path = app
        .dialog()
        .file()
        .set_file_name(format!("gamepad-report.{ext}"))
        .add_filter(ext.to_uppercase(), &[ext])
        .blocking_save_file()
        .ok_or_else(|| "save cancelled".to_string())?;
    let path = path
        .into_path()
        .map_err(|e| format!("invalid save path: {e}"))?;
    std::fs::write(path, content.as_bytes()).map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
fn open_config_folder() -> Result<(), String> {
    let dir = DiagnosticConfig::config_dir();
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    if cfg!(target_os = "linux") {
        Command::new("xdg-open").arg(&dir).spawn().map_err(|e| e.to_string())?;
    } else if cfg!(target_os = "macos") {
        Command::new("open").arg(&dir).spawn().map_err(|e| e.to_string())?;
    } else {
        Command::new("explorer").arg(&dir).spawn().map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn skip_broken_gtk_hicolor_themes() {
    #[cfg(target_os = "linux")]
    {
        const DEFAULT_DIRS: &str = "/usr/local/share:/usr/share";
        let raw = std::env::var("XDG_DATA_DIRS").unwrap_or_else(|_| DEFAULT_DIRS.into());
        let kept: Vec<&str> = raw
            .split(':')
            .filter(|dir| !dir.is_empty() && hicolor_theme_usable(dir))
            .collect();
        let value = if kept.is_empty() {
            DEFAULT_DIRS.to_string()
        } else {
            kept.join(":")
        };
        if value != raw {
            std::env::set_var("XDG_DATA_DIRS", value);
        }
    }
}

#[cfg(target_os = "linux")]
fn hicolor_theme_usable(data_dir: &str) -> bool {
    let index = std::path::Path::new(data_dir).join("icons/hicolor/index.theme");
    match std::fs::read_to_string(index) {
        Ok(text) => {
            text.lines().any(|line| line.starts_with("Name="))
                && text.lines().any(|line| line.starts_with("Directories="))
        }
        Err(_) => true,
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    skip_broken_gtk_hicolor_themes();
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(AppState {
            service: Mutex::new(GamepadService::new()),
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                window.state::<AppState>().service.lock().unwrap().shutdown();
            }
        })
        .invoke_handler(tauri::generate_handler![
            health,
            get_pad_state,
            get_config,
            put_config,
            get_locale_strings,
            get_diagnostics_status,
            start_diagnostics,
            stop_diagnostics,
            skip_step,
            get_report,
            get_log,
            rumble,
            export_report,
            open_config_folder
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

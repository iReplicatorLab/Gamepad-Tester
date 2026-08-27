use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

use reqwest::blocking::Client;
use tauri::{Manager, State};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

enum RunningSidecar {
    Python(Child),
    Bundled(CommandChild),
}

impl RunningSidecar {
    fn kill(self) {
        match self {
            RunningSidecar::Python(mut child) => {
                let _ = child.kill();
                let _ = child.wait();
            }
            RunningSidecar::Bundled(child) => {
                let _ = child.kill();
            }
        }
    }
}

struct SidecarState {
    process: Mutex<Option<RunningSidecar>>,
    url: Mutex<Option<String>>,
}

impl SidecarState {
    fn new() -> Self {
        Self {
            process: Mutex::new(None),
            url: Mutex::new(None),
        }
    }
}

fn project_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("project root")
        .to_path_buf()
}

fn parse_service_url(line: &str) -> Option<String> {
    line.strip_prefix("SERVICE_URL=")
        .map(str::trim)
        .map(ToString::to_string)
}

fn read_service_url_from_reader(mut reader: impl BufRead) -> Option<String> {
    let mut buf = String::new();
    loop {
        buf.clear();
        match reader.read_line(&mut buf) {
            Ok(0) => return None,
            Ok(_) => {
                if let Some(url) = parse_service_url(buf.trim()) {
                    return Some(url);
                }
            }
            Err(_) => return None,
        }
    }
}

fn python_candidates() -> Vec<&'static str> {
    if cfg!(windows) {
        vec!["python", "py", "python3"]
    } else {
        vec!["python3", "python"]
    }
}

fn spawn_python_sidecar() -> Result<(RunningSidecar, String), String> {
    let root = project_root();
    let script = root.join("service").join("gamepad_service.py");
    let mut last_err = String::new();
    let mut child = None;
    for python in python_candidates() {
        match Command::new(python)
            .arg(&script)
            .args(["--host", "127.0.0.1", "--port", "0"])
            .stdout(Stdio::piped())
            .stderr(if cfg!(debug_assertions) {
                Stdio::piped()
            } else {
                Stdio::null()
            })
            .spawn()
        {
            Ok(spawned) => {
                child = Some(spawned);
                break;
            }
            Err(e) => last_err = format!("{python}: {e}"),
        }
    }
    let mut child = child.ok_or_else(|| format!("failed to spawn python sidecar ({last_err})"))?;
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "sidecar stdout unavailable".to_string())?;
    if cfg!(debug_assertions) {
        if let Some(stderr) = child.stderr.take() {
            std::thread::spawn(move || {
                let mut reader = BufReader::new(stderr);
                let mut line = String::new();
                loop {
                    line.clear();
                    if reader.read_line(&mut line).ok().unwrap_or(0) == 0 {
                        break;
                    }
                    eprintln!("sidecar stderr: {}", line.trim_end());
                }
            });
        }
    }
    let mut reader = BufReader::new(stdout);
    let url = read_service_url_from_reader(&mut reader)
        .ok_or_else(|| "sidecar did not report SERVICE_URL".to_string())?;
    std::thread::spawn(move || {
        let mut line = String::new();
        loop {
            line.clear();
            if reader.read_line(&mut line).ok().unwrap_or(0) == 0 {
                break;
            }
        }
    });
    Ok((RunningSidecar::Python(child), url))
}

fn spawn_bundled_sidecar(app: &tauri::App) -> Result<(RunningSidecar, String), String> {
    let (mut rx, child) = app
        .shell()
        .sidecar("gamepad-service")
        .map_err(|e| e.to_string())?
        .args(["--host", "127.0.0.1", "--port", "0"])
        .spawn()
        .map_err(|e| e.to_string())?;

    let mut url = None;
    let deadline = std::time::Instant::now() + Duration::from_secs(15);
    while url.is_none() && std::time::Instant::now() < deadline {
        if let Some(event) = rx.blocking_recv() {
            if let CommandEvent::Stdout(line_bytes) = event {
                let line = String::from_utf8_lossy(&line_bytes);
                if let Some(found) = parse_service_url(line.trim()) {
                    url = Some(found);
                }
            }
        } else {
            break;
        }
    }
    let url = url.ok_or_else(|| "sidecar did not report SERVICE_URL".to_string())?;
    Ok((RunningSidecar::Bundled(child), url))
}

fn start_sidecar(app: &tauri::App, state: &SidecarState) -> Result<String, String> {
    let (process, url) = if cfg!(debug_assertions) {
        spawn_python_sidecar().or_else(|_| spawn_bundled_sidecar(app))?
    } else {
        spawn_bundled_sidecar(app)?
    };
    *state.process.lock().unwrap() = Some(process);
    *state.url.lock().unwrap() = Some(url.clone());
    Ok(url)
}

fn stop_sidecar(state: &SidecarState) {
    if let Some(process) = state.process.lock().unwrap().take() {
        process.kill();
    }
    *state.url.lock().unwrap() = None;
}

#[tauri::command]
fn get_service_url(state: State<'_, SidecarState>) -> Result<String, String> {
    state
        .url
        .lock()
        .unwrap()
        .clone()
        .ok_or_else(|| "sidecar not ready".to_string())
}

#[tauri::command]
fn export_report(
    app: tauri::AppHandle,
    state: State<'_, SidecarState>,
    format: String,
) -> Result<(), String> {
    let url = get_service_url(state)?;
    let endpoint = if format == "csv" {
        "/api/export/csv"
    } else {
        "/api/export/json"
    };
    let client = Client::builder()
        .timeout(Duration::from_secs(30))
        .build()
        .map_err(|e| e.to_string())?;
    let response = client
        .get(format!("{url}{endpoint}"))
        .send()
        .map_err(|e| e.to_string())?;
    let body = response.text().map_err(|e| e.to_string())?;
    let payload: serde_json::Value =
        serde_json::from_str(&body).map_err(|e| e.to_string())?;
    let content = payload
        .get("content")
        .and_then(|v| v.as_str())
        .ok_or_else(|| "export response missing content".to_string())?;
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
    let dir = std::env::var("HOME")
        .or_else(|_| std::env::var("USERPROFILE"))
        .map(PathBuf::from)
        .map_err(|_| "home dir unavailable".to_string())?
        .join(".config")
        .join("ireplicator-gamepad-tester");
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

/// Flatpak exports an empty `icons/hicolor/index.theme`. GTK loads it before
/// `/usr/share/icons/hicolor` and prints "Theme file for hicolor has no name".
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
    let sidecar_state = SidecarState::new();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(sidecar_state)
        .setup(|app| {
            let state = app.state::<SidecarState>();
            let service_url = start_sidecar(app, &state)?;
            eprintln!("sidecar ready at {service_url}");
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                let state = window.state::<SidecarState>();
                stop_sidecar(&state);
            }
        })
        .invoke_handler(tauri::generate_handler![
            get_service_url,
            export_report,
            open_config_folder
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

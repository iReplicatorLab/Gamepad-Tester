import { invoke, isTauri } from "@tauri-apps/api/core";

async function request<T>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  return invoke<T>(cmd, args);
}

export type PadState = {
  connected: boolean;
  name: string;
  axis_profile: string;
  hint: string;
  transport: string;
  diagram_kind: string;
  buttons: Record<string, boolean>;
  axes: { left_x: number; left_y: number; right_x: number; right_y: number; lt: number; rt: number };
};

export type DiagnosticsStatus = {
  running: boolean;
  progress: number;
  step: string;
  focus: string;
  phase: string;
  step_index: number;
  step_total: number;
  can_skip: boolean;
  selected: string[];
  failed_buttons: number[];
  passed_buttons: number[];
  hold: { total: number; remaining: number } | null;
  cue: { side: string; motion: string; repeats: number };
  hold_seconds: number;
  tests: Record<string, string>;
  overall: string;
  score: number;
  category_done: number;
  category_total: number;
};

export const api = {
  health: () => request<{ ok: boolean }>("health"),
  state: () => request<PadState>("get_pad_state"),
  config: {
    get: () => request<Record<string, unknown>>("get_config"),
    put: (body: Record<string, unknown>) => request<Record<string, unknown>>("put_config", { config: body }),
  },
  locale: (code: string) => request<Record<string, string>>("get_locale_strings", { code }),
  assetUrl: (name: string) => `./assets/${name}`,
  diagnostics: {
    status: () => request<DiagnosticsStatus>("get_diagnostics_status"),
    start: (tests?: string[]) => request<{ ok: boolean }>("start_diagnostics", { tests }),
    stop: () => request<{ ok: boolean }>("stop_diagnostics"),
    skip: () => request<{ ok: boolean }>("skip_step"),
  },
  report: () => request<{ report: Record<string, unknown>; lines: string[] }>("get_report"),
  log: (since = 0) => request<{ lines: string[]; next: number }>("get_log", { since }),
  rumble: (left: number, right: number, duration_ms = 800) =>
    request<{ ok: boolean }>("rumble", { left, right, durationMs: duration_ms }),
  export: (format: "json" | "csv") => invoke<void>("export_report", { format }),
};

export { isTauri };

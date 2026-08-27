let baseUrl = import.meta.env.VITE_SERVICE_URL ?? "";

export function setServiceUrl(url: string): void {
  baseUrl = url.replace(/\/$/, "");
}

export function serviceUrl(): string {
  return baseUrl;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${baseUrl}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return (await res.json()) as T;
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
  health: () => request<{ ok: boolean }>("/api/health"),
  state: () => request<PadState>("/api/state"),
  config: {
    get: () => request<Record<string, unknown>>("/api/config"),
    put: (body: Record<string, unknown>) =>
      request<Record<string, unknown>>("/api/config", { method: "PUT", body: JSON.stringify(body) }),
  },
  locale: (code: string) => request<Record<string, string>>(`/api/locale/${code}`),
  assetUrl: (name: string) => `${baseUrl}/api/assets/${name}`,
  diagnostics: {
    status: () => request<DiagnosticsStatus>("/api/diagnostics/status"),
    start: (tests?: string[]) =>
      request<{ ok: boolean }>("/api/diagnostics/start", {
        method: "POST",
        body: JSON.stringify({ tests }),
      }),
    stop: () => request<{ ok: boolean }>("/api/diagnostics/stop", { method: "POST", body: "{}" }),
    skip: () => request<{ ok: boolean }>("/api/diagnostics/skip", { method: "POST", body: "{}" }),
  },
  report: () => request<{ report: Record<string, unknown>; lines: string[] }>("/api/report"),
  log: (since = 0) => request<{ lines: string[]; next: number }>(`/api/log?since=${since}`),
  rumble: (left: number, right: number, duration_ms = 800) =>
    request<{ ok: boolean }>("/api/rumble", {
      method: "POST",
      body: JSON.stringify({ left, right, duration_ms }),
    }),
  export: (format: "json" | "csv") => request<{ content: string }>(`/api/export/${format}`),
};

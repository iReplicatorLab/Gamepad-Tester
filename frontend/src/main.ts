import "./style.css";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { api, setServiceUrl, serviceUrl, type DiagnosticsStatus, type PadState } from "./api";
import { getLocale, loadLocale, t } from "./i18n";
import { LivePad } from "./live-pad";

const SITE_URL = "https://ireplicator.com/";
type TabId = "diagnostics" | "log" | "report";

const app = document.querySelector<HTMLDivElement>("#app")!;
let activeTab: TabId = "diagnostics";
let padState: PadState | null = null;
let diagStatus: DiagnosticsStatus | null = null;
let logLines: string[] = [];
let reportLines: string[] = [];
let livePad: LivePad | null = null;
let configCache: Record<string, unknown> = {};
let shellBuilt = false;

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className?: string,
  text?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function showMessage(text: string): void {
  app.replaceChildren();
  const msg = el("pre", "panel log-box");
  msg.textContent = text;
  app.appendChild(msg);
  shellBuilt = false;
}

async function initServiceUrl(): Promise<void> {
  if (isTauri()) {
    for (let i = 0; i < 60; i += 1) {
      try {
        const url = await invoke<string>("get_service_url");
        setServiceUrl(url);
        return;
      } catch {
        await new Promise((r) => setTimeout(r, 250));
      }
    }
    throw new Error("Sidecar not ready. Restart the app.");
  }
  const envUrl = import.meta.env.VITE_SERVICE_URL as string | undefined;
  if (envUrl) setServiceUrl(envUrl);
  else setServiceUrl("http://127.0.0.1:8765");
}

function diagnosticsFinished(): boolean {
  if (!diagStatus || diagStatus.running) return false;
  if ((diagStatus.progress ?? 0) >= 0.999) return true;
  return (diagStatus.overall ?? "NOT_TESTED") !== "NOT_TESTED";
}

function startTests(tests: string[]): void {
  if (!padState?.connected) {
    const text = document.querySelector(".step-text");
    if (text) text.textContent = t("status.disconnected");
    return;
  }
  void api.diagnostics.start(tests).then(() => void refreshAll());
}

function renderDiagnosticsView(root: HTMLElement): void {
  livePad?.destroy();
  root.replaceChildren();

  const toolbar = el("div", "toolbar");
  const runBtn = el("button", "btn primary", `▶  ${t("diag.run_full")}`);
  runBtn.onclick = () => startTests(["sticks", "triggers", "buttons"]);
  toolbar.appendChild(runBtn);
  for (const test of ["sticks", "triggers", "buttons"] as const) {
    const chip = el("button", "chip", t(`diag.${test}`));
    chip.dataset.test = test;
    chip.onclick = () => startTests([test]);
    toolbar.appendChild(chip);
  }
  toolbar.appendChild(el("div", "toolbar-spacer"));
  const stopBtn = el("button", "btn hidden", `■  ${t("diag.stop")}`);
  stopBtn.id = "diag-stop";
  stopBtn.onclick = () => void api.diagnostics.stop().then(() => void refreshAll());
  const reportBtn = el("button", "btn primary hidden", t("diag.open_report"));
  reportBtn.id = "diag-open-report";
  reportBtn.onclick = () => {
    activeTab = "report";
    render();
  };
  toolbar.append(stopBtn, reportBtn);

  const card = el("div", "step-card idle");
  card.id = "step-card";
  const kicker = el("div", "step-kicker", t("diag.step_idle_kicker"));
  kicker.id = "step-kicker";
  const row = el("div", "step-row");
  const text = el("div", "step-text", t("diag.hint_idle"));
  text.id = "step-text";
  const skipBtn = el("button", "btn ghost hidden", t("diag.skip"));
  skipBtn.id = "diag-skip";
  skipBtn.onclick = () => void api.diagnostics.skip().then(() => void refreshAll());
  row.append(text, skipBtn);
  const state = el("div", "step-state idle hidden");
  state.id = "step-state";
  card.append(kicker, row, state);

  livePad = new LivePad((left, right, durationMs) => {
    void api.rumble(left, right, durationMs);
  });

  const result = el("div", "result-card hidden");
  result.id = "result-card";
  result.innerHTML = `
    <div id="prog-panel" class="hidden">
      <div class="progress-head">
        <div class="progress-caption">${t("diag.progress_title").toUpperCase()}</div>
        <div class="progress-count" id="progress-count">0 / 0</div>
      </div>
      <div class="tech-progress"><span id="progress-fill"></span></div>
    </div>
    <div class="score-badge hidden" id="score-badge"></div>
    <div class="device-line hidden" id="score-hint">${t("diag.score_hint")}</div>
    <pre class="device-line hidden" id="result-lines"></pre>`;

  root.append(toolbar, card, livePad.root, result);
  syncDiagnosticsChrome();
  livePad.update(padState, diagStatus);
}

function setStepCard(mode: "idle" | "waiting" | "holding" | "done"): void {
  const card = document.querySelector("#step-card");
  if (!card) return;
  card.classList.remove("idle", "waiting", "holding", "done");
  card.classList.add(mode);
}

function setStepState(mode: "idle" | "hold" | "done", text: string, visible: boolean): void {
  const node = document.querySelector("#step-state");
  if (!node) return;
  node.classList.remove("idle", "hold", "done");
  node.classList.add(mode);
  node.textContent = text;
  node.classList.toggle("hidden", !visible);
}

function syncDiagnosticsChrome(): void {
  const running = Boolean(diagStatus?.running);
  const finished = diagnosticsFinished();
  const kicker = document.querySelector("#step-kicker");
  const text = document.querySelector("#step-text");
  const skip = document.querySelector("#diag-skip");
  const stop = document.querySelector("#diag-stop");
  const openReport = document.querySelector("#diag-open-report");
  if (!kicker || !text || !skip || !stop || !openReport) return;

  skip.classList.toggle("hidden", !diagStatus?.can_skip);
  stop.classList.toggle("hidden", !running);
  openReport.classList.toggle("hidden", !(finished && !running));

  if (running) {
    const current = Math.min(diagStatus!.category_total || diagStatus!.step_total, (diagStatus!.category_done ?? 0) + 1);
    const total = diagStatus!.category_total || diagStatus!.step_total;
    kicker.textContent = t("diag.step_n", { current, total });
    text.textContent = diagStatus!.step || t("diag.hint_idle");
    const holding = Boolean(diagStatus!.hold && diagStatus!.hold.remaining > 0);
    if (holding) {
      setStepCard("holding");
      setStepState("hold", t("diag.state_holding"), true);
    } else {
      setStepCard("waiting");
      setStepState("idle", t("diag.state_waiting"), true);
    }
  } else if (finished) {
    const done = diagStatus?.category_done ?? diagStatus?.step_total ?? 0;
    const total = diagStatus?.category_total ?? diagStatus?.step_total ?? 0;
    kicker.textContent = t("diag.step_n", { current: Math.max(done, total), total });
    text.textContent = t("diag.done_hint");
    setStepCard("done");
    setStepState("done", t("diag.state_done"), true);
  } else {
    kicker.textContent = t("diag.step_idle_kicker");
    text.textContent = t("diag.hint_idle");
    setStepCard("idle");
    setStepState("idle", "", false);
  }

  const titles: Record<string, string> = {
    sticks: t("diag.sticks"),
    triggers: t("diag.triggers"),
    buttons: t("diag.buttons"),
  };
  for (const chip of document.querySelectorAll<HTMLButtonElement>(".chip[data-test]")) {
    const key = chip.dataset.test ?? "";
    const status = diagStatus?.tests?.[key] ?? "NOT_TESTED";
    chip.classList.remove("running", "pass", "warn", "fail");
    chip.disabled = running;
    let prefix = "○  ";
    if (running && diagStatus?.phase === key) {
      chip.classList.add("running");
      prefix = "●  ";
    } else if (status === "PASS") {
      chip.classList.add("pass");
      prefix = "✓  ";
    } else if (status === "WARN") {
      chip.classList.add("warn");
      prefix = "!  ";
    } else if (status === "FAIL") {
      chip.classList.add("fail");
      prefix = "×  ";
    }
    chip.textContent = prefix + (titles[key] ?? key);
  }

  const result = document.querySelector("#result-card");
  const prog = document.querySelector("#prog-panel");
  const score = document.querySelector("#score-badge");
  const hint = document.querySelector("#score-hint");
  const lines = document.querySelector("#result-lines");
  const count = document.querySelector("#progress-count");
  const fill = document.querySelector<HTMLElement>("#progress-fill");
  if (!result || !prog || !score || !hint || !lines) return;

  if (running) {
    result.classList.remove("hidden");
    prog.classList.remove("hidden");
    score.classList.add("hidden");
    hint.classList.add("hidden");
    lines.classList.add("hidden");
    if (count) count.textContent = `${diagStatus?.category_done ?? 0} / ${diagStatus?.category_total ?? 0}`;
    if (fill) fill.style.width = `${Math.round((diagStatus?.progress ?? 0) * 100)}%`;
  } else if (finished) {
    result.classList.remove("hidden");
    prog.classList.add("hidden");
    score.classList.remove("hidden");
    hint.classList.remove("hidden");
    lines.classList.remove("hidden");
    const value = diagStatus?.score ?? 0;
    score.textContent = t("diag.score", { score: value });
    score.classList.remove("score-good", "score-ok", "score-bad");
    score.classList.add(value >= 8 ? "score-good" : value >= 5 ? "score-ok" : "score-bad");
    lines.textContent = reportLines.slice(1).join("\n");
  } else {
    result.classList.add("hidden");
  }
}

function renderLogView(root: HTMLElement): void {
  livePad?.destroy();
  livePad = null;
  root.replaceChildren();
  const box = el("pre", "panel log-box");
  box.id = "log-box";
  box.textContent = logLines.length ? logLines.join("\n") : t("log.empty");
  root.appendChild(box);
}

function renderReportView(root: HTMLElement): void {
  livePad?.destroy();
  livePad = null;
  root.replaceChildren();
  const toolbar = el("div", "toolbar");
  const jsonBtn = el("button", "btn", t("report.export_json"));
  const csvBtn = el("button", "btn", t("report.export_csv"));
  jsonBtn.onclick = () => void exportReport("json");
  csvBtn.onclick = () => void exportReport("csv");
  toolbar.append(jsonBtn, csvBtn);
  const box = el("pre", "panel report-box");
  box.id = "report-box";
  box.textContent = reportLines.length ? reportLines.join("\n") : t("report.empty");
  const note = el("p", "device-line", t("report.disclaimer"));
  root.append(toolbar, box, note);
}

async function exportReport(format: "json" | "csv"): Promise<void> {
  if (isTauri()) {
    await invoke("export_report", { format });
    return;
  }
  const payload = await api.export(format);
  const ext = format === "json" ? "json" : "csv";
  const blob = new Blob([payload.content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `gamepad-report.${ext}`;
  a.click();
  URL.revokeObjectURL(url);
}

function renderSettingsModal(): void {
  const form = document.querySelector<HTMLFormElement>("#settings-form");
  if (!form) return;
  const locale = form.querySelector<HTMLSelectElement>('[name="locale"]')!;
  locale.value = String(configCache.locale ?? "ru");
  for (const name of [
    "stick_drift_warn",
    "stick_drift_fail",
    "rest_test_seconds",
    "left_stick_deadzone",
    "right_stick_deadzone",
    "button_hold_seconds",
  ]) {
    const input = form.querySelector<HTMLInputElement>(`[name="${name}"]`);
    if (input && configCache[name] !== undefined) input.value = String(configCache[name]);
  }
}

function buildSettingsModal(): void {
  document.querySelector("#settings-modal")?.remove();
  const backdrop = el("div", "modal-backdrop hidden");
  backdrop.id = "settings-modal";
  const modal = el("div", "modal");
  modal.innerHTML = `<h2>${t("settings.title")}</h2>`;
  const form = el("form");
  form.id = "settings-form";
  form.innerHTML = `
    <div class="field"><label>${t("settings.locale")}</label><select name="locale"><option value="ru">Русский</option><option value="en">English</option></select></div>
    <div class="field"><label>${t("settings.drift_warn")}</label><input name="stick_drift_warn" type="number" step="0.01" /></div>
    <div class="field"><label>${t("settings.drift_fail")}</label><input name="stick_drift_fail" type="number" step="0.01" /></div>
    <div class="field"><label>${t("settings.rest_seconds")}</label><input name="rest_test_seconds" type="number" step="1" /></div>
    <div class="field"><label>${t("settings.left_dz")}</label><input name="left_stick_deadzone" type="number" step="0.01" /></div>
    <div class="field"><label>${t("settings.right_dz")}</label><input name="right_stick_deadzone" type="number" step="0.01" /></div>
    <div class="field"><label>${t("settings.button_hold")}</label><input name="button_hold_seconds" type="number" step="1" /></div>
    <div class="row">
      <button type="button" class="btn" id="settings-cancel">${t("settings.reset")}</button>
      <button type="submit" class="btn primary">${t("settings.save")}</button>
    </div>`;
  form.onsubmit = async (ev) => {
    ev.preventDefault();
    const data = Object.fromEntries(new FormData(form).entries());
    const body: Record<string, unknown> = { ...configCache };
    for (const [k, v] of Object.entries(data)) {
      const num = Number(v);
      body[k] = Number.isFinite(num) && v !== "" && k !== "locale" ? num : v;
    }
    configCache = await api.config.put(body);
    await loadLocale(String(configCache.locale ?? "ru"));
    backdrop.classList.add("hidden");
    shellBuilt = false;
    render();
  };
  form.querySelector("#settings-cancel")!.addEventListener("click", () => backdrop.classList.add("hidden"));
  modal.appendChild(form);
  backdrop.appendChild(modal);
  backdrop.addEventListener("click", (ev) => {
    if (ev.target === backdrop) backdrop.classList.add("hidden");
  });
  document.body.appendChild(backdrop);
}

function syncHeader(): void {
  const connected = Boolean(padState?.connected);
  const dot = document.querySelector(".status-dot");
  const pill = document.querySelector(".status-pill");
  const pillText = document.querySelector("#pill-text");
  const transport = document.querySelector("#header-transport");
  if (dot) dot.classList.toggle("on", connected);
  if (pill) {
    pill.classList.toggle("ok", connected);
    pill.classList.toggle("bad", !connected);
  }
  if (pillText) pillText.textContent = connected ? t("status.connected_pill") : t("status.disconnected_pill");
  if (transport) {
    transport.textContent = connected ? (padState?.transport ?? "") : "";
    transport.classList.toggle("hidden", !connected);
  }
}

function render(): void {
  livePad?.destroy();
  livePad = null;
  app.replaceChildren();
  const shell = el("div", "app-shell");
  const header = el("header", "header");
  const title = el("h1");
  const link = document.createElement("a");
  link.href = SITE_URL;
  link.target = "_blank";
  link.rel = "noreferrer";
  link.textContent = t("app.title");
  title.appendChild(link);

  const tabs = el("nav", "tabs");
  for (const tab of [
    ["diagnostics", "tab.diagnostics"],
    ["log", "tab.log"],
    ["report", "tab.report"],
  ] as const) {
    const btn = el("button", `tab${activeTab === tab[0] ? " active" : ""}`, t(tab[1]));
    btn.onclick = () => {
      if (activeTab === tab[0]) return;
      activeTab = tab[0];
      render();
    };
    tabs.appendChild(btn);
  }

  const right = el("div", "header-right");
  const transport = el("span", "header-transport hidden");
  transport.id = "header-transport";
  const pill = el("div", "status-pill");
  const dot = el("span", "status-dot");
  const pillText = el("span");
  pillText.id = "pill-text";
  pill.append(dot, pillText);
  const settingsBtn = el("button", "btn icon", "⚙");
  settingsBtn.title = t("settings.title");
  settingsBtn.onclick = () => {
    renderSettingsModal();
    document.querySelector("#settings-modal")?.classList.remove("hidden");
  };
  right.append(transport, pill, settingsBtn);
  header.append(title, tabs, right);

  const content = el("main", "content");
  content.id = "content";
  if (activeTab === "diagnostics") renderDiagnosticsView(content);
  if (activeTab === "log") renderLogView(content);
  if (activeTab === "report") renderReportView(content);

  shell.append(header, content);
  app.appendChild(shell);
  shellBuilt = true;
  syncHeader();
}

async function refreshAll(): Promise<void> {
  try {
    const [state, diag, log, report, cfg] = await Promise.all([
      api.state(),
      api.diagnostics.status(),
      api.log(logLines.length),
      api.report(),
      api.config.get(),
    ]);
    padState = state;
    diagStatus = diag;
    if (log.lines.length) logLines.push(...log.lines);
    if (logLines.length > 2000) logLines = logLines.slice(-1500);
    reportLines = report.lines;
    configCache = cfg;

    if (!shellBuilt) {
      render();
      return;
    }
    syncHeader();
    if (activeTab === "diagnostics" && livePad) {
      livePad.update(state, diag);
      syncDiagnosticsChrome();
    } else if (activeTab === "log") {
      const box = document.querySelector("#log-box");
      if (box) box.textContent = logLines.length ? logLines.join("\n") : t("log.empty");
    } else if (activeTab === "report") {
      const box = document.querySelector("#report-box");
      if (box) box.textContent = reportLines.length ? reportLines.join("\n") : t("report.empty");
    }
  } catch {
    // sidecar not ready yet
  }
}

async function boot(): Promise<void> {
  showMessage("Connecting to sidecar...");
  try {
    await initServiceUrl();
    for (let i = 0; i < 40; i += 1) {
      try {
        await api.health();
        break;
      } catch {
        if (i === 39) throw new Error(`Sidecar unavailable at ${serviceUrl()}`);
        await new Promise((r) => setTimeout(r, 250));
      }
    }
    configCache = await api.config.get();
    await loadLocale(String(configCache.locale ?? getLocale()));
    buildSettingsModal();
    render();
    window.setInterval(() => void refreshAll(), 30);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    showMessage(`Failed to start UI:\n${message}`);
  }
}

void boot();

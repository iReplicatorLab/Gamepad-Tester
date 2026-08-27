import type { DiagnosticsStatus, PadState } from "./api";
import { t } from "./i18n";
import { PadDiagram } from "./pad-diagram";

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

type CueMotion = "up" | "down" | "left" | "right" | "circle" | "";

class StickCue {
  readonly root: HTMLElement;
  private canvas: HTMLCanvasElement;
  private times: HTMLElement;
  private motion: CueMotion = "";

  constructor() {
    this.root = el("div", "stick-cue hidden");
    this.canvas = el("canvas", "cue-canvas");
    this.canvas.width = 120;
    this.canvas.height = 120;
    this.times = el("div", "stick-cue-times");
    this.root.append(this.canvas, this.times);
  }

  setCue(motion: string, repeats: number, holdSeconds: number): void {
    this.motion = (["up", "down", "left", "right", "circle"].includes(motion) ? motion : "") as CueMotion;
    let text = "";
    if (repeats > 1) text = `×${repeats}`;
    else if (holdSeconds > 0 && this.motion && this.motion !== "circle") text = `${holdSeconds}s`;
    else if (holdSeconds > 0 && this.motion === "circle") text = `${holdSeconds}s`;
    this.times.textContent = text;
    this.times.classList.toggle("hidden", !text);
    this.root.classList.toggle("hidden", !this.motion);
    this.draw();
  }

  private draw(): void {
    const ctx = this.canvas.getContext("2d");
    if (!ctx) return;
    const w = this.canvas.width;
    const h = this.canvas.height;
    const cx = w / 2;
    const cy = h / 2;
    const radius = Math.min(w, h) * 0.38;
    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = "#16C60C";
    ctx.fillStyle = "#16C60C";
    ctx.lineWidth = 2.2;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.stroke();
    const motion = this.motion;
    if (motion === "up" || motion === "down" || motion === "left" || motion === "right") {
      const angle = { up: -Math.PI / 2, down: Math.PI / 2, left: Math.PI, right: 0 }[motion];
      this.arrow(ctx, cx, cy, radius * 0.82, angle);
    } else if (motion === "circle") {
      ctx.beginPath();
      ctx.arc(cx, cy, radius * 0.55, 0.4, Math.PI * 2 - 0.9);
      ctx.stroke();
      const tip = 0.4;
      this.arrowhead(ctx, cx + radius * 0.55 * Math.cos(tip), cy + radius * 0.55 * Math.sin(tip), tip + Math.PI / 2, 12);
    }
    ctx.beginPath();
    ctx.arc(cx, cy, 5.5, 0, Math.PI * 2);
    ctx.fill();
  }

  private arrow(ctx: CanvasRenderingContext2D, cx: number, cy: number, length: number, angle: number): void {
    const dx = Math.cos(angle);
    const dy = Math.sin(angle);
    ctx.lineCap = "round";
    ctx.lineWidth = 2.4;
    ctx.beginPath();
    ctx.moveTo(cx + dx * 8, cy + dy * 8);
    ctx.lineTo(cx + dx * length, cy + dy * length);
    ctx.stroke();
    this.arrowhead(ctx, cx + dx * length, cy + dy * length, angle, 14);
  }

  private arrowhead(ctx: CanvasRenderingContext2D, x: number, y: number, angle: number, size: number): void {
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x - size * Math.cos(angle - 0.55), y - size * Math.sin(angle - 0.55));
    ctx.lineTo(x - size * Math.cos(angle + 0.55), y - size * Math.sin(angle + 0.55));
    ctx.closePath();
    ctx.fill();
  }
}

export class LivePad {
  readonly root: HTMLElement;
  private diagram: PadDiagram;
  private buttons = new Map<number, HTMLElement>();
  private deviceTitle: HTMLElement;
  private ltFill: HTMLElement;
  private rtFill: HTMLElement;
  private ltValue: HTMLElement;
  private rtValue: HTMLElement;
  private timerBox: HTMLElement;
  private timerValue: HTMLElement;
  private timerCaption: HTMLElement;
  private cueLeft = new StickCue();
  private cueRight = new StickCue();
  private telemLeft: HTMLElement;
  private telemRight: HTMLElement;
  private rumbleLeft = 0.8;
  private rumbleRight = 0.8;
  private rumbleMs = 1000;
  private onRumble: (left: number, right: number, ms: number) => void;

  constructor(onRumble: (left: number, right: number, ms: number) => void) {
    this.onRumble = onRumble;
    this.root = el("div", "pad-stage");

    const leftCol = el("div", "pad-side");
    const rightCol = el("div", "pad-side");
    this.buildSideButtons(leftCol, rightCol);

    const center = el("div", "pad-center");
    this.deviceTitle = el("div", "pad-device-name", t("status.waiting"));
    center.appendChild(this.deviceTitle);

    const mid = el("div", "pad-mid");
    const ltCol = this.triggerColumn("LT");
    this.ltFill = ltCol.querySelector(".trigger-fill")!;
    this.ltValue = ltCol.querySelector(".trigger-value")!;
    const rtCol = this.triggerColumn("RT");
    this.rtFill = rtCol.querySelector(".trigger-fill")!;
    this.rtValue = rtCol.querySelector(".trigger-value")!;

    const canvasWrap = el("div", "pad-canvas-wrap");
    const canvas = el("canvas", "pad-canvas");
    canvasWrap.appendChild(canvas);
    this.diagram = new PadDiagram(canvas);

    this.timerBox = el("div", "hold-timer-box hidden");
    this.timerValue = el("div", "hold-timer");
    this.timerCaption = el("div", "hold-timer-caption");
    this.timerBox.append(this.timerValue, this.timerCaption);
    canvasWrap.appendChild(this.timerBox);

    this.telemLeft = this.stickTelem("left");
    this.telemRight = this.stickTelem("right");
    canvasWrap.append(this.telemLeft, this.telemRight);

    const lr = this.rumbleButton("lr", 1, 1);
    lr.classList.add("rumble-lr");
    canvasWrap.appendChild(lr);

    mid.append(ltCol, this.motorRail(this.cueLeft, "l"), canvasWrap, this.motorRail(this.cueRight, "r"), rtCol);
    center.appendChild(mid);

    this.root.append(leftCol, center, rightCol);
  }

  destroy(): void {
    this.diagram.destroy();
  }

  update(state: PadState | null, diag: DiagnosticsStatus | null): void {
    const kind = state?.diagram_kind ?? "series";
    const connected = state?.connected ?? false;
    const buttons = state?.buttons ?? {};
    const axes = state?.axes ?? { left_x: 0, left_y: 0, right_x: 0, right_y: 0, lt: 0, rt: 0 };
    const failed = new Set(diag?.failed_buttons ?? []);
    const passed = new Set(diag?.passed_buttons ?? []);
    const focus = diag?.running ? (diag.focus ?? "") : "";

    this.deviceTitle.textContent = connected
      ? `${state!.name}${state!.axis_profile ? ` · ${state!.axis_profile}` : ""}`
      : state?.hint || t("status.waiting");

    for (const [idx, node] of this.buttons) {
      const pressed = buttons[String(idx)] ?? false;
      node.classList.toggle("pressed", pressed);
      node.classList.toggle("focused", focus === `btn:${idx}`);
      node.classList.toggle("failed", failed.has(idx));
      node.classList.toggle("passed", passed.has(idx) && !failed.has(idx));
      const mark = node.querySelector(".pad-btn-mark");
      if (mark) {
        if (failed.has(idx)) {
          mark.textContent = "!";
          mark.classList.remove("hidden");
        } else if (passed.has(idx)) {
          mark.textContent = "✓";
          mark.classList.remove("hidden");
        } else {
          mark.textContent = "";
          mark.classList.add("hidden");
        }
      }
      if (idx === 15) node.classList.toggle("hidden", kind === "360");
    }

    this.setTrigger(this.ltFill, this.ltValue, axes.lt);
    this.setTrigger(this.rtFill, this.rtValue, axes.rt);

    const hold = diag?.hold;
    if (diag?.running && hold && hold.remaining > 0) {
      this.timerValue.textContent = String(Math.max(1, Math.ceil(hold.remaining - 1e-6)));
      this.timerCaption.textContent = t("diag.hold_seconds").toUpperCase();
      this.timerBox.classList.remove("hidden");
    } else {
      this.timerBox.classList.add("hidden");
    }

    const cue = diag?.running ? diag.cue : undefined;
    const holdS = diag?.hold_seconds ?? 0;
    this.cueLeft.setCue(cue?.side === "left" ? cue.motion : "", cue?.side === "left" ? cue.repeats : 0, cue?.side === "left" ? holdS : 0);
    this.cueRight.setCue(cue?.side === "right" ? cue.motion : "", cue?.side === "right" ? cue.repeats : 0, cue?.side === "right" ? holdS : 0);

    const showLeft = Boolean(diag?.running && (focus === "left" || focus.startsWith("left_")));
    const showRight = Boolean(diag?.running && (focus === "right" || focus.startsWith("right_")));
    this.fillTelem(this.telemLeft, t("telem.left_stick"), axes.left_x, axes.left_y, showLeft);
    this.fillTelem(this.telemRight, t("telem.right_stick"), axes.right_x, axes.right_y, showRight);

    this.diagram.update({
      connected,
      diagram_kind: kind,
      buttons,
      axes,
      focus,
      failed_buttons: diag?.failed_buttons,
      trail: Boolean(diag?.running),
    });
  }

  private setTrigger(fill: HTMLElement, label: HTMLElement, value: number): void {
    const clamped = Math.max(0, Math.min(1, value));
    fill.style.height = `${Math.round(clamped * 100)}%`;
    label.textContent = `${Math.round(clamped * 100)}%`;
  }

  private fillTelem(box: HTMLElement, title: string, x: number, y: number, show: boolean): void {
    box.classList.toggle("hidden", !show);
    if (!show) return;
    const r = Math.hypot(x, y);
    box.querySelector(".telem-title")!.textContent = title;
    box.querySelector(".telem-x")!.textContent = `X  ${x >= 0 ? "+" : ""}${x.toFixed(3)}`;
    box.querySelector(".telem-y")!.textContent = `Y  ${y >= 0 ? "+" : ""}${y.toFixed(3)}`;
    box.querySelector(".telem-flags")!.textContent = `${t("telem.center")} ${r < 0.08 ? "✓" : "—"}`;
  }

  private triggerColumn(name: string): HTMLElement {
    const col = el("div", "trigger-col");
    col.append(el("div", "trigger-label", name));
    const value = el("div", "trigger-value", "0%");
    const bar = el("div", "trigger-bar-v");
    const fill = el("span", "trigger-fill");
    bar.appendChild(fill);
    col.append(value, bar);
    return col;
  }

  private stickTelem(side: string): HTMLElement {
    const box = el("div", `stick-telem stick-telem-${side} hidden`);
    box.append(
      el("div", "telem-title"),
      el("div", "telem-mono telem-x"),
      el("div", "telem-mono telem-y"),
      el("div", "telem-flags"),
    );
    return box;
  }

  private motorRail(cue: StickCue, side: "l" | "r"): HTMLElement {
    const rail = el("div", "motor-rail");
    const stack = el("div", "motor-stack");
    stack.appendChild(cue.root);
    const rumble = this.rumbleButton(side, side === "l" ? 1 : 0, side === "r" ? 1 : 0);
    stack.appendChild(rumble);
    rail.append(stack, this.rumbleScale(side));
    return rail;
  }

  private rumbleScale(side: "l" | "r"): HTMLElement {
    const box = el("div", "rumble-scale-box");
    const scale = el("input", "rumble-scale");
    scale.type = "range";
    scale.min = "0";
    scale.max = "100";
    scale.value = "80";
    const value = el("div", "rumble-power-value", "80%");
    scale.addEventListener("input", () => {
      const pct = Number(scale.value);
      value.textContent = `${pct}%`;
      if (side === "l") this.rumbleLeft = pct / 100;
      else this.rumbleRight = pct / 100;
    });
    box.append(scale, value);
    return box;
  }

  private rumbleButton(key: string, left: number, right: number): HTMLButtonElement {
    const btn = el("button", "rumble-btn", t(`monitor.rumble_${key}`));
    btn.addEventListener("click", () => {
      btn.classList.add("active");
      this.onRumble(left * this.rumbleLeft, right * this.rumbleRight, this.rumbleMs);
      window.setTimeout(() => btn.classList.remove("active"), 900);
    });
    return btn;
  }

  private buildSideButtons(left: HTMLElement, right: HTMLElement): void {
    left.appendChild(this.padButton(4, "LB", "bumper"));
    left.appendChild(this.cluster([
      [11, "↑", "n"],
      [13, "←", "w"],
      [14, "→", "e"],
      [12, "↓", "s"],
    ], "dpad"));
    left.appendChild(this.padButton(6, "View"));
    left.appendChild(this.padButton(8, "Xbox"));
    left.appendChild(this.padButton(9, "L3"));

    right.appendChild(this.padButton(5, "RB", "bumper"));
    right.appendChild(this.cluster([
      [3, "Y", "n"],
      [2, "X", "w"],
      [1, "B", "e"],
      [0, "A", "s"],
    ], "face"));
    right.appendChild(this.padButton(7, "Menu"));
    right.appendChild(this.padButton(15, "Share"));
    right.appendChild(this.padButton(10, "R3"));
  }

  private cluster(items: [number, string, string][], kind: string): HTMLElement {
    const grid = el("div", "btn-cluster");
    for (const [idx, name, pos] of items) {
      const btn = this.padButton(idx, name, kind);
      btn.classList.add(`c-${pos}`);
      grid.appendChild(btn);
    }
    return grid;
  }

  private padButton(idx: number, name: string, extra = ""): HTMLElement {
    const css = extra ? `pad-btn ${extra}` : "pad-btn";
    const btn = el("div", css);
    btn.dataset.idx = String(idx);
    btn.append(el("span", "pad-btn-label", name), el("span", "pad-btn-mark hidden"));
    this.buttons.set(idx, btn);
    return btn;
  }
}

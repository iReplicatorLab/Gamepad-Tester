import { api } from "./api";
import layoutsFile from "./assets/pad-layouts.json";

type Hotspot = [number, number, number];

type Layout = {
  file: string;
  buttons: Record<string, Hotspot>;
  left_stick: Hotspot;
  right_stick: Hotspot;
  lt: Hotspot;
  rt: Hotspot;
  dpad: Hotspot;
};

type LayoutsFile = {
  imageSize: [number, number];
  "360": Layout;
  series: Layout;
};

const GREEN: [number, number, number] = [0.06, 0.82, 0.18];
const RED: [number, number, number] = [0.77, 0.17, 0.11];

export class PadDiagram {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private layouts: LayoutsFile | null = null;
  private images = new Map<string, HTMLImageElement>();
  private kind = "series";
  private connected = false;
  private buttons: Record<string, boolean> = {};
  private left = { x: 0, y: 0 };
  private right = { x: 0, y: 0 };
  private lt = 0;
  private rt = 0;
  private focus = "";
  private failed = new Set<number>();
  private trailLeft: { x: number; y: number }[] = [];
  private trailRight: { x: number; y: number }[] = [];
  private trail = false;
  private raf = 0;
  private pulseT = 0;

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("canvas 2d unavailable");
    this.ctx = ctx;
    void this.loadLayouts();
    this.raf = requestAnimationFrame(this.loop);
  }

  destroy(): void {
    cancelAnimationFrame(this.raf);
  }

  private loop = (now: number): void => {
    this.pulseT = now / 1000;
    this.draw();
    this.raf = requestAnimationFrame(this.loop);
  };

  private async loadLayouts(): Promise<void> {
    this.layouts = layoutsFile as unknown as LayoutsFile;
    if (this.layouts) {
      this.canvas.width = this.layouts.imageSize[0];
      this.canvas.height = this.layouts.imageSize[1];
      await Promise.all([
        this.loadImage("360", this.layouts["360"].file),
        this.loadImage("series", this.layouts.series.file),
      ]);
    }
  }

  private loadImage(kind: string, file: string): Promise<void> {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => {
        this.images.set(kind, img);
        resolve();
      };
      img.onerror = () => resolve();
      img.src = api.assetUrl(file);
    });
  }

  setKind(kind: string): void {
    this.kind = kind === "360" ? "360" : "series";
  }

  update(input: {
    connected: boolean;
    diagram_kind: string;
    buttons: Record<string, boolean>;
    axes: { left_x: number; left_y: number; right_x: number; right_y: number; lt: number; rt: number };
    focus?: string;
    failed_buttons?: number[];
    trail?: boolean;
  }): void {
    const nextFocus = input.focus ?? "";
    if (nextFocus !== this.focus) {
      const leftOn = nextFocus === "left" || nextFocus.startsWith("left_");
      const rightOn = nextFocus === "right" || nextFocus.startsWith("right_");
      if (!leftOn && !rightOn) {
        this.trailLeft = [];
        this.trailRight = [];
      } else if (leftOn) {
        this.trailRight = [];
      } else {
        this.trailLeft = [];
      }
    }
    this.connected = input.connected;
    this.kind = input.diagram_kind === "360" ? "360" : "series";
    this.buttons = input.buttons;
    this.left = { x: input.axes.left_x, y: input.axes.left_y };
    this.right = { x: input.axes.right_x, y: input.axes.right_y };
    this.lt = input.axes.lt;
    this.rt = input.axes.rt;
    this.focus = nextFocus;
    this.failed = new Set(input.failed_buttons ?? []);
    this.trail = Boolean(input.trail);
    if (this.trail && (this.focus === "left" || this.focus.startsWith("left_"))) {
      this.trailLeft.push({ ...this.left });
      if (this.trailLeft.length > 500) this.trailLeft = this.trailLeft.slice(-500);
    }
    if (this.trail && (this.focus === "right" || this.focus.startsWith("right_"))) {
      this.trailRight.push({ ...this.right });
      if (this.trailRight.length > 500) this.trailRight = this.trailRight.slice(-500);
    }
  }

  private layout(): Layout | null {
    if (!this.layouts) return null;
    return this.layouts[this.kind as "360" | "series"];
  }

  private draw(): void {
    const layout = this.layout();
    const w = this.canvas.width;
    const h = this.canvas.height;
    const ctx = this.ctx;
    ctx.clearRect(0, 0, w, h);

    const img = this.images.get(this.kind);
    if (img) ctx.drawImage(img, 0, 0, w, h);
    else {
      ctx.fillStyle = "#111";
      ctx.fillRect(0, 0, w, h);
    }

    if (!this.connected) {
      ctx.fillStyle = "rgba(0, 0, 0, 0.55)";
      ctx.fillRect(0, 0, w, h);
    }

    if (!layout) return;

    const spot = (spec: Hotspot): [number, number, number] => [spec[0] * w, spec[1] * h, spec[2] * w];
    const pulse = 1 + 0.18 * Math.abs(Math.sin(this.pulseT * 8));
    const focus = this.focus;

    if (focus === "left" || focus.startsWith("left_")) this.ring(...spot(layout.left_stick));
    if (focus === "right" || focus.startsWith("right_")) this.ring(...spot(layout.right_stick));
    if (focus === "lt") this.ring(...spot(layout.lt));
    if (focus === "rt") this.ring(...spot(layout.rt));
    if (focus === "dpad") this.ring(...spot(layout.dpad));
    if (focus.startsWith("btn:")) {
      const idx = focus.slice(4);
      const btn = layout.buttons[idx];
      if (btn) this.ring(...spot(btn));
    }

    for (const [idx, spec] of Object.entries(layout.buttons)) {
      const fail = this.failed.has(Number(idx));
      const on = this.buttons[idx] ?? false;
      if (fail) this.glow(...spot([spec[0], spec[1], spec[2] * pulse]), RED);
      else if (on) this.glow(...spot([spec[0], spec[1], spec[2] * pulse]), GREEN);
    }

    this.triggerFill(...spot(layout.lt), this.lt);
    this.triggerFill(...spot(layout.rt), this.rt);

    const leftOn = focus === "left" || focus.startsWith("left_");
    const rightOn = focus === "right" || focus.startsWith("right_");
    this.stick(...spot(layout.left_stick), this.left, this.trailLeft, leftOn);
    this.stick(...spot(layout.right_stick), this.right, this.trailRight, rightOn);
  }

  private glow(x: number, y: number, r: number, color: [number, number, number]): void {
    const ctx = this.ctx;
    ctx.save();
    ctx.fillStyle = `rgba(${rgb(color)}, 0.28)`;
    ctx.beginPath();
    ctx.arc(x, y, r * 2.1, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = `rgba(${rgb(color)}, 0.85)`;
    ctx.beginPath();
    ctx.arc(x, y, r * 1.25, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = `rgb(${Math.min(255, color[0] * 255 + 178)}, ${Math.min(255, color[1] * 255 + 64)}, ${Math.min(255, color[2] * 255 + 64)})`;
    ctx.lineWidth = Math.max(3, r * 0.22);
    ctx.beginPath();
    ctx.arc(x, y, r * 1.05, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = "rgba(255, 255, 255, 0.95)";
    ctx.beginPath();
    ctx.arc(x, y, Math.max(4, r * 0.28), 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  private ring(x: number, y: number, r: number): void {
    const ctx = this.ctx;
    ctx.save();
    ctx.fillStyle = `rgba(${rgb(GREEN)}, 0.14)`;
    ctx.beginPath();
    ctx.arc(x, y, r * 1.55, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = `rgba(${rgb(GREEN)}, 0.28)`;
    ctx.beginPath();
    ctx.arc(x, y, r * 1.28, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = `rgba(${rgb(GREEN)}, 0.95)`;
    ctx.lineWidth = 2.4;
    ctx.beginPath();
    ctx.arc(x, y, r * 1.18, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }

  private triggerFill(x: number, y: number, r: number, value: number): void {
    if (value <= 0.02) return;
    const ctx = this.ctx;
    ctx.save();
    ctx.fillStyle = `rgba(${rgb(GREEN)}, ${0.25 + 0.55 * value})`;
    ctx.beginPath();
    ctx.arc(x, y, r * (0.55 + 0.7 * value), 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  private stick(
    cx: number,
    cy: number,
    radius: number,
    pos: { x: number; y: number },
    trail: { x: number; y: number }[],
    active: boolean,
  ): void {
    const ctx = this.ctx;
    const px = Math.max(-1, Math.min(1, pos.x));
    const py = Math.max(-1, Math.min(1, pos.y));
    const x = cx + px * radius * 0.75;
    const y = cy + py * radius * 0.75;
    const moved = Math.abs(px) > 0.08 || Math.abs(py) > 0.08;

    ctx.save();
    for (const point of trail) {
      ctx.fillStyle = `rgba(${rgb(GREEN)}, 0.35)`;
      ctx.beginPath();
      ctx.arc(cx + point.x * radius, cy + point.y * radius, 2.2, 0, Math.PI * 2);
      ctx.fill();
    }

    if (this.connected || moved || active) {
      const pulse = active ? 0.12 * Math.sin(this.pulseT * 8) : 0;
      ctx.fillStyle = `rgba(${rgb(GREEN)}, ${this.connected ? 0.55 : 0.22})`;
      ctx.beginPath();
      ctx.arc(x, y, radius * (0.72 + pulse), 0, Math.PI * 2);
      ctx.fill();
    }

    if (active) {
      ctx.fillStyle = `rgba(${rgb(GREEN)}, 0.16)`;
      ctx.beginPath();
      ctx.arc(cx, cy, radius * 1.2, 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.fillStyle = `rgba(${rgb(GREEN)}, ${active ? 0.95 : this.connected ? 0.8 : 0.35})`;
    ctx.beginPath();
    ctx.arc(x, y, active ? 9 : 6, 0, Math.PI * 2);
    ctx.fill();
    if (active || moved) {
      ctx.fillStyle = "rgba(255, 255, 255, 0.95)";
      ctx.beginPath();
      ctx.arc(x, y, 3, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }
}

function rgb(color: [number, number, number]): string {
  return `${Math.round(color[0] * 255)}, ${Math.round(color[1] * 255)}, ${Math.round(color[2] * 255)}`;
}

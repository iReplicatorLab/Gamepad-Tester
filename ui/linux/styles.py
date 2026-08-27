"""GTK CSS — Xbox Diagnostic / Hardware Monitor, dark technical UI."""

CSS = """
.tech-shell {
  background: #151515;
  color: #F2F2F2;
}
.tech-shell > * {
  background: #151515;
}

headerbar.tech-header {
  min-height: 64px;
  padding: 0 10px;
  background: #1D1D1D;
  color: #F2F2F2;
  border-bottom: 1px solid #343434;
  box-shadow: none;
}
headerbar.tech-header windowcontrols button {
  min-width: 28px;
  min-height: 28px;
}
.brand-title {
  font-weight: 800;
  font-size: 12px;
  letter-spacing: 0.12em;
  color: #F2F2F2;
  padding: 0 8px 0 4px;
}
.header-device {
  padding: 0 10px 0 4px;
}
.header-device-name {
  font-size: 13px;
  font-weight: 600;
  color: #F2F2F2;
}
.pad-device-name {
  font-size: 12px;
  font-weight: 600;
  color: #A0A0A0;
  padding: 2px 8px 8px 8px;
}
.header-brand {
  font-size: 26px;
  font-weight: 700;
  color: #F2F2F2;
}
.header-brand link {
  color: #F2F2F2;
  text-decoration: none;
}
.header-brand link:hover {
  color: #16C60C;
}
.header-brand link:visited {
  color: #F2F2F2;
}
.header-device-profile {
  font-size: 11px;
  color: #A0A0A0;
}
.header-transport {
  font-family: JetBrains Mono, Consolas, monospace;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #A0A0A0;
}

stackswitcher.tech-nav {
  background: transparent;
  border: none;
  box-shadow: none;
}
stackswitcher.tech-nav > button {
  min-height: 56px;
  padding: 0 16px;
  border: none;
  border-radius: 0;
  box-shadow: none;
  background: transparent;
  color: #A0A0A0;
  font-weight: 600;
  font-size: 14px;
  border-bottom: 2px solid transparent;
}
stackswitcher.tech-nav > button:hover {
  background: #242424;
  color: #F2F2F2;
}
stackswitcher.tech-nav > button:checked,
stackswitcher.tech-nav > button.checked {
  background: #242424;
  color: #F2F2F2;
  border-bottom: 2px solid #107C10;
}

.tech-panel {
  background: #1D1D1D;
  border: 1px solid #343434;
  border-radius: 10px;
  padding: 10px 12px;
}
.tech-panel-title {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: #A0A0A0;
}

.device-name {
  font-size: 16px;
  font-weight: 600;
  color: #F2F2F2;
}
.device-profile {
  font-size: 12px;
  color: #A0A0A0;
}
.device-link {
  font-family: JetBrains Mono, Consolas, monospace;
  font-size: 11px;
  color: #A0A0A0;
}
.tech-panel.device-status {
  border-left: 3px solid #343434;
}
.tech-panel.device-status.ok {
  border-left-color: #107C10;
}
.tech-panel.device-status.bad {
  border-left-color: #F04F4F;
}
.status-pill {
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.status-pill.ok {
  background: alpha(#16C60C, 0.16);
  color: #16C60C;
}
.status-pill.bad {
  background: alpha(#F04F4F, 0.16);
  color: #F04F4F;
}
.status-pill.wait {
  background: #242424;
  color: #A0A0A0;
}

.pad-btn {
  min-width: 40px;
  min-height: 28px;
  padding: 2px 8px;
  border-radius: 6px;
  background: #242424;
  border: 1px solid #343434;
  color: #A0A0A0;
  font-weight: 600;
  font-size: 12px;
}
.pad-btn.pressed {
  background: #107C10;
  color: #F2F2F2;
  border-color: #107C10;
  box-shadow: 0 0 8px alpha(#16C60C, 0.4);
}
.pad-btn.face { min-width: 36px; }
.pad-btn.bumper { min-width: 38px; min-height: 26px; }
.pad-btn.dpad { min-width: 32px; min-height: 28px; }
.pad-btn.focused {
  border: 1px solid #107C10;
  background: #242424;
  color: #F2F2F2;
}
.pad-btn.focused.pressed {
  background: #107C10;
  color: #F2F2F2;
}
.pad-btn.failed {
  background: #F04F4F;
  color: #F2F2F2;
  border-color: #F04F4F;
}
.pad-btn.failed.pressed {
  background: #c43b3b;
}
.pad-btn.passed {
  border-color: #107C10;
}
.pad-btn-mark {
  font-size: 10px;
  font-weight: 700;
  color: #16C60C;
  line-height: 1.0;
}
.pad-btn.failed .pad-btn-mark {
  color: #F2F2F2;
}

.trigger-col {
  padding: 6px 5px;
  border-radius: 8px;
  background: alpha(#000000, 0.45);
  min-width: 44px;
}
.trigger-label {
  font-size: 11px;
  font-weight: 700;
  color: #A0A0A0;
}
.trigger-value {
  font-family: JetBrains Mono, Consolas, monospace;
  font-size: 11px;
  color: #F2F2F2;
}
progressbar.trigger-bar trough {
  min-height: 8px;
  border-radius: 4px;
  background: #242424;
  border: 1px solid #343434;
}
progressbar.trigger-bar progress {
  min-height: 8px;
  border-radius: 4px;
  background: #107C10;
}
progressbar.trigger-bar.vertical trough {
  min-width: 10px;
  min-height: 210px;
}
progressbar.trigger-bar.vertical progress {
  min-width: 10px;
}

button.rumble-btn {
  min-width: 56px;
  min-height: 32px;
  border-radius: 8px;
  background: #242424;
  border: 1px solid #343434;
  color: #F2F2F2;
  font-weight: 600;
}
button.rumble-btn:hover {
  background: #303030;
}
button.rumble-btn.active {
  background: #107C10;
  border-color: #107C10;
  color: #F2F2F2;
}
.rumble-power-label {
  font-family: JetBrains Mono, Consolas, monospace;
  font-size: 12px;
  font-weight: 700;
  color: #A0A0A0;
  min-width: 18px;
}
.rumble-power-value {
  font-family: JetBrains Mono, Consolas, monospace;
  font-size: 10px;
  font-weight: 700;
  color: #A0A0A0;
}
scale.rumble-scale {
  min-width: 60px;
  padding: 0;
}
scale.rumble-scale trough {
  min-height: 8px;
  border-radius: 4px;
  background: #242424;
  border: 1px solid #343434;
}
scale.rumble-scale highlight {
  border-radius: 4px;
  background: #107C10;
}

button.primary-btn {
  min-height: 40px;
  padding: 0 18px;
  border-radius: 8px;
  background: #107C10;
  color: #F2F2F2;
  font-weight: 700;
  border: none;
}
button.primary-btn:hover { background: #0e6b0e; }
button.stop-btn {
  min-height: 36px;
  padding: 0 16px;
  border-radius: 8px;
  background: #242424;
  color: #F2F2F2;
  border: 1px solid #343434;
  font-weight: 700;
}
button.stop-btn:hover { background: #303030; }
button.ghost-btn {
  min-height: 28px;
  padding: 0 12px;
  border-radius: 8px;
  background: transparent;
  color: #A0A0A0;
  border: 1px solid #343434;
  font-weight: 600;
}
button.ghost-btn:hover {
  background: #303030;
  color: #F2F2F2;
}

button.check-chip {
  min-height: 32px;
  padding: 0 12px;
  border-radius: 8px;
  background: #242424;
  color: #A0A0A0;
  border: 1px solid #343434;
  font-weight: 600;
  font-size: 13px;
}
button.check-chip:hover { background: #303030; color: #F2F2F2; }
button.check-chip.running {
  border-color: #4DB6E8;
  color: #4DB6E8;
  background: alpha(#4DB6E8, 0.1);
}
button.check-chip.pass {
  border-color: #16C60C;
  color: #16C60C;
  background: alpha(#16C60C, 0.1);
}
button.check-chip.warn {
  border-color: #F2C94C;
  color: #F2C94C;
}
button.check-chip.fail {
  border-color: #F04F4F;
  color: #F04F4F;
  background: alpha(#F04F4F, 0.1);
}
button.check-chip.disabled {
  color: #666666;
  background: #1B1B1B;
}
.chip-soon {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.12em;
  color: #666666;
  margin-top: 2px;
}

.progress-caption {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: #A0A0A0;
}
.progress-count {
  font-family: JetBrains Mono, Consolas, monospace;
  font-size: 13px;
  color: #F2F2F2;
}
.progress-cat {
  font-size: 12px;
  font-weight: 600;
  color: #A0A0A0;
}
.progress-cat.running { color: #4DB6E8; }
.progress-cat.pass { color: #16C60C; }
.progress-cat.warn { color: #F2C94C; }
.progress-cat.fail { color: #F04F4F; }
.progress-cat.soon { color: #666666; }
progressbar.tech-progress trough {
  min-height: 8px;
  border-radius: 4px;
  background: #242424;
  border: 1px solid #343434;
}
progressbar.tech-progress progress {
  min-height: 8px;
  border-radius: 4px;
  background: #107C10;
}

.step-card {
  background: #242424;
  border: 1px solid #343434;
  border-radius: 10px;
  border-left: 5px solid #107C10;
  padding: 8px 12px 8px 14px;
}
.step-card.idle { border-left-color: #343434; }
.step-card.waiting { border-left-color: #4DB6E8; }
.step-card.holding { border-left-color: #107C10; }
.step-card.done { border-left-color: #16C60C; }
.step-kicker {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  color: #A0A0A0;
}
.step-text {
  font-size: 14px;
  font-weight: 600;
  color: #F2F2F2;
}
.step-state {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: #4DB6E8;
}
.step-state.hold { color: #16C60C; }
.step-state.idle { color: #A0A0A0; }
.step-state.done { color: #16C60C; }

.telem-box {
  background: #1D1D1D;
  border: 1px solid #343434;
  border-radius: 10px;
  padding: 8px 12px;
}
.telem-title {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: #A0A0A0;
}
.telem-mono {
  font-family: JetBrains Mono, Consolas, monospace;
  font-size: 13px;
  color: #F2F2F2;
}
.stick-cue-times {
  font-size: 21px;
  font-weight: 800;
  color: #16C60C;
}
.stick-telem {
  background: alpha(#151515, 0.72);
  border-radius: 8px;
  padding: 6px 8px;
}

.score-badge {
  font-size: 1.6em;
  font-weight: 800;
  padding: 4px 0;
}
.score-good { color: #16C60C; }
.score-ok { color: #F2C94C; }
.score-bad { color: #F04F4F; }
.status-pass { color: #16C60C; font-weight: 700; }
.status-warn { color: #F2C94C; font-weight: 700; }
.status-fail { color: #F04F4F; font-weight: 700; }
.status-connected { color: #16C60C; font-weight: 600; }
.status-disconnected { color: #F04F4F; font-weight: 600; }

.hold-timer-box {
  background: alpha(#151515, 0.78);
  border-radius: 10px;
  padding: 8px 22px 10px 22px;
  border: 2px solid #107C10;
  min-width: 120px;
}
.hold-timer {
  font-family: JetBrains Mono, Consolas, monospace;
  font-size: 56px;
  font-weight: 800;
  color: #F2F2F2;
  line-height: 1.0;
}
.hold-timer-caption {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: #A0A0A0;
}
.pad-stage {
  background: #000000;
  border-radius: 10px;
  padding: 8px 6px;
}
.pad-side {
  min-width: 84px;
  padding: 8px 6px;
}
.pad-diagram {
  background: #000000;
  border-radius: 0;
  min-height: 280px;
  border: none;
}

.result-card {
  background: #1D1D1D;
  border: 1px solid #343434;
  border-radius: 10px;
  padding: 12px 14px;
}
"""

import { state } from "./state.js";

// These are set lazily so pages can register their own updaters
let _onSensorUpdate = null;
let _onEmotionUpdate = null;
let _onCameraFrame = null;
let _onLogLine = null;

export function registerPageCallbacks({
  onSensor,
  onEmotion,
  onFrame,
  onLog,
} = {}) {
  _onSensorUpdate = onSensor ?? null;
  _onEmotionUpdate = onEmotion ?? null;
  _onCameraFrame = onFrame ?? null;
  _onLogLine = onLog ?? null;
}

export function updateConnectionUI(connected, mode) {
  const dot = document.getElementById("statusDot");
  const text = document.getElementById("statusText");
  const badge = document.getElementById("connBadge");
  const modeBadge = document.getElementById("modeBadge");

  if (mode === "waiting") {
    dot?.classList.add("waiting");
    if (text) text.textContent = "Waiting for ESP32...";
    return;
  }

  state.connected = connected;
  if (dot) {
    dot.className = "status-dot" + (connected ? " connected" : "");
  }
  setText(
    "statusText",
    connected ? `Connected (${state.mode ?? ""})` : "Disconnected",
  );
  setText("connBadge", connected ? "Connected" : "Disconnected");
  setText("modeBadge", state.mode ?? "—");
}

import { state } from "../state.js";
import { toast } from "../utils/dom.js";

const CONTENT = document.getElementById("mainContent");

const GESTURES = [
  { id: "wave", icon: "👋", label: "Wave" },
  { id: "handshake", icon: "🤝", label: "Handshake" },
  { id: "nod", icon: "✅", label: "Nod" },
  { id: "shake", icon: "❌", label: "Shake" },
  { id: "happy", icon: "😄", label: "Happy" },
  { id: "sad", icon: "😢", label: "Sad" },
  { id: "surprised", icon: "😲", label: "Surprised" },
  { id: "point", icon: "👉", label: "Point" },
  { id: "hug_leg", icon: "🫂", label: "Hug (Leg)" },
  { id: "hug_waist", icon: "🫂", label: "Hug (Waist)" },
  { id: "hug_reach", icon: "🫂", label: "Hug (Reach)" },
  { id: "comfort_pat", icon: "🤗", label: "Comfort Pat" },
];

const EMOTIONS = [
  "happy",
  "sad",
  "neutral",
  "angry",
  "fear",
  "surprise",
  "disgust",
];

const LED_SWATCHES = [
  { hex: "#00e5ff", r: 0, g: 229, b: 255 },
  { hex: "#7c3aed", r: 124, g: 58, b: 237 },
  { hex: "#22c55e", r: 34, g: 197, b: 94 },
  { hex: "#f59e0b", r: 245, g: 158, b: 11 },
  { hex: "#ff4444", r: 255, g: 68, b: 68 },
  { hex: "#ffffff", r: 255, g: 255, b: 255 },
  { hex: "#ff69b4", r: 255, g: 105, b: 180 },
  { hex: "#000000", r: 0, g: 0, b: 0 },
];

// Render
export async function renderControl() {
  CONTENT.innerHTML = html();
  wireEvents();
}

// Template
function html() {
  return `
  <div class="page-header">
    <div class="page-title">CONTROL PANEL</div>
    <div class="page-sub">Send commands and control robot behavior</div>
  </div>
  <div class="grid-2">
    <div class="card">
      <div class="card-title">Gestures</div>
      <div class="gesture-grid">
        ${GESTURES.map(
          (g) => `
          <div class="gesture-btn" data-gesture="${g.id}">
            <span class="g-icon">${g.icon}</span>
            <span>${g.label}</span>
          </div>
        `,
        ).join("")}
      </div>
    </div>

    <div style="display:flex;flex-direction:column;gap:16px">
      <div class="card">
        <div class="card-title">Make Robot Speak</div>
        <div class="form-group">
          <textarea class="form-control" id="speakText" rows="3"
            placeholder="Type what the robot should say…" style="resize:vertical"></textarea>
        </div>
        <button class="btn btn-primary w100" id="speakBtn">▶ Speak</button>
      </div>

      <div class="card">
        <div class="card-title">Override Emotion</div>
        <div class="emotion-grid" id="emotionGrid">
          ${EMOTIONS.map(
            (e) => `
            <div class="emotion-pill ${state.emotion === e ? "active" : ""}" data-emotion="${e}">${e}</div>
          `,
          ).join("")}
        </div>
        <div class="divider"></div>
        <div class="flex-row" style="justify-content:space-between;align-items:center">
          <span class="text-dim text-sm">
            Current: <span id="currentEmotionLbl" style="color:var(--violet)">${state.emotion}</span>
          </span>
          <button class="btn btn-secondary btn-sm" id="resetEmotionBtn">Reset</button>
        </div>
      </div>

      <div class="card">
        <div class="card-title">LED Color</div>
        <div class="led-swatches">
          ${LED_SWATCHES.map(
            (s) => `
            <div class="led-swatch"
                 style="background:${s.hex}"
                 data-r="${s.r}" data-g="${s.g}" data-b="${s.b}"
                 title="${s.hex}"></div>
          `,
          ).join("")}
        </div>
        <div class="flex-row mt8">
          <input type="number" class="form-control" id="ledR" min="0" max="255" placeholder="R" style="flex:1">
          <input type="number" class="form-control" id="ledG" min="0" max="255" placeholder="G" style="flex:1">
          <input type="number" class="form-control" id="ledB" min="0" max="255" placeholder="B" style="flex:1">
          <button class="btn btn-secondary" id="setLedCustomBtn">Set</button>
        </div>
      </div>

      <div class="card">
        <div class="card-title">System</div>
        <div class="flex-row">
          <button class="btn btn-secondary w100" id="resetPosBtn">Reset Position</button>
          <button class="btn btn-danger w100"    id="estopCtrlBtn">⊗ Emergency Stop</button>
        </div>
      </div>
    </div>
  </div>
  `;
}

// Wire events
function wireEvents() {
  // Gestures
  document.querySelectorAll("[data-gesture]").forEach((btn) => {
    btn.addEventListener("click", () => sendGesture(btn.dataset.gesture));
  });

  // Speak
  document.getElementById("speakBtn").addEventListener("click", sendSpeak);

  // Emotion pills
  document.querySelectorAll("[data-emotion]").forEach((pill) => {
    pill.addEventListener("click", () => setEmotion(pill.dataset.emotion));
  });
  document
    .getElementById("resetEmotionBtn")
    .addEventListener("click", () => setEmotion("neutral"));

  // LED swatches
  document.querySelectorAll(".led-swatch").forEach((swatch) => {
    swatch.addEventListener("click", () => {
      const { r, g, b } = swatch.dataset;
      window.robot.setLed({ r: +r, g: +g, b: +b });
    });
  });
  document
    .getElementById("setLedCustomBtn")
    .addEventListener("click", setLedCustom);

  // System
  document
    .getElementById("resetPosBtn")
    .addEventListener("click", () => window.robot.neutral());
  document
    .getElementById("estopCtrlBtn")
    .addEventListener("click", () => window.robot.emergencyStop());
}

// Actions
async function sendGesture(name) {
  if (!state.connected) {
    toast("Not connected", "error");
    return;
  }
  if (state.gesturePending) {
    toast("Gesture in progress…", "info");
    return;
  }
  state.gesturePending = true;
  await window.robot.gesture(name);
  toast(`Sent: ${name}`, "info");
}

async function sendSpeak() {
  const text = document.getElementById("speakText")?.value.trim();
  if (!text) return;
  if (!state.connected) {
    toast("Not connected", "error");
    return;
  }
  await window.robot.speak(text);
  toast("Speaking…", "info");
}

async function setEmotion(emotion) {
  state.emotion = emotion;
  document.querySelectorAll(".emotion-pill").forEach((el) => {
    el.classList.toggle("active", el.dataset.emotion === emotion);
  });
  const lbl = document.getElementById("currentEmotionLbl");
  if (lbl) lbl.textContent = emotion;
  await window.robot.setEmotion(emotion);
}

function setLedCustom() {
  const r = parseInt(document.getElementById("ledR")?.value ?? 0);
  const g = parseInt(document.getElementById("ledG")?.value ?? 0);
  const b = parseInt(document.getElementById("ledB")?.value ?? 0);
  window.robot.setLed({ r, g, b });
  toast(`LED → rgb(${r},${g},${b})`, "info");
}
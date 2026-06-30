import { state } from "../state.js";
import { setText } from "../utils/dom.js";
import { registerPageCallbacks } from "../events.js";

const CONTENT = document.getElementById("mainContent");

export async function renderDashboard() {
  CONTENT.innerHTML = html();
  registerPageCallbacks({ onSensor: updateSensorUI });
  updateSensorUI();
  drawSensorChart();
}

// Sensor UI
function updateSensorUI() {
  const s = state.sensor;
  setText("dashDist", s.dist_cm ?? "—");
  setText("dashPIR", s.pir ? "● Active" : "○ None");
  setText("dashTouch", s.touch ? "● Active" : "○ None");
  setText("dashEmotion", state.emotion);
  setText("tilDistVal", s.dist_cm ?? "—");
  setText("tilePIRVal", s.pir ? "YES" : "NO");
  setText("tileTouchVal", s.touch ? "YES" : "NO");

  const tile = document.getElementById("tileDist");
  if (tile)
    tile.className = "sensor-tile" + (s.dist_cm < 50 ? " sensor-warn" : "");
  drawSensorChart();
}

// Chart
function drawSensorChart() {
  const canvas = document.getElementById("sensorChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const W = canvas.offsetWidth || 400;
  const H = 140;
  canvas.width = W;
  canvas.height = H;
  ctx.clearRect(0, 0, W, H);

  const hist = state.sensorHistory;
  if (hist.length < 2) return;

  // Grid lines
  ctx.strokeStyle = "rgba(255,255,255,0.04)";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = (i / 4) * H;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(W, y);
    ctx.stroke();
  }

  // Distance line
  const maxDist = 200;
  ctx.beginPath();
  ctx.strokeStyle = "#00e5ff";
  ctx.lineWidth = 1.5;
  hist.forEach((pt, i) => {
    const x = (i / (hist.length - 1)) * W;
    const y = H - Math.min(pt.dist_cm / maxDist, 1) * H;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Fill under line
  ctx.lineTo(W, H);
  ctx.lineTo(0, H);
  ctx.closePath();
  ctx.fillStyle = "rgba(0,229,255,0.05)";
  ctx.fill();

  // Label
  ctx.fillStyle = "rgba(0,229,255,0.5)";
  ctx.font = "10px Inter";
  ctx.fillText("Distance (0–200cm)", 8, 14);
}

// Template
function html() {
  return `
  <div class="page-header">
    <div class="page-title">DASHBOARD</div>
    <div class="page-sub">Live robot status and sensor overview</div>
  </div>
  <div class="stat-bar">
    <div class="stat-item">
      <div class="stat-num" id="dashDist">—</div>
      <div class="stat-lbl">Distance (cm)</div>
    </div>
    <div class="stat-item">
      <div class="stat-num" id="dashPIR" style="font-size:16px">—</div>
      <div class="stat-lbl">Presence</div>
    </div>
    <div class="stat-item">
      <div class="stat-num" id="dashTouch" style="font-size:16px">—</div>
      <div class="stat-lbl">Touch</div>
    </div>
    <div class="stat-item">
      <div class="stat-num" id="dashEmotion" style="font-size:16px">—</div>
      <div class="stat-lbl">Emotion</div>
    </div>
  </div>
  <div class="grid-2">
    <div class="card">
      <div class="card-title">Sensor Timeline</div>
      <canvas id="sensorChart" height="140" style="width:100%"></canvas>
    </div>
    <div class="card">
      <div class="card-title">Robot State</div>
      <div class="sensor-grid">
        <div class="sensor-tile" id="tileDist">
          <div class="sensor-val" id="tilDistVal">—</div>
          <div class="sensor-label">Distance cm</div>
        </div>
        <div class="sensor-tile" id="tilePIR">
          <div class="sensor-val" id="tilePIRVal">—</div>
          <div class="sensor-label">PIR Motion</div>
        </div>
        <div class="sensor-tile" id="tileTouch">
          <div class="sensor-val" id="tileTouchVal">—</div>
          <div class="sensor-label">Touch</div>
        </div>
      </div>
      <div class="divider"></div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:4px" id="dashTags">
        <span class="badge badge-cyan"   id="connBadge">Disconnected</span>
        <span class="badge badge-violet" id="modeBadge">—</span>
        <span class="badge badge-green"  id="emotionBadge">neutral</span>
      </div>
    </div>
  </div>
  <div class="card">
    <div class="card-title">Quick Actions</div>
    <div class="flex-row flex-wrap" id="quickActions">
      <button class="btn btn-secondary" data-gesture="wave">👋 Wave</button>
      <button class="btn btn-secondary" data-gesture="nod">🤝 Nod</button>
      <button class="btn btn-secondary" data-gesture="happy">😄 Happy</button>
      <button class="btn btn-violet"    id="openControlBtn">Open Control →</button>
      <button class="btn btn-danger"    id="estopDashBtn">⊗ Emergency Stop</button>
    </div>
  </div>
  `;
}

function wireQuickActions() {
  document.querySelectorAll("[data-gesture]").forEach((btn) => {
    btn.addEventListener("click", () => sendGesture(btn.dataset.gesture));
  });
  document
    .getElementById("openControlBtn")
    .addEventListener("click", () => window.showPage("control"));
  document
    .getElementById("estopDashBtn")
    .addEventListener("click", emergencyStop);
}

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
}

async function emergencyStop() {
  await window.robot.emergencyStop();
}
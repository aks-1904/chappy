import { state } from "../state.js";
import { toast } from "../utils/dom.js";

const CONTENT = document.getElementById("mainContent");

// Render
export async function renderSettings() {
  CONTENT.innerHTML = shellHtml();
  state.settings = await window.robot.getSettings();
  wireTabNav();
  wireSaveBtn();
  showTab("connection");
}

// Shell
function shellHtml() {
  return `
  <div class="page-header">
    <div class="page-title">SETTINGS</div>
    <div class="page-sub">Configure all robot parameters</div>
  </div>
  <div class="tabs" id="settingsTabs">
    <div class="tab active" data-tab="connection">Connection</div>
    <div class="tab"        data-tab="audio">Audio</div>
    <div class="tab"        data-tab="vision">Vision</div>
    <div class="tab"        data-tab="ai">AI / LLM</div>
    <div class="tab"        data-tab="integrations">Integrations</div>
  </div>
  <div id="settingsContent"></div>
  <div class="flex-row mt16" style="justify-content:flex-end">
    <button class="btn btn-primary" id="saveSettingsBtn">Save All Settings</button>
  </div>
  `;
}

// Tab nav 
function wireTabNav() {
  document.querySelectorAll("#settingsTabs .tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document
        .querySelectorAll("#settingsTabs .tab")
        .forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      showTab(tab.dataset.tab);
    });
  });
}

function showTab(tab) {
  const el = document.getElementById("settingsContent");
  if (!el) return;
  el.innerHTML = TAB_RENDERERS[tab]?.() ?? "";
  if (tab === "vision") wireVisionBrowse();
}

// Helpers 
const s = () => state.settings;

// Render a standard text/number input bound to a settings key
function field(key, label, type = "text", extra = "") {
  return `
  <div class="form-group">
    <label class="form-label">${label}</label>
    <input class="form-control" id="s_${key}" type="${type}" value="${s()[key] ?? ""}" ${extra}>
  </div>`;
}

// Render a <select> bound to a settings key.
function selectField(key, label, options) {
  return `
  <div class="form-group">
    <label class="form-label">${label}</label>
    <select class="form-control" id="s_${key}">
      ${options.map((o) => `<option value="${o}" ${s()[key] === o ? "selected" : ""}>${o}</option>`).join("")}
    </select>
  </div>`;
}

// Tab content renderers 
const TAB_RENDERERS = {
  connection: () => `
    <div class="grid-2">
      <div class="card">
        <div class="card-title">Serial / Arduino</div>
        ${field("serial_port", "Default Serial Port")}
      </div>
      <div class="card">
        <div class="card-title">Wireless / ESP32</div>
        ${field("ws_port", "WebSocket Port", "number")}
        ${field("ws_path", "WebSocket Path")}
        ${field("laptop_ip", "Laptop IP (shown in firmware)")}
      </div>
    </div>
    <div class="grid-2">
      <div class="card">
        <div class="card-title">Proximity Thresholds</div>
        ${field("greet_distance", "Greet Distance (cm)", "number")}
        ${field("handshake_distance", "Handshake Distance (cm)", "number")}
        ${field("greet_cooldown", "Greet Cooldown (sec)", "number")}
        ${field("proactive_checkin_interval", "Proactive Check-in Interval (sec)", "number")}
      </div>
    </div>`,

  audio: () => `
    <div class="grid-2">
      <div class="card">
        <div class="card-title">Speech Recognition (Whisper)</div>
        ${selectField("whisper_model", "Model Size", ["tiny", "base", "small", "medium", "large"])}
        ${field("whisper_language", "Language Code (e.g. en, hi)")}
      </div>
      <div class="card">
        <div class="card-title">Text-to-Speech</div>
        ${field("tts_rate", "Speech Rate (words/min)", "number")}
        <div class="form-group">
          <label class="form-label">Volume: <span id="volVal">${s().tts_volume ?? 0.9}</span></label>
          <div class="range-wrap">
            <input type="range" min="0" max="1" step="0.05" value="${s().tts_volume ?? 0.9}" id="s_tts_volume">
          </div>
        </div>
        ${field("tts_voice_index", "Voice Index", "number")}
      </div>
    </div>`,

  vision: () => `
    <div class="grid-2">
      <div class="card">
        <div class="card-title">Camera</div>
        ${field("camera_index", "Camera Device Index", "number")}
        <div class="form-group">
          <label class="form-label">Face Database Path</label>
          <div class="flex-row">
            <input class="form-control" id="s_face_db_path" value="${s().face_db_path ?? "./faces"}">
            <button class="btn btn-secondary" id="browseFacePathBtn">Browse</button>
          </div>
        </div>
      </div>
    </div>`,

  ai: () => `
    <div class="grid-2">
      <div class="card">
        <div class="card-title">Ollama / LLM</div>
        ${field("ollama_host", "Ollama Host URL")}
        ${field("ollama_model", "Model Name")}
      </div>
    </div>`,

  integrations: () => `
    <div class="grid-2">
      <div class="card">
        <div class="card-title">Weather (OpenWeatherMap)</div>
        ${field("openweather_api_key", "API Key")}
      </div>
      <div class="card">
        <div class="card-title">News API</div>
        ${field("news_api_key", "API Key")}
      </div>
      <div class="card">
        <div class="card-title">Email (Gmail SMTP)</div>
        ${field("email_smtp", "SMTP Host")}
        ${field("email_port", "SMTP Port", "number")}
        ${field("email_user", "Username / Email")}
        <div class="form-group">
          <label class="form-label">Password / App Password</label>
          <input class="form-control" id="s_email_pass" type="password" value="${s().email_pass ?? ""}">
        </div>
      </div>
    </div>`,
};

// Wiring
function wireVisionBrowse() {
  const btn = document.getElementById("browseFacePathBtn");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    const p = await window.robot.chooseFile();
    if (p) {
      const el = document.getElementById("s_face_db_path");
      if (el) el.value = p;
    }
  });
}

// Volume slider live label 
CONTENT.addEventListener("input", (e) => {
  if (e.target.id === "s_tts_volume") {
    const el = document.getElementById("volVal");
    if (el) el.textContent = parseFloat(e.target.value).toFixed(2);
  }
});

function wireSaveBtn() {
  // Save btn is outside #settingsContent, so wire once on shell render
  document
    .getElementById("saveSettingsBtn")
    .addEventListener("click", saveSettings);
}

async function saveSettings() {
  const inputs = document.querySelectorAll('[id^="s_"]');
  const obj = {};
  inputs.forEach((el) => {
    obj[el.id.slice(2)] = el.value;
  });
  await window.robot.saveSettings(obj);
  state.settings = { ...state.settings, ...obj };
  toast("Settings saved!", "success");
}

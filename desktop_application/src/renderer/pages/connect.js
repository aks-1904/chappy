import { state } from "../state.js";
import { toast } from "../utils/dom.js";
import { updateConnectionUI } from "../events.js";
import { showPage } from "../router.js";

const CONTENT = document.getElementById("mainContent");

export async function renderConnect() {
  CONTENT.innerHTML = html();
  await init();
}

function html() {
  return `
  <div class="connect-hero">
    <div class="connect-orb"></div>
    <div class="connect-title">COMPANION ROBOT</div>
    <div class="connect-sub">Choose how to connect to your robot</div>
  </div>
  <div class="grid-2" style="max-width:700px;margin:0 auto">
    <div class="card">
      <div class="card-title">Arduino / USB Serial</div>
      <div class="form-group">
        <label class="form-label">Serial Port</label>
        <div class="flex-row">
          <select class="form-control" id="serialPort" style="flex:1"></select>
          <button class="btn btn-secondary btn-icon" id="refreshPortsBtn" title="Refresh">↺</button>
        </div>
      </div>
      <button class="btn btn-primary w100" id="serialConnectBtn">Connect via USB</button>
    </div>

    <div class="card">
      <div class="card-title">ESP32 / WiFi Wireless</div>
      <div class="form-group">
        <label class="form-label">WebSocket Port</label>
        <input class="form-control" id="wsPort" type="number" value="8765">
      </div>
      <div class="form-group">
        <label class="form-label">WS Path</label>
        <input class="form-control" id="wsPath" value="/robot">
      </div>
      <button class="btn btn-violet w100" id="wirelessConnectBtn">Start WS Server</button>
    </div>
  </div>
  <div id="connectStatus" style="text-align:center;margin-top:20px;color:var(--text-secondary);font-size:12px"></div>
  `;
}

async function init() {
  document
    .getElementById("refreshPortsBtn")
    .addEventListener("click", refreshPorts);
  document
    .getElementById("serialConnectBtn")
    .addEventListener("click", connectSerial);
  document
    .getElementById("wirelessConnectBtn")
    .addEventListener("click", connectWireless);

  await refreshPorts();

  const s = state.settings;
  if (s.ws_port) document.getElementById("wsPort").value = s.ws_port;
  if (s.ws_path) document.getElementById("wsPath").value = s.ws_path;
}

// Actions
async function refreshPorts() {
  const sel = document.getElementById("serialPort");
  if (!sel) return;
  const ports = await window.robot.listPorts();
  sel.innerHTML = ports.length
    ? ports
        .map(
          (p) =>
            `<option value="${p.path}">${p.path}${p.manufacturer ? " · " + p.manufacturer : ""}</option>`,
        )
        .join("")
    : '<option value="">No ports found</option>';
}

async function connectSerial() {
  const port = document.getElementById("serialPort")?.value;
  if (!port) {
    toast("Select a port first", "error");
    return;
  }
  setStatus("Connecting to " + port + "…");
  const result = await window.robot.connectSerial(port);
  if (!result.ok) {
    setStatus("Failed: " + result.error);
    toast("Connection failed", "error");
  } else {
    setTimeout(() => showPage("dashboard"), 600);
  }
}

async function connectWireless() {
  const port = parseInt(document.getElementById("wsPort")?.value ?? "8765");
  const wsPath = document.getElementById("wsPath")?.value ?? "/robot";
  setStatus(`Starting WebSocket server on port ${port}…`);
  const result = await window.robot.connectWireless({ port, path: wsPath });
  if (result.ok) {
    setStatus(
      `Server running on ws://0.0.0.0:${port}${wsPath} — waiting for ESP32...`,
    );
    updateConnectionUI(true, "waiting");
  } else {
    setStatus("Failed: " + result.error);
    toast("Could not start WS server", "error");
  }
}

function setStatus(msg) {
  const el = document.getElementById("connectStatus");
  if (el) el.textContent = msg;
}

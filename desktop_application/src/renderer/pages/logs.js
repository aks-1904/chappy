import { state } from "../state.js";
import { escHtml } from "../utils/dom.js";
import { registerPageCallbacks } from "../events.js";

const CONTENT = document.getElementById("mainContent");

// Render
export async function renderLogs() {
  CONTENT.innerHTML = html();
  wireControls();
  registerPageCallbacks({ onLog: appendLogLine });

  const logs = await window.robot.getLogs(500);
  state.logLines = logs;
  renderAll(logs);
}

// Template 
function html() {
  return `
  <div class="page-header">
    <div class="page-title">SYSTEM LOGS</div>
    <div class="page-sub">Real-time diagnostics and event history</div>
  </div>
  <div class="card">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
      <div class="card-title" style="margin:0">Log Output</div>
      <div class="flex-row">
        <select class="form-control" id="logFilter" style="width:110px">
          <option value="all">All levels</option>
          <option value="info">Info</option>
          <option value="warn">Warn</option>
          <option value="error">Error</option>
          <option value="debug">Debug</option>
        </select>
        <button class="btn btn-secondary btn-sm" id="refreshLogsBtn">↺ Refresh</button>
        <button class="btn btn-secondary btn-sm" id="exportLogsBtn">⬇ Export</button>
        <button class="btn btn-danger btn-sm"    id="clearLogsBtn">Clear</button>
      </div>
    </div>
    <div class="log-viewer" id="logViewer"></div>
    <div style="display:flex;align-items:center;gap:8px;margin-top:8px">
      <input type="checkbox" id="autoScroll" checked>
      <label for="autoScroll" class="text-dim text-sm">Auto-scroll</label>
      <span class="text-dim text-sm" id="logCount" style="margin-left:auto"></span>
    </div>
  </div>
  `;
}

// Wire 
function wireControls() {
  document.getElementById("logFilter").addEventListener("change", filterLogs);
  document.getElementById("refreshLogsBtn").addEventListener("click", refresh);
  document
    .getElementById("exportLogsBtn")
    .addEventListener("click", () => window.robot.exportLogs());
  document.getElementById("clearLogsBtn").addEventListener("click", clearLogs);
}

// Rendering 
function currentFilter() {
  return document.getElementById("logFilter")?.value ?? "all";
}

function filtered(lines) {
  const f = currentFilter();
  return f === "all" ? lines : lines.filter((l) => l.level === f);
}

function renderAll(lines) {
  const viewer = document.getElementById("logViewer");
  if (!viewer) return;
  const rows = filtered(lines);
  viewer.innerHTML = rows.map(logLineHTML).join("");
  updateCount(rows.length);
  scrollToBottom();
}

function filterLogs() {
  renderAll(state.logLines);
}

async function refresh() {
  const logs = await window.robot.getLogs(500);
  state.logLines = logs;
  renderAll(logs);
}

function appendLogLine(entry) {
  const viewer = document.getElementById("logViewer");
  if (!viewer) return;
  if (currentFilter() !== "all" && entry.level !== currentFilter()) return;

  const div = document.createElement("div");
  div.innerHTML = logLineHTML(entry);
  viewer.appendChild(div.firstElementChild);
  updateCount(state.logLines.length);
  scrollToBottom();
}

function logLineHTML(l) {
  return `
  <div class="log-line ${l.level ?? ""}">
    <span class="ts">${l.ts ? l.ts.slice(11, 19) : ""} </span>
    <span class="lvl">${(l.level ?? "").toUpperCase().slice(0, 5)}</span>
    <span> ${escHtml(l.message ?? "")}</span>
  </div>`;
}

function updateCount(n) {
  const el = document.getElementById("logCount");
  if (el) el.textContent = `${n} entries`;
}

function scrollToBottom() {
  const autoScroll = document.getElementById("autoScroll");
  const viewer = document.getElementById("logViewer");
  if (viewer && autoScroll?.checked) viewer.scrollTop = viewer.scrollHeight;
}

async function clearLogs() {
  await window.robot.clearLogs();
  state.logLines = [];
  const viewer = document.getElementById("logViewer");
  if (viewer) viewer.innerHTML = "";
  updateCount(0);
}

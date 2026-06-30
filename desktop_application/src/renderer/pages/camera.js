import { state } from "../state.js";
import { toast, fmtDate } from "../utils/dom.js";
import { registerPageCallbacks } from "../events.js";

const CONTENT = document.getElementById("mainContent");

let _fpsCount = 0;
let _lastFpsTick = 0;

// Render
export async function renderCamera() {
  CONTENT.innerHTML = html();
  registerPageCallbacks({
    onFrame: updateCameraUI,
    onEmotion: updateEmotionBadge,
  });

  loadFaceList();
  if (state.liveFrame) updateCameraUI(state.liveFrame);
}

// Template
function html() {
  return `
  <div class="page-header">
    <div class="page-title">CAMERA & FACE REGISTRATION</div>
    <div class="page-sub">Live feed from robot camera · Register faces for recognition</div>
  </div>
  <div class="grid-2">
    <div>
      <div class="card-title" style="margin-bottom:8px">Live Feed</div>
      <div class="camera-wrap" id="cameraWrap">
        <canvas id="liveCanvas"></canvas>
        <div class="camera-overlay">
          <span id="camFps">—</span>
          <span id="camRes">—</span>
        </div>
        <div class="emotion-badge" id="emotionBadgeOverlay">${state.emotion}</div>
        <div class="camera-no-signal" id="camNoSignal">No camera signal</div>
      </div>
    </div>

    <div>
      <div class="card">
        <div class="card-title">Register New Face</div>
        <div class="form-group">
          <label class="form-label">Person Name</label>
          <input class="form-control" id="faceNameInput" placeholder="e.g. Alice">
        </div>
        <p class="text-dim text-sm mb8">
          Aim the robot camera at the person's face, then click Capture.
        </p>
        <button class="btn btn-primary w100" id="captureBtn">📸 Capture & Register</button>
        <div id="captureStatus" class="text-dim text-sm mt8"></div>
      </div>

      <div class="card">
        <div class="card-title">Registered Faces</div>
        <div id="faceList">Loading…</div>
      </div>
    </div>
  </div>
  `;
}

// Camera feed
function updateCameraUI(frameData) {
  const canvas = document.getElementById("liveCanvas");
  const noSig = document.getElementById("camNoSignal");
  if (!canvas) return;

  const img = new Image();
  img.onload = () => {
    canvas.width = img.width;
    canvas.height = img.height;
    canvas.getContext("2d").drawImage(img, 0, 0);
    if (noSig) noSig.style.display = "none";

    // FPS counter
    _fpsCount++;
    const now = Date.now();
    if (now - _lastFpsTick >= 1000) {
      const fpsEl = document.getElementById("camFps");
      if (fpsEl) fpsEl.textContent = `${_fpsCount} fps`;
      _fpsCount = 0;
      _lastFpsTick = now;
    }
    const resEl = document.getElementById("camRes");
    if (resEl) resEl.textContent = `${img.width}×${img.height}`;
  };
  img.src = `data:image/jpeg;base64,${frameData.data}`;
}

function updateEmotionBadge() {
  const el = document.getElementById("emotionBadgeOverlay");
  if (el) el.textContent = state.emotion;
}

// Face registration
async function captureAndRegister() {
  const name = document.getElementById("faceNameInput")?.value.trim();
  const canvas = document.getElementById("liveCanvas");
  const status = document.getElementById("captureStatus");

  if (!name) {
    toast("Enter a name first", "error");
    return;
  }
  if (!canvas || canvas.width === 0) {
    toast("No camera frame available", "error");
    return;
  }

  if (status) status.textContent = "Registering…";
  const imageData = canvas.toDataURL("image/jpeg", 0.9);
  const result = await window.robot.registerFace({ name, imageData });

  if (result.ok) {
    if (status) status.textContent = `✓ Registered ${name}`;
    toast(`Face registered: ${name}`, "success");
    loadFaceList();
  } else {
    if (status) status.textContent = `Error: ${result.error ?? "Unknown"}`;
    toast("Registration failed", "error");
  }
}

async function loadFaceList() {
  const faces = await window.robot.listFaces();
  const el = document.getElementById("faceList");
  if (!el) return;

  if (!faces.length) {
    el.innerHTML = '<p class="text-dim text-sm">No faces registered yet.</p>';
    return;
  }

  el.innerHTML = faces
    .map(
      (f) => `
    <div class="rel-card">
      <div class="rel-avatar">👤</div>
      <div class="rel-info">
        <div class="rel-name">${f.name}</div>
        <div class="rel-meta">Registered ${fmtDate(f.created_at)}</div>
      </div>
      <button class="btn btn-danger btn-sm" data-delete-face="${f.name}">Delete</button>
    </div>
  `,
    )
    .join("");

  el.querySelectorAll("[data-delete-face]").forEach((btn) => {
    btn.addEventListener("click", () => deleteFace(btn.dataset.deleteFace));
  });
}

async function deleteFace(name) {
  await window.robot.deleteFace(name);
  toast(`Removed face: ${name}`, "info");
  loadFaceList();
}

// Wire events (called after html() inject)
// Using event delegation on CONTENT so listeners survive re-renders
CONTENT.addEventListener("click", (e) => {
  if (e.target.id === "captureBtn") captureAndRegister();
});

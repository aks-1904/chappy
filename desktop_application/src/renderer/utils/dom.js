export function toast(msg, type = "info") {
  const container = document.getElementById("toastContainer");
  const el = document.createElement("div");
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

// Safely set textContent of an element by ID
export function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

// Format a Unix timestamp (seconds) to locale date+time string
export function fmtDate(ts) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString();
}

// Format a Unix timestamp (seconds) to locale time string
export function fmtTime(ts) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleTimeString();
}

// Escape HTML special characters
export function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

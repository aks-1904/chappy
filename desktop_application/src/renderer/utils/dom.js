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

export function fmtDate(ts) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString();
}

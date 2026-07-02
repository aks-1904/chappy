import { state } from "../state.js";
import { toast, fmtDate, fmtTime, escHtml } from "../utils/dom.js";

const CONTENT = document.getElementById("mainContent");

// Render
export async function renderMemory() {
  CONTENT.innerHTML = shellHtml();
  state.users = await window.robot.getUsers();
  wireTabNav();
  showTab("users");
}

// Shell 
function shellHtml() {
  return `
  <div class="page-header">
    <div class="page-title">MEMORY & HISTORY</div>
    <div class="page-sub">Conversation history, users, and reminders</div>
  </div>
  <div class="tabs" id="memTabs">
    <div class="tab active" data-tab="users">Users</div>
    <div class="tab"        data-tab="history">Conversation</div>
    <div class="tab"        data-tab="reminders">Reminders</div>
  </div>
  <div id="memTabContent"></div>
  `;
}

// Tab nav 
function wireTabNav() {
  document.querySelectorAll("#memTabs .tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document
        .querySelectorAll("#memTabs .tab")
        .forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      showTab(tab.dataset.tab);
    });
  });
}

async function showTab(tab) {
  const el = document.getElementById("memTabContent");
  if (!el) return;

  if (tab === "users") {
    el.innerHTML = usersHtml(state.users);
    wireUsers();
  } else if (tab === "history") {
    el.innerHTML = historyHtml();
    wireHistory();
  } else {
    const reminders = await window.robot.getReminders();
    el.innerHTML = remindersHtml(reminders);
  }
}

// Users tab
function usersHtml(users) {
  return `
  <div class="card">
    <div class="card-title">Known Users (${users.length})</div>
    ${
      users.length
        ? `
    <table class="data-table">
      <thead><tr><th>Name</th><th>First Seen</th><th>Last Seen</th><th>Actions</th></tr></thead>
      <tbody>
        ${users
          .map(
            (u) => `
          <tr>
            <td><strong>${u.name}</strong></td>
            <td class="text-mono text-dim text-sm">${fmtDate(u.first_seen)}</td>
            <td class="text-mono text-dim text-sm">${fmtDate(u.last_seen)}</td>
            <td>
              <div class="flex-row">
                <button class="btn btn-secondary btn-sm" data-view-history="${u.name}">History</button>
                <button class="btn btn-danger btn-sm"    data-delete-user="${u.name}">Delete</button>
              </div>
            </td>
          </tr>
        `,
          )
          .join("")}
      </tbody>
    </table>`
        : '<p class="text-dim text-sm">No users in memory yet.</p>'
    }
  </div>
  `;
}

function wireUsers() {
  document.querySelectorAll("[data-view-history]").forEach((btn) => {
    btn.addEventListener("click", () =>
      viewHistoryForUser(btn.dataset.viewHistory),
    );
  });
  document.querySelectorAll("[data-delete-user]").forEach((btn) => {
    btn.addEventListener("click", () => deleteUser(btn.dataset.deleteUser));
  });
}

async function deleteUser(name) {
  await window.robot.deleteUser(name);
  state.users = state.users.filter((u) => u.name !== name);
  const el = document.getElementById("memTabContent");
  if (el) {
    el.innerHTML = usersHtml(state.users);
    wireUsers();
  }
  toast(`Deleted user: ${name}`, "info");
}

async function viewHistoryForUser(name) {
  // Switch to history tab and pre-select user
  document
    .querySelectorAll("#memTabs .tab")
    .forEach((t) => t.classList.remove("active"));
  const histTab = document.querySelector('#memTabs [data-tab="history"]');
  if (histTab) histTab.classList.add("active");
  const el = document.getElementById("memTabContent");
  if (!el) return;
  el.innerHTML = historyHtml();
  wireHistory();
  // Slight delay to let DOM settle
  setTimeout(() => {
    const sel = document.getElementById("histUserSel");
    if (sel) {
      sel.value = name;
      loadHistory(name);
    }
  }, 50);
}

// History tab
function historyHtml() {
  return `
  <div class="card">
    <div class="card-title">Conversation History</div>
    <div class="flex-row mb8">
      <select class="form-control" id="histUserSel">
        <option value="">Select user…</option>
        ${state.users.map((u) => `<option value="${u.name}">${u.name}</option>`).join("")}
      </select>
      <button class="btn btn-danger btn-sm" id="clearHistBtn">Clear History</button>
    </div>
    <div id="historyList"><p class="text-dim text-sm">Select a user to view history.</p></div>
  </div>
  `;
}

function wireHistory() {
  document
    .getElementById("histUserSel")
    .addEventListener("change", (e) => loadHistory(e.target.value));
  document
    .getElementById("clearHistBtn")
    .addEventListener("click", clearHistory);
}

async function loadHistory(username) {
  if (!username) return;
  const history = await window.robot.getHistory(username);
  const el = document.getElementById("historyList");
  if (!el) return;

  if (!history.length) {
    el.innerHTML = '<p class="text-dim text-sm">No history.</p>';
    return;
  }

  el.innerHTML = `
  <div style="max-height:400px;overflow-y:auto">
    ${history
      .map(
        (h) => `
      <div style="padding:8px;border-bottom:1px solid var(--border);display:flex;gap:10px">
        <span class="badge ${h.role === "user" ? "badge-cyan" : "badge-violet"}" style="flex-shrink:0">${h.role}</span>
        <span style="flex:1;font-size:13px">${escHtml(h.message)}</span>
        <span class="text-dim text-sm text-mono" style="flex-shrink:0">${fmtTime(h.timestamp)}</span>
      </div>
    `,
      )
      .join("")}
  </div>`;
}

async function clearHistory() {
  const sel = document.getElementById("histUserSel")?.value;
  if (!sel) {
    toast("Select a user", "error");
    return;
  }
  await window.robot.clearHistory(sel);
  toast("History cleared", "success");
  loadHistory(sel);
}

// Reminders tab 
function remindersHtml(reminders) {
  return `
  <div class="card">
    <div class="card-title">Reminders (${reminders.length})</div>
    ${
      reminders.length
        ? `
    <table class="data-table">
      <thead><tr><th>User</th><th>Text</th><th>Due</th><th>Status</th></tr></thead>
      <tbody>
        ${reminders
          .map(
            (r) => `
          <tr>
            <td>${r.user_name}</td>
            <td>${escHtml(r.text)}</td>
            <td class="text-mono text-sm">${fmtDate(r.due_time)}</td>
            <td>
              <span class="badge ${r.done ? "badge-green" : "badge-amber"}">
                ${r.done ? "Done" : "Pending"}
              </span>
            </td>
          </tr>
        `,
          )
          .join("")}
      </tbody>
    </table>`
        : '<p class="text-dim text-sm">No reminders.</p>'
    }
  </div>
  `;
}

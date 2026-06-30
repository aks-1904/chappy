import { state } from "../state.js";
import { toast } from "../utils/dom.js";

const CONTENT = document.getElementById("mainContent");

const ARCHETYPES = [
  "warm",
  "energetic",
  "calm",
  "witty",
  "nurturing",
  "professional",
];
const EMOTIONS = ["happy", "sad", "neutral", "angry", "calm", "excited"];
const RELATIONS = [
  "owner",
  "father",
  "mother",
  "son",
  "daughter",
  "brother",
  "sister",
  "grandfather",
  "grandmother",
  "uncle",
  "aunt",
  "cousin",
  "baby",
  "friend",
  "best friend",
  "colleague",
  "guest",
  "caregiver",
  "student",
  "elder",
];

const ARCHETYPE_ICONS = {
  warm: "❤️",
  energetic: "⚡",
  calm: "🌊",
  witty: "😄",
  nurturing: "🌱",
  professional: "💼",
};
const REL_EMOJI = {
  owner: "👑",
  father: "👨",
  mother: "👩",
  son: "👦",
  daughter: "👧",
  brother: "🧑",
  sister: "👧",
  grandfather: "👴",
  grandmother: "👵",
  friend: "😊",
  baby: "👶",
  "best friend": "⭐",
  colleague: "💼",
  guest: "🙋",
  elder: "🧓",
};

// Render
export async function renderPersona() {
  CONTENT.innerHTML = shellHtml();

  state.persona = await window.robot.getPersona();
  state.relationships = await window.robot.getRelationships();

  wireTabNav();
  showTab("identity");
}

// Shell
function shellHtml() {
  return `
  <div class="page-header">
    <div class="page-title">PERSONA & RELATIONSHIPS</div>
    <div class="page-sub">Customize robot personality and who it knows</div>
  </div>
  <div class="tabs" id="personaTabs">
    <div class="tab active" data-tab="identity">Robot Identity</div>
    <div class="tab"        data-tab="relationships">Relationships</div>
  </div>
  <div id="personaTabContent"></div>
  `;
}

// Tab nav
function wireTabNav() {
  document.querySelectorAll("#personaTabs .tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document
        .querySelectorAll("#personaTabs .tab")
        .forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      showTab(tab.dataset.tab);
    });
  });
}

function showTab(tab) {
  const el = document.getElementById("personaTabContent");
  if (!el) return;
  if (tab === "identity") {
    el.innerHTML = identityHtml();
    wireIdentity();
  } else {
    el.innerHTML = relationshipsHtml();
    wireRelationships();
  }
}

// Identity tab
function identityHtml() {
  const p = state.persona;
  return `
  <div class="grid-2">
    <div class="card">
      <div class="card-title">Robot Identity</div>
      <div class="form-group">
        <label class="form-label">Robot Name</label>
        <input class="form-control" id="pName" value="${p.name ?? "Buddy"}">
      </div>
      <div class="form-group">
        <label class="form-label">Catchphrase (optional)</label>
        <input class="form-control" id="pCatchphrase" value="${p.catchphrase ?? ""}" placeholder="e.g. Let's do this!">
      </div>
      <div class="form-group">
        <label class="form-label">Base Emotion / Default Mood</label>
        <select class="form-control" id="pBaseEmotion">
          ${EMOTIONS.map((e) => `<option value="${e}" ${p.base_emotion === e ? "selected" : ""}>${e}</option>`).join("")}
        </select>
      </div>
      <button class="btn btn-primary" id="savePersonaBtn">Save Identity</button>
    </div>

    <div class="card">
      <div class="card-title">Personality Archetype</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px" id="archetypeGrid">
        ${ARCHETYPES.map((a) => {
          const active = p.personality === a;
          return `
          <div class="gesture-btn" data-arch="${a}"
               style="${active ? "border-color:var(--cyan);color:var(--cyan);background:var(--cyan-glow)" : ""}">
            <span class="g-icon">${ARCHETYPE_ICONS[a] ?? "🤖"}</span>
            <span>${a}</span>
          </div>`;
        }).join("")}
      </div>
      <input type="hidden" id="pPersonality" value="${p.personality ?? "warm"}">
    </div>
  </div>
  `;
}

function wireIdentity() {
  document.querySelectorAll("[data-arch]").forEach((btn) => {
    btn.addEventListener("click", () => selectArchetype(btn));
  });
  document
    .getElementById("savePersonaBtn")
    .addEventListener("click", savePersona);
}

function selectArchetype(el) {
  document.querySelectorAll("[data-arch]").forEach((b) => {
    b.style.borderColor = "";
    b.style.color = "";
    b.style.background = "";
  });
  el.style.borderColor = "var(--cyan)";
  el.style.color = "var(--cyan)";
  el.style.background = "var(--cyan-glow)";
  document.getElementById("pPersonality").value = el.dataset.arch;
}

async function savePersona() {
  const data = {
    name: document.getElementById("pName")?.value.trim() ?? "Buddy",
    personality: document.getElementById("pPersonality")?.value ?? "warm",
    base_emotion: document.getElementById("pBaseEmotion")?.value ?? "happy",
    catchphrase: document.getElementById("pCatchphrase")?.value.trim() ?? "",
  };
  await window.robot.savePersona(data);
  state.persona = data;
  toast("Persona saved!", "success");
}

// Relationships tab
function relationshipsHtml() {
  return `
  <div class="card">
    <div class="card-title">People the Robot Knows</div>
    <div id="relList">${renderRelList(state.relationships)}</div>
    <div class="divider"></div>
    <div class="card-title mt16">Add / Edit Person</div>
    <div class="grid-2">
      <div>
        <div class="form-group">
          <label class="form-label">Name</label>
          <input class="form-control" id="relName" placeholder="e.g. Alice">
        </div>
        <div class="form-group">
          <label class="form-label">Nickname</label>
          <input class="form-control" id="relNick" placeholder="e.g. Ali">
        </div>
        <div class="form-group">
          <label class="form-label">Relationship</label>
          <select class="form-control" id="relType">
            ${RELATIONS.map((r) => `<option>${r}</option>`).join("")}
          </select>
        </div>
      </div>
      <div>
        <div class="form-group">
          <label class="form-label">Notes</label>
          <textarea class="form-control" id="relNotes" rows="3" placeholder="Any notes…"></textarea>
        </div>
        <div class="form-group">
          <label class="form-label">Love Level: <span id="loveLevelVal">5</span>/10</label>
          <div class="range-wrap">
            <input type="range" min="1" max="10" value="5" id="relLove">
          </div>
        </div>
      </div>
    </div>
    <button class="btn btn-violet" id="saveRelBtn">Save Relationship</button>
  </div>
  `;
}

function wireRelationships() {
  document.getElementById("relLove").addEventListener("input", (e) => {
    document.getElementById("loveLevelVal").textContent = e.target.value;
  });
  document
    .getElementById("saveRelBtn")
    .addEventListener("click", saveRelationship);
  wireRelListButtons();
}

function renderRelList(rels) {
  if (!rels.length)
    return '<p class="text-dim text-sm">No relationships defined yet.</p>';
  return rels
    .map(
      (r) => `
    <div class="rel-card">
      <div class="rel-avatar">${REL_EMOJI[r.relation] ?? "👤"}</div>
      <div class="rel-info">
        <div class="rel-name">
          ${r.person_name}
          ${r.nickname ? `<span class="text-dim text-sm">· "${r.nickname}"</span>` : ""}
        </div>
        <div class="rel-meta">${r.relation}</div>
        <div class="love-bar">
          ${Array.from(
            { length: 10 },
            (_, i) =>
              `<div class="love-dot${i < r.love_level ? " filled" : ""}"></div>`,
          ).join("")}
        </div>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px">
        <button class="btn btn-secondary btn-sm" data-edit-rel="${r.person_name}">Edit</button>
        <button class="btn btn-danger btn-sm"    data-del-rel="${r.person_name}">Delete</button>
      </div>
    </div>
  `,
    )
    .join("");
}

function wireRelListButtons() {
  document.querySelectorAll("[data-edit-rel]").forEach((btn) => {
    btn.addEventListener("click", () => editRelationship(btn.dataset.editRel));
  });
  document.querySelectorAll("[data-del-rel]").forEach((btn) => {
    btn.addEventListener("click", () => deleteRelationship(btn.dataset.delRel));
  });
}

function editRelationship(name) {
  const rel = state.relationships.find((r) => r.person_name === name);
  if (!rel) return;
  document.getElementById("relName").value = rel.person_name;
  document.getElementById("relNick").value = rel.nickname ?? "";
  document.getElementById("relNotes").value = rel.notes ?? "";
  document.getElementById("relLove").value = rel.love_level ?? 5;
  document.getElementById("loveLevelVal").textContent = rel.love_level ?? 5;
  const sel = document.getElementById("relType");
  if (sel) sel.value = rel.relation;
}

async function saveRelationship() {
  const rel = {
    person_name: document.getElementById("relName")?.value.trim(),
    nickname: document.getElementById("relNick")?.value.trim() ?? "",
    relation: document.getElementById("relType")?.value ?? "friend",
    notes: document.getElementById("relNotes")?.value.trim() ?? "",
    love_level: parseInt(document.getElementById("relLove")?.value ?? "5"),
  };
  if (!rel.person_name) {
    toast("Name is required", "error");
    return;
  }
  await window.robot.saveRelationship(rel);
  state.relationships = await window.robot.getRelationships();
  const listEl = document.getElementById("relList");
  if (listEl) {
    listEl.innerHTML = renderRelList(state.relationships);
    wireRelListButtons();
  }
  toast(`Saved: ${rel.person_name}`, "success");
}

async function deleteRelationship(name) {
  await window.robot.deleteRelationship(name);
  state.relationships = state.relationships.filter(
    (r) => r.person_name !== name,
  );
  const listEl = document.getElementById("relList");
  if (listEl) {
    listEl.innerHTML = renderRelList(state.relationships);
    wireRelListButtons();
  }
  toast(`Removed: ${name}`, "info");
}

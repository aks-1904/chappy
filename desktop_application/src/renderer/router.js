import { state } from "./state.js";
import { registerPageCallbacks } from "./events.js";

import { renderConnect } from "./pages/connect.js";

const PAGES = {
  connect: renderConnect,
};

export async function showPage(name) {
  if (!PAGES[name]) {
    console.warn(`[Router] Unkown page: ${name}`);
    return;
  }

  state.currentPage = name;

  // Update sidebar nav highlights
  document.querySelectorAll(".nav-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.page === name);
  });

  // Clear page callbacks - pages re-register them on render
  registerPageCallbacks({});

  // Render the page (each page writes its own HTML + wires events)
  await PAGES[name]();
}

// Expose to inline onclick handlers in HTML (connect page uses if for sub-actions)
window.showPage = showPage;

import { state } from "./state.js";
import { showPage } from "./router.js";

// Make showPage globally available if other modules need it
window.showPage = showPage;

// Title bar buttons
document.getElementById("minimize-button").addEventListener("click", () => {
  window.robot.minimize();
});

document.getElementById("maximize-button").addEventListener("click", () => {
  window.robot.maximize();
});

document.getElementById("close-button").addEventListener("click", () => {
  window.robot.close();
});

document.querySelector(".sidebar").addEventListener("click", async (e) => {
  const navItem = e.target.closest(".nav-item");

  if (navItem) {
    await showPage(navItem.dataset.page);
    return;
  }

  if (e.target.closest("#emergency-stop-button")) {
    window.robot.emergencyStop();
  }
});

// Initial startup
window.addEventListener("DOMContentLoaded", async () => {
  // state.settings = await window.robot.getSettings();

  await showPage("connect");
});

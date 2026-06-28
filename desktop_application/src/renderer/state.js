/**
 * Central state object for the renderer process.
 * All pages read from and write to this object.
 * @type {AppState}
 */
export const state = {
  connected: false,
  mode: null,
  emotion: "neutral",
  currentPage: "connect",
  gesturePending: false,

  sensor: { dist_cm: 0, pir: false, touch: false },
  sensorHistory: [], // max 120 entries

  logLines: [], // max 2000 entries
  liveFrame: null,

  // Loaded from DB on page render
  faces: [],
  relationships: [],
  users: [],
  persona: {},
  settings: {},
};

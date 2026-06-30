"use strict";

const { contextBridge, ipcRenderer } = require("electron");

// Channels the renderer is allowed to receive on.
const ALLOWED_EVENTS = [
  "robot:sensor",
  "robot:event",
  "robot:frame",
  "robot:log",
  "robot:connected",
  "robot:disconnected",
  "robot:emotion",
];

contextBridge.exposeInMainWorld("robot", {
  // Window
  minimize: () => ipcRenderer.send("window:minimize"),
  maximize: () => ipcRenderer.send("window:maximize"),
  close: () => ipcRenderer.send("window:close"),

  // Settings
  getSettings: () => ipcRenderer.invoke("settings:get"),

  // Connections
  listPorts: () => ipcRenderer.invoke("connect:list-ports"),
  connectSerial: (port) => ipcRenderer.invoke("connect:serial", port),
  connectWireless: (config) => ipcRenderer.invoke("connect:wireless", config),

  on(channel, cb) {
    if (!ALLOWED_EVENTS.includes(channel)) {
      console.warn(`[Preload] Blocked unknown channel: ${channel}`);
      return () => {};
    }
    const handler = (_, data) => cb(data);
    ipcRenderer.on(channel, handler);
    return () => ipcRenderer.removeListener(channel, handler);
  },
});

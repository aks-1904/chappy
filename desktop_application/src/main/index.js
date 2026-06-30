"use strict";

import { nativeTheme, BrowserWindow, app } from "electron";
import path from "path";
import { fileURLToPath } from "url";
import { registerIpcHandlers } from "./ipc.js";
import { DatabaseManager } from "./database.js";
import { RobotBridge } from "./robot-bridge.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

nativeTheme.themeSource = "dark";

/** @type {BrowserWindow | null} */
let mainWindow = null;
/** @type {RobotBridge | null} */
let robotBridge = null;
/** @type {DatabaseManager | null} */
let db = null;

// Window
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    backgroundColor: "#0a0e1a",
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "hidden",
    frame: false,
    webPreferences: {
      preload: path.join(__dirname, "../preload/index.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
    icon: path.join(__dirname, "../assets/icon.png"),
  });

  mainWindow.loadFile(path.join(__dirname, "../renderer/index.html"));

  if (process.argv.includes("--dev")) {
    mainWindow.webContents.openDevTools();
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
    robotBridge?.disconnect();
  });
}

// Send an IPC event to the renderer
function send(channel, data) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(channel, data);
  }
}

// Wire robot-bridge events -> renderer IPC channels
function bridgeEvents(bridge) {
  const forward = (bridgeEvent, ipcChannel) =>
    bridge.on(bridgeEvent, (data) => send(ipcChannel, data));

  forward("sensor", "robot:sensor");
  forward("event", "robot:event");
  forward("frame", "robot:frame");
  forward("log", "robot:log");
  forward("connected", "robot:connected");
  forward("disconnected", "robot:disconnected");
  forward("emotion", "robot:emotion");
}

app.whenReady().then(() => {
  db = new DatabaseManager();
  robotBridge = new RobotBridge(db);

  bridgeEvents(robotBridge);
  registerIpcHandlers({ db, robotBridge, getWindow: () => mainWindow });

  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  robotBridge?.disconnect();
  if (process.platform !== "darwin") app.quit();
});
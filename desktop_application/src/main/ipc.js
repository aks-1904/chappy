"use strict";

import { ipcMain, dialog } from "electron";
import fs from "fs";

/**
 * Register all IPC handlers.
 * @param {{ db: import('./database').DatabaseManager, robotBridge: import('./robot-bridge').RobotBridge, getWindow: () => Electron.BrowserWindow | null }} ctx
 */
export function registerIpcHandlers({ db, robotBridge, getWindow }) {
  // Window controls
  ipcMain.on("window:minimize", () => getWindow()?.minimize());
  ipcMain.on("window:maximize", () => {
    const win = getWindow();
    if (win?.isMaximized()) win.unmaximize();
    else win?.maximize();
  });
  ipcMain.on("window:close", () => getWindow()?.close());

  // Connections
  ipcMain.handle("connect:list-ports", () => robotBridge.listPorts());
  ipcMain.handle("connect:serial", (_, port) =>
    robotBridge.connectSerial(port),
  );
  ipcMain.handle("connect:wireless", (_, config) =>
    robotBridge.connectWireless(config),
  );

  // Settings
  ipcMain.handle("settings:get", () => db.getSettings());
}

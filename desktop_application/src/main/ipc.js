"use strict";

import { ipcMain, dialog } from "electron";
import fs from "fs";

export function registerIpcHandlers({ getWindow }) {
  // Window controls
  ipcMain.on("window:minimize", () => getWindow()?.minimize());
  ipcMain.on("window:maximize", () => {
    const win = getWindow();
    if (win?.isMaximized()) win.unmaximize();
    else win?.maximize();
  });
  ipcMain.on("window:close", () => getWindow()?.close());
}

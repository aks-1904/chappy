"use strict";

import EventEmitter from "events";
import WebSocket, { WebSocketServer } from "ws";
import fs from "fs";
import path from "path";
import { SerialPort } from "serialport";
import { ReadlineParser } from "@serialport/parser-readline";

export class RobotBridge extends EventEmitter {
  constructor(db) {
    super();
    this._db = db;
    this._mode = null; // 'serial' | 'wireless' | null
    this._serial = null;
    this._ws = null;
    this._wsServer = null;
    this._connected = false;
    this._esp32Connected = false;
    this._lastSensor = {};
    this._stopped = false;
  }

  // Status
  getStatus() {
    return {
      connected: this._connected,
      mode: this._mode,
      esp32Connected: this._esp32Connected,
      lastSensor: this._lastSensor,
    };
  }

  // Serial (Arduino)
  async listPorts() {
    if (!SerialPort) return [];

    try {
      const ports = await SerialPort.list();

      return ports.map(({ path: p, manufacturer = "", vendorId = "" }) => ({
        path: p,
        manufacturer,
        vendorId,
      }));
    } catch {
      return [];
    }
  }

  async connectSerial(portPath) {
    this._stopped = false;

    return new Promise((resolve) => {
      try {
        this._serial = new SerialPort({
          path: portPath,
          baudRate: 115200,
          autoOpen: false,
        });
      } catch (e) {
        return resolve({ ok: false, error: e.message });
      }

      this._serial.open((err) => {
        if (err) {
          this._log("error", `Serial open failed: ${err.message}`);
          return resolve({ ok: false, error: err.message });
        }

        const parser = this._serial.pipe(
          new ReadlineParser({ delimiter: "\n" }),
        );
        parser.on("data", (line) => this._handleLine(line.trim()));

        this._serial.on("error", (e) => {
          this._log("error", `Serial error: ${e.message}`);
          this._setConnected(false);
        });

        this._serial.on("close", () => {
          this._log("warn", "Serial port closed");
          this._setConnected(false);
          if (!this._stopped) this._scheduleSerialReconnect(portPath);
        });

        this._mode = "serial";
        this._setConnected(true);
        this._log("info", `Connected via Serial on ${portPath}`);
        resolve({ ok: true });
      });
    });
  }

  _handleLine(line) {
    if (!line) return;
    try {
      this._routeMessage(JSON.parse(line));
    } catch {
      this._log("debug", `Non-JSON serial: ${line}`);
    }
  }

  _scheduleSerialReconnect(portPath) {
    setTimeout(() => {
      if (!this._stopped) {
        this._log("info", "Attempting serial reconnect...");
        this.connectSerial(portPath);
      }
    }, 3000);
  }

  // Wireless (ESP32)
  async connectWireless(config = {}) {
    this._stopped = false;
    const port = config.port ?? 8765;
    const wsPath = config.path ?? "/robot";

    return new Promise((resolve) => {
      const wss = new WebSocketServer({ port });
      wss.on("listening", () => {
        this._log(
          "info",
          `WebSocket server listening on ws://0.0.0.0:${port}${wsPath}`,
        );

        this._mode = "wireless";
        this._setConnected(true);

        resolve({
          ok: true,
          port,
        });
      });

      wss.on("error", (e) => {
        this._log("error", `WS Server error: ${e.message}`);
        resolve({ ok: false, error: e.message });
      });

      wss.on("connection", (ws, req) => {
        const ip = req.socket.remoteAddress;
        this._log("info", `ESP32 connected from ${ip}`);
        this._ws = ws;
        this._esp32Connected = true;
        this.emit("connected", { mode: "wireless", ip });

        ws.on("message", (raw) => {
          try {
            this._routeMessage(JSON.parse(raw.toString()));
          } catch {
            this._log("debug", `Non-JSON WS: ${raw.toString().slice(0, 80)}`);
          }
        });

        ws.on("close", () => {
          this._log("warn", "ESP32 disconnected");
          this._ws = null;
          this._esp32Connected = false;
          this.emit("disconnected", { reason: "esp32_dropped" });
        });

        ws.on("error", (e) =>
          this._log("error", `ESP32 WS error: ${e.message}`),
        );
      });

      this._wsServer = wss;
    });
  }

  // Message Router
  _routeMessage(msg) {
    const type = msg.type ?? msg.event ?? "";

    switch (type) {
      case "sensors":
      case "sensor": {
        const sensor = {
          dist_cm: msg.dist_cm ?? msg.data?.dist_cm ?? 999,
          pir: msg.pir ?? msg.data?.pir ?? false,
          touch: msg.touch ?? msg.data?.touch ?? false,
          ts: Date.now(),
        };
        this._lastSensor = sensor;
        this.emit("sensor", sensor);
        break;
      }
      case "frame":
        this.emit("frame", { data: msg.data, w: msg.w, h: msg.h });
        break;

      case "event": {
        const evt = msg.event ?? msg.data?.event;
        this.emit("event", { event: evt, data: msg.data ?? {} });
        this._log("info", `Robot event: ${evt}`);
        break;
      }
      case "presence_detected":
        this.emit("event", { event: "presence_detected", data: {} });
        this._log("info", "Presence detected");
        break;

      case "touch_detected":
        this.emit("event", { event: "touch_detected", data: {} });
        this._log("info", "Touch detected");
        break;

      case "gesture_done":
        this.emit("event", { event: "gesture_done", data: msg.data ?? {} });
        break;

      case "ready":
        this._log("info", "Robot says: ready");
        this.emit("event", { event: "ready", data: {} });
        break;

      case "pong":
        break;

      default:
        this._log("debug", `Unknown msg type: ${type}`);
    }
  }

  // Commands
  sendCommand(cmd, payload = {}) {
    const msg = JSON.stringify({ cmd, ...payload });

    if (this._mode === "serial" && this._serial?.isOpen) {
      this._serial.write(msg + "\n");
      this._log("debug", `→ Serial: ${cmd}`);
      return { ok: true };
    }

    if (this._mode === "wireless" && this._ws?.readyState === WebSocket.OPEN) {
      this._ws.send(msg);
      this._log("debug", `→ WS: ${cmd}`);
      return { ok: true };
    }

    this._log("warn", `Command dropped (not connected): ${cmd}`);

    return { ok: false, error: "Not connected" };
  }

  emergencyStop() {
    this._log("warn", "EMERGENCY STOP");
    this.sendCommand("neutral");
    this.sendCommand("thinking_stop");
    this.sendCommand("speaking_stop");
    return { ok: true };
  }

  registerFace(name, imageData) {
    const facesDir = this._db.getSetting("face_db_path") ?? "./faces";
    const dir = path.join(facesDir, name);

    fs.mkdirSync(dir, { recursive: true });
    const buf = Buffer.from(imageData.split(",")[1], "base64");
    const fname = path.join(dir, `${Date.now()}.jpg`);
    fs.writeFileSync(fname, buf);
    this._db.addFace(name);
    this._log("info", `Face registered for ${name}: ${fname}`);

    return { ok: true, path: fname };
  }

  disconnect() {
    this._stopped = true;
    if (this._serial?.isOpen) {
      this._serial.close();
      this._serial = null;
    }
    if (this._ws) {
      this._ws.close();
      this._ws = null;
    }
    if (this._wsServer) {
      this._wsServer.close();
      this._wsServer = null;
    }
    this._mode = null;
    this._setConnected(false);
    this._log("info", "Disconnected");

    return { ok: true };
  }

  // Helpers
  _setConnected(val) {
    this._connected = val;
    if (val) this.emit("connected", { mode: this._mode });
    else this.emit("disconnected", {});
  }

  _log(level, message) {
    const entry = { level, message, ts: new Date().toISOString() };
    this._db?.addLog(entry);
    this.emit("log", entry);

    const method =
      level === "error" ? "error" : level === "warn" ? "warn" : "log";
  }
}

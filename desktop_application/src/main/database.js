"use strict";

import path from "path";
import { app } from "electron";
import Database from "better-sqlite3";

const DB_PATH = path.join(
  app?.getPath("userData") || ".",
  "robot-companion.db",
);

const SCHEMA = `
CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT
);
CREATE TABLE IF NOT EXISTS robot_persona (
  id           INTEGER PRIMARY KEY DEFAULT 1,
  name         TEXT DEFAULT 'Buddy',
  personality  TEXT DEFAULT 'warm',
  base_emotion TEXT DEFAULT 'happy',
  catchphrase  TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS relationships (
  person_name TEXT PRIMARY KEY,
  relation    TEXT DEFAULT 'friend',
  nickname    TEXT DEFAULT '',
  love_level  INTEGER DEFAULT 5,
  notes       TEXT DEFAULT '',
  updated_at  REAL
);
CREATE TABLE IF NOT EXISTS users (
  name       TEXT PRIMARY KEY,
  first_seen REAL,
  last_seen  REAL,
  notes      TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS interactions (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  user_name TEXT,
  role      TEXT,
  message   TEXT,
  emotion   TEXT DEFAULT 'neutral',
  timestamp REAL
);
CREATE TABLE IF NOT EXISTS reminders (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  user_name TEXT,
  text      TEXT,
  due_time  REAL,
  done      INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS faces (
  name       TEXT PRIMARY KEY,
  created_at REAL
);
CREATE TABLE IF NOT EXISTS logs (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  level   TEXT,
  message TEXT,
  ts      TEXT
);
CREATE INDEX IF NOT EXISTS idx_logs_ts ON logs(ts);
CREATE INDEX IF NOT EXISTS idx_interactions_user ON interactions(user_name, timestamp);
`;

const DEFAULT_SETTINGS = {
  serial_port: "",
  ws_port: "8765",
  ws_path: "/robot",
  wifi_ssid: "",
  laptop_ip: "192.168.1.100",
  whisper_model: "base",
  whisper_language: "en",
  tts_rate: "180",
  tts_volume: "0.9",
  tts_voice_index: "0",
  camera_index: "0",
  face_db_path: "./faces",
  ollama_host: "http://localhost:11434",
  ollama_model: "llama3",
  greet_distance: "120",
  handshake_distance: "40",
  greet_cooldown: "600",
  proactive_checkin_interval: "300",
  openweather_api_key: "",
  news_api_key: "",
  email_smtp: "smtp.gmail.com",
  email_port: "587",
  email_user: "",
  email_pass: "",
  log_max_rows: "5000",
};

export class DatabaseManager {
  constructor() {
    this._db = new Database(DB_PATH);
    this._db.exec(SCHEMA);
    this._seedDefaults();
  }

  getDbPath() {
    return DB_PATH;
  }

  _seedDefaults() {
    const insert = this._db.prepare(
      "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
    );
    for (const [k, v] of Object.entries(DEFAULT_SETTINGS)) {
      insert.run(k, v);
    }
    this._db
      .prepare("INSERT OR IGNORE INTO robot_persona(id) VALUES (1)")
      .run();
  }

  // Settings
  getSettings() {
    if (this._mock) return { ...DEFAULT_SETTINGS };
    const rows = this._db.prepare("SELECT key, value FROM settings").all();
    return Object.fromEntries(rows.map((r) => [r.key, r.value]));
  }

  getSetting(key) {
    if (this._mock) return DEFAULT_SETTINGS[key];
    return this._db.prepare("SELECT value FROM settings WHERE key=?").get(key)
      ?.value;
  }
}

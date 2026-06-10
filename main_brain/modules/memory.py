import logging
from pathlib import Path
from contextlib import contextmanager
import sqlite3
import time
from typing import Optional
import json
import datetime

from config.settings import MEMORY

log = logging.getLogger(__name__)

# Postgres Database Schema
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    UNIQUE NOT NULL,
    first_seen  REAL    NOT NULL,
    last_seen   REAL    NOT NULL,
    preferences TEXT    DEFAULT '{}',   -- JSON blob
    notes       TEXT    DEFAULT ''
);

CREATE TABLE IF NOT EXISTS interactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name   TEXT    NOT NULL,
    role        TEXT    NOT NULL,       -- 'user' or 'robot'
    message     TEXT    NOT NULL,
    emotion     TEXT    DEFAULT 'neutral',
    timestamp   REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS reminders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name   TEXT    NOT NULL,
    text        TEXT    NOT NULL,
    due_time    REAL    NOT NULL,
    done        INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_interactions_user
    ON interactions(user_name, timestamp);

CREATE INDEX IF NOT EXISTS idx_reminders_due
    ON reminders(due_time, done);
"""

def _fmt_time(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %h:%M")

class MemoryModule:
    def __init__(self):
        db_path = Path(MEMORY["db_path"])
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = str(db_path)
        self._init_db()

    def _init_db(self):
        with self._conn() as con:
            con.executescript(SCHEMA)
        log.info(f"[Memory] DB ready at {self._db_path}")

    @contextmanager
    def _conn(self):
        con = sqlite3.connect(
            self._db_path,
            check_same_thread=False
            )
        con.row_factory = sqlite3.Row

        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def build_context_for_llm(self, user_name: str) -> str:
        user = self.get_user(user_name)
        if not user:
            return f"You are speaking with an unkown person."
        
        history = self.get_history(user_name, limit=MEMORY["summary_after"])
        prefs = user["preferences"]
        notes = user.get("notes", "")

        lines = [
            f"User: {user_name}",
            f"Known since: {_fmt_time(user['first_seen'])}",
            f"Last seen:   {_fmt_time(user['last_seen'])}",
        ]
        if prefs:
            lines.append(f"Preferences: {json.dumps(prefs)}")
        if notes:
            lines.append(f"Notes: {notes}")

        # Recent conversation turns
        if history:
            lines.append("Recent conversation:")
            for turn in history[-6:]:   # last 3 exchanges
                speaker = "Human" if turn["role"] == "user" else "Robot"
                lines.append(f"  {speaker}: {turn['message']}")

        return "\n".join(lines)

    def to_llm_messages(self, user_name: str) -> list[dict]:
        history = self.get_history(
            user_name, limit=MEMORY["summary_after"]
        )
        messages = []
        for turn in history:
            role = "user" if turn["role"] == "user" else "assistant"
            messages.append({"role": role, "content": turn["message"]})
        return messages

    def upsert_user(self, name: str) -> dict:
        now = time.time()
        
        with self._conn() as con:
            row = con.execute("SELECT * from users WHERE name = ?", (name,)).fetchone()

            if row is None:
                con.execute(
                    "INSERT INTO users(name, first_seen, last_seen) VALUES (?,?,?)",
                    (name, now, now),
                )
                log.info(f"[Memory] New user registered: {name}")
            else:
                con.execute(
                    "UPDATE users SET last_seen=? WHERE name=?", (now, name)
                )
        return self.get_user(name)
    
    def get_user(self, name: str) -> Optional[dict]:
        with self._conn() as con:
            row = con.execute(
                "SELECT * FROM users WHERE name=?", (name,)
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["preferences"] = json.loads(d["preferences"] or "{}")
        return d
    
    def set_preference(self, name: str, key: str, value):
        user = self.get_user(name)
        if not user:
            self.upsert_user(name)
            user = self.get_user(name)
        prefs = user["preferences"]
        prefs[key] = value
        with self._conn() as con:
            con.execute(
                "UPDATE users SET preferences=? WHERE name=?",
                (json.dumps(prefs), name),
            )
        log.debug(f"[Memory] {name}.{key} = {value}")

    def get_preference(self, name: str, key: str, default=None):
        user = self.get_user(name)
        if not user:
            return default
        return user["preferences"].get(key, default)

    def update_notes(self, name: str, notes: str):
        with self._conn() as con:
            con.execute(
                "UPDATE users SET notes=? WHERE name=?", (notes, name)
            )

    def add_interaction(
        self,
        user_name: str,
        role: str,
        message: str,
        emotion: str = "neutral",
    ):
        """
        role: 'user' (human spoke) | 'robot' (robot responded)
        """
        with self._conn() as con:
            con.execute(
                "INSERT INTO interactions(user_name, role, message, emotion, timestamp)"
                " VALUES (?,?,?,?,?)",
                (user_name, role, message, emotion, time.time()),
            )
        # Prune old records beyond max_history
        self._prune_history(user_name)

    def get_history(
        self, user_name: str, limit: int = 20
    ) -> list[dict]:
        """Fetch the N most recent interactions for a user, oldest-first."""
        with self._conn() as con:
            rows = con.execute(
                "SELECT role, message, emotion, timestamp"
                " FROM interactions"
                " WHERE user_name=?"
                " ORDER BY timestamp DESC LIMIT ?",
                (user_name, limit),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def _prune_history(self, user_name: str):
        max_h = MEMORY["max_history"]
        with self._conn() as con:
            count = con.execute(
                "SELECT COUNT(*) FROM interactions WHERE user_name=?",
                (user_name,),
            ).fetchone()[0]
            if count > max_h:
                con.execute(
                    """DELETE FROM interactions WHERE id IN (
                        SELECT id FROM interactions
                        WHERE user_name=?
                        ORDER BY timestamp ASC
                        LIMIT ?
                    )""",
                    (user_name, count - max_h),
                )

    # Reminders
    def add_reminder(self, user_name: str, text: str, due_time: float):
        with self._conn() as con:
            con.execute(
                "INSERT INTO reminders(user_name, text, due_time) VALUES (?,?,?)",
                (user_name, text, due_time),
            )
        log.info(f"[Memory] Reminder for {user_name}: {text!r}")

    def get_due_reminders(self) -> list[dict]:
        """Return all reminders that are due and not yet done."""
        now = time.time()
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM reminders WHERE due_time<=? AND done=0",
                (now,),
            ).fetchall()
        return [dict(r) for r in rows]
    
    def mark_reminder_done(self, reminder_id: int):
        with self._conn() as con:
            con.execute(
                "UPDATE reminders SET done=1 WHERE id=?", (reminder_id,)
            )
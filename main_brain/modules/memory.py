import logging
from pathlib import Path
from contextlib import contextmanager
import sqlite3
import time
from typing import Optional
import json

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
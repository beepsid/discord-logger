"""SQLite storage for presence sessions.

A "session" is a continuous stretch of one status (online / idle / dnd /
offline) on one set of devices. While the bot runs, a periodic heartbeat keeps the
open session's `ended_at` fresh, so if the bot crashes or is stopped, the
gap is NOT counted as time in that status.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    status      TEXT    NOT NULL,
    devices     TEXT    NOT NULL DEFAULT '',
    started_at  REAL    NOT NULL,
    ended_at    REAL    NOT NULL,
    is_open     INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_sessions_user_time
    ON sessions (user_id, started_at);
"""


@dataclass
class Session:
    status: str
    devices: str
    started_at: float
    ended_at: float


class Store:
    def __init__(self, path: str) -> None:
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close_stale(self) -> None:
        """Close sessions left open by a previous run, ending them at the
        last heartbeat so bot downtime isn't counted."""
        with self.conn:
            self.conn.execute("UPDATE sessions SET is_open = 0 WHERE is_open = 1")

    def current(self, user_id: int) -> tuple[str, str] | None:
        row = self.conn.execute(
            "SELECT status, devices FROM sessions WHERE user_id = ? AND is_open = 1",
            (user_id,),
        ).fetchone()
        return (row[0], row[1]) if row else None

    def record(self, user_id: int, status: str, devices: str, now: float | None = None) -> bool:
        """Record the user's state. Returns True if it changed.

        Discord sends one presence update per shared server, so duplicates
        are expected and ignored here.
        """
        now = time.time() if now is None else now
        if self.current(user_id) == (status, devices):
            return False
        with self.conn:
            self.conn.execute(
                "UPDATE sessions SET ended_at = ?, is_open = 0 WHERE user_id = ? AND is_open = 1",
                (now, user_id),
            )
            self.conn.execute(
                "INSERT INTO sessions (user_id, status, devices, started_at, ended_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, status, devices, now, now),
            )
        return True

    def heartbeat(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self.conn:
            self.conn.execute("UPDATE sessions SET ended_at = ? WHERE is_open = 1", (now,))

    def sessions(self, user_id: int, start: float, end: float) -> list[Session]:
        """Sessions overlapping [start, end], clipped to that window."""
        now = time.time()
        rows = self.conn.execute(
            """
            SELECT status, devices,
                   MAX(started_at, ?) AS s,
                   MIN(CASE WHEN is_open = 1 THEN ? ELSE ended_at END, ?) AS e
            FROM sessions
            WHERE user_id = ? AND started_at < ?
              AND (CASE WHEN is_open = 1 THEN ? ELSE ended_at END) > ?
            ORDER BY started_at
            """,
            (start, now, end, user_id, end, now, start),
        ).fetchall()
        return [Session(*r) for r in rows if r[3] > r[2]]

    def totals(self, user_id: int, start: float, end: float) -> tuple[dict[str, float], float]:
        """Return ({status: seconds}, seconds_active_on_mobile)."""
        by_status: dict[str, float] = {}
        mobile = 0.0
        for s in self.sessions(user_id, start, end):
            dur = s.ended_at - s.started_at
            by_status[s.status] = by_status.get(s.status, 0.0) + dur
            if s.status != "offline" and "mobile" in s.devices.split(","):
                mobile += dur
        return by_status, mobile

    def close(self) -> None:
        self.conn.close()

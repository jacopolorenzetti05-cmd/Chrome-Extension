"""SQLite store with full posting history and per-run source health."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .. import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS postings (
  id TEXT PRIMARY KEY, source_key TEXT, company TEXT, sector TEXT, segment TEXT,
  title TEXT, location TEXT, country TEXT, url TEXT, apply_url TEXT,
  posted_at TEXT, deadline TEXT, first_seen TEXT, last_seen TEXT,
  status TEXT DEFAULT 'active', consecutive_misses INTEGER DEFAULT 0,
  relevance TEXT, reason TEXT, level TEXT, type TEXT, timing TEXT, timing_fit INTEGER,
  pay TEXT, languages TEXT, score INTEGER, why TEXT, score_source TEXT,
  verified INTEGER, verify_note TEXT, verified_at TEXT,
  description TEXT, salary_text TEXT, source_adapter TEXT, removed_at TEXT, extra TEXT
);
CREATE INDEX IF NOT EXISTS ix_postings_source ON postings(source_key);
CREATE TABLE IF NOT EXISTS runs (run_id INTEGER PRIMARY KEY AUTOINCREMENT, started TEXT, finished TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS source_runs (
  run_id INTEGER, run_at TEXT, source_key TEXT, name TEXT, sector TEXT, adapter TEXT,
  ok INTEGER, fetched INTEGER, relevant INTEGER, maybe INTEGER, error TEXT, duration REAL, snapshot TEXT, health TEXT
);
CREATE INDEX IF NOT EXISTS ix_sr ON source_runs(source_key, run_id);
"""

COLS = ["id", "source_key", "company", "sector", "segment", "title", "location", "country", "url", "apply_url",
        "posted_at", "deadline", "first_seen", "last_seen", "status", "consecutive_misses", "relevance", "reason",
        "level", "type", "timing", "timing_fit", "pay", "languages", "score", "why", "score_source", "verified",
        "verify_note", "verified_at", "description", "salary_text", "source_adapter", "removed_at", "extra"]


class Store:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or config.DB_FILE)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.commit()
        self.db.close()

    # ---- postings
    def get(self, pid: str) -> dict | None:
        r = self.db.execute("SELECT * FROM postings WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None

    def by_source(self, key: str) -> dict[str, dict]:
        return {r["id"]: dict(r) for r in self.db.execute("SELECT * FROM postings WHERE source_key=?", (key,))}

    def upsert(self, rec: dict):
        rec = {c: rec.get(c) for c in COLS}
        if isinstance(rec["extra"], (dict, list)):
            rec["extra"] = json.dumps(rec["extra"], ensure_ascii=False)
        cols = ",".join(COLS)
        qs = ",".join("?" * len(COLS))
        upd = ",".join(f"{c}=excluded.{c}" for c in COLS if c not in ("id", "first_seen"))
        self.db.execute(f"INSERT INTO postings ({cols}) VALUES ({qs}) ON CONFLICT(id) DO UPDATE SET {upd}",
                        [rec[c] for c in COLS])

    def update(self, pid: str, **fields):
        sets = ",".join(f"{k}=?" for k in fields)
        self.db.execute(f"UPDATE postings SET {sets} WHERE id=?", [*fields.values(), pid])

    def all(self, where: str = "1=1", args=()) -> list[dict]:
        return [dict(r) for r in self.db.execute(f"SELECT * FROM postings WHERE {where}", args)]

    # ---- runs
    def start_run(self, started: str) -> int:
        cur = self.db.execute("INSERT INTO runs (started) VALUES (?)", (started,))
        return cur.lastrowid

    def finish_run(self, run_id: int, finished: str, notes: str = ""):
        self.db.execute("UPDATE runs SET finished=?, notes=? WHERE run_id=?", (finished, notes, run_id))
        self.db.commit()

    def add_source_run(self, **kw):
        cols = ",".join(kw)
        self.db.execute(f"INSERT INTO source_runs ({cols}) VALUES ({','.join('?' * len(kw))})", list(kw.values()))

    def source_history(self, key: str, limit: int = 10) -> list[dict]:
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM source_runs WHERE source_key=? ORDER BY run_id DESC LIMIT ?", (key, limit))]

    def last_success(self, key: str) -> str:
        r = self.db.execute("SELECT run_at FROM source_runs WHERE source_key=? AND ok=1 ORDER BY run_id DESC LIMIT 1",
                            (key,)).fetchone()
        return r[0] if r else ""

    def latest_source_runs(self) -> list[dict]:
        r = self.db.execute("SELECT MAX(run_id) FROM source_runs").fetchone()
        if not r or r[0] is None:
            return []
        return [dict(x) for x in self.db.execute("SELECT * FROM source_runs WHERE run_id=?", (r[0],))]

    def commit(self):
        self.db.commit()

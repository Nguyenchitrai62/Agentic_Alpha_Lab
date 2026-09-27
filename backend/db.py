"""SQLite store for the web app: WAL mode, per-thread connections, covering indexes, one writer at a time.

Times are epoch milliseconds (INTEGER) for compact, fast range scans. The web API only reads; pipeline jobs write.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from .config import SETTINGS

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,            -- 'live' (scheduled/admin run of the frozen pipeline) | 'walkforward' (out-of-sample replay)
  decision_time INTEGER NOT NULL,  -- start of the 4h bar the orders are for (ms)
  pipeline TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  scale REAL, governor REAL, gross REAL,
  payload TEXT,
  UNIQUE(source, decision_time)
);
CREATE INDEX IF NOT EXISTS runs_src_time ON runs(source, decision_time DESC);
CREATE TABLE IF NOT EXISTS run_books(
  run_id INTEGER NOT NULL, symbol TEXT NOT NULL, side TEXT, weight REAL, entry REAL, sl REAL, tp REAL,
  confidence TEXT, strength REAL, members_agree INTEGER,
  PRIMARY KEY(run_id, symbol)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS run_books_sym ON run_books(symbol, run_id);
CREATE TABLE IF NOT EXISTS run_sleeve(
  run_id INTEGER NOT NULL, symbol TEXT NOT NULL, rung REAL NOT NULL, buy_limit REAL, tp REAL, sl REAL, size_frac REAL,
  PRIMARY KEY(run_id, symbol, rung)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS candles(
  symbol TEXT NOT NULL, interval TEXT NOT NULL, t INTEGER NOT NULL, o REAL, h REAL, l REAL, c REAL, v REAL,
  PRIMARY KEY(symbol, interval, t)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS trades(
  id INTEGER PRIMARY KEY, source TEXT NOT NULL, t INTEGER NOT NULL, symbol TEXT NOT NULL, kind TEXT NOT NULL,
  side TEXT, price REAL, weight REAL, extra TEXT
);
CREATE INDEX IF NOT EXISTS trades_q ON trades(source, symbol, t);
CREATE TABLE IF NOT EXISTS equity(
  source TEXT NOT NULL, t INTEGER NOT NULL, equity REAL NOT NULL, PRIMARY KEY(source, t)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS users(
  email TEXT PRIMARY KEY, name TEXT, picture TEXT, role TEXT NOT NULL, approved INTEGER NOT NULL DEFAULT 0,
  first_seen INTEGER, last_seen INTEGER
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS jobs(
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL, started_at INTEGER, finished_at INTEGER,
  message TEXT, triggered_by TEXT
);
CREATE INDEX IF NOT EXISTS jobs_time ON jobs(started_at DESC);
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT) WITHOUT ROWID;
"""

_local = threading.local()
_write_lock = threading.Lock()


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=30, isolation_level=None, check_same_thread=False)
    con.row_factory = sqlite3.Row
    for pragma in ("journal_mode=WAL", "synchronous=NORMAL", "busy_timeout=10000", "cache_size=-65536",
                   "mmap_size=268435456", "temp_store=MEMORY", "foreign_keys=ON"):
        con.execute(f"PRAGMA {pragma}")
    return con


def conn() -> sqlite3.Connection:
    c = getattr(_local, "con", None)
    if c is None:
        c = _connect(SETTINGS.db_path)
        _local.con = c
    return c


def init() -> None:
    with _write_lock:
        conn().executescript(SCHEMA)


@contextmanager
def write():
    """Single-writer transaction (readers keep working under WAL)."""
    with _write_lock:
        c = conn()
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
            c.execute("COMMIT")
        except Exception:
            if c.in_transaction:
                c.execute("ROLLBACK")
            raise


def now_ms() -> int:
    return int(time.time() * 1000)


def rows(sql: str, args: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn().execute(sql, args).fetchall()]


def one(sql: str, args: tuple = ()) -> dict | None:
    r = conn().execute(sql, args).fetchone()
    return dict(r) if r else None


def kv_get(k: str, default=None):
    r = one("SELECT v FROM kv WHERE k = ?", (k,))
    return json.loads(r["v"]) if r else default


def kv_set(k: str, v) -> None:
    with write() as c:
        c.execute("INSERT INTO kv(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (k, json.dumps(v)))


def optimize() -> None:
    c = conn()
    c.execute("PRAGMA optimize")
    c.execute("PRAGMA wal_checkpoint(PASSIVE)")

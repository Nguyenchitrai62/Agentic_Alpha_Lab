"""Opt-in retention for the web app database (artifacts/web/app.db).

Keeps the latest N days of append-only operational rows and never touches
identity, sessions, market data or frozen research replays:

  pruned by age   jobs (started_at), live + paper_* runs (+ their run_books /
                  run_sleeve), paper_* orders (entry_t) and paper_* trades (t)
  never touched   users, auth_sessions, auth_refresh_tokens,
                  user_pipeline_access, kv, candles, and any tm_* /
                  walkforward / forward replay rows

Not scheduled anywhere: run it explicitly, e.g.::

  .venv/Scripts/python.exe -m backend.maintenance --days 90         # dry run (default)
  .venv/Scripts/python.exe -m backend.maintenance --days 90 --apply # actually delete
  .venv/Scripts/python.exe -m backend.maintenance --days 90 --apply --vacuum

An admin can call :func:`prune_old_rows` from a Python shell instead.
"""

from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "artifacts/web/app.db"

DAY_MS = 86_400_000


def cutoff_ms(days: int, now_ms: int | None = None) -> int:
    if days < 1:
        raise ValueError("days must be >= 1")
    now = int(time.time() * 1000) if now_ms is None else int(now_ms)
    return now - int(days) * DAY_MS


def _counts(con: sqlite3.Connection, cutoff: int) -> dict[str, int]:
    """Rows older than `cutoff` that retention would delete, per table."""
    out: dict[str, int] = {}
    out["jobs"] = con.execute(
        "SELECT COUNT(*) FROM jobs WHERE started_at IS NOT NULL AND started_at < ?",
        (cutoff,),
    ).fetchone()[0]
    out["runs"] = con.execute(
        "SELECT COUNT(*) FROM runs WHERE (source = 'live' OR source LIKE 'paper\\_%' ESCAPE '\\') "
        "AND decision_time < ?",
        (cutoff,),
    ).fetchone()[0]
    out["run_books"] = con.execute(
        "SELECT COUNT(*) FROM run_books WHERE run_id IN "
        "(SELECT id FROM runs WHERE (source = 'live' OR source LIKE 'paper\\_%' ESCAPE '\\') "
        "AND decision_time < ?)",
        (cutoff,),
    ).fetchone()[0]
    out["run_sleeve"] = con.execute(
        "SELECT COUNT(*) FROM run_sleeve WHERE run_id IN "
        "(SELECT id FROM runs WHERE (source = 'live' OR source LIKE 'paper\\_%' ESCAPE '\\') "
        "AND decision_time < ?)",
        (cutoff,),
    ).fetchone()[0]
    out["orders"] = con.execute(
        "SELECT COUNT(*) FROM orders WHERE source LIKE 'paper\\_%' ESCAPE '\\' "
        "AND entry_t IS NOT NULL AND entry_t < ?",
        (cutoff,),
    ).fetchone()[0]
    out["trades"] = con.execute(
        "SELECT COUNT(*) FROM trades WHERE source LIKE 'paper\\_%' ESCAPE '\\' AND t < ?",
        (cutoff,),
    ).fetchone()[0]
    return out


def prune_old_rows(
    db_path: str | Path | None = None,
    days: int = 90,
    dry_run: bool = True,
    vacuum: bool = False,
    now_ms: int | None = None,
) -> dict:
    """Delete operational rows older than `days`; read-only when `dry_run`.

    Never deletes users / sessions / settings (kv) / candles / tm_* /
    walkforward / forward rows. Returns {"cutoff": ..., "deleted": {...}}.
    """
    path = Path(db_path) if db_path is not None else DEFAULT_DB
    cutoff = cutoff_ms(days, now_ms)
    if dry_run:
        con = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True, timeout=30)
        try:
            plan = _counts(con, cutoff)
        finally:
            con.close()
        print(f"retention dry-run: db={path} keep_last_days={days} cutoff_ms={cutoff}")
        for table, n in plan.items():
            print(f"  would delete {table}: {n}")
        print("  protected (never pruned): users, auth_sessions, auth_refresh_tokens, "
              "user_pipeline_access, kv, candles, tm_*/walkforward/forward rows")
        return {"cutoff": cutoff, "deleted": dict(plan), "dry_run": True}

    con = sqlite3.connect(str(path), timeout=30, isolation_level=None, check_same_thread=False)
    try:
        con.execute("PRAGMA busy_timeout=10000")
        con.execute("BEGIN IMMEDIATE")
        try:
            deleted = _counts(con, cutoff)
            con.execute(
                "DELETE FROM run_books WHERE run_id IN "
                "(SELECT id FROM runs WHERE (source = 'live' OR source LIKE 'paper\\_%' ESCAPE '\\') "
                "AND decision_time < ?)",
                (cutoff,),
            )
            con.execute(
                "DELETE FROM run_sleeve WHERE run_id IN "
                "(SELECT id FROM runs WHERE (source = 'live' OR source LIKE 'paper\\_%' ESCAPE '\\') "
                "AND decision_time < ?)",
                (cutoff,),
            )
            con.execute(
                "DELETE FROM runs WHERE (source = 'live' OR source LIKE 'paper\\_%' ESCAPE '\\') "
                "AND decision_time < ?",
                (cutoff,),
            )
            con.execute(
                "DELETE FROM orders WHERE source LIKE 'paper\\_%' ESCAPE '\\' "
                "AND entry_t IS NOT NULL AND entry_t < ?",
                (cutoff,),
            )
            con.execute(
                "DELETE FROM trades WHERE source LIKE 'paper\\_%' ESCAPE '\\' AND t < ?",
                (cutoff,),
            )
            con.execute(
                "DELETE FROM jobs WHERE started_at IS NOT NULL AND started_at < ?",
                (cutoff,),
            )
            con.execute("COMMIT")
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        if vacuum:
            con.execute("VACUUM")
        print(f"retention apply: db={path} keep_last_days={days} cutoff_ms={cutoff}")
        for table, n in deleted.items():
            print(f"  deleted {table}: {n}")
        return {"cutoff": cutoff, "deleted": deleted, "dry_run": False}
    finally:
        con.close()


def main(argv: list[str] | None = None) -> dict:
    p = argparse.ArgumentParser(description="Opt-in app.db retention (dry-run by default).")
    p.add_argument("--db", default=str(DEFAULT_DB), help="SQLite file (never the live file while the backend runs it)")
    p.add_argument("--days", type=int, default=90, help="keep the latest N days (default 90)")
    p.add_argument("--apply", action="store_true", help="actually delete (default is dry-run)")
    p.add_argument("--vacuum", action="store_true", help="VACUUM after deleting (apply only)")
    args = p.parse_args(argv)
    return prune_old_rows(db_path=args.db, days=args.days, dry_run=not args.apply, vacuum=args.vacuum)


if __name__ == "__main__":
    main()

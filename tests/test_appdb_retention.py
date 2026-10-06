"""Synthetic-DB tests for the opt-in app.db retention (backend/maintenance.py)."""

import sqlite3

from backend.maintenance import cutoff_ms, prune_old_rows

DAY = 86_400_000
NOW = 1_791_299_000_000  # fixed ~2026-10-06 UTC for deterministic cutoffs


def _seed(path):
    con = sqlite3.connect(str(path))
    con.executescript(
        """
        CREATE TABLE jobs(id INTEGER PRIMARY KEY, kind TEXT, status TEXT, started_at INTEGER, finished_at INTEGER, message TEXT, triggered_by TEXT);
        CREATE TABLE runs(id INTEGER PRIMARY KEY, source TEXT, decision_time INTEGER, pipeline TEXT, created_at INTEGER, payload TEXT);
        CREATE TABLE run_books(run_id INTEGER, symbol TEXT, side TEXT);
        CREATE TABLE run_sleeve(run_id INTEGER, symbol TEXT, rung REAL);
        CREATE TABLE orders(id INTEGER PRIMARY KEY, source TEXT, symbol TEXT, kind TEXT, entry_t INTEGER, exit_t INTEGER);
        CREATE TABLE trades(id INTEGER PRIMARY key, source TEXT, t INTEGER, symbol TEXT, kind TEXT);
        CREATE TABLE users(email TEXT PRIMARY KEY, role TEXT);
        CREATE TABLE auth_sessions(id TEXT PRIMARY KEY, email TEXT, expires_at INTEGER);
        CREATE TABLE kv(k TEXT PRIMARY KEY, v TEXT);
        CREATE TABLE candles(symbol TEXT, interval TEXT, t INTEGER);
        CREATE TABLE equity(source TEXT, t INTEGER, equity REAL);
        """
    )
    old, new = NOW - 200 * DAY, NOW - 5 * DAY
    con.executemany("INSERT INTO jobs(kind,status,started_at) VALUES(?,?,?)",
                    [("cycle", "done", old), ("cycle", "failed", old), ("cycle", "done", new), ("cycle", "done", None)])
    # live + paper runs: one old (with children), one new
    con.execute("INSERT INTO runs(id,source,decision_time,pipeline,created_at) VALUES(1,'live',?,?,?)",
                (old, "v205", old))
    con.execute("INSERT INTO runs(id,source,decision_time,pipeline,created_at) VALUES(2,'live',?,?,?)",
                (new, "v205", new))
    con.execute("INSERT INTO runs(id,source,decision_time,pipeline,created_at) VALUES(3,'paper_v301',?,?,?)",
                (old, "v301", old))
    con.execute("INSERT INTO runs(id,source,decision_time,pipeline,created_at) VALUES(4,'tm_v301',?,?,?)",
                (old, "v301", old))  # frozen replay: same age, must survive
    con.execute("INSERT INTO runs(id,source,decision_time,pipeline,created_at) VALUES(5,'walkforward',?,?,?)",
                (old, "v205", old))
    con.executemany("INSERT INTO run_books(run_id,symbol,side) VALUES(?,?,?)",
                    [(1, "BTCUSDT", "LONG"), (3, "ETHUSDT", "SHORT"), (4, "BTCUSDT", "LONG"), (5, "BTCUSDT", "LONG")])
    con.executemany("INSERT INTO run_sleeve(run_id,symbol,rung) VALUES(?,?,?)",
                    [(1, "BTCUSDT", 3.0), (4, "BTCUSDT", 3.0)])
    con.executemany("INSERT INTO orders(source,symbol,kind,entry_t) VALUES(?,?,?,?)",
                    [("paper_v301", "BTCUSDT", "book", old), ("paper_v301", "BTCUSDT", "book", new),
                     ("tm_v301", "BTCUSDT", "book", old), ("walkforward", "BTCUSDT", "book", old)])
    con.executemany("INSERT INTO trades(source,t,symbol,kind) VALUES(?,?,?,?)",
                    [("paper_v301", old, "BTCUSDT", "book_fill"), ("paper_v301", new, "BTCUSDT", "book_fill"),
                     ("tm_v301", old, "BTCUSDT", "book_fill")])
    con.execute("INSERT INTO users(email,role) VALUES('a@x.y','viewer')")
    con.execute("INSERT INTO auth_sessions(id,email,expires_at) VALUES('s','a@x.y',?)", (old,))
    con.execute("INSERT INTO kv(k,v) VALUES('trade_plan_v301','{}')")
    con.execute("INSERT INTO candles(symbol,interval,t) VALUES('BTCUSDT','4h',?)", (old,))
    con.execute("INSERT INTO equity(source,t,equity) VALUES('tm_v301',?,100.0)", (old,))
    con.commit()
    con.close()


def test_dry_run_deletes_nothing_but_reports(tmp_path):
    db = tmp_path / "syn.db"
    _seed(db)
    before = {t: sqlite3.connect(str(db)).execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
              for t in ("jobs", "runs", "run_books", "run_sleeve", "orders", "trades")}
    res = prune_old_rows(db_path=db, days=90, dry_run=True, now_ms=NOW)
    assert res["dry_run"] is True
    assert res["deleted"] == {"jobs": 2, "runs": 2, "run_books": 2, "run_sleeve": 1, "orders": 1, "trades": 1}
    after = {t: sqlite3.connect(str(db)).execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
             for t in before}
    assert after == before  # dry-run is read-only


def test_apply_keeps_frozen_replays_identity_and_market_data(tmp_path):
    db = tmp_path / "syn.db"
    _seed(db)
    res = prune_old_rows(db_path=db, days=90, dry_run=False, now_ms=NOW)
    assert res["deleted"]["jobs"] == 2
    con = sqlite3.connect(str(db))
    assert con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 2  # new + NULL-started kept
    assert con.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 3  # new live + tm + walkforward
    assert {r[0] for r in con.execute("SELECT source FROM runs")} == {"live", "tm_v301", "walkforward"}
    assert con.execute("SELECT COUNT(*) FROM run_books").fetchone()[0] == 2  # tm + walkforward children
    assert con.execute("SELECT COUNT(*) FROM run_sleeve").fetchone()[0] == 1  # tm child kept
    assert con.execute("SELECT COUNT(*) FROM orders WHERE source LIKE 'tm%' OR source='walkforward'").fetchone()[0] == 2
    assert con.execute("SELECT COUNT(*) FROM trades WHERE source='tm_v301'").fetchone()[0] == 1
    # protected tables untouched even though their rows are old
    assert con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM kv").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM candles").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM equity").fetchone()[0] == 1
    con.close()


def test_cutoff_rejects_bad_days():
    try:
        cutoff_ms(0)
    except ValueError:
        pass
    else:
        raise AssertionError("days=0 must raise")

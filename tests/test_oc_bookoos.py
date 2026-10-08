"""oc_bookoos honesty + schema checks (fast, no network, no engine)."""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/diagnostics/oc_bookoos"
OOS_DIR = ROOT / "data/raw/majors_1m_oos_20261006"
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]


def load_results():
    p = HERE / "results.json"
    assert p.exists(), "run research/diagnostics/oc_bookoos/score_oos.py --run first"
    return json.loads(p.read_text())


def test_window_is_genuinely_new():
    r = load_results()
    assert r["window"]["start"] == "2026-09-30 00:00:00+00:00"
    assert r["label"] == "clean OOS, tiny sample"
    assert r["version"] == "oc_bookoos"
    # live-growing: weekly --fetch appends days, so the end moves out
    # (6 d on 2026-10-06 -> 7 d on 2026-10-07); the start is the invariant.
    start = pd.Timestamp(r["window"]["start"])
    end = pd.Timestamp(r["window"]["end_exclusive"])
    assert end >= pd.Timestamp("2026-10-06 00:00:00+00:00", tz="UTC")
    assert r["window"]["days"] == (end - start).days
    assert r["window"]["days"] >= 6
    assert len(r["daily_equity"]) == r["window"]["days"] + 1
    assert r["expectation_band"]["window_days"] == r["window"]["days"]


def test_full_book_prospective_no_agents_no_bear():
    r = load_results()
    assert "book+dip" in r["mode"] and "prospective" in r["mode"]
    h = r["honesty"]
    assert h["backfill_used"] is False and h["refit"] is False
    assert "not used" in h["agent_tables"]
    assert "prospective-only" in h["books"]
    bc = r["books_coverage"]
    assert bc["oos_start_holding"] == "2026-09-30 00:00:00+00:00"
    assert bc["oos_start_book_t"] == "2026-09-29 20:00:00+00:00"
    assert pd.Timestamp(bc["first_common_t"]) <= pd.Timestamp(bc["oos_start_book_t"])
    assert bc["n_common"] > 0 and bc["n_o1"] > 0 and bc["n_cb"] > 0
    for cand, lag in bc["lag_max_h"].items():
        assert 0 <= lag <= 6.0, cand
    assert bc["n_gaps_ffilled"] == len(bc["gaps_ffilled"])


def test_gate_costs():
    r = load_results()
    c = r["costs"]
    assert (c["maker"], c["taker"]) == (0.0002, 0.00055)
    assert c["funding_long_per_settlement"] == 0.0001 and c["funding_short"] == 0.0
    assert c["win_start_minute"] == 5 and c["stop_first"] is True


def test_metrics_internally_consistent():
    r = load_results()
    daily = r["daily_equity"]
    assert len(daily) == r["window"]["days"] + 1
    # totals are rounded from full-precision equity while daily legs are
    # rounded to 6 dp first; allow 0.005 (half a bp) instead of 1e-6.
    assert abs(r["total_pct"] - round(100 * (daily[-1][1] - 1), 3)) < 0.005
    assert r["gate_dd_pct"] == max(r["max_dd_close_pct"], r["max_dd_1m_pct"])
    t = r["trades"]
    assert t["rungs"] == len(r["rung_exits"])
    assert t["rung_wins"] == sum(1 for _, x in r["rung_exits"] if x > 0)
    assert t["book_episodes"] == len(r["book_exits"])
    assert t["all"] == t["rungs"] + t["book_episodes"]
    if t["rungs"]:
        assert abs(t["rung_win_rate"] - round(t["rung_wins"] / t["rungs"], 4)) < 1e-9
    if t["book_episodes"]:
        assert abs(t["book_win_rate"] - round(t["book_wins"] / t["book_episodes"], 4)) < 1e-9
    else:
        assert t["book_win_rate"] is None
    if t["all"]:
        assert abs(t["all_win_rate"] - round(t["all_wins"] / t["all"], 4)) < 1e-9
    t0 = pd.Timestamp(r["window"]["start"])
    t1 = pd.Timestamp(r["window"]["end_exclusive"]) + pd.Timedelta(hours=4)
    for ts, _ in r["rung_exits"] + r["book_exits"]:
        assert t0 < pd.Timestamp(ts) <= t1
    for s, d in r["phases"].items():
        assert len(d["rungs"]) + len(d["book_exits"]) > 0 or d["n_book_events"] >= 0


def test_expectation_band_sane():
    r = load_results()
    b = r["expectation_band"]["total_pct"]
    assert b["p5"] < b["p50"] < b["p95"]
    assert r["expectation_band"]["window_days"] == r["window"]["days"]
    assert 0.0 <= r["oos_percentile_vs_band"] <= 100.0


def test_oos_data_checksum_verified_and_complete():
    import hashlib

    man = json.loads((OOS_DIR / "manifest.json").read_text())
    # live-growing: the shared 1m dir is extended weekly (12 d on 2026-10-06
    # -> 13 d on 2026-10-07). The start is fixed; the end only moves out.
    assert man["window"][0] == "2026-09-24 00:00:00+00:00"
    w0 = pd.Timestamp(man["window"][0])
    w1 = pd.Timestamp(man["window"][1])
    assert w1 >= pd.Timestamp("2026-10-06 00:00:00+00:00", tz="UTC")
    n_days = (w1 - w0).days
    assert n_days >= 12
    assert set(man["symbols"]) == set(SYMS)
    for s in SYMS:
        e = man["symbols"][s]
        p = OOS_DIR / f"{s}_1m_oos.parquet"
        m = pd.read_parquet(p, columns=["open_time"])
        assert len(m) == n_days * 1440
        assert m["open_time"].min() == w0
        assert m["open_time"].max() == w1 - pd.Timedelta(minutes=1)
        # file is self-consistent with its own manifest entry
        assert e["rows"] == len(m)
        assert pd.Timestamp(e["first"]) == w0
        assert pd.Timestamp(e["last"]) == w1 - pd.Timedelta(minutes=1)
        assert len(e["days"]) == n_days
        assert hashlib.sha256(p.read_bytes()).hexdigest() == e["parquet_sha256"]

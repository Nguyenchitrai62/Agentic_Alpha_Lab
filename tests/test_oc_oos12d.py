"""oc_oos12d honesty + schema checks (fast, no network, no engine)."""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/diagnostics/oc_oos12d"
OOS_DIR = ROOT / "data/raw/majors_1m_oos_20261006"
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]


def load_results():
    p = HERE / "results.json"
    assert p.exists(), "run oc_oos12d.py --run first"
    return json.loads(p.read_text())


def test_window_is_genuinely_new():
    r = load_results()
    assert r["window"]["start"] == "2026-09-24 00:00:00+00:00"
    assert r["label"] == "tiny sample, clean"
    # live-growing: a --run after a --fetch extends the window (12 d on
    # 2026-10-06 -> 13 d once 2026-10-06 completes). The start is invariant.
    start = pd.Timestamp(r["window"]["start"])
    end = pd.Timestamp(r["window"]["end_exclusive"])
    assert end >= pd.Timestamp("2026-10-06 00:00:00+00:00", tz="UTC")
    assert r["window"]["days"] == (end - start).days
    assert r["window"]["days"] >= 12
    assert len(r["daily_equity"]) == r["window"]["days"] + 1


def test_dip_only_no_book_no_agents():
    r = load_results()
    assert "dip-only" in r["mode"] and "books=0" in r["mode"]
    assert r["honesty"]["refit"] is False and r["honesty"]["backfill_used"] is False
    assert "not used" in r["honesty"]["agent_tables"]
    assert r["trades"]["book_events"] == 0
    for s, d in r["phases"].items():
        assert d["n_book_events"] == 0


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
    assert abs(daily[0][1] - 1.0) < 1e-9
    # same rounding note as bookoos: daily legs are 6-dp rounded.
    assert abs(r["total_pct"] - round(100 * (daily[-1][1] - 1), 3)) < 0.005
    assert r["gate_dd_pct"] == max(r["max_dd_close_pct"], r["max_dd_1m_pct"])
    n, w = r["trades"]["rungs"], r["trades"]["wins"]
    assert n == len(r["rung_exits"]) and w == sum(1 for _, x in r["rung_exits"] if x > 0)
    if n:
        assert abs(r["trades"]["win_rate"] - round(w / n, 4)) < 1e-9
        assert 0.0 <= r["trades"]["win_rate"] <= 1.0
    t0 = pd.Timestamp(r["window"]["start"])
    t1 = pd.Timestamp(r["window"]["end_exclusive"]) + pd.Timedelta(hours=4)
    for t, _ in r["rung_exits"]:
        assert t0 < pd.Timestamp(t) <= t1


def test_expectation_band_sane():
    r = load_results()
    b = r["expectation_band_12d"]["total_pct"]
    assert b["p5"] < b["p50"] < b["p95"]
    assert 0.0 <= r["oos_percentile_vs_band"] <= 100.0


def test_oos_data_checksum_verified_and_complete():
    import hashlib

    man = json.loads((OOS_DIR / "manifest.json").read_text())
    # shared live-growing dir (see bookoos): start fixed, end moves out.
    assert man["window"][0] == "2026-09-24 00:00:00+00:00"
    w0 = pd.Timestamp(man["window"][0])
    w1 = pd.Timestamp(man["window"][1])
    assert w1 >= pd.Timestamp("2026-10-06 00:00:00+00:00", tz="UTC")
    n_days = (w1 - w0).days
    assert n_days >= 12
    assert set(man["symbols"]) == set(SYMS)
    names = sorted(p.name for p in OOS_DIR.iterdir())
    assert names == sorted([f"{s}_1m_oos.parquet" for s in SYMS] + ["manifest.json"])
    for s in SYMS:
        p = OOS_DIR / f"{s}_1m_oos.parquet"
        m = pd.read_parquet(p, columns=["open_time"])
        assert len(m) == n_days * 1440
        assert m["open_time"].min() == w0
        assert m["open_time"].max() == w1 - pd.Timedelta(minutes=1)
        assert len(man["symbols"][s]["files"]) == n_days
        assert hashlib.sha256(p.read_bytes()).hexdigest() == man["symbols"][s]["parquet_sha256"]
    # the scored results must not run past the available data
    r = load_results()
    assert pd.Timestamp(r["window"]["end_exclusive"]) <= w1

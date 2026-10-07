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
    assert r["window"]["days"] == 12
    assert r["label"] == "tiny sample, clean"


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
    assert abs(r["total_pct"] - round(100 * (daily[-1][1] - 1), 3)) < 1e-6
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
    man = json.loads((OOS_DIR / "manifest.json").read_text())
    assert man["window"] == ["2026-09-24 00:00:00+00:00", "2026-10-06 00:00:00+00:00"]
    assert set(man["symbols"]) == set(SYMS)
    names = sorted(p.name for p in OOS_DIR.iterdir())
    assert names == sorted([f"{s}_1m_oos.parquet" for s in SYMS] + ["manifest.json"])
    for s in SYMS:
        m = pd.read_parquet(OOS_DIR / f"{s}_1m_oos.parquet", columns=["open_time"])
        assert len(m) == 12 * 1440
        assert m["open_time"].min() == pd.Timestamp("2026-09-24 00:00:00+00:00", tz="UTC")
        assert m["open_time"].max() == pd.Timestamp("2026-10-05 23:59:00+00:00", tz="UTC")
        assert len(man["symbols"][s]["files"]) == 12

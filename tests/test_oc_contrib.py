"""Tests for oc_contrib: diagnostic attribution integrity (no simulation).

Fast checks only: file presence, PLAN-before-results, synthetic pairing/math,
year bucketing, and results.json consistency vs oc_kpi.
"""
import importlib.util
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ME = ROOT / "research/tournament/oc_contrib"
KPI = ROOT / "research/tournament/oc_kpi"


def _load_attr():
    spec = importlib.util.spec_from_file_location("oc_contrib_attr", ME / "attribute.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _res():
    return json.loads((ME / "results.json").read_text())


def test_files_present():
    for f in ("PLAN.md", "attribute.py", "results.json", "REPORT.md"):
        assert (ME / f).exists(), f


def test_plan_predates_results():
    assert (ME / "PLAN.md").stat().st_mtime <= (ME / "results.json").stat().st_mtime


def test_year_of_boundaries():
    a = _load_attr()
    assert a.year_of("2021-09-24 00:00:00+00:00") == 0
    assert a.year_of("2022-09-23 23:59:00+00:00") == 0
    assert a.year_of("2022-09-24 00:00:00+00:00") == 1
    assert a.year_of("2026-09-23 23:59:00+00:00") == 4
    assert a.year_of("2026-09-24 00:00:00+00:00") is None


def test_pair_rungs_fifo_math():
    a = _load_attr()
    ev = pd.DataFrame([
        dict(t="2022-01-01 00:01:00+00:00", symbol="BTCUSDT", kind="rung_fill",
             side="buy", price=100.0, weight=0.10, rung=2.5, ret=float("nan")),
        dict(t="2022-01-01 00:02:00+00:00", symbol="BTCUSDT", kind="rung_tp",
             side="sell", price=101.0, weight=0.10, rung=float("nan"), ret=0.01),
        dict(t="2022-01-01 00:03:00+00:00", symbol="BTCUSDT", kind="rung_fill",
             side="buy", price=100.0, weight=0.20, rung=5.0, ret=float("nan")),
        dict(t="2022-01-01 00:04:00+00:00", symbol="BTCUSDT", kind="rung_sl",
             side="sell", price=90.0, weight=0.20, rung=float("nan"), ret=-0.10),
    ])
    ev["t"] = pd.to_datetime(ev["t"], utc=True)
    pairs, unpaired, left, _ = a.pair_rungs(ev)
    assert unpaired == 0 and left == 0 and len(pairs) == 2
    assert pairs[0]["depth"] == 2.5 and abs(pairs[0]["pnl"] - 0.001) < 1e-12
    assert pairs[1]["depth"] == 5.0 and abs(pairs[1]["pnl"] + 0.02) < 1e-12


def test_book_episode_math():
    a = _load_attr()
    ev = pd.DataFrame([
        dict(t="2022-01-01 00:00:00+00:00", symbol="ETHUSDT", kind="book_fill",
             side="buy", price=100.0, weight=0.05, sl=1.0, tp=2.0),
        dict(t="2022-01-02 00:00:00+00:00", symbol="ETHUSDT", kind="book_close",
             side="sell", price=110.0, weight=-0.05, sl=float("nan"), tp=float("nan")),
    ])
    ev["t"] = pd.to_datetime(ev["t"], utc=True)
    out, left = a.book_episodes(ev)
    assert left == 0 and len(out) == 1
    # cost=0.05, proceeds=0.05*1.1=0.055, fees=0.05*0.0002+0.055*0.0002
    exp = 0.005 - (0.05 * 0.0002 + 0.055 * 0.0002)
    assert abs(out[0]["pnl"] - exp) < 1e-12 and out[0]["side"] == 1


def test_counts_match_oc_kpi():
    r = _res()
    k = json.loads((KPI / "results.json").read_text())
    assert r["pooled"]["n_book"] == k["win_rates"]["pooled"]["n_book"] == 4955
    assert r["pooled"]["n_rungs"] == k["win_rates"]["pooled"]["n_rungs"] == 21389
    assert r["checks"]["unpaired_exits"] == 0
    assert r["checks"]["tp_unknown"] == 0
    assert r["checks"]["open_books_left"] == k["win_rates"]["open_book_positions_at_end"] == 18


def test_wins_match_oc_kpi():
    r = _res()
    k = json.loads((KPI / "results.json").read_text())
    b = r["by_sleeve"]["pooled"]
    n_bl, n_bs = b["book_long"]["n"], b["book_short"]["n"]
    w_bl, w_bs = b["book_long"]["win"], b["book_short"]["win"]
    pooled_book_win = (w_bl * n_bl + w_bs * n_bs) / (n_bl + n_bs)
    assert abs(pooled_book_win - k["win_rates"]["pooled"]["win_book"]) < 5e-4
    assert abs(r["by_exit"]["pooled"]["rung_tp"]["win"] - 1.0) < 1e-12
    assert abs(r["by_exit"]["pooled"]["rung_sl"]["win"] - 0.0) < 1e-12


def test_year_partition_and_buckets():
    r = _res()
    for dim in ("by_sleeve", "by_depth", "by_coin", "by_exit", "by_tp"):
        tot = sum(v["n"] for v in r[dim]["pooled"].values())
        yrs = sum(sum(v["n"] for v in r[dim][str(y)].values()) for y in range(5))
        assert tot == yrs, dim
    assert set(r["by_depth"]["pooled"]) == {"2.5", "3.0", "3.5", "4.0", "5.0"}
    assert set(r["by_tp"]["pooled"]) <= {"0.5", "1.0", "1.5"}
    assert set(r["by_exit"]["pooled"]) == {"rung_sl", "rung_tp", "rung_timeout"}
    assert len(r["dd_episodes"]) == 5


def test_dd_shares_sum_to_one():
    r = _res()
    for e in r["dd_episodes"]:
        # sleeve and coin cover all trades -> shares sum to 1 of window net
        for dim in ("by_sleeve", "by_coin"):
            shares = [v["share_of_window"] for v in e[dim].values()]
            assert all(s is not None for s in shares), (e["peak"], dim)
            assert abs(sum(shares) - 1.0) < 2e-4, (e["peak"], dim, sum(shares))
        # depth/exit/TP cover dip rungs only -> sum to the dip share of the window
        dip_share = e["by_sleeve"]["dip"]["share_of_window"]
        for dim in ("by_depth", "by_exit", "by_tp"):
            shares = [v["share_of_window"] for v in e[dim].values()]
            assert all(s is not None for s in shares), (e["peak"], dim)
            assert abs(sum(shares) - dip_share) < 2e-4, (e["peak"], dim, sum(shares))

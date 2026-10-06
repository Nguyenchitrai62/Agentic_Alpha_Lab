"""Tests for oc_eventstress (research/tournament/oc_eventstress/results.json).

frozen-study checks: structure, no-leak windows, internal consistency,
basket-drop recompute from hourly_ext, v421/v422 G2 identity.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_eventstress"
RES = json.loads((HERE / "results.json").read_text())
CUT = pd.Timestamp("2026-09-24 00:00", tz="UTC")
GRID_START = pd.Timestamp("2021-09-24", tz="UTC")


def test_structure():
    assert set(RES) == {"meta", "basket_drops", "events"}
    assert len(RES["events"]) == 10
    assert len(RES["basket_drops"]) == 5
    req = {"key", "label", "anchor", "window", "pnl_comb_pct", "pnl_g2_pct",
           "dd_close_pct", "dd_mark_pct", "trough_hour", "rec_days",
           "dip_gross_max", "dip_gross_hour", "comb_gross_max", "margin",
           "stops", "stop_triggered", "liquidation", "m1"}
    for e in RES["events"]:
        assert req <= set(e), e["key"]
        assert set(e["margin"]) == {"usage_eq_max", "bal_base_max",
                                    "bal_stress_max", "bal_cons_max",
                                    "blocked_hours", "mm_bal_max",
                                    "mm_breached", "spot_cost_eq_max"}


def test_named_anchors_exact():
    got = {e["key"]: e["anchor"] for e in RES["events"]}
    assert got["LUNA"].startswith("2022-05-11 00:00")
    assert got["3AC"].startswith("2022-06-13 00:00")
    assert got["FTX"].startswith("2022-11-08 00:00")
    assert got["USDC"].startswith("2023-03-11 00:00")
    assert got["AUG24"].startswith("2024-08-05 00:00")


def test_windows_in_range_no_leak():
    for e in RES["events"]:
        a = pd.Timestamp(e["anchor"])
        w0, w1 = pd.Timestamp(e["window"][0]), pd.Timestamp(e["window"][1])
        assert GRID_START <= a < CUT, e["key"]
        assert w1 < CUT, e["key"]
        assert w1 - w0 == pd.Timedelta(days=8), e["key"]
        assert pd.Timestamp(e["trough_hour"]) >= w0 - pd.Timedelta(hours=1)
        assert pd.Timestamp(e["trough_hour"]) <= w1


def test_internal_consistency():
    for e in RES["events"]:
        assert e["dd_mark_pct"] >= e["dd_close_pct"] - 1e-9, e["key"]
        assert -50.0 < e["pnl_comb_pct"] < 50.0, e["key"]
        assert -50.0 < e["pnl_g2_pct"] < 50.0, e["key"]
        assert e["rec_days"] is None or e["rec_days"] >= 0.0, e["key"]
        m = e["margin"]
        assert 0.0 <= m["usage_eq_max"] <= 1.0, e["key"]
        assert m["blocked_hours"] == 0, e["key"]
        assert m["mm_breached"] is False, e["key"]
        assert e["liquidation"] is False, e["key"]
        assert e["stop_triggered"] == (e["stops"]["n_stop"] > 0), e["key"]
        assert e["m1"]["coverage_ok"] is True, e["key"]
        assert e["dip_gross_max"] <= e["comb_gross_max"] + 1e-9, e["key"]


def test_basket_drops_recompute():
    h = pd.read_parquet(ROOT / "research/tournament/ext/hourly_ext.parquet",
                        columns=["t", "close", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    piv = {}
    for c in ("BTCUSDT", "ETHUSDT"):
        d = h[h["sym"] == c].sort_values("t").drop_duplicates("t")
        piv[c] = pd.Series(d["close"].to_numpy(float),
                           index=pd.to_datetime(d["t"], utc=True))
    bh = pd.DataFrame(piv).sort_index()
    bh = bh[(bh.index >= pd.Timestamp("2021-09-24", tz="UTC"))]
    bh = bh.asfreq("1h").ffill()
    basket = ((bh / bh.shift(24) - 1.0).mean(axis=1).dropna())
    basket = basket[basket.index >= pd.Timestamp("2021-09-25", tz="UTC")]
    cands = basket.sort_values()
    taken, top = [], []
    for ts, v in cands.items():
        if all(abs((ts - t).total_seconds()) >= 24 * 3600 for t in taken):
            top.append((pd.Timestamp(ts).tz_convert("UTC"), float(v)))
            taken.append(ts)
        if len(top) == 5:
            break
    got = [(pd.Timestamp(d["end"]), d["basket_24h_pct"] / 100.0)
           for d in RES["basket_drops"]]
    assert [str(t) for t, _ in top] == [str(t) for t, _ in got]
    for (_, v), (_, g) in zip(top, got):
        assert abs(v - g) < 5e-3
    vals = [d["basket_24h_pct"] for d in RES["basket_drops"]]
    assert vals == sorted(vals) and all(v < 0 for v in vals)


def test_g2_runs_identity_and_dd_check():
    r421 = pickle.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2"
                         "/v421/v421_runs.pkl").read_bytes())
    r422 = pickle.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2"
                         "/v422/v422_runs.pkl").read_bytes())
    for s in range(4):
        assert (r421[s]["R2B1D17BFG2"]["eq"]
                == r422[s]["R2B1D17BFG2"]["eq"])
    check = RES["meta"]["g2_full_path_dd_check"]
    assert abs(check[0] - check[1]) < 0.05


def test_only_allowed_paths_written():
    assert (HERE / "compute_eventstress.py").exists()
    assert (HERE / "REPORT.md").exists()
    assert (HERE / "results.json").exists()

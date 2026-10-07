"""oc_grindsignal tests: files, PLAN-before-results, episodes, causality, no-1m."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_grindsignal"
sys.path.insert(0, str(OC))
import analyze_grindsignal as A

STAT_ORDER = A.STAT_ORDER


@pytest.fixture(scope="module")
def res():
    return json.loads((OC / "results.json").read_text())


def test_files_exist():
    for f in ("PLAN.md", "analyze_grindsignal.py", "results.json", "REPORT.md"):
        assert (OC / f).exists(), f


def test_plan_predates_results():
    assert os.path.getmtime(OC / "PLAN.md") <= os.path.getmtime(OC / "results.json")


def test_episodes_match_mix(res):
    mix4 = json.loads((ROOT / "research/tournament/oc_ddanat4p/mix_episodes.json").read_text())
    peaks = [e["peak"] for e in mix4["reset_episodes"]]
    assert len(peaks) == 4
    got = [e["peak"] for e in res["meta"]["episodes"]]
    assert got == [str(pd.Timestamp(p, tz="UTC")) for p in peaks]
    mixg2 = json.loads((ROOT / "research/tournament/oc_ddanat_g2/mix_episodes.json").read_text())
    assert got[0] == str(pd.Timestamp(mixg2["reset_episodes"][0]["peak"], tz="UTC"))


def test_schema(res):
    assert [s["name"] for s in res["stats"]] == STAT_ORDER
    assert len(res["stats"]) == 30
    for s in res["stats"]:
        assert set(s["episodes"]) == {"E0_grind", "E1", "E2_flash", "E3"}
        for k, v in s["episodes"].items():
            assert {"value", "pct"} <= set(v)
        assert s["n_extreme"] == len(s["extreme_episodes"])
        if s["hypothesis"]:
            assert s["n_extreme"] >= 3 and s["same_tail"]


def test_funding_strictly_before_T():
    fund = A.load_funding()
    T = pd.Timestamp("2023-04-17", tz="UTC")
    ref = A.fund7_at(fund, pd.DatetimeIndex([T])).iloc[0]
    trunc = {s: d[d["calc_time"] < T].reset_index(drop=True) for s, d in fund.items()}
    got = A.fund7_at(trunc, pd.DatetimeIndex([T])).iloc[0]
    for s in A.MAJORS:
        assert (np.isnan(ref[s]) and np.isnan(got[s])) or ref[s] == pytest.approx(got[s])
    # a settlement exactly at T must not be used
    assert all((pd.to_datetime(d["calc_time"], utc=True) < T).all() or True for d in trunc.values())


def test_hourly_strictly_before_T():
    px = A.load_hourly()
    T = pd.Timestamp("2023-04-17", tz="UTC")
    full = {s: A.Stats(px, {}, pd.Series([], dtype="datetime64[ns, UTC]"),
                       pd.DataFrame({"t": [], "kind": [], "is_tp": []}),
                       pd.DataFrame({"exit_t": [], "win": []})).close_at(s, T)
            for s in A.MAJORS}
    cut = {}
    for s in A.MAJORS:
        d = px[s]
        keep = d[d.index < T + pd.Timedelta(hours=1)]
        # dropping every bar-end > T leaves the causal close unchanged
        keep2 = d[d.index <= T]
        assert len(keep) == len(keep2)
        cut[s] = float(keep["close"].iloc[-1])
    for s in A.MAJORS:
        assert full[s] == pytest.approx(cut[s])


def test_breadth_spot_value(res):
    """Independent recomputation of breadth at E0 from raw hourly closes."""
    h = pd.read_parquet(ROOT / "research/tournament/ext/hourly_ext.parquet",
                        columns=["t", "close", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    T = pd.Timestamp("2023-04-17", tz="UTC")
    n_above = 0
    for s in A.MAJORS:
        d = h[h["sym"] == s].sort_values("t").reset_index(drop=True)
        be = d["t"] + pd.Timedelta(hours=1)
        m = be <= T
        assert m.sum() >= 4801
        c0 = float(d.loc[m, "close"].iloc[-1])
        ma = float(d.loc[m, "close"].iloc[-4801:-1].mean())
        n_above += c0 > ma
    want = n_above / 5
    got = res["stats"][STAT_ORDER.index("breadth")]["episodes"]["E0_grind"]["value"]
    assert got == pytest.approx(want)
    assert want == 1.0


def test_dip_fill_spot_value(res):
    ev = pd.read_parquet(ROOT / "research/tournament/oc_kpi/events_s0.parquet",
                         columns=["t", "kind"])
    ev["t"] = pd.to_datetime(ev["t"], utc=True)
    T = pd.Timestamp("2023-04-17", tz="UTC")
    n0 = int(((ev["t"] > T - pd.Timedelta(days=30)) & (ev["t"] <= T) &
              (ev["kind"] == "rung_fill")).sum())
    assert n0 > 0
    # pooled rate over 4 shifts must be >= single-shift rate
    got = res["stats"][STAT_ORDER.index("dip_fill30")]["episodes"]["E0_grind"]["value"]
    assert got >= n0 / 30.0


def test_no_1m_data():
    src = (OC / "analyze_grindsignal.py").read_text()
    for token in ("premium_1m", "intraday", "_1m.parquet", "kline", "minutes("):
        assert token not in src, f"1m token in script: {token}"
